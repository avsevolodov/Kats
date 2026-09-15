using System.Net.WebSockets;
using System.Security.Claims;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Authentication;

namespace AgentPlatform;

public static class ConversationStream
{
    public static async Task Handle(HttpContext c, ChatStore store, IConfiguration config)
    {
        Rules.Require(OriginAllowed(c, config), "INVALID_ORIGIN", 403);
        if (!c.WebSockets.IsWebSocketRequest) { c.Response.StatusCode = 400; return; }
        var owner = c.User.FindFirstValue("sub") ?? throw new PlatformException("UNAUTHENTICATED", 401);
        var auth = await c.AuthenticateAsync();
        var expires = auth.Properties?.ExpiresUtc ?? DateTimeOffset.UtcNow.AddHours(1);
        if (expires <= DateTimeOffset.UtcNow) throw new PlatformException("UNAUTHENTICATED", 401);
        using var socket = await c.WebSockets.AcceptWebSocketAsync();
        using var stop = CancellationTokenSource.CreateLinkedTokenSource(c.RequestAborted);
        var sendLock = new SemaphoreSlim(1, 1);
        async Task Send(object value)
        {
            var data = Encoding.UTF8.GetBytes(Wire.Serialize(value));
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(stop.Token);
            timeout.CancelAfter(TimeSpan.FromSeconds(5));
            await sendLock.WaitAsync(timeout.Token);
            try { await socket.SendAsync(data.AsMemory(), WebSocketMessageType.Text, true, timeout.Token); }
            finally { sendLock.Release(); }
        }
        async Task<JsonElement> Receive()
        {
            var bytes = new byte[4096];
            var result = await socket.ReceiveAsync(bytes.AsMemory(), stop.Token);
            Rules.Require(result.MessageType == WebSocketMessageType.Text && result.EndOfMessage, "INVALID_FRAME", 400);
            return JsonSerializer.Deserialize<JsonElement>(bytes.AsSpan(0, result.Count));
        }
        try
        {
            var first = await Receive();
            Rules.Require(first.GetProperty("type").GetString() == "subscribe", "SUBSCRIBE_REQUIRED", 400);
            var conversationId = first.GetProperty("conversationId").GetGuid();
            var cursor = long.Parse(first.GetProperty("afterSequence").GetString()!);
            var conv = await store.GetConversation(owner, conversationId);
            await Send(new
            {
                type = "subscribed",
                conversationId,
                highWatermark = conv.HighWatermark,
                earliestAvailableSequence = "1"
            });
            async Task ReadCommands()
            {
                try
                {
                    while (!stop.IsCancellationRequested)
                    {
                        var m = await Receive();
                        var type = m.GetProperty("type").GetString();
                        if (type == "ping") await Send(new { type = "pong" });
                    }
                }
                finally { stop.Cancel(); }
            }
            var receive = ReadCommands();
            try
            {
                while (!stop.IsCancellationRequested && DateTimeOffset.UtcNow < expires)
                {
                    var page = await store.Events(owner, conversationId, cursor);
                    foreach (var e in page.Items)
                    {
                        cursor = long.Parse(e.Sequence);
                        await Send(new { type = "event", sequence = e.Sequence, kind = e.Kind, payload = e.Payload, createdAt = e.CreatedAt });
                    }
                    if (page.Items.Count == 0)
                        await Send(new { type = "caughtUp", cursor = cursor.ToString() });
                    await Task.Delay(500, stop.Token);
                }
            }
            finally
            {
                stop.Cancel();
                try { await receive; } catch { /* ignore */ }
            }
        }
        catch (OperationCanceledException) { }
        catch (PlatformException e)
        {
            if (socket.State == WebSocketState.Open)
            {
                var data = Encoding.UTF8.GetBytes(Wire.Serialize(new { type = "error", code = e.Code }));
                await socket.SendAsync(data, WebSocketMessageType.Text, true, CancellationToken.None);
            }
        }
    }

    static bool OriginAllowed(HttpContext c, IConfiguration config)
    {
        var origin = c.Request.Headers.Origin.ToString();
        if (string.IsNullOrEmpty(origin)) return true;
        var allowed = config.GetSection("Browser:AllowedOrigins").Get<string[]>() ?? [];
        return allowed.Contains(origin, StringComparer.OrdinalIgnoreCase);
    }
}
