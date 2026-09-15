namespace AgentPlatform;

/// <summary>Registered capability handlers for agent.v1 bus (T012/T013).</summary>
public sealed class CapabilityHandlers(ChatStore chat, SqlStore runs)
{
    public static readonly HashSet<string> Required = new(StringComparer.Ordinal)
    {
        "catalog.search@1",
        "repositories.describe@1",
        "repositories.resolve_ref@1",
        "code.search@1",
        "coding.execute@1"
    };

    public async Task<string> ExecuteAsync(string owner, EnsureInvocationRequest request, EnsureInvocationResult ensured)
    {
        return request.Capability switch
        {
            "catalog.search" => await CatalogSearch(owner, request.InputJson),
            "repositories.describe" => await Describe(owner, request.InputJson),
            "repositories.resolve_ref" => await ResolveRef(owner, request.InputJson),
            "code.search" => """{"hits":[],"truncated":true}""",
            "coding.execute" => await CodingExecute(owner, request.InputJson, ensured),
            _ => throw new PlatformException("CAPABILITY_UNAVAILABLE", 400)
        };
    }

    async Task<string> CatalogSearch(string owner, string inputJson)
    {
        var ids = await chat.ListAccessibleRepositoryIds(owner, "read");
        var repos = await runs.Repositories();
        var allowed = repos.Where(r => ids.Contains(r.RepositoryId)).Select(r => new
        {
            repositoryId = r.RepositoryId,
            displayName = r.DisplayName,
            evidence = new[] { "catalog" }
        });
        return Wire.Serialize(new { items = allowed });
    }

    async Task<string> Describe(string owner, string inputJson)
    {
        using var doc = System.Text.Json.JsonDocument.Parse(string.IsNullOrWhiteSpace(inputJson) ? "{}" : inputJson);
        var id = doc.RootElement.GetProperty("repositoryId").GetGuid();
        var allowed = await chat.ListAccessibleRepositoryIds(owner, "read");
        Rules.Require(allowed.Contains(id), "NOT_FOUND", 404);
        var repos = await runs.Repositories();
        var repo = repos.SingleOrDefault(r => r.RepositoryId == id) ?? throw new PlatformException("NOT_FOUND", 404);
        return Wire.Serialize(new { repositoryId = repo.RepositoryId, displayName = repo.DisplayName, cloneUrl = repo.CloneUrl });
    }

    async Task<string> ResolveRef(string owner, string inputJson)
    {
        using var doc = System.Text.Json.JsonDocument.Parse(string.IsNullOrWhiteSpace(inputJson) ? "{}" : inputJson);
        var id = doc.RootElement.GetProperty("repositoryId").GetGuid();
        var @ref = doc.RootElement.GetProperty("ref").GetString() ?? "main";
        var allowed = await chat.ListAccessibleRepositoryIds(owner, "run");
        Rules.Require(allowed.Contains(id), "NOT_FOUND", 404);
        var immutable = System.Text.RegularExpressions.Regex.IsMatch(@ref, @"\A[a-fA-F0-9]{40}\z");
        return Wire.Serialize(new { repositoryId = id, requestedRef = @ref, commit = immutable ? @ref : null, immutable });
    }

    async Task<string> CodingExecute(string owner, string inputJson, EnsureInvocationResult ensured)
    {
        Rules.Require(ensured.RunId is Guid runId, "RUN_ID_REQUIRED", 500);
        using var doc = System.Text.Json.JsonDocument.Parse(string.IsNullOrWhiteSpace(inputJson) ? "{}" : inputJson);
        Rules.Require(doc.RootElement.TryGetProperty("repositoryId", out var repoEl), "INVALID_REPOSITORY", 400);
        Rules.Require(repoEl.TryGetGuid(out var repositoryId), "INVALID_REPOSITORY", 400);
        var baseCommit = doc.RootElement.TryGetProperty("baseCommit", out var bc) ? bc.GetString() ?? "" : "";
        var prompt = doc.RootElement.TryGetProperty("prompt", out var pr) ? pr.GetString() ?? "" : "";
        Rules.Require(!string.IsNullOrWhiteSpace(baseCommit) && !string.IsNullOrWhiteSpace(prompt), "INVALID_CODING_INPUT", 400);
        // CommandId == RunId (deterministic from intent) so lost Start ACK cannot create a second Run.
        var accepted = await runs.Start(owner, new StartRun(ensured.RunId!.Value, repositoryId, baseCommit, prompt));
        Rules.Require(accepted.RunId == ensured.RunId, "RUN_ID_MISMATCH", 500);
        return Wire.Serialize(new
        {
            runId = accepted.RunId,
            status = "ACCEPTED",
            checks = new[]
            {
                new { name = "build", outcome = "not_run", explanation = "Checks not executed until OpenCode completes" }
            }
        });
    }
}
