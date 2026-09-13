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
    public static bool ValidBaseRef(string? value)
    {
        if (string.IsNullOrWhiteSpace(value) || value.Length > 255) return false;
        if (Regex.IsMatch(value, @"\A(?:[0-9a-f]{40}|[0-9a-f]{64})\z")) return true;
        if (value.StartsWith('-') || value.StartsWith('/') || value.EndsWith('/') || value.EndsWith(".lock", StringComparison.Ordinal)
            || value.Contains("..", StringComparison.Ordinal) || value.Contains("//", StringComparison.Ordinal)
            || value.Contains("@{", StringComparison.Ordinal)) return false;
        return Regex.IsMatch(value, @"\A[A-Za-z0-9][A-Za-z0-9._/-]*\z");
    }
    public static void Validate(StartRun request)
    {
        Require(request.CommandId != Guid.Empty && request.RepositoryId != Guid.Empty, "INVALID_ID", 400);
        Require(!string.IsNullOrWhiteSpace(request.Prompt), "EMPTY_PROMPT", 400);
        Require(Encoding.UTF8.GetByteCount(request.Prompt) <= 16384, "PROMPT_TOO_LARGE", 413);
        Require(ValidBaseRef(request.BaseCommit), "INVALID_COMMIT", 400);
    }
    public static Uri ValidateRepository(UpsertRepository request, IReadOnlyCollection<string> allowedHosts, bool requireCredential)
    {
        Require(!string.IsNullOrWhiteSpace(request.DisplayName) && request.DisplayName.Trim().Length <= 200, "INVALID_DISPLAY_NAME", 400);
        Require(request.AuthKind is "Anonymous" or "Pat", "INVALID_AUTH_KIND", 400);
        Require(request.ProviderHint is "Generic" or "GitHub", "INVALID_PROVIDER", 400);
        Require(Uri.TryCreate(request.CloneUrl?.Trim(), UriKind.Absolute, out var url)
            && url.Scheme == Uri.UriSchemeHttps
            && string.IsNullOrEmpty(url.UserInfo)
            && !string.IsNullOrEmpty(url.Host), "INVALID_CLONE_URL", 400);
        Require(allowedHosts.Contains(url!.Host, StringComparer.OrdinalIgnoreCase), "REPOSITORY_HOST_NOT_ALLOWED", 400);
        if (request.AuthKind == "Pat")
        {
            var hasUser = !string.IsNullOrWhiteSpace(request.Username);
            var hasPass = !string.IsNullOrWhiteSpace(request.Password);
            Require(hasUser == hasPass, "CREDENTIAL_INCOMPLETE", 400);
            Require(!requireCredential || (hasUser && hasPass), "CREDENTIAL_REQUIRED", 400);
            if (hasUser)
            {
                var user = request.Username!;
                var pass = request.Password!;
                Require(user.Length <= 200 && pass.Length <= 4000, "CREDENTIAL_TOO_LARGE", 400);
                Require(!user.Contains(':') && !pass.Contains('\n') && !pass.Contains('\r'), "INVALID_CREDENTIAL", 400);
            }
        }
        else Require(string.IsNullOrEmpty(request.Username) && string.IsNullOrEmpty(request.Password), "ANONYMOUS_HAS_CREDENTIAL", 400);
        return url;
    }
}
