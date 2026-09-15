using AgentPlatform.Contracts.Agent.V1;
using Grpc.Core;

namespace AgentPlatform;

public sealed class AgentService(ChatStore chat, CapabilityHandlers handlers, IConfiguration config) : AgentChannel.AgentChannelBase
{
    public override async Task Connect(IAsyncStreamReader<AgentFrame> requests, IServerStreamWriter<GatewayAgentFrame> responses, ServerCallContext context)
    {
        var http = context.GetHttpContext();
        var cert = await http.Connection.GetClientCertificateAsync();
        var allowed = config.GetSection("Runner:AllowedThumbprints").Get<string[]>() ?? [];
        var chatAllowed = config.GetSection("Chat:AllowedThumbprints").Get<string[]>() ?? allowed;
        if (cert == null || !chatAllowed.Contains(cert.Thumbprint, StringComparer.OrdinalIgnoreCase))
            throw new RpcException(new Status(StatusCode.Unauthenticated, "Chat agent certificate required"));
        Guid? boot = null;
        long fence = 0;
        Guid? currentInvocation = null;
        await foreach (var f in requests.ReadAllAsync(context.CancellationToken))
        {
            var reply = new GatewayAgentFrame { MessageId = Guid.NewGuid().ToString("D"), CorrelationId = f.MessageId, ProtocolVersion = 1 };
            try
            {
                Rules.Require(Guid.TryParse(f.MessageId, out _), "INVALID_MESSAGE_ID", 400);
                Rules.Require(f.ProtocolVersion == 0 || f.ProtocolVersion == 1, "CONTRACT_VERSION_UNSUPPORTED", 400);
                if (boot == null)
                {
                    Rules.Require(f.Hello != null, "HELLO_REQUIRED", 400);
                    Rules.Require(Guid.TryParse(f.Hello!.BootId, out var parsedBoot), "HELLO_REQUIRED", 400);
                    boot = parsedBoot;
                    reply.Ack = new AckPersisted { Code = "HELLO_OK" };
                }
                else
                {
                    switch (f.PayloadCase)
                    {
                        case AgentFrame.PayloadOneofCase.Claim:
                        {
                            var a = await chat.ClaimChatExecution(cert.Thumbprint, boot.Value);
                            if (a == null) reply.NoWork = new NoWork();
                            else
                            {
                                currentInvocation = a.InvocationId;
                                fence = a.Fence;
                                reply.Assignment = new Assignment
                                {
                                    InvocationId = a.InvocationId.ToString("D"),
                                    TaskId = a.TaskId.ToString("D"),
                                    ConversationId = a.ConversationId.ToString("D"),
                                    DefinitionVersion = a.DefinitionVersion,
                                    ModelProfile = a.ModelProfile,
                                    Fence = a.Fence,
                                    // T028: resume payload for second claim (no proto field yet).
                                    Goal = string.IsNullOrEmpty(a.ResumeJson)
                                        ? a.Goal
                                        : a.Goal + "\n\n[[KATS_RESUME]]" + a.ResumeJson
                                };
                            }
                            break;
                        }
                        case AgentFrame.PayloadOneofCase.Heartbeat:
                        {
                            Rules.Require(Guid.TryParse(f.Heartbeat!.InvocationId, out var inv), "INVALID_ID", 400);
                            await chat.RenewChatExecution(boot.Value, inv, f.Heartbeat.Fence);
                            reply.Ack = new AckPersisted { Code = "OK" };
                            break;
                        }
                        case AgentFrame.PayloadOneofCase.EnsureInvocation:
                        {
                            var e = f.EnsureInvocation!;
                            Rules.Require(Guid.TryParse(e.TaskId, out var taskId), "INVALID_ID", 400);
                            var request = new EnsureInvocationRequest(
                                taskId, e.CheckpointId, e.GraphTaskPath, e.ToolCallId, e.Capability, e.Version, e.InputJson);
                            var (owner, ensured) = await chat.EnsureInvocationWithOwner(request);
                            if (string.IsNullOrEmpty(ensured.ResultJson))
                            {
                                var resultJson = await handlers.ExecuteAsync(owner, request, ensured);
                                // coding.execute is async: ACCEPTED/RUNNING until Run projects terminal.
                                var invStatus = request.Capability == "coding.execute" ? "RUNNING" : "SUCCEEDED";
                                ensured = await chat.CompleteInvocationResult(ensured.InvocationId, invStatus, resultJson);
                            }
                            reply.InvocationAccepted = new InvocationAccepted
                            {
                                InvocationId = ensured.InvocationId.ToString("D"),
                                Status = ensured.Status,
                                RunId = ensured.RunId?.ToString("D") ?? ""
                            };
                            break;
                        }
                        case AgentFrame.PayloadOneofCase.GetInvocation:
                        {
                            Rules.Require(Guid.TryParse(f.GetInvocation!.InvocationId, out var invId), "INVALID_ID", 400);
                            var snap = await chat.GetInvocation(invId) ?? throw new PlatformException("NOT_FOUND", 404);
                            reply.InvocationSnapshot = new InvocationSnapshot
                            {
                                InvocationId = snap.InvocationId.ToString("D"),
                                Status = snap.Status,
                                ResultJson = snap.ResultJson ?? "",
                                RunId = snap.RunId?.ToString("D") ?? ""
                            };
                            break;
                        }
                        case AgentFrame.PayloadOneofCase.Complete:
                        {
                            Rules.Require(Guid.TryParse(f.Complete!.InvocationId, out var invId), "INVALID_ID", 400);
                            Rules.Require(currentInvocation == invId, "FENCED", 403);
                            string? text = null;
                            try
                            {
                                using var doc = System.Text.Json.JsonDocument.Parse(string.IsNullOrWhiteSpace(f.Complete.ResultJson) ? "{}" : f.Complete.ResultJson);
                                if (doc.RootElement.TryGetProperty("assistantText", out var at)) text = at.GetString();
                            }
                            catch { /* ignore malformed preview */ }
                            var errorCode = string.IsNullOrWhiteSpace(f.Complete.ErrorCode) ? null : f.Complete.ErrorCode;
                            var safeMessage = string.IsNullOrWhiteSpace(f.Complete.SafeMessage) ? null : f.Complete.SafeMessage;
                            await chat.CompleteChatExecution(boot.Value, invId, fence, f.Complete.Status, f.Complete.ResultJson, text, errorCode, safeMessage);
                            reply.Ack = new AckPersisted { Code = "PERSISTED" };
                            currentInvocation = null;
                            break;
                        }
                        case AgentFrame.PayloadOneofCase.CreateInteraction:
                        {
                            var ci = f.CreateInteraction!;
                            Rules.Require(Guid.TryParse(ci.InteractionId, out var iid), "INVALID_ID", 400);
                            Rules.Require(Guid.TryParse(ci.TaskId, out var tid), "INVALID_ID", 400);
                            var expires = DateTimeOffset.FromUnixTimeMilliseconds(ci.ExpiresUnixMs).UtcDateTime;
                            await chat.CreateInteraction(iid, tid, ci.Kind, ci.PayloadJson, ci.PayloadHash, expires);
                            reply.Ack = new AckPersisted { Code = "PERSISTED" };
                            break;
                        }
                        case AgentFrame.PayloadOneofCase.CheckpointPut:
                        {
                            var p = f.CheckpointPut!;
                            Rules.Require(Guid.TryParse(p.ThreadId, out var thread), "INVALID_ID", 400);
                            await chat.PutCheckpoint(new CheckpointPutRequest(
                                thread, p.Namespace, p.CheckpointId,
                                string.IsNullOrEmpty(p.ParentCheckpointId) ? null : p.ParentCheckpointId,
                                p.CodecVersion, p.PayloadJson, p.MetadataJson, p.Fence));
                            reply.Ack = new AckPersisted { Code = "PERSISTED" };
                            break;
                        }
                        case AgentFrame.PayloadOneofCase.CheckpointPutWrites:
                        {
                            var p = f.CheckpointPutWrites!;
                            Rules.Require(Guid.TryParse(p.ThreadId, out var thread), "INVALID_ID", 400);
                            await chat.PutCheckpointWrites(new CheckpointPutWritesRequest(
                                thread, p.Namespace, p.CheckpointId, p.GraphTaskId,
                                p.Writes.Select(w => new CheckpointWriteItem(w.WriteIndex, w.Channel, w.ValueJson)).ToList()));
                            reply.Ack = new AckPersisted { Code = "PERSISTED" };
                            break;
                        }
                        case AgentFrame.PayloadOneofCase.CheckpointGet:
                        {
                            var p = f.CheckpointGet!;
                            Rules.Require(Guid.TryParse(p.ThreadId, out var thread), "INVALID_ID", 400);
                            var item = await chat.GetCheckpoint(thread, p.Namespace, string.IsNullOrEmpty(p.CheckpointId) ? null : p.CheckpointId);
                            if (item == null) reply.Ack = new AckPersisted { Code = "NOT_FOUND" };
                            else
                            {
                                reply.CheckpointItem = new CheckpointItem
                                {
                                    ThreadId = item.ThreadId.ToString("D"),
                                    Namespace = item.Namespace,
                                    CheckpointId = item.CheckpointId,
                                    ParentCheckpointId = item.ParentCheckpointId ?? "",
                                    CodecVersion = item.CodecVersion,
                                    PayloadJson = item.PayloadJson,
                                    MetadataJson = item.MetadataJson
                                };
                            }
                            break;
                        }
                        case AgentFrame.PayloadOneofCase.Suspend:
                        {
                            var s = f.Suspend!;
                            Rules.Require(Guid.TryParse(s.InvocationId, out var invId), "INVALID_ID", 400);
                            Rules.Require(currentInvocation == invId, "FENCED", 403);
                            await chat.SuspendExecution(boot.Value, invId, fence, s.CheckpointId, s.DependencyIds.ToList());
                            reply.Ack = new AckPersisted { Code = "SUSPENDED" };
                            currentInvocation = null;
                            break;
                        }
                        case AgentFrame.PayloadOneofCase.Output:
                            reply.Ack = new AckPersisted { Code = "OK" };
                            break;
                        default:
                            throw new PlatformException("INVALID_MESSAGE", 400);
                    }
                }
            }
            catch (PlatformException e)
            {
                reply.Error = new ProtocolError { Code = e.Code, SafeMessage = e.Code, Retryable = e.Status >= 500 };
            }
            catch (Exception)
            {
                reply.Error = new ProtocolError { Code = "UNAVAILABLE", SafeMessage = "Storage unavailable", Retryable = true };
            }
            await responses.WriteAsync(reply);
        }
    }
}
