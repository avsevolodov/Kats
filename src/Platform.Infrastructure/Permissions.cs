using AgentPlatform.Contracts.Runner.V1;
using Microsoft.EntityFrameworkCore;
namespace AgentPlatform;

public sealed class PermissionRow
{
    public Guid OperationId { get; set; }
    public string RequestId { get; set; } = "";
    public string Description { get; set; } = "";
    public string Decision { get; set; } = "";
    public string Status { get; set; } = "pending";
    public DateTime CreatedAt { get; set; }
    public DateTime? DecidedAt { get; set; }
    public string? DecidedBy { get; set; }
}

public sealed partial class SqlStore
{
    public Task<PermissionResult> ExchangePermission(string workload, PermissionExchange request) => Write(async (db, now) =>
    {
        var op = await Bound(db, workload, request.Key); Live(op, now);
        var run = await db.Runs.SingleAsync(x => x.Id == op.RunId);
        Rules.Require(op.Status == "RUNNING" && op.SessionId == request.SessionId, "SESSION_CONFLICT");
        Rules.Require(!op.CancelDesired && !run.CancelDesired && run.Deadline > now && !States.Terminal(run.Status), "PERMISSION_EXPIRED");
        Rules.Require(System.Text.RegularExpressions.Regex.IsMatch(request.RequestId, @"\A[a-zA-Z0-9_-]{1,100}\z"), "INVALID_PERMISSION", 400);
        Rules.Require(request.Description.Length is > 0 and <= 8192, "INVALID_PERMISSION", 400);
        Rules.Require(request.Phase is "pending" or "applied" or "unknown" or "expired", "INVALID_PERMISSION_PHASE", 400);
        var row = await db.Permissions.FindAsync(op.Id, request.RequestId);
        if (row == null)
        {
            Rules.Require(request.Phase == "pending", "PERMISSION_NOT_FOUND", 404);
            Rules.Require(await db.Permissions.CountAsync(x => x.OperationId == op.Id) < 100, "PERMISSION_LIMIT", 429);
            row = new() { OperationId = op.Id, RequestId = request.RequestId, Description = request.Description, CreatedAt = now };
            db.Permissions.Add(row);
            Emit(db, run, now, "PermissionRequested", new { requestId = row.RequestId });
        }
        Rules.Require(row.Description == request.Description, "PERMISSION_CONFLICT");
        if (request.Phase != "pending" && row.Status != request.Phase)
        {
            Rules.Require(row.Status is "pending" or "decided", "PERMISSION_CLOSED");
            Rules.Require(request.Phase != "applied" || row.Status == "decided", "PERMISSION_NOT_DECIDED");
            row.Status = request.Phase;
            Emit(db, run, now, "PermissionDelivery", new { requestId = row.RequestId, status = row.Status });
        }
        return new PermissionResult { Decision = row.Decision, Status = row.Status };
    });

    public Task<List<PermissionView>> Permissions(string owner, Guid id) => Write(async (db, now) =>
    {
        var run = await Owned(db, owner, id);
        var op = await db.Operations.FindAsync(run.OperationId);
        var live = op != null && op.Status == "RUNNING" && op.LeaseUntil > now && !op.CancelDesired && !run.CancelDesired && run.Deadline > now && !States.Terminal(run.Status);
        var rows = await db.Permissions.Where(x => x.OperationId == run.OperationId).OrderBy(x => x.CreatedAt).ToListAsync();
        return rows.Select(x => new PermissionView(x.RequestId, x.Description, !live && (x.Status is "pending" or "decided") ? "expired" : x.Status, x.Decision, x.DecidedAt)).ToList();
    });

    public Task<bool> DecidePermission(string owner, Guid id, string requestId, PermissionDecision decision) => Write(async (db, now) =>
    {
        Rules.Require(decision.Decision is "once" or "reject", "INVALID_PERMISSION_DECISION", 400);
        var run = await Owned(db, owner, id);
        var row = await db.Permissions.FindAsync(run.OperationId, requestId) ?? throw new PlatformException("NOT_FOUND", 404);
        if (row.Decision != "") { Rules.Require(row.Decision == decision.Decision, "PERMISSION_CONFLICT"); return true; }
        var op = await db.Operations.FindAsync(run.OperationId) ?? throw new PlatformException("NOT_FOUND", 404);
        Live(op, now);
        Rules.Require(row.Status == "pending" && op.Status == "RUNNING" && !op.CancelDesired && !run.CancelDesired && run.Deadline > now && !States.Terminal(run.Status), "PERMISSION_EXPIRED");
        row.Decision = decision.Decision; row.Status = "decided"; row.DecidedAt = now; row.DecidedBy = owner;
        Emit(db, run, now, "PermissionDecided", new { requestId, decision = row.Decision });
        return true;
    });
}
