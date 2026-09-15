using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace AgentPlatform;

/// <summary>RFC 8785-ish canonical JSON hash for agent.v1 golden vectors (T007).</summary>
public static class CanonicalHash
{
    public static string HashObject(JsonNode node)
    {
        var canonical = Canonicalize(node);
        return Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(canonical)));
    }

    public static string Canonicalize(JsonNode? node) => node switch
    {
        null => "null",
        JsonValue v when v.TryGetValue<bool>(out var b) => b ? "true" : "false",
        JsonValue v when v.TryGetValue<string>(out var s) => JsonSerializer.Serialize(s),
        JsonValue v when v.TryGetValue<long>(out var l) => JsonSerializer.Serialize(l.ToString()),
        JsonValue v when v.TryGetValue<int>(out var i) => JsonSerializer.Serialize(i.ToString()),
        JsonArray arr => "[" + string.Join(",", arr.Select(Canonicalize)) + "]",
        JsonObject obj => "{" + string.Join(",", obj.OrderBy(p => p.Key, StringComparer.Ordinal)
            .Where(p => p.Value is not null)
            .Select(p => JsonSerializer.Serialize(p.Key) + ":" + Canonicalize(p.Value))) + "}",
        _ => JsonSerializer.Serialize(node)
    };
}
