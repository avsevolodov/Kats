using System.Net.WebSockets;
using System.Security.Claims;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Authentication;
namespace AgentPlatform;

public static class BrowserStream
{
    public static async Task Handle(HttpContext c, SqlStore store, IConfiguration config)
    {
        Rules.Require(OriginAllowed(c, config), "INVALID_ORIGIN", 403);
        if (!c.WebSockets.IsWebSocketRequest) { c.Response.StatusCode = 400; return; }
        var owner = c.User.FindFirstValue("sub") ?? throw new PlatformException("UNAUTHENTICATED", 401);
        var auth = await c.AuthenticateAsync();
        // Cookie tickets should carry ExpiresUtc; never treat "missing" as already expired
        // or the server accepts the socket and closes it before any events (UI reconnect loop).
        var expires = auth.Properties?.ExpiresUtc ?? DateTimeOffset.UtcNow.AddHours(1);
        if (expires <= DateTimeOffset.UtcNow) throw new PlatformException("UNAUTHENTICATED", 401);
        using var socket = await c.WebSockets.AcceptWebSocketAsync();
        using var stop = CancellationTokenSource.CreateLinkedTokenSource(c.RequestAborted);
        var sendLock = new SemaphoreSlim(1, 1);
        async Task Send(object value)
        {
            var data = Encoding.UTF8.GetBytes(Wire.Serialize(value));
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(stop.Token); timeout.CancelAfter(TimeSpan.FromSeconds(5));
            await sendLock.WaitAsync(timeout.Token);
            try { await socket.SendAsync(data.AsMemory(), WebSocketMessageType.Text, true, timeout.Token); }
            finally { sendLock.Release(); }
        }
        async Task<JsonElement> Receive()
        {
            var bytes = new byte[4096]; var result = await socket.ReceiveAsync(bytes.AsMemory(), stop.Token);
            Rules.Require(result.MessageType == WebSocketMessageType.Text && result.EndOfMessage, "INVALID_FRAME", 400);
            return JsonSerializer.Deserialize<JsonElement>(bytes.AsSpan(0, result.Count));
        }
        try
        {
            var first = await Receive();
            Rules.Require(first.GetProperty("type").GetString() == "subscribe", "SUBSCRIBE_REQUIRED", 400);
            var runId = first.GetProperty("runId").GetGuid(); var cursor = long.Parse(first.GetProperty("afterSequence").GetString()!);
            var run = await store.Get(owner, runId);
            await Send(new { type = "subscribed", runId, earliestAvailableSequence = run.EarliestAvailableSequence, highWatermark = run.LastEventSequence, status = run.Status });
            async Task ReadCommands()
            {
                try
                {
                    while (!stop.IsCancellationRequested)
                    {
                        var m = await Receive();
                        if (m.GetProperty("type").GetString() == "cancel")
                        {
                            Rules.Require(m.GetProperty("runId").GetGuid() == runId, "WRONG_RUN", 403);
                            var accepted = await store.Cancel(owner, runId, m.GetProperty("commandId").GetGuid());
                            await Send(new { type = "ack", commandId = accepted.CommandId, ack = "PERSISTED" });
                        }
                        else await Send(new { type = "pong" });
                    }
                }
                finally { stop.Cancel(); }
            }
            var receive = ReadCommands();
            try
            {
                while (!stop.IsCancellationRequested && DateTimeOffset.UtcNow < expires)
                {
                    var page = await store.Events(owner, runId, cursor, 20);
                    foreach (var e in page.Items)
                    {
                        await Send(new { type = "event", runId, sequence = e.Sequence, kind = e.Kind, payload = e.Payload });
                        cursor = long.Parse(e.Sequence);
                    }
                    // Catch up without artificial delay; idle poll stays short for near-live UI.
                    if (page.Items.Count == 0) await Task.Delay(150, stop.Token);
                }
            }
            finally { stop.Cancel(); try { await receive; } catch (Exception) { } }
        }
        catch (PlatformException e) { try { await Send(new { type = e.Code == "CURSOR_EXPIRED" ? "cursor_expired" : "error", code = e.Code }); } catch (Exception) { } }
        catch (Exception e) when (e is OperationCanceledException or WebSocketException or JsonException or FormatException or InvalidOperationException) { }
        finally { if (socket.State == WebSocketState.Open) { using var end = new CancellationTokenSource(1000); try { await socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "Reconnect with cursor", end.Token); } catch (Exception) { } } }
    }

    static bool OriginAllowed(HttpContext c, IConfiguration config)
    {
        var origin = c.Request.Headers.Origin.ToString().Trim().TrimEnd('/');
        if (string.IsNullOrEmpty(origin)) return false;
        var configured = (config["Security:PublicOrigin"] ?? "").Trim().TrimEnd('/');
        var request = $"{c.Request.Scheme}://{c.Request.Host}".TrimEnd('/');
        return origin.Equals(configured, StringComparison.OrdinalIgnoreCase)
            || origin.Equals(request, StringComparison.OrdinalIgnoreCase);
    }
}
