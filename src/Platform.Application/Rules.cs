using System.Text;
using System.Text.RegularExpressions;
namespace AgentPlatform;

public sealed class PlatformException(string code, int status = 409) : Exception(code)
{
    public string Code { get; } = code;
    public int Status { get; } = status;
}
public static class Rules
{
    public static void Require(bool condition, string code, int status = 409)
    { if (!condition) throw new PlatformException(code, status); }
    public static void Validate(StartRun request)
    {
        Require(request.CommandId != Guid.Empty && request.RepositoryId != Guid.Empty, "INVALID_ID", 400);
        Require(!string.IsNullOrWhiteSpace(request.Prompt), "EMPTY_PROMPT", 400);
        Require(Encoding.UTF8.GetByteCount(request.Prompt) <= 16384, "PROMPT_TOO_LARGE", 413);
        Require(ValidBaseRef(request.BaseCommit), "INVALID_COMMIT", 400);
    }
    public static bool ValidBaseRef(string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return false;
        if (Regex.IsMatch(value, @"\A(?:[0-9a-f]{40}|[0-9a-f]{64})\z")) return true;
        if (!Regex.IsMatch(value, @"\A[A-Za-z0-9][A-Za-z0-9._/-]{0,254}\z")) return false;
        if (value.StartsWith('-') || value.StartsWith('/') || value.EndsWith('/') || value.EndsWith(".lock")) return false;
        return !value.Contains("..") && !value.Contains("//") && !value.Contains("@{");
    }
    public static void Validate(UpsertRepository request, bool requireNewCredential = true)
    {
        ValidateRepository(request, null, requireNewCredential);
    }
    public static Uri ValidateRepository(UpsertRepository request, IReadOnlyList<string>? allowedHosts, bool requireCredential = true)
    {
        Require(!string.IsNullOrWhiteSpace(request.DisplayName) && request.DisplayName.Trim().Length <= 200, "INVALID_NAME", 400);
        Require(Uri.TryCreate(request.CloneUrl?.Trim(), UriKind.Absolute, out var url)
            && url is not null && url.Scheme == Uri.UriSchemeHttps && string.IsNullOrEmpty(url.UserInfo), "INVALID_CLONE_URL", 400);
        if (allowedHosts != null)
            Require(allowedHosts.Contains(url!.Host, StringComparer.OrdinalIgnoreCase), "HOST_NOT_ALLOWED", 400);
        var kind = (request.AuthKind ?? "").Trim();
        Require(kind is "Anonymous" or "Pat", "INVALID_AUTH_KIND", 400);
        if (kind == "Pat")
        {
            if (requireCredential)
                Require(!string.IsNullOrWhiteSpace(request.Password), "CREDENTIAL_REQUIRED", 400);
        }
        else
            Require(string.IsNullOrWhiteSpace(request.Password) && string.IsNullOrWhiteSpace(request.Username), "CREDENTIAL_NOT_ALLOWED", 400);
        Require((request.ProviderHint ?? "").Length <= 32, "INVALID_PROVIDER", 400);
        return url!;
    }
    public static void Validate(ConfirmRun request)
    {
        Require(request.CommandId != Guid.Empty, "INVALID_ID", 400);
        Require(!string.IsNullOrWhiteSpace(request.RequestId) && request.RequestId.Length <= 200, "INVALID_REQUEST_ID", 400);
        var decision = (request.Decision ?? "").Trim();
        Require(decision is "once" or "always" or "reject" or "answer", "INVALID_DECISION", 400);
        if (decision == "answer")
            Require(request.Answers is { Length: > 0 }, "ANSWERS_REQUIRED", 400);
        else
            Require(request.Answers is null or { Length: 0 }, "ANSWERS_NOT_ALLOWED", 400);
    }
}
