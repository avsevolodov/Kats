using AgentPlatform.Contracts.Runner.V1;
using Grpc.Core;
namespace AgentPlatform;

public sealed class RunnerService(SqlStore store, IConfiguration config) : RunnerGateway.RunnerGatewayBase
{
    public override async Task WorkChannel(IAsyncStreamReader<RunnerFrame> requests, IServerStreamWriter<GatewayFrame> responses, ServerCallContext context)
    {
        var cert = await context.GetHttpContext().Connection.GetClientCertificateAsync();
        var allowed = config.GetSection("Runner:AllowedThumbprints").Get<string[]>() ?? [];
        if (cert == null || !allowed.Contains(cert.Thumbprint, StringComparer.OrdinalIgnoreCase)) throw new RpcException(new(StatusCode.Unauthenticated, "Runner certificate required"));
        var workload = cert.Thumbprint;
        string? boot = null;
        await foreach (var f in requests.ReadAllAsync(context.CancellationToken))
        {
            var reply = new GatewayFrame { CorrelationMessageId = f.MessageId };
            try
            {
                Rules.Require(Guid.TryParse(f.MessageId, out _), "INVALID_MESSAGE_ID", 400);
                if (boot == null)
                {
                    Rules.Require(f.Hello != null && f.Hello.ProtocolVersion == 1 && Guid.TryParse(f.Hello.BootId, out _), "HELLO_REQUIRED", 400);
                    boot = f.Hello!.BootId; reply.Hello = new() { HeartbeatSeconds = 5, LeaseSeconds = 45 };
                }
                else
                {
                    var key = f.Resume?.Key ?? f.Begin?.Key ?? f.Heartbeat?.Key ?? f.Output?.Key ?? f.Complete?.Key ?? f.FetchGitCredential?.Key;
                    if (key != null) Rules.Require(key.BootId == boot, "FENCED", 403);
                    switch (f.PayloadCase)
                    {
                        case RunnerFrame.PayloadOneofCase.Claim:
                            var a = await store.Claim(workload, boot); if (a == null) reply.NoWork = new() { RetryAfterMs = 1000 }; else reply.Assignment = a; break;
                        case RunnerFrame.PayloadOneofCase.Resume: reply.Snapshot = await store.Resume(workload, f.Resume!.Key); break;
                        case RunnerFrame.PayloadOneofCase.Begin: reply.Ack = await store.Renew(workload, f.Begin!.Key, f.Begin.OpencodeSessionId); break;
                        case RunnerFrame.PayloadOneofCase.Heartbeat:
                            reply.Ack = await store.Renew(workload, f.Heartbeat!.Key);
                            var snapshot = await store.Resume(workload, f.Heartbeat.Key);
                            if (snapshot.CancelDesired) await responses.WriteAsync(new GatewayFrame { Abort = new() { Key = f.Heartbeat.Key, Reason = "CANCEL_REQUESTED" } });
                            break;
                        case RunnerFrame.PayloadOneofCase.Output:
                        case RunnerFrame.PayloadOneofCase.Complete: reply.Ack = await store.Produce(workload, f); break;
                        case RunnerFrame.PayloadOneofCase.FetchGitCredential:
                            reply.GitCredential = await store.FetchGitCredential(workload, f.FetchGitCredential!.Key); break;
                        default: throw new PlatformException("INVALID_MESSAGE", 400);
                    }
                }
            }
            catch (PlatformException e) { reply.Error = new() { Code = e.Code, SafeMessage = e.Code, Retryable = false }; }
            catch (Exception) { reply.Error = new() { Code = "UNAVAILABLE", SafeMessage = "Storage unavailable", Retryable = true }; }
            await responses.WriteAsync(reply);
        }
    }
}
