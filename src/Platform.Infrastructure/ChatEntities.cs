using Microsoft.EntityFrameworkCore;

namespace AgentPlatform;

public sealed class ConversationRow
{
    public Guid Id { get; set; }
    public string OwnerSubject { get; set; } = "";
    public string Title { get; set; } = "";
    public DateTime CreatedAt { get; set; }
    public DateTime UpdatedAt { get; set; }
    public long NextEventSequence { get; set; }
    public long SummaryCursor { get; set; }
}

public sealed class AgentTaskRow
{
    public Guid Id { get; set; }
    public Guid ConversationId { get; set; }
    public string Goal { get; set; } = "";
    public int GoalRevision { get; set; } = 1;
    public string Status { get; set; } = "ACCEPTED";
    public Guid? RootInvocationId { get; set; }
    public string WorkflowId { get; set; } = "";
    public DateTime WallDeadline { get; set; }
    public bool CancelDesired { get; set; }
    public string DefinitionVersion { get; set; } = "chat-v1";
    public bool IsActive { get; set; } = true;
    public DateTime CreatedAt { get; set; }
    public DateTime UpdatedAt { get; set; }
}

public sealed class MessageRow
{
    public Guid Id { get; set; }
    public Guid ConversationId { get; set; }
    public string Role { get; set; } = "user";
    public string Content { get; set; } = "";
    public Guid? TaskId { get; set; }
    public string? SourceKey { get; set; }
    public Guid? ReplyToInteractionId { get; set; }
    public DateTime CreatedAt { get; set; }
}

public sealed class ConversationCommandRow
{
    public Guid CommandId { get; set; }
    public string OwnerSubject { get; set; } = "";
    public Guid ConversationId { get; set; }
    public string RequestHash { get; set; } = "";
    public Guid AcceptedResourceId { get; set; }
    public string Status { get; set; } = "PENDING";
    public string Kind { get; set; } = "";
    public DateTime CreatedAt { get; set; }
}

public sealed class TaskInputRow
{
    public Guid Id { get; set; }
    public Guid TaskId { get; set; }
    public Guid MessageId { get; set; }
    public int Revision { get; set; }
    public string Disposition { get; set; } = "new_task";
    public DateTime? AppliedAt { get; set; }
}

public sealed class InvocationRow
{
    public Guid Id { get; set; }
    public Guid TaskId { get; set; }
    public Guid? ParentId { get; set; }
    public string Kind { get; set; } = "agent";
    public string Capability { get; set; } = "";
    public string Version { get; set; } = "1";
    public string RequestHash { get; set; } = "";
    public string Status { get; set; } = "ACCEPTED";
    public Guid? RunId { get; set; }
    public string? ResultJson { get; set; }
    public bool CancelDesired { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime UpdatedAt { get; set; }
}

public sealed class DispatchIntentRow
{
    public Guid TaskId { get; set; }
    public string CheckpointId { get; set; } = "";
    public string GraphTaskPath { get; set; } = "";
    public string ToolCallId { get; set; } = "";
    public Guid InvocationId { get; set; }
    public string InputHash { get; set; } = "";
    public DateTime CreatedAt { get; set; }
}

public sealed class AgentExecutionRow
{
    public Guid InvocationId { get; set; }
    public Guid BootId { get; set; }
    public long Fence { get; set; }
    public DateTime LeaseUntil { get; set; }
    public string? CheckpointId { get; set; }
    public string Status { get; set; } = "LEASED";
}

public sealed class InteractionRequestRow
{
    public Guid Id { get; set; }
    public Guid TaskId { get; set; }
    public Guid? OriginInvocationId { get; set; }
    public string? ExternalRequestId { get; set; }
    public string Kind { get; set; } = "clarification";
    public string PayloadJson { get; set; } = "{}";
    public string PayloadHash { get; set; } = "";
    public string Status { get; set; } = "PENDING";
    public DateTime ExpiresAt { get; set; }
    public string DeliveryStatus { get; set; } = "NONE";
    public DateTime CreatedAt { get; set; }
}

public sealed class InteractionDecisionRow
{
    public Guid InteractionId { get; set; }
    public Guid CommandId { get; set; }
    public string Decision { get; set; } = "";
    public string? AnswersJson { get; set; }
    public string ActorSubject { get; set; } = "";
    public DateTime DecidedAt { get; set; }
    public string DecisionHash { get; set; } = "";
}

public sealed class ConversationEventRow
{
    public Guid ConversationId { get; set; }
    public long Sequence { get; set; }
    public Guid EventId { get; set; }
    public Guid? TaskId { get; set; }
    public Guid? InvocationId { get; set; }
    public string Kind { get; set; } = "";
    public string Payload { get; set; } = "{}";
    public string SourceEventKey { get; set; } = "";
    public DateTime CreatedAt { get; set; }
}

public sealed class GraphCheckpointRow
{
    public Guid ThreadId { get; set; }
    public string Namespace { get; set; } = "";
    public string CheckpointId { get; set; } = "";
    public string? ParentCheckpointId { get; set; }
    public string DefinitionVersion { get; set; } = "chat-v1";
    public string CodecVersion { get; set; } = "";
    public string Payload { get; set; } = "{}";
    public string Metadata { get; set; } = "{}";
    public DateTime CreatedAt { get; set; }
}

public sealed class GraphPendingWriteRow
{
    public Guid ThreadId { get; set; }
    public string Namespace { get; set; } = "";
    public string CheckpointId { get; set; } = "";
    public string GraphTaskId { get; set; } = "";
    public int WriteIndex { get; set; }
    public string Channel { get; set; } = "";
    public string ValueJson { get; set; } = "{}";
}

public sealed class ContextBindingRow
{
    public Guid Id { get; set; }
    public Guid TaskId { get; set; }
    public Guid RepositoryId { get; set; }
    public string BaseCommit { get; set; } = "";
    public string EvidenceRefsJson { get; set; } = "[]";
    public string CatalogVersion { get; set; } = "";
    public DateTime SelectedAt { get; set; }
    public int TaskRevision { get; set; }
}

public sealed class RepositoryMetadataRow
{
    public Guid RepositoryId { get; set; }
    public string Description { get; set; } = "";
    public string AliasesJson { get; set; } = "[]";
    public string ServiceNamesJson { get; set; } = "[]";
    public string ComponentsJson { get; set; } = "[]";
    public string DefaultRef { get; set; } = "main";
    public string SourceRefs { get; set; } = "[]";
    public DateTime UpdatedAt { get; set; }
    public string CatalogVersion { get; set; } = "1";
}

public sealed class RepositoryAccessRow
{
    public Guid RepositoryId { get; set; }
    public string PrincipalKind { get; set; } = "user";
    public string PrincipalId { get; set; } = "";
    public string Action { get; set; } = "read";
}

public static class ChatDbModel
{
    public static void Configure(ModelBuilder b)
    {
        b.Entity<ConversationRow>().HasKey(x => x.Id);
        b.Entity<ConversationRow>().Property(x => x.OwnerSubject).HasMaxLength(200).UseCollation("Latin1_General_100_BIN2");
        b.Entity<ConversationRow>().HasIndex(x => new { x.OwnerSubject, x.UpdatedAt });

        b.Entity<AgentTaskRow>().HasKey(x => x.Id);
        b.Entity<AgentTaskRow>().Property(x => x.Status).HasMaxLength(32);
        b.Entity<AgentTaskRow>().Property(x => x.WorkflowId).HasMaxLength(200);
        b.Entity<AgentTaskRow>().HasIndex(x => x.ConversationId).HasFilter("[IsActive] = 1").IsUnique();

        b.Entity<MessageRow>().HasKey(x => x.Id);
        b.Entity<MessageRow>().HasIndex(x => new { x.ConversationId, x.CreatedAt });

        b.Entity<ConversationCommandRow>().HasKey(x => new { x.OwnerSubject, x.CommandId });
        b.Entity<ConversationCommandRow>().Property(x => x.OwnerSubject).HasMaxLength(200).UseCollation("Latin1_General_100_BIN2");

        b.Entity<TaskInputRow>().HasKey(x => x.Id);
        b.Entity<TaskInputRow>().HasIndex(x => x.MessageId).IsUnique();

        b.Entity<InvocationRow>().HasKey(x => x.Id);
        b.Entity<InvocationRow>().HasIndex(x => x.RunId).HasFilter("[RunId] IS NOT NULL").IsUnique();

        b.Entity<DispatchIntentRow>().HasKey(x => new { x.TaskId, x.CheckpointId, x.GraphTaskPath, x.ToolCallId });
        b.Entity<DispatchIntentRow>().Property(x => x.CheckpointId).HasMaxLength(200);
        b.Entity<DispatchIntentRow>().Property(x => x.GraphTaskPath).HasMaxLength(200);
        b.Entity<DispatchIntentRow>().Property(x => x.ToolCallId).HasMaxLength(200);

        b.Entity<AgentExecutionRow>().HasKey(x => x.InvocationId);

        b.Entity<InteractionRequestRow>().HasKey(x => x.Id);
        b.Entity<InteractionDecisionRow>().HasKey(x => x.InteractionId);

        b.Entity<ConversationEventRow>().HasKey(x => new { x.ConversationId, x.Sequence });
        b.Entity<ConversationEventRow>().HasIndex(x => x.SourceEventKey).IsUnique();

        b.Entity<GraphCheckpointRow>().HasKey(x => new { x.ThreadId, x.Namespace, x.CheckpointId });
        b.Entity<GraphCheckpointRow>().Property(x => x.Namespace).HasMaxLength(200);
        b.Entity<GraphCheckpointRow>().Property(x => x.CheckpointId).HasMaxLength(200);

        b.Entity<GraphPendingWriteRow>().HasKey(x => new { x.ThreadId, x.Namespace, x.CheckpointId, x.GraphTaskId, x.WriteIndex });

        b.Entity<ContextBindingRow>().HasKey(x => x.Id);
        b.Entity<RepositoryMetadataRow>().HasKey(x => x.RepositoryId);
        b.Entity<RepositoryAccessRow>().HasKey(x => new { x.RepositoryId, x.PrincipalKind, x.PrincipalId, x.Action });
    }
}
