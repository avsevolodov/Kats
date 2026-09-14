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
        Require(Regex.IsMatch(request.BaseCommit ?? "", "\\A(?:[0-9a-f]{40}|[0-9a-f]{64})\\z"), "INVALID_COMMIT", 400);
    }
}
