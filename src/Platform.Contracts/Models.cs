using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace AgentPlatform;

public static class States
{
    public static bool Terminal(string s) => s is "SUCCEEDED" or "FAILED" or "CANCELLED" or "NEEDS_ATTENTION" or "UNKNOWN";
    public static string RunStatus(string operation) => operation == "UNKNOWN" ? "NEEDS_ATTENTION" : operation == "LEASED" ? "QUEUED" : operation;
}
public sealed record StartRun(Guid CommandId, Guid RepositoryId, string BaseCommit, string Prompt);
public sealed record CancelRun(Guid CommandId);
public sealed record UpsertRepository(string DisplayName, string CloneUrl, string AuthKind, string ProviderHint, string? Username = null, string? Password = null);
public sealed record RepositoryView(Guid RepositoryId, string DisplayName, string CloneUrl, string AuthKind, string ProviderHint, bool HasCredential, bool Enabled);
public sealed record SecurityMe(string Subject, bool IsAdmin);
public sealed record CommandAccepted(Guid CommandId, Guid RunId, string CommandStatus = "PENDING")
{
    public string Ack => "PERSISTED";
    public string StatusUrl => $"/api/v1/runs/{RunId}";
}
public sealed record WorkflowInput(Guid RunId, Guid OperationId, DateTime Deadline);
public sealed record OperationView(string Status, bool CancelDesired, string? ErrorCode);
public sealed record EventView(string Sequence, string Kind, JsonElement Payload, DateTime CreatedAt);
public sealed record ArtifactView(Guid ArtifactId, string Kind, string MediaType, long SizeBytes, string Sha256, DateTime ExpiresAt, string DownloadUrl);
public sealed record RunView(Guid RunId, Guid RepositoryId, string BaseCommit, string Status, string? OperationStatus,
    DateTime CreatedAt, DateTime UpdatedAt, string LastEventSequence, string EarliestAvailableSequence,
    string? ErrorCode, IReadOnlyList<ArtifactView> Artifacts);
public sealed record EventPage(IReadOnlyList<EventView> Items, string HighWatermark, string EarliestAvailableSequence, bool HasMore);
public static class Wire
{
    public static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    public static string Serialize<T>(T value) => JsonSerializer.Serialize(value, Json);
    public static string Hash(string text) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(text)));
    public static string ResultHash(string summary, string patch, string commit)
    {
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        Span<byte> size = stackalloc byte[8];
        foreach (var value in new[] { summary, patch, commit })
        {
            var bytes = Encoding.UTF8.GetBytes(value);
            BinaryPrimitives.WriteUInt64BigEndian(size, (ulong)bytes.Length);
            hash.AppendData(size); hash.AppendData(bytes);
        }
        return Convert.ToHexStringLower(hash.GetHashAndReset());
    }
}
