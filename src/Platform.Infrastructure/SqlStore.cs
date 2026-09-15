using System.Data;
using System.Linq;
using System.Text;
using System.Text.Json;
using AgentPlatform.Contracts.Runner.V1;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
namespace AgentPlatform;

// Deliberately serialized short writes for the ten-run MVP. No network calls while holding the lock.
public partial class SqlStore(IDbContextFactory<PlatformDb> factory, IDataProtectionProvider protection, IConfiguration config)
{
    public const int ConnectedFreshnessSeconds = RunnerPresence.FreshnessSeconds;
    readonly IDataProtector credentials = protection.CreateProtector("GitCredentials.v1");
    IReadOnlyList<string> AllowedHosts
    {
        get
        {
            var hosts = config.GetSection("Git:AllowedHosts").GetChildren()
                .Select(x => x.Value)
                .Where(x => !string.IsNullOrWhiteSpace(x))
                .Select(x => x!)
                .ToArray();
            return hosts.Length > 0 ? hosts : ["github.com"];
        }
    }

    public async Task<T> Write<T>(Func<PlatformDb, DateTime, Task<T>> action)
    {
        await using var db = await factory.CreateDbContextAsync();
        await using var tx = await db.Database.BeginTransactionAsync(IsolationLevel.ReadCommitted);
        await db.Database.ExecuteSqlRawAsync("DECLARE @r int; EXEC @r=sp_getapplock @Resource=N'agent-platform-write-v1',@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=10000; IF @r<0 THROW 51000,'Store busy',1;");
        var now = await db.Database.SqlQueryRaw<DateTime>("SELECT SYSUTCDATETIME() AS [Value]").SingleAsync();
        var result = await action(db, now);
        await db.SaveChangesAsync(); await tx.CommitAsync(); return result;
    }
    static void Emit(PlatformDb db, RunRow run, DateTime now, string kind, object payload)
    {
        db.Events.Add(new() { RunId = run.Id, Sequence = run.NextSequence++, Kind = kind, Payload = Wire.Serialize(payload), CreatedAt = now });
        run.UpdatedAt = now;
    }
    static RepositoryView RepoView(RepositoryRow x) => new(x.Id, x.DisplayName, x.CloneUrl, x.AuthKind, x.ProviderHint,
        x.CredentialCipher is { Length: > 0 } || !string.IsNullOrEmpty(x.CredentialRef), x.Enabled);
    byte[]? ProtectPat(UpsertRepository request)
    {
        if (request.AuthKind != "Pat" || string.IsNullOrEmpty(request.Password)) return null;
        var json = Wire.Serialize(new { username = (request.Username ?? "x-access-token").Trim(), password = request.Password });
        return credentials.Protect(Encoding.UTF8.GetBytes(json));
    }
    public Task<CommandAccepted> Start(string owner, StartRun request)
    {
        Rules.Validate(request);
        return Write(async (db, now) =>
        {
            var hash = Wire.Hash(Wire.Serialize(request));
            var old = await db.Commands.FindAsync(owner, request.CommandId);
            if (old != null) { Rules.Require(old.Hash == hash && old.Kind == "START", "COMMAND_CONFLICT"); return new(old.Id, old.RunId, old.Status); }
            Rules.Require(await db.Repositories.AnyAsync(x => x.Id == request.RepositoryId && x.Enabled), "REPOSITORY_NOT_FOUND", 404);
            Rules.Require(await db.Runs.CountAsync(x => x.Status != "SUCCEEDED" && x.Status != "FAILED" && x.Status != "CANCELLED" && x.Status != "NEEDS_ATTENTION") < 10, "CAPACITY", 429);
            var run = new RunRow { Id = request.CommandId, OperationId = Guid.NewGuid(), Owner = owner, RepositoryId = request.RepositoryId, BaseCommit = request.BaseCommit, Prompt = request.Prompt, CreatedAt = now, UpdatedAt = now, Deadline = now.AddMinutes(20) };
            db.Runs.Add(run); db.Commands.Add(new() { Id = request.CommandId, Owner = owner, RunId = run.Id, Kind = "START", Hash = hash, CreatedAt = now });
            Emit(db, run, now, "RunAccepted", new { status = "ACCEPTED" });
            return new CommandAccepted(request.CommandId, run.Id);
        });
    }
    public Task<CommandAccepted> Cancel(string owner, Guid id, Guid commandId) => Write(async (db, now) =>
    {
        Rules.Require(commandId != Guid.Empty, "INVALID_ID", 400);
        var run = await Owned(db, owner, id); var hash = Wire.Hash($"cancel:{id:D}");
        var old = await db.Commands.FindAsync(owner, commandId);
        if (old != null) { Rules.Require(old.Hash == hash && old.Kind == "CANCEL", "COMMAND_CONFLICT"); return new(old.Id, old.RunId, old.Status); }
        var terminal = States.Terminal(run.Status);
        db.Commands.Add(new() { Id = commandId, Owner = owner, RunId = id, Kind = "CANCEL", Hash = hash, CreatedAt = now, Status = terminal ? "PROCESSED" : "PENDING" });
        if (!terminal)
        {
            run.CancelDesired = true;
            var op = await db.Operations.FindAsync(run.OperationId);
            if (op != null) op.CancelDesired = true;
            foreach (var pending in await db.OperationConfirmations.Where(x => x.OperationId == run.OperationId && x.Status == "PENDING").ToListAsync())
                pending.Status = "SUPERSEDED";
            Emit(db, run, now, "CancelRequested", new { commandId });
        }
        return new CommandAccepted(commandId, id, terminal ? "PROCESSED" : "PENDING");
    });
    public Task<CommandAccepted> Confirm(string owner, Guid id, ConfirmRun request)
    {
        Rules.Validate(request);
        return Write(async (db, now) =>
        {
            var run = await Owned(db, owner, id);
            var decision = request.Decision.Trim();
            var answersJson = request.Answers is { Length: > 0 } ? Wire.Serialize(request.Answers) : null;
            var hash = Wire.Hash($"confirm:{id:D}:{request.RequestId}:{decision}:{answersJson}");
            var old = await db.Commands.FindAsync(owner, request.CommandId);
            if (old != null)
            {
                Rules.Require(old.Hash == hash && old.Kind == "CONFIRM", "COMMAND_CONFLICT");
                return new(old.Id, old.RunId, old.Status);
            }
            Rules.Require(!States.Terminal(run.Status), "RUN_TERMINAL", 409);
            Rules.Require(!run.CancelDesired, "CANCEL_DESIRED", 409);
            var conf = await db.OperationConfirmations.SingleOrDefaultAsync(x => x.OperationId == run.OperationId && x.RequestId == request.RequestId)
                ?? throw new PlatformException("CONFIRMATION_NOT_FOUND", 404);
            Rules.Require(conf.Status == "PENDING", "CONFIRMATION_NOT_PENDING", 409);
            if (conf.Kind == "permission")
                Rules.Require(decision is "once" or "always" or "reject", "INVALID_DECISION", 400);
            else if (conf.Kind == "question")
                Rules.Require(decision is "answer" or "reject", "INVALID_DECISION", 400);
            else
                throw new PlatformException("INVALID_KIND", 400);
            conf.Status = "ANSWERED";
            conf.Decision = decision;
            conf.AnswersJson = answersJson;
            conf.CommandId = request.CommandId;
            conf.AnsweredAt = now;
            db.Commands.Add(new() { Id = request.CommandId, Owner = owner, RunId = id, Kind = "CONFIRM", Hash = hash, CreatedAt = now, Status = "PROCESSED" });
            Emit(db, run, now, "ConfirmationResolved", new { requestId = conf.RequestId, decision, status = "ANSWERED" });
            return new CommandAccepted(request.CommandId, id, "PROCESSED");
        });
    }
    static async Task<RunRow> Owned(PlatformDb db, string owner, Guid id) =>
        await db.Runs.SingleOrDefaultAsync(x => x.Id == id && x.Owner == owner) ?? throw new PlatformException("NOT_FOUND", 404);
    public async Task<IReadOnlyList<RepositoryView>> Repositories(bool includeDisabled = false)
    {
        await using var db = await factory.CreateDbContextAsync();
        var q = db.Repositories.AsQueryable();
        if (!includeDisabled) q = q.Where(x => x.Enabled);
        return (await q.OrderBy(x => x.DisplayName).ToListAsync()).Select(RepoView).ToList();
    }
    public Task<RepositoryView> CreateRepository(UpsertRepository request)
    {
        var url = Rules.ValidateRepository(request, AllowedHosts, requireCredential: request.AuthKind == "Pat");
        var cipher = ProtectPat(request);
        return Write(async (db, now) =>
        {
            var row = new RepositoryRow
            {
                Id = Guid.NewGuid(),
                DisplayName = request.DisplayName.Trim(),
                CloneUrl = url.AbsoluteUri,
                AuthKind = request.AuthKind.Trim(),
                ProviderHint = (request.ProviderHint ?? "").Trim(),
                CredentialRef = "",
                CredentialCipher = cipher,
                Enabled = true
            };
            db.Repositories.Add(row);
            return RepoView(row);
        });
    }
    public Task<RepositoryView> UpdateRepository(Guid id, UpsertRepository request)
    {
        var url = Rules.ValidateRepository(request, AllowedHosts, requireCredential: false);
        var replace = request.AuthKind == "Pat" && !string.IsNullOrEmpty(request.Password);
        var cipher = replace ? ProtectPat(request) : null;
        return Write(async (db, now) =>
        {
            var row = await db.Repositories.FindAsync(id) ?? throw new PlatformException("NOT_FOUND", 404);
            if (request.AuthKind == "Pat" && !replace)
                Rules.Require(row.CredentialCipher is { Length: > 0 } || !string.IsNullOrEmpty(row.CredentialRef), "CREDENTIAL_REQUIRED", 400);
            row.DisplayName = request.DisplayName.Trim();
            row.CloneUrl = url.AbsoluteUri;
            row.AuthKind = request.AuthKind.Trim();
            row.ProviderHint = (request.ProviderHint ?? "").Trim();
            if (request.AuthKind == "Anonymous") { row.CredentialCipher = null; row.CredentialRef = ""; }
            else if (replace) { row.CredentialCipher = cipher; row.CredentialRef = ""; }
            return RepoView(row);
        });
    }
    public Task DisableRepository(Guid id) => Write(async (db, now) =>
    {
        var row = await db.Repositories.FindAsync(id) ?? throw new PlatformException("NOT_FOUND", 404);
        row.Enabled = false;
        return true;
    });
    public Task TouchRunnerSession(string bootId, string workload, string? version = null) => Write(async (db, now) =>
    {
        Rules.Require(Guid.TryParse(bootId, out _), "INVALID_BOOT", 400);
        Rules.Require(!string.IsNullOrWhiteSpace(workload), "INVALID_WORKLOAD", 400);
        var row = await db.RunnerSessions.FindAsync(bootId);
        if (row == null)
        {
            db.RunnerSessions.Add(new RunnerSessionRow
            {
                BootId = bootId,
                WorkloadSubject = workload,
                Version = Truncate(version ?? "", 200),
                LastSeenAt = now
            });
        }
        else
        {
            row.WorkloadSubject = workload;
            row.LastSeenAt = now;
            if (!string.IsNullOrWhiteSpace(version)) row.Version = Truncate(version, 200);
        }
        return true;
    });
    public async Task<IReadOnlyList<RunnerView>> ListConnectedRunners(TimeSpan? freshness = null)
    {
        var window = freshness ?? TimeSpan.FromSeconds(ConnectedFreshnessSeconds);
        await using var db = await factory.CreateDbContextAsync();
        var now = await db.Database.SqlQueryRaw<DateTime>("SELECT SYSUTCDATETIME() AS [Value]").SingleAsync();
        var cutoff = now - window;
        var sessions = await db.RunnerSessions.AsNoTracking()
            .Where(x => x.LastSeenAt >= cutoff)
            .OrderByDescending(x => x.LastSeenAt)
            .ToListAsync();
        if (sessions.Count == 0) return [];
        var boots = sessions.Select(x => x.BootId).ToList();
        var ops = await db.Operations.AsNoTracking()
            .Where(x => x.BootId != null && boots.Contains(x.BootId) && (x.Status == "LEASED" || x.Status == "RUNNING"))
            .ToListAsync();
        var byBoot = ops.GroupBy(x => x.BootId!).ToDictionary(g => g.Key, g => g.First());
        return sessions.Select(s =>
        {
            byBoot.TryGetValue(s.BootId, out var op);
            return new RunnerView(
                Guid.Parse(s.BootId),
                WorkloadHint(s.WorkloadSubject),
                s.Version,
                DateTime.SpecifyKind(s.LastSeenAt, DateTimeKind.Utc),
                op == null ? "idle" : "busy",
                op?.RunId,
                op?.Id,
                op?.Status);
        }).ToList();
    }
    static string WorkloadHint(string workload) =>
        string.IsNullOrEmpty(workload) ? "" : workload.Length <= 8 ? workload : workload[^8..];
    static string Truncate(string value, int max) =>
        value.Length <= max ? value : value[..max];
    
    public async Task<IReadOnlyList<RunView>> List(string owner)
    {
        await using var db = await factory.CreateDbContextAsync();
        var runs = await db.Runs.AsNoTracking().Where(x => x.Owner == owner).OrderByDescending(x => x.CreatedAt).Take(100).ToListAsync();
        return runs.Select(x => View(x, null, [])).ToList();
    }
    static RunView View(RunRow r, string? operation, IReadOnlyList<ArtifactView> artifacts) => new(r.Id, r.RepositoryId, r.BaseCommit, r.Status, operation, r.CreatedAt, r.UpdatedAt, (r.NextSequence - 1).ToString(), r.EarliestSequence.ToString(), r.ErrorCode, artifacts);
    public async Task<RunView> Get(string owner, Guid id)
    {
        await using var db = await factory.CreateDbContextAsync();
        await using var tx = await db.Database.BeginTransactionAsync(IsolationLevel.Serializable);
        var r = await Owned(db, owner, id); var op = await db.Operations.FindAsync(r.OperationId);
        var a = await db.Artifacts.Where(x => x.RunId == id).Select(x => new { x.Id, x.Kind, Size = x.Content.Length, x.Hash, x.ExpiresAt }).ToListAsync();
        return View(r, op?.Status, a.Select(x => new ArtifactView(x.Id, x.Kind, "text/plain; charset=utf-8", x.Size, x.Hash, x.ExpiresAt, $"/api/v1/runs/{id}/artifacts/{x.Id}")).ToList());
    }
    public async Task<EventPage> Events(string owner, Guid id, long after, int limit = 100)
    {
        await using var db = await factory.CreateDbContextAsync();
        await using var tx = await db.Database.BeginTransactionAsync(IsolationLevel.Serializable);
        var r = await Owned(db, owner, id);
        Rules.Require(after >= r.EarliestSequence - 1, "CURSOR_EXPIRED", 410);
        Rules.Require(after >= 0, "INVALID_CURSOR", 400);
        // Cursor past high watermark means "caught up" — empty page, not an error
        // (avoids killing the browser stream on a benign race).
        if (after >= r.NextSequence)
            return new([], (r.NextSequence - 1).ToString(), r.EarliestSequence.ToString(), false);
        var rows = await db.Events.AsNoTracking().Where(x => x.RunId == id && x.Sequence > after).OrderBy(x => x.Sequence).Take(Math.Clamp(limit, 1, 100)).ToListAsync();
        var items = rows.Select(x => new EventView(x.Sequence.ToString(), x.Kind, JsonSerializer.Deserialize<JsonElement>(x.Payload), x.CreatedAt)).ToList();
        return new(items, (rows.LastOrDefault()?.Sequence ?? after).ToString(), r.EarliestSequence.ToString(), (rows.LastOrDefault()?.Sequence ?? after) < r.NextSequence - 1);
    }
    public async Task<ArtifactRow> Artifact(string owner, Guid runId, Guid artifactId)
    {
        await using var db = await factory.CreateDbContextAsync(); await Owned(db, owner, runId);
        var a = await db.Artifacts.SingleOrDefaultAsync(x => x.Id == artifactId && x.RunId == runId) ?? throw new PlatformException("NOT_FOUND", 404);
        Rules.Require(a.ExpiresAt > DateTime.UtcNow, "ARTIFACT_EXPIRED", 410); return a;
    }
    public Task EnsureOperation(WorkflowInput input) => Write(async (db, now) =>
    {
        var r = await db.Runs.SingleAsync(x => x.Id == input.RunId);
        Rules.Require(r.OperationId == input.OperationId, "OPERATION_CONFLICT");
        if (!await db.Operations.AnyAsync(x => x.Id == input.OperationId)) db.Operations.Add(new() { Id = input.OperationId, RunId = input.RunId, CancelDesired = r.CancelDesired, Status = r.CancelDesired ? "CANCELLED" : "QUEUED" });
        return true;
    });
    public async Task<OperationView> Poll(Guid opId)
    { await using var db = await factory.CreateDbContextAsync(); var op = await db.Operations.SingleAsync(x => x.Id == opId); return new(op.Status, op.CancelDesired, op.ErrorCode); }
    public Task Publish(Guid runId, string status, string? error = null) => Write(async (db, now) =>
    {
        var key = status; var hash = Wire.Hash(status + ":" + error); var p = await db.Publications.FindAsync(runId, key);
        if (p != null) { Rules.Require(p.Hash == hash, "PUBLICATION_CONFLICT"); return true; }
        var r = await db.Runs.SingleAsync(x => x.Id == runId);
        Rules.Require(!States.Terminal(r.Status), "RUN_TERMINAL");
        r.Status = status; r.ErrorCode = error;
        db.Publications.Add(new() { RunId = runId, Key = key, Hash = hash });
        Emit(db, r, now, States.Terminal(status) ? "RunCompleted" : "RunStatusChanged", new { status, errorCode = error });
        return true;
    });
    public Task RequestAbort(Guid opId) => Write(async (db, now) =>
    {
        var op = await db.Operations.SingleAsync(x => x.Id == opId); op.CancelDesired = true;
        if (op.Status == "QUEUED") op.Status = "CANCELLED";
        return true;
    });
    public Task MarkUnknown(Guid opId) => Write(async (db, now) =>
    { var op = await db.Operations.SingleAsync(x => x.Id == opId); if (!States.Terminal(op.Status)) { op.Status = "UNKNOWN"; op.ErrorCode = "ABORT_UNCONFIRMED"; } return true; });
    public Task<int> Reap() => Write(async (db, now) =>
    {
        var ops = await db.Operations.Where(x => (x.Status == "LEASED" || x.Status == "RUNNING") && x.LeaseUntil < now).ToListAsync();
        foreach (var op in ops) { op.Status = "UNKNOWN"; op.ErrorCode = "RUNNER_LEASE_EXPIRED"; }
        var expired = await db.OperationConfirmations.Where(x => x.Status == "PENDING" && x.CreatedAt < now.AddMinutes(-5)).ToListAsync();
        foreach (var conf in expired)
        {
            conf.Status = "EXPIRED";
            conf.Decision = "reject";
            conf.AnsweredAt = now;
            var run = await db.Runs.SingleAsync(x => x.OperationId == conf.OperationId);
            Emit(db, run, now, "ConfirmationResolved", new { requestId = conf.RequestId, decision = "reject", status = "EXPIRED" });
        }
        return ops.Count + expired.Count;
    });
    public Task<CommandRow?> ClaimCommand() => Write(async (db, now) =>
    {
        var c = await db.Commands.Where(x => x.Status == "PENDING" && (x.LeaseUntil == null || x.LeaseUntil < now)).OrderBy(x => x.CreatedAt).FirstOrDefaultAsync();
        if (c != null) { c.LeaseUntil = now.AddSeconds(30); c.LeaseToken = Guid.NewGuid(); }
        return c;
    });
    public Task Dispatched(CommandRow claimed) => Write(async (db, now) =>
    { var c = await db.Commands.FindAsync(claimed.Owner, claimed.Id); if (c != null && c.LeaseToken == claimed.LeaseToken) c.Status = "DISPATCHED"; return true; });
    public async Task<WorkflowInput> Input(Guid id)
    { await using var db = await factory.CreateDbContextAsync(); var r = await db.Runs.SingleAsync(x => x.Id == id); return new(r.Id, r.OperationId, DateTime.SpecifyKind(r.Deadline, DateTimeKind.Utc)); }
    public Task<Assignment?> Claim(string workload, string boot) => Write(async (db, now) =>
    {
        var old = await db.Operations.FirstOrDefaultAsync(x => x.BootId == boot && x.Workload == workload && (x.Status == "LEASED" || x.Status == "RUNNING"));
        // Lost Assignment is recovered by the same process, not by a new BootId.
        var op = old ?? await db.Operations.FirstOrDefaultAsync(x => x.Status == "QUEUED" && !x.CancelDesired);
        if (op == null) return null;
        var r = await db.Runs.SingleAsync(x => x.Id == op.RunId);
        if (old == null)
        {
            if (r.CancelDesired) { op.CancelDesired = true; op.Status = "CANCELLED"; return null; }
            op.Workload = workload; op.BootId = boot; op.Fence++; op.Status = "LEASED"; op.LeaseUntil = now.AddSeconds(45);
        }
        else Rules.Require(op.LeaseUntil > now, "LEASE_EXPIRED");
        var repo = await db.Repositories.SingleAsync(x => x.Id == r.RepositoryId);
        return new Assignment
        {
            Key = new() { OperationId = op.Id.ToString(), BootId = boot, Fence = op.Fence },
            RunId = r.Id.ToString(),
            RepositoryId = repo.Id.ToString(),
            CloneUrl = repo.CloneUrl,
            CredentialRef = repo.CredentialRef,
            AuthKind = repo.AuthKind,
            BaseCommit = r.BaseCommit,
            Prompt = r.Prompt,
            DefinitionVersion = "mvp-1",
            LeaseUntilUnixMs = Epoch(op.LeaseUntil!.Value),
            DeadlineUnixMs = Epoch(r.Deadline)
        };
    });
    public Task<GitCredential> FetchGitCredential(string workload, OperationKey key) => Write(async (db, now) =>
    {
        var op = await Bound(db, workload, key); Live(op, now);
        Rules.Require(op.Status is "LEASED" or "RUNNING", "FENCED", 403);
        var r = await db.Runs.SingleAsync(x => x.Id == op.RunId);
        var repo = await db.Repositories.SingleAsync(x => x.Id == r.RepositoryId);
        if (repo.AuthKind == "Anonymous") return new GitCredential { AuthKind = "anonymous" };
        Rules.Require(repo.AuthKind == "Pat", "INVALID_AUTH_KIND", 400);
        Rules.Require(repo.CredentialCipher is { Length: > 0 }, "CREDENTIAL_MISSING", 400);
        var json = Encoding.UTF8.GetString(credentials.Unprotect(repo.CredentialCipher!));
        var doc = JsonSerializer.Deserialize<JsonElement>(json);
        return new GitCredential
        {
            AuthKind = "pat",
            Username = doc.GetProperty("username").GetString() ?? "x-access-token",
            Password = doc.GetProperty("password").GetString() ?? ""
        };
    });
    static long Epoch(DateTime time) => new DateTimeOffset(DateTime.SpecifyKind(time, DateTimeKind.Utc)).ToUnixTimeMilliseconds();
    static async Task<OperationRow> Bound(PlatformDb db, string workload, OperationKey key)
    {
        Rules.Require(Guid.TryParse(key.OperationId, out var id), "INVALID_ID", 400);
        var op = await db.Operations.FindAsync(id) ?? throw new PlatformException("NOT_FOUND", 404);
        Rules.Require(op.Workload == workload && op.BootId == key.BootId && op.Fence == key.Fence, "FENCED", 403); return op;
    }
    static void Live(OperationRow op, DateTime now)
    { Rules.Require(!States.Terminal(op.Status), "FENCED"); Rules.Require(op.LeaseUntil > now, "LEASE_EXPIRED"); }
    public Task<OperationSnapshot> Resume(string workload, OperationKey key) => Write(async (db, now) =>
    {
        var op = await Bound(db, workload, key);
        var reply = await db.OperationConfirmations
            .Where(x => x.OperationId == op.Id && (x.Status == "ANSWERED" || x.Status == "EXPIRED"))
            .OrderByDescending(x => x.AnsweredAt)
            .FirstOrDefaultAsync();
        var pending = await db.OperationConfirmations.FirstOrDefaultAsync(x => x.OperationId == op.Id && x.Status == "PENDING");
        return new OperationSnapshot
        {
            Key = key,
            Status = op.Status,
            LastAcceptedProducerSequence = op.ProducerSequence,
            LeaseUntilUnixMs = Epoch(op.LeaseUntil ?? now),
            CancelDesired = op.CancelDesired,
            BeginCommitted = op.SessionId != null,
            PendingConfirmationRequestId = pending?.RequestId ?? reply?.RequestId ?? "",
            ConfirmationReplyReady = reply != null,
            ConfirmationDecision = reply?.Decision ?? "",
            ConfirmationAnswersJson = reply?.AnswersJson ?? ""
        };
    });
    public Task<PersistedAck> Renew(string workload, OperationKey key, string? session = null) => Write(async (db, now) =>
    {
        var op = await Bound(db, workload, key); Live(op, now); var r = await db.Runs.SingleAsync(x => x.Id == op.RunId);
        if (session != null)
        {
            Rules.Require(!op.CancelDesired && !r.CancelDesired, "CANCEL_DESIRED");
            Rules.Require(op.SessionId == null || op.SessionId == session, "SESSION_CONFLICT");
            if (op.SessionId == null) { op.SessionId = session; op.Status = "RUNNING"; Emit(db, r, now, "OperationStarted", new { operationId = op.Id }); }
        }
        op.LeaseUntil = now.AddSeconds(45); return Ack(op, r.NextSequence - 1, session != null);
    });
    static PersistedAck Ack(OperationRow op, long events, bool begin = false) => new() { OperationId = op.Id.ToString(), LastAcceptedProducerSequence = op.ProducerSequence, LastRunEventSequence = events, LeaseUntilUnixMs = Epoch(op.LeaseUntil ?? DateTime.UtcNow), BeginAuthorized = begin };
    public Task<PersistedAck> Produce(string workload, RunnerFrame frame) => Write(async (db, now) =>
    {
        var output = frame.Output; var complete = frame.Complete; var confirmation = frame.ConfirmationRequired;
        Rules.Require(output != null || complete != null || confirmation != null, "INVALID_MESSAGE", 400);
        var key = output?.Key ?? complete?.Key ?? confirmation!.Key;
        var seq = output?.ProducerSequence ?? complete?.ProducerSequence ?? confirmation!.ProducerSequence;
        var op = await Bound(db, workload, key); var r = await db.Runs.SingleAsync(x => x.Id == op.RunId);
        var hash = output != null ? Wire.Hash(output.Kind + ":" + output.Text)
            : complete != null ? Wire.Hash(complete.Outcome + ":" + complete.ResultSha256 + ":" + complete.ErrorCode)
            : Wire.Hash($"confirm:{confirmation!.RequestId}:{confirmation.Kind}:{confirmation.SafePayloadJson}");
        var receipt = await db.Receipts.FindAsync(op.Id, seq);
        if (receipt != null) { Rules.Require(receipt.Hash == hash && receipt.MessageId == frame.MessageId, "PAYLOAD_CONFLICT"); return Ack(op, receipt.EventSequence); }
        Live(op, now); Rules.Require(seq == op.ProducerSequence + 1, "EXPECTED_SEQUENCE");
        Rules.Require(!await db.Receipts.AnyAsync(x => x.OperationId == op.Id && x.MessageId == frame.MessageId), "MESSAGE_CONFLICT");
        if (output != null)
        {
            var bytes = Encoding.UTF8.GetByteCount(output.Text); Rules.Require(bytes <= 8192, "PAYLOAD_TOO_LARGE", 413);
            Rules.Require(output.Kind is "preview" or "progress" or "output_truncated", "INVALID_KIND", 400);
            if (op.PreviewBytes + bytes > 262144 || output.Kind == "output_truncated")
            { if (!op.Truncated) { Emit(db, r, now, "OutputTruncated", new { }); op.Truncated = true; } }
            else if (!op.Truncated) { Emit(db, r, now, "OutputBatch", new { text = output.Text }); op.PreviewBytes += bytes; }
        }
        else if (confirmation != null)
        {
            Rules.Require(confirmation.Kind is "permission" or "question", "INVALID_KIND", 400);
            Rules.Require(!string.IsNullOrWhiteSpace(confirmation.RequestId) && confirmation.RequestId.Length <= 200, "INVALID_REQUEST_ID", 400);
            Rules.Require(Encoding.UTF8.GetByteCount(confirmation.SafePayloadJson) <= 8192, "PAYLOAD_TOO_LARGE", 413);
            var existing = await db.OperationConfirmations.SingleOrDefaultAsync(x => x.OperationId == op.Id && x.RequestId == confirmation.RequestId);
            if (existing == null)
            {
                Rules.Require(!await db.OperationConfirmations.AnyAsync(x => x.OperationId == op.Id && x.Status == "PENDING"), "CONFIRMATION_PENDING", 409);
                Rules.Require(!op.CancelDesired && !r.CancelDesired, "CANCEL_DESIRED", 409);
                JsonDocument.Parse(confirmation.SafePayloadJson);
                db.OperationConfirmations.Add(new OperationConfirmationRow
                {
                    Id = Guid.NewGuid(),
                    OperationId = op.Id,
                    RequestId = confirmation.RequestId,
                    Kind = confirmation.Kind,
                    PayloadJson = confirmation.SafePayloadJson,
                    Status = "PENDING",
                    CreatedAt = now
                });
                Emit(db, r, now, "ConfirmationRequired", new
                {
                    requestId = confirmation.RequestId,
                    kind = confirmation.Kind,
                    payload = JsonSerializer.Deserialize<JsonElement>(confirmation.SafePayloadJson)
                });
            }
            else
                Rules.Require(existing.Kind == confirmation.Kind && existing.PayloadJson == confirmation.SafePayloadJson, "PAYLOAD_CONFLICT");
        }
        else
        {
            var c = complete!;
            Rules.Require(c.BaseCommit == r.BaseCommit, "BASE_COMMIT_CONFLICT");
            Rules.Require(Wire.ResultHash(c.Summary, c.Patch, c.BaseCommit) == c.ResultSha256, "RESULT_HASH_CONFLICT");
            Rules.Require(Encoding.UTF8.GetByteCount(c.Summary) <= 262144 && Encoding.UTF8.GetByteCount(c.Patch) <= 4194304, "RESULT_TOO_LARGE", 413);
            var state = c.Outcome switch { OperationOutcome.Succeeded => "SUCCEEDED", OperationOutcome.Failed => "FAILED", OperationOutcome.Cancelled => "CANCELLED", OperationOutcome.Unknown => "UNKNOWN", _ => throw new PlatformException("INVALID_OUTCOME", 400) };
            Rules.Require(op.Status == "RUNNING" || state is "FAILED" or "CANCELLED" or "UNKNOWN", "BEGIN_REQUIRED");
            if (state == "SUCCEEDED")
                foreach (var (kind, value) in new[] { ("summary", c.Summary), ("patch", c.Patch) }) db.Artifacts.Add(new() { Id = Guid.NewGuid(), RunId = r.Id, OperationId = op.Id, Kind = kind, Content = Encoding.UTF8.GetBytes(value), Hash = Wire.Hash(value), ExpiresAt = now.AddDays(7) });
            op.Status = state; op.ErrorCode = string.IsNullOrEmpty(c.ErrorCode) ? null : c.ErrorCode;
            foreach (var pending in await db.OperationConfirmations.Where(x => x.OperationId == op.Id && x.Status == "PENDING").ToListAsync())
                pending.Status = "SUPERSEDED";
            Emit(db, r, now, "OperationCompleted", new { status = state, errorCode = op.ErrorCode });
        }
        op.ProducerSequence = seq;
        db.Receipts.Add(new() { OperationId = op.Id, Sequence = seq, MessageId = frame.MessageId, Hash = hash, EventSequence = r.NextSequence - 1 });
        return Ack(op, r.NextSequence - 1);
    });
}
