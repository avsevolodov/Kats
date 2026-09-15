namespace AgentPlatform;

public sealed record CreateConversation(Guid CommandId, string? Title = null);
public sealed record ConversationView(Guid ConversationId, string Title, DateTime CreatedAt, DateTime UpdatedAt, string HighWatermark);
public sealed record PostMessage(Guid CommandId, string Text, Guid? ReplyToInteractionId = null);
public sealed record MessageAccepted(Guid CommandId, Guid MessageId, Guid? TaskId, string Disposition)
{
    public string Ack => "PERSISTED";
}
public sealed record MessageView(Guid MessageId, string Role, string Content, Guid? TaskId, DateTime CreatedAt);
public sealed record AgentTaskView(Guid TaskId, Guid ConversationId, string Status, int GoalRevision, string WorkflowId, DateTime WallDeadline, bool CancelDesired);
public sealed record TaskWorkflowInput(Guid TaskId, Guid ConversationId, Guid RootInvocationId, DateTime Deadline);
public sealed record CancelTask(Guid CommandId);
public sealed record InteractionResponse(Guid CommandId, string PayloadHash, string Decision, string[][]? Answers = null);
public sealed record InteractionResponseResult(Guid InteractionId, string DecisionStatus, string DeliveryStatus)
{
    public string Ack => "PERSISTED";
}
public sealed record ChatAssignment(Guid InvocationId, Guid TaskId, Guid ConversationId, string DefinitionVersion, string ModelProfile, long Fence, string Goal, string ResumeJson = "");
public sealed record InvocationSnapshotView(Guid InvocationId, string Status, string? ResultJson, Guid? RunId);
public sealed record EnsureInvocationRequest(
    Guid TaskId,
    string CheckpointId,
    string GraphTaskPath,
    string ToolCallId,
    string Capability,
    string Version,
    string InputJson);
public sealed record EnsureInvocationResult(Guid InvocationId, string Status, Guid? RunId, string? ResultJson = null);
public sealed record CheckpointPutRequest(
    Guid ThreadId,
    string Namespace,
    string CheckpointId,
    string? ParentCheckpointId,
    string CodecVersion,
    string PayloadJson,
    string MetadataJson,
    long Fence);
public sealed record CheckpointWriteItem(int WriteIndex, string Channel, string ValueJson);
public sealed record CheckpointPutWritesRequest(
    Guid ThreadId,
    string Namespace,
    string CheckpointId,
    string GraphTaskId,
    IReadOnlyList<CheckpointWriteItem> Writes);
public sealed record CheckpointView(
    Guid ThreadId,
    string Namespace,
    string CheckpointId,
    string? ParentCheckpointId,
    string CodecVersion,
    string PayloadJson,
    string MetadataJson);
public sealed record ConversationEventView(string Sequence, string Kind, string Payload, DateTime CreatedAt);
public sealed record ConversationEventPage(IReadOnlyList<ConversationEventView> Items, string HighWatermark, string EarliestAvailableSequence, bool HasMore);
