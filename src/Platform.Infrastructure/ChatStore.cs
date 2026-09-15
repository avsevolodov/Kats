using Microsoft.EntityFrameworkCore;

namespace AgentPlatform;

public sealed class ChatStore(IDbContextFactory<PlatformDb> factory)
{
    public bool ChatEnabled { get; init; } = true;

    public Task<ConversationView> CreateConversation(string owner, CreateConversation request) => Write(async (db, now) =>
    {
        Rules.Require(request.CommandId != Guid.Empty, "INVALID_ID", 400);
        var title = string.IsNullOrWhiteSpace(request.Title) ? "Диалог" : request.Title.Trim();
        Rules.Require(title.Length <= 200, "INVALID_TITLE", 400);
        var hash = Wire.Hash($"conv-create:{title}");
        var old = await db.ConversationCommands.FindAsync(owner, request.CommandId);
        if (old != null)
        {
            Rules.Require(old.RequestHash == hash && old.Kind == "CREATE_CONVERSATION", "COMMAND_CONFLICT");
            var existing = await db.Conversations.SingleAsync(x => x.Id == old.AcceptedResourceId);
            return View(existing);
        }
        var id = Guid.NewGuid();
        db.Conversations.Add(new ConversationRow
        {
            Id = id,
            OwnerSubject = owner,
            Title = title,
            CreatedAt = now,
            UpdatedAt = now
        });
        db.ConversationCommands.Add(new ConversationCommandRow
        {
            CommandId = request.CommandId,
            OwnerSubject = owner,
            ConversationId = id,
            RequestHash = hash,
            AcceptedResourceId = id,
            Status = "PROCESSED",
            Kind = "CREATE_CONVERSATION",
            CreatedAt = now
        });
        return new ConversationView(id, title, now, now, "0");
    });

    public async Task<IReadOnlyList<ConversationView>> ListConversations(string owner)
    {
        await using var db = await factory.CreateDbContextAsync();
        var rows = await db.Conversations.Where(x => x.OwnerSubject == owner).OrderByDescending(x => x.UpdatedAt).Take(100).ToListAsync();
        return rows.Select(View).ToList();
    }

    public async Task<ConversationView> GetConversation(string owner, Guid id)
    {
        await using var db = await factory.CreateDbContextAsync();
        return View(await OwnedConversation(db, owner, id));
    }

    public Task<MessageAccepted> PostMessage(string owner, Guid conversationId, PostMessage request) => Write(async (db, now) =>
    {
        Rules.Require(ChatEnabled, "CHAT_DISABLED", 503);
        Rules.Require(request.CommandId != Guid.Empty, "INVALID_ID", 400);
        Rules.Require(!string.IsNullOrWhiteSpace(request.Text) && request.Text.Length <= 16000, "INVALID_TEXT", 400);
        var hash = Wire.Hash($"msg:{conversationId:D}:{request.Text}:{request.ReplyToInteractionId}");
        var old = await db.ConversationCommands.FindAsync(owner, request.CommandId);
        if (old != null)
        {
            Rules.Require(old.RequestHash == hash && old.Kind == "POST_MESSAGE", "COMMAND_CONFLICT");
            var msg = await db.Messages.SingleAsync(x => x.Id == old.AcceptedResourceId);
            var tin = await db.TaskInputs.SingleOrDefaultAsync(x => x.MessageId == msg.Id);
            return new MessageAccepted(request.CommandId, msg.Id, msg.TaskId, tin?.Disposition ?? "status_query");
        }
        var conv = await OwnedConversation(db, owner, conversationId);
        var active = await db.AgentTasks.SingleOrDefaultAsync(x => x.ConversationId == conversationId && x.IsActive);
        string disposition;
        Guid? taskId;
        Guid messageId = Guid.NewGuid();
        if (request.ReplyToInteractionId is Guid interactionId)
        {
            disposition = "interaction_response";
            var interaction = await db.InteractionRequests.SingleOrDefaultAsync(x => x.Id == interactionId)
                ?? throw new PlatformException("NOT_FOUND", 404);
            taskId = interaction.TaskId;
        }
        else if (IsStatusQuery(request.Text))
        {
            disposition = "status_query";
            taskId = active?.Id;
        }
        else if (active == null)
        {
            disposition = "new_task";
            taskId = Guid.NewGuid();
            var rootInvocation = Guid.NewGuid();
            var workflowId = $"task-{taskId:D}";
            db.AgentTasks.Add(new AgentTaskRow
            {
                Id = taskId.Value,
                ConversationId = conversationId,
                Goal = request.Text,
                GoalRevision = 1,
                Status = "ACCEPTED",
                RootInvocationId = rootInvocation,
                WorkflowId = workflowId,
                WallDeadline = now.AddMinutes(30),
                DefinitionVersion = "chat-v1",
                IsActive = true,
                CreatedAt = now,
                UpdatedAt = now
            });
            db.Invocations.Add(new InvocationRow
            {
                Id = rootInvocation,
                TaskId = taskId.Value,
                Kind = "agent",
                Capability = "chat.root",
                Version = "1",
                RequestHash = Wire.Hash($"root:{taskId:D}"),
                Status = "ACCEPTED",
                CreatedAt = now,
                UpdatedAt = now
            });
            // Stable dispatch inbox for TaskWorkflow (CommandId = TaskId).
            if (await db.ConversationCommands.FindAsync(owner, taskId.Value) == null)
            {
                db.ConversationCommands.Add(new ConversationCommandRow
                {
                    CommandId = taskId.Value,
                    OwnerSubject = owner,
                    ConversationId = conversationId,
                    RequestHash = Wire.Hash($"start-task:{taskId:D}"),
                    AcceptedResourceId = taskId.Value,
                    Status = "PENDING",
                    Kind = "START_TASK",
                    CreatedAt = now
                });
            }
        }
        else if (active.Status is "WAITING_INTERACTION" or "WAITING_CHILD" or "ACTIVE")
        {
            disposition = "steer_pending";
            taskId = active.Id;
        }
        else
        {
            disposition = "queued";
            taskId = active.Id;
        }

        db.Messages.Add(new MessageRow
        {
            Id = messageId,
            ConversationId = conversationId,
            Role = "user",
            Content = request.Text,
            TaskId = taskId,
            ReplyToInteractionId = request.ReplyToInteractionId,
            CreatedAt = now
        });
        if (taskId is Guid tid)
        {
            db.TaskInputs.Add(new TaskInputRow
            {
                Id = Guid.NewGuid(),
                TaskId = tid,
                MessageId = messageId,
                Revision = disposition == "new_task" ? 1 : (active?.GoalRevision ?? 1),
                Disposition = disposition,
                AppliedAt = disposition == "new_task" ? now : null
            });
        }
        db.ConversationCommands.Add(new ConversationCommandRow
        {
            CommandId = request.CommandId,
            OwnerSubject = owner,
            ConversationId = conversationId,
            RequestHash = hash,
            AcceptedResourceId = messageId,
            Status = "PROCESSED",
            Kind = "POST_MESSAGE",
            CreatedAt = now
        });
        await EmitConversationEvent(db, conv, now, "MessageAccepted", new { messageId, disposition, taskId }, $"msg-accepted:{messageId:D}");
        conv.UpdatedAt = now;
        return new MessageAccepted(request.CommandId, messageId, taskId, disposition);
    });

    public async Task<IReadOnlyList<MessageView>> ListMessages(string owner, Guid conversationId)
    {
        await using var db = await factory.CreateDbContextAsync();
        await OwnedConversation(db, owner, conversationId);
        var rows = await db.Messages.Where(x => x.ConversationId == conversationId).OrderBy(x => x.CreatedAt).Take(500).ToListAsync();
        return rows.Select(x => new MessageView(x.Id, x.Role, x.Content, x.TaskId, x.CreatedAt)).ToList();
    }

    public async Task<AgentTaskView> GetTask(string owner, Guid taskId)
    {
        await using var db = await factory.CreateDbContextAsync();
        var task = await db.AgentTasks.SingleOrDefaultAsync(x => x.Id == taskId) ?? throw new PlatformException("NOT_FOUND", 404);
        await OwnedConversation(db, owner, task.ConversationId);
        return new AgentTaskView(task.Id, task.ConversationId, task.Status, task.GoalRevision, task.WorkflowId, task.WallDeadline, task.CancelDesired);
    }

    public Task<MessageAccepted> CancelTask(string owner, Guid taskId, CancelTask request) => Write(async (db, now) =>
    {
        Rules.Require(request.CommandId != Guid.Empty, "INVALID_ID", 400);
        var task = await db.AgentTasks.SingleOrDefaultAsync(x => x.Id == taskId) ?? throw new PlatformException("NOT_FOUND", 404);
        await OwnedConversation(db, owner, task.ConversationId);
        var hash = Wire.Hash($"cancel-task:{taskId:D}");
        var old = await db.ConversationCommands.FindAsync(owner, request.CommandId);
        if (old != null)
        {
            Rules.Require(old.RequestHash == hash && old.Kind == "CANCEL_TASK", "COMMAND_CONFLICT");
            return new MessageAccepted(request.CommandId, old.AcceptedResourceId, taskId, "status_query");
        }
        task.CancelDesired = true;
        task.UpdatedAt = now;
        // T027: mark child invocations cancelled; linked Runs get CANCEL inbox via SqlStore from Worker/activity.
        var children = await db.Invocations.Where(x => x.TaskId == taskId && x.Capability != "chat.root").ToListAsync();
        foreach (var child in children)
        {
            child.CancelDesired = true;
            child.UpdatedAt = now;
            if (child.Status is "ACCEPTED" or "RUNNING")
            {
                child.Status = "CANCELLED";
                child.UpdatedAt = now;
            }
        }
        db.ConversationCommands.Add(new ConversationCommandRow
        {
            CommandId = request.CommandId,
            OwnerSubject = owner,
            ConversationId = task.ConversationId,
            RequestHash = hash,
            AcceptedResourceId = taskId,
            Status = "PROCESSED",
            Kind = "CANCEL_TASK",
            CreatedAt = now
        });
        var signalId = Guid.NewGuid();
        db.ConversationCommands.Add(new ConversationCommandRow
        {
            CommandId = signalId,
            OwnerSubject = owner,
            ConversationId = task.ConversationId,
            RequestHash = Wire.Hash($"signal-cancel:{taskId:D}:{request.CommandId:D}"),
            AcceptedResourceId = taskId,
            Status = "PENDING",
            Kind = "SIGNAL_CANCEL",
            CreatedAt = now
        });
        // Ask worker to abort linked Runs (AcceptedResourceId = taskId; payload via kind).
        var abortId = DeterministicGuid(taskId, "abort-runs", request.CommandId.ToString("D"));
        if (await db.ConversationCommands.FindAsync(owner, abortId) == null)
        {
            db.ConversationCommands.Add(new ConversationCommandRow
            {
                CommandId = abortId,
                OwnerSubject = owner,
                ConversationId = task.ConversationId,
                RequestHash = Wire.Hash($"abort-runs:{taskId:D}:{request.CommandId:D}"),
                AcceptedResourceId = taskId,
                Status = "PENDING",
                Kind = "ABORT_TASK_RUNS",
                CreatedAt = now
            });
        }
        var conv = await db.Conversations.SingleAsync(x => x.Id == task.ConversationId);
        await EmitConversationEvent(db, conv, now, "TaskStatusChanged", new { taskId, status = "CANCEL_REQUESTED" }, $"task-cancel:{taskId:D}:{request.CommandId:D}");
        return new MessageAccepted(request.CommandId, taskId, taskId, "status_query");
    });

    public Task<InteractionResponseResult> RespondInteraction(string owner, Guid interactionId, InteractionResponse request) => Write(async (db, now) =>
    {
        Rules.Require(request.CommandId != Guid.Empty, "INVALID_ID", 400);
        var interaction = await db.InteractionRequests.SingleOrDefaultAsync(x => x.Id == interactionId)
            ?? throw new PlatformException("NOT_FOUND", 404);
        var task = await db.AgentTasks.SingleAsync(x => x.Id == interaction.TaskId);
        await OwnedConversation(db, owner, task.ConversationId);
        Rules.Require(interaction.PayloadHash == request.PayloadHash, "PAYLOAD_HASH_MISMATCH", 409);
        Rules.Require(interaction.Status == "PENDING" && interaction.ExpiresAt > now, "INTERACTION_EXPIRED", 409);
        InteractionRules.ValidateDecision(interaction.Kind, request.Decision, request.Answers);
        var answersJson = request.Answers is { Length: > 0 } ? Wire.Serialize(request.Answers) : null;
        var decisionHash = Wire.Hash($"{interactionId:D}:{request.Decision}:{answersJson}");
        var existing = await db.InteractionDecisions.FindAsync(interactionId);
        if (existing != null)
        {
            Rules.Require(existing.DecisionHash == decisionHash, "DECISION_CONFLICT", 409);
            if (task.Status == "WAITING_INTERACTION")
            {
                var convStuck = await db.Conversations.SingleAsync(x => x.Id == task.ConversationId);
                await RequeueRootClaim(db, task, convStuck, now, $"interaction-answered-retry:{interactionId:D}");
            }
            return new InteractionResponseResult(interactionId, "ANSWERED", interaction.DeliveryStatus);
        }
        db.InteractionDecisions.Add(new InteractionDecisionRow
        {
            InteractionId = interactionId,
            CommandId = request.CommandId,
            Decision = request.Decision.Trim().ToLowerInvariant(),
            AnswersJson = answersJson,
            ActorSubject = owner,
            DecidedAt = now,
            DecisionHash = decisionHash
        });
        interaction.Status = "ANSWERED";
        var conv = await db.Conversations.SingleAsync(x => x.Id == task.ConversationId);
        await EmitConversationEvent(db, conv, now, "InteractionDecided", new { interactionId, decision = request.Decision }, $"interaction-decided:{interactionId:D}");
        // T025: wake chat root for re-claim (do not leave WAITING_INTERACTION forever).
        await RequeueRootClaim(db, task, conv, now, $"interaction-answered:{interactionId:D}");
        return new InteractionResponseResult(interactionId, "ANSWERED", interaction.DeliveryStatus);
    });

    public Task<EnsureInvocationResult> EnsureInvocation(EnsureInvocationRequest request) => Write(async (db, now) =>
    {
        Rules.Require(!string.IsNullOrWhiteSpace(request.CheckpointId), "INVALID_CHECKPOINT", 400);
        Rules.Require(!string.IsNullOrWhiteSpace(request.ToolCallId), "INVALID_TOOL_CALL", 400);
        Rules.Require(!string.IsNullOrWhiteSpace(request.Capability), "INVALID_CAPABILITY", 400);
        var inputHash = Wire.Hash(request.InputJson ?? "{}");
        var existing = await db.DispatchIntents.FindAsync(request.TaskId, request.CheckpointId, request.GraphTaskPath, request.ToolCallId);
        if (existing != null)
        {
            Rules.Require(existing.InputHash == inputHash, "INTENT_CONFLICT", 409);
            var inv = await db.Invocations.SingleAsync(x => x.Id == existing.InvocationId);
            return new EnsureInvocationResult(inv.Id, inv.Status, inv.RunId, inv.ResultJson);
        }
        var task = await db.AgentTasks.SingleOrDefaultAsync(x => x.Id == request.TaskId) ?? throw new PlatformException("NOT_FOUND", 404);
        Rules.Require(!task.CancelDesired && !States.Terminal(task.Status), "TASK_TERMINAL", 409);
        var invocationId = Guid.NewGuid();
        Guid? runId = null;
        if (request.Capability == "coding.execute")
        {
            // Stable RunId derived from intent key — lost Start reply must not create a second Run.
            runId = DeterministicGuid(request.TaskId, request.CheckpointId, request.ToolCallId);
        }
        db.Invocations.Add(new InvocationRow
        {
            Id = invocationId,
            TaskId = request.TaskId,
            ParentId = task.RootInvocationId,
            Kind = request.Capability == "coding.execute" ? "coding" : "tool",
            Capability = request.Capability,
            Version = request.Version,
            RequestHash = inputHash,
            Status = "ACCEPTED",
            RunId = runId,
            CreatedAt = now,
            UpdatedAt = now
        });
        db.DispatchIntents.Add(new DispatchIntentRow
        {
            TaskId = request.TaskId,
            CheckpointId = request.CheckpointId,
            GraphTaskPath = request.GraphTaskPath,
            ToolCallId = request.ToolCallId,
            InvocationId = invocationId,
            InputHash = inputHash,
            CreatedAt = now
        });
        return new EnsureInvocationResult(invocationId, "ACCEPTED", runId);
    });

    public async Task<(string Owner, EnsureInvocationResult Ensured)> EnsureInvocationWithOwner(EnsureInvocationRequest request)
    {
        await using var db = await factory.CreateDbContextAsync();
        var task = await db.AgentTasks.SingleOrDefaultAsync(x => x.Id == request.TaskId) ?? throw new PlatformException("NOT_FOUND", 404);
        var conv = await db.Conversations.SingleAsync(x => x.Id == task.ConversationId);
        var ensured = await EnsureInvocation(request);
        return (conv.OwnerSubject, ensured);
    }

    public Task<EnsureInvocationResult> CompleteInvocationResult(Guid invocationId, string status, string resultJson) => Write(async (db, now) =>
    {
        var inv = await db.Invocations.SingleAsync(x => x.Id == invocationId);
        if (!string.IsNullOrEmpty(inv.ResultJson) && inv.Status == status && inv.ResultJson == resultJson)
            return new EnsureInvocationResult(inv.Id, inv.Status, inv.RunId, inv.ResultJson);
        if (!string.IsNullOrEmpty(inv.ResultJson) && inv.ResultJson != resultJson)
            throw new PlatformException("RESULT_CONFLICT", 409);
        inv.Status = status;
        inv.ResultJson = resultJson;
        inv.UpdatedAt = now;
        return new EnsureInvocationResult(inv.Id, inv.Status, inv.RunId, inv.ResultJson);
    });

    public Task PutCheckpoint(CheckpointPutRequest request) => Write(async (db, now) =>
    {
        Rules.Require(request.CodecVersion == "kats-checkpoint-v1", "INCOMPATIBLE_CODEC", 409);
        Rules.Require(request.PayloadJson.Length <= 2 * 1024 * 1024, "CHECKPOINT_TOO_LARGE", 413);
        var existing = await db.GraphCheckpoints.FindAsync(request.ThreadId, request.Namespace ?? "", request.CheckpointId);
        if (existing != null)
        {
            Rules.Require(existing.Payload == request.PayloadJson && existing.Metadata == request.MetadataJson, "CHECKPOINT_CONFLICT", 409);
            return;
        }
        db.GraphCheckpoints.Add(new GraphCheckpointRow
        {
            ThreadId = request.ThreadId,
            Namespace = request.Namespace ?? "",
            CheckpointId = request.CheckpointId,
            ParentCheckpointId = request.ParentCheckpointId,
            CodecVersion = request.CodecVersion,
            Payload = request.PayloadJson,
            Metadata = request.MetadataJson,
            CreatedAt = now
        });
    });

    public Task PutCheckpointWrites(CheckpointPutWritesRequest request) => Write(async (db, now) =>
    {
        foreach (var w in request.Writes)
        {
            var keyNs = request.Namespace ?? "";
            var existing = await db.GraphPendingWrites.FindAsync(request.ThreadId, keyNs, request.CheckpointId, request.GraphTaskId, w.WriteIndex);
            if (existing != null)
            {
                Rules.Require(existing.Channel == w.Channel && existing.ValueJson == w.ValueJson, "PENDING_WRITE_CONFLICT", 409);
                continue;
            }
            db.GraphPendingWrites.Add(new GraphPendingWriteRow
            {
                ThreadId = request.ThreadId,
                Namespace = keyNs,
                CheckpointId = request.CheckpointId,
                GraphTaskId = request.GraphTaskId,
                WriteIndex = w.WriteIndex,
                Channel = w.Channel,
                ValueJson = w.ValueJson
            });
        }
    });

    public async Task<CheckpointView?> GetCheckpoint(Guid threadId, string ns, string? checkpointId)
    {
        await using var db = await factory.CreateDbContextAsync();
        GraphCheckpointRow? row;
        if (!string.IsNullOrEmpty(checkpointId))
            row = await db.GraphCheckpoints.FindAsync(threadId, ns ?? "", checkpointId);
        else
            row = await db.GraphCheckpoints.Where(x => x.ThreadId == threadId && x.Namespace == (ns ?? "")).OrderByDescending(x => x.CreatedAt).FirstOrDefaultAsync();
        return row == null ? null : new CheckpointView(row.ThreadId, row.Namespace, row.CheckpointId, row.ParentCheckpointId, row.CodecVersion, row.Payload, row.Metadata);
    }

    public async Task<IReadOnlyList<CheckpointView>> ListCheckpoints(Guid threadId, string ns, int limit = 10)
    {
        await using var db = await factory.CreateDbContextAsync();
        var rows = await db.GraphCheckpoints.Where(x => x.ThreadId == threadId && x.Namespace == (ns ?? ""))
            .OrderByDescending(x => x.CreatedAt).Take(Math.Clamp(limit, 1, 100)).ToListAsync();
        return rows.Select(row => new CheckpointView(row.ThreadId, row.Namespace, row.CheckpointId, row.ParentCheckpointId, row.CodecVersion, row.Payload, row.Metadata)).ToList();
    }

    public async Task<ConversationEventPage> Events(string owner, Guid conversationId, long afterSequence)
    {
        await using var db = await factory.CreateDbContextAsync();
        var conv = await OwnedConversation(db, owner, conversationId);
        var rows = await db.ConversationEvents.Where(x => x.ConversationId == conversationId && x.Sequence > afterSequence)
            .OrderBy(x => x.Sequence).Take(100).ToListAsync();
        var items = rows.Select(x => new ConversationEventView(x.Sequence.ToString(), x.Kind, x.Payload, x.CreatedAt)).ToList();
        return new ConversationEventPage(items, conv.NextEventSequence.ToString(), "1", rows.Count == 100);
    }

    public Task AppendAssistantMessage(Guid conversationId, Guid? taskId, string content) => Write(async (db, now) =>
    {
        var conv = await db.Conversations.SingleAsync(x => x.Id == conversationId);
        var messageId = Guid.NewGuid();
        db.Messages.Add(new MessageRow
        {
            Id = messageId,
            ConversationId = conversationId,
            Role = "assistant",
            Content = content,
            TaskId = taskId,
            CreatedAt = now
        });
        await EmitConversationEvent(db, conv, now, "AssistantMessageCompleted", new { messageId, finalContent = content }, $"assistant-final:{messageId:D}");
        conv.UpdatedAt = now;
    });

    public Task SetTaskStatus(Guid taskId, string status) => Write(async (db, now) =>
    {
        var task = await db.AgentTasks.SingleAsync(x => x.Id == taskId);
        task.Status = status;
        task.UpdatedAt = now;
        if (States.Terminal(status) || status is "SUCCEEDED" or "FAILED" or "CANCELLED" or "NEEDS_ATTENTION")
            task.IsActive = false;
        var conv = await db.Conversations.SingleAsync(x => x.Id == task.ConversationId);
        await EmitConversationEvent(db, conv, now, "TaskStatusChanged", new { taskId, status }, $"task-status:{taskId:D}:{status}:{now.Ticks}");
    });

    public async Task<AgentTaskRow?> GetTaskRow(Guid taskId)
    {
        await using var db = await factory.CreateDbContextAsync();
        return await db.AgentTasks.SingleOrDefaultAsync(x => x.Id == taskId);
    }

    public async Task<IReadOnlyList<Guid>> ListAccessibleRepositoryIds(string owner, string action)
    {
        await using var db = await factory.CreateDbContextAsync();
        var viaAcl = await db.RepositoryAccess
            .Where(x => x.PrincipalKind == "user" && x.PrincipalId == owner && x.Action == action)
            .Select(x => x.RepositoryId).ToListAsync();
        if (viaAcl.Count > 0) return viaAcl;
        // Dev fallback: enabled repositories readable when ACL empty (explicit ACL rows still filter).
        var anyAcl = await db.RepositoryAccess.AnyAsync();
        if (anyAcl) return viaAcl;
        return await db.Repositories.Where(x => x.Enabled).Select(x => x.Id).ToListAsync();
    }

    public Task<ConversationCommandRow?> ClaimChatCommand() => Write(async (db, now) =>
    {
        var row = await db.ConversationCommands
            .Where(x => x.Status == "PENDING" && (x.Kind == "START_TASK" || x.Kind == "SIGNAL_CANCEL" || x.Kind == "SIGNAL_CHILD_COMPLETED" || x.Kind == "ABORT_TASK_RUNS"))
            .OrderBy(x => x.CreatedAt)
            .FirstOrDefaultAsync();
        if (row == null) return null;
        row.Status = "CLAIMED";
        return row;
    });

    public Task MarkChatDispatched(Guid ownerCommandId, string owner) => Write(async (db, now) =>
    {
        var row = await db.ConversationCommands.FindAsync(owner, ownerCommandId)
            ?? throw new PlatformException("NOT_FOUND", 404);
        row.Status = "DISPATCHED";
    });

    public async Task<TaskWorkflowInput> TaskInput(Guid taskId)
    {
        await using var db = await factory.CreateDbContextAsync();
        var task = await db.AgentTasks.SingleAsync(x => x.Id == taskId);
        Rules.Require(task.RootInvocationId is Guid, "ROOT_REQUIRED", 500);
        return new TaskWorkflowInput(task.Id, task.ConversationId, task.RootInvocationId!.Value, task.WallDeadline);
    }

    public Task<ChatAssignment?> ClaimChatExecution(string workload, Guid bootId) => Write(async (db, now) =>
    {
        // Skip WAITING_CHILD/INTERACTION and leased roots; otherwise the oldest stuck row blocks the queue.
        var candidates = await db.Invocations
            .Where(x => x.Capability == "chat.root" && !x.CancelDesired
                && (x.Status == "ACCEPTED" || x.Status == "RUNNING"))
            .OrderBy(x => x.CreatedAt)
            .Take(50)
            .ToListAsync();
        foreach (var inv in candidates)
        {
            var task = await db.AgentTasks.SingleAsync(x => x.Id == inv.TaskId);
            if (task.CancelDesired || States.Terminal(task.Status)) continue;
            if (task.Status is "WAITING_CHILD" or "WAITING_INTERACTION") continue;
            var existing = await db.AgentExecutions.FindAsync(inv.Id);
            if (existing != null && existing.LeaseUntil > now && existing.Status == "LEASED")
                continue;

            await ApplyPendingSteers(db, task, now);
            var resumeJson = await BuildResumeJson(db, task);
            var fence = 1L;
            if (existing != null)
            {
                fence = existing.Fence + 1;
                existing.BootId = bootId;
                existing.Fence = fence;
                existing.LeaseUntil = now.AddSeconds(45);
                existing.Status = "LEASED";
            }
            else
            {
                db.AgentExecutions.Add(new AgentExecutionRow
                {
                    InvocationId = inv.Id,
                    BootId = bootId,
                    Fence = fence,
                    LeaseUntil = now.AddSeconds(45),
                    Status = "LEASED"
                });
            }
            inv.Status = "RUNNING";
            inv.UpdatedAt = now;
            if (task.Status is "ACCEPTED" or "ACTIVE") { task.Status = "ACTIVE"; task.UpdatedAt = now; }
            return new ChatAssignment(inv.Id, task.Id, task.ConversationId, task.DefinitionVersion, "fake-or-configured", fence, task.Goal, resumeJson);
        }
        return null;
    });

    public Task RenewChatExecution(Guid bootId, Guid invocationId, long fence) => Write(async (db, now) =>
    {
        var exec = await db.AgentExecutions.FindAsync(invocationId) ?? throw new PlatformException("NOT_FOUND", 404);
        Rules.Require(exec.BootId == bootId && exec.Fence == fence, "FENCED", 403);
        exec.LeaseUntil = now.AddSeconds(45);
        var inv = await db.Invocations.SingleAsync(x => x.Id == invocationId);
        var task = await db.AgentTasks.SingleAsync(x => x.Id == inv.TaskId);
        if (task.CancelDesired || inv.CancelDesired)
            throw new PlatformException("CANCEL_REQUESTED", 409);
    });

    public Task CompleteChatExecution(Guid bootId, Guid invocationId, long fence, string status, string resultJson, string? assistantText, string? errorCode = null, string? safeMessage = null) => Write(async (db, now) =>
    {
        var exec = await db.AgentExecutions.FindAsync(invocationId) ?? throw new PlatformException("NOT_FOUND", 404);
        Rules.Require(exec.BootId == bootId && exec.Fence == fence, "FENCED", 403);
        var inv = await db.Invocations.SingleAsync(x => x.Id == invocationId);
        var task = await db.AgentTasks.SingleAsync(x => x.Id == inv.TaskId);
        inv.Status = status;
        inv.ResultJson = resultJson;
        inv.UpdatedAt = now;
        exec.Status = status;
        task.Status = status is "SUCCEEDED" or "FAILED" or "CANCELLED" or "NEEDS_ATTENTION" or "UNKNOWN" ? status : task.Status;
        if (States.Terminal(task.Status) || task.Status is "SUCCEEDED" or "FAILED" or "CANCELLED" or "NEEDS_ATTENTION" or "UNKNOWN")
            task.IsActive = false;
        task.UpdatedAt = now;
        var conv = await db.Conversations.SingleAsync(x => x.Id == task.ConversationId);
        if (!string.IsNullOrWhiteSpace(errorCode) || status is "FAILED" or "NEEDS_ATTENTION" or "UNKNOWN")
        {
            var msg = string.IsNullOrWhiteSpace(safeMessage) ? (errorCode ?? status) : safeMessage;
            await EmitConversationEvent(db, conv, now, "AgentError", new
            {
                taskId = task.Id,
                invocationId,
                errorCode = errorCode ?? status,
                safeMessage = msg,
                status
            }, $"agent-error:{invocationId:D}:{errorCode ?? status}");
            if (string.IsNullOrWhiteSpace(assistantText))
                assistantText = msg;
        }
        if (!string.IsNullOrWhiteSpace(assistantText))
        {
            var messageId = Guid.NewGuid();
            db.Messages.Add(new MessageRow
            {
                Id = messageId,
                ConversationId = conv.Id,
                Role = "assistant",
                Content = assistantText,
                TaskId = task.Id,
                CreatedAt = now
            });
            await EmitConversationEvent(db, conv, now, "AssistantMessageCompleted", new { messageId, finalContent = assistantText }, $"assistant-final:{messageId:D}");
        }
        await EmitConversationEvent(db, conv, now, "InvocationCompleted", new { invocationId, status, taskId = task.Id, errorCode }, $"inv-complete:{invocationId:D}");
        await EmitConversationEvent(db, conv, now, "TaskStatusChanged", new { taskId = task.Id, status = task.Status }, $"task-status:{task.Id:D}:{task.Status}:{now.Ticks}");
        conv.UpdatedAt = now;
    });

    public async Task<InvocationSnapshotView?> GetInvocation(Guid invocationId)
    {
        await using var db = await factory.CreateDbContextAsync();
        var inv = await db.Invocations.SingleOrDefaultAsync(x => x.Id == invocationId);
        return inv == null ? null : new InvocationSnapshotView(inv.Id, inv.Status, inv.ResultJson, inv.RunId);
    }

    public Task CreateInteraction(Guid interactionId, Guid taskId, string kind, string payloadJson, string payloadHash, DateTime expiresAt) => Write(async (db, now) =>
    {
        if (await db.InteractionRequests.FindAsync(interactionId) != null) return;
        var task = await db.AgentTasks.SingleAsync(x => x.Id == taskId);
        db.InteractionRequests.Add(new InteractionRequestRow
        {
            Id = interactionId,
            TaskId = taskId,
            Kind = kind,
            PayloadJson = payloadJson,
            PayloadHash = payloadHash,
            Status = "PENDING",
            ExpiresAt = expiresAt,
            DeliveryStatus = "NONE",
            CreatedAt = now
        });
        var conv = await db.Conversations.SingleAsync(x => x.Id == task.ConversationId);
        await EmitConversationEvent(db, conv, now, "InteractionRequested", new { interactionId, kind, safePayload = payloadJson, payloadHash, expiresAt }, $"interaction:{interactionId:D}");
        task.Status = "WAITING_INTERACTION";
        task.UpdatedAt = now;
        // Release root lease so only RespondInteraction can re-claim (T025).
        if (task.RootInvocationId is Guid rootId)
        {
            var root = await db.Invocations.SingleOrDefaultAsync(x => x.Id == rootId);
            if (root != null && !States.Terminal(root.Status))
            {
                root.Status = "ACCEPTED";
                root.UpdatedAt = now;
            }
            var exec = await db.AgentExecutions.FindAsync(rootId);
            if (exec != null)
            {
                exec.Status = "SUSPENDED";
                exec.LeaseUntil = now;
            }
        }
        conv.UpdatedAt = now;
    });

    public Task SuspendExecution(Guid bootId, Guid invocationId, long fence, string? checkpointId, IReadOnlyList<string>? dependencyIds) => Write(async (db, now) =>
    {
        var exec = await db.AgentExecutions.FindAsync(invocationId) ?? throw new PlatformException("NOT_FOUND", 404);
        Rules.Require(exec.BootId == bootId && exec.Fence == fence, "FENCED", 403);
        var inv = await db.Invocations.SingleAsync(x => x.Id == invocationId);
        Rules.Require(inv.Capability == "chat.root", "INVALID_SUSPEND", 400);
        var task = await db.AgentTasks.SingleAsync(x => x.Id == inv.TaskId);
        Rules.Require(!States.Terminal(task.Status), "TASK_TERMINAL", 409);
        exec.Status = "SUSPENDED";
        exec.LeaseUntil = now;
        inv.Status = "ACCEPTED";
        inv.UpdatedAt = now;
        task.Status = "WAITING_CHILD";
        task.IsActive = true;
        task.UpdatedAt = now;
        var conv = await db.Conversations.SingleAsync(x => x.Id == task.ConversationId);
        await EmitConversationEvent(db, conv, now, "TaskStatusChanged", new
        {
            taskId = task.Id,
            status = task.Status,
            checkpointId,
            dependencyIds
        }, $"task-suspend:{task.Id:D}:{checkpointId}:{now.Ticks}");
        conv.UpdatedAt = now;
    });

    public Task ProjectRunStatus(Guid runId, string status, string? errorCode) => Write(async (db, now) =>
    {
        var inv = await db.Invocations.FirstOrDefaultAsync(x => x.RunId == runId);
        if (inv == null) return;
        var task = await db.AgentTasks.SingleOrDefaultAsync(x => x.Id == inv.TaskId);
        if (task == null) return;
        var conv = await db.Conversations.SingleAsync(x => x.Id == task.ConversationId);
        var childTerminal = States.Terminal(status) || status is "NEEDS_ATTENTION" or "UNKNOWN";
        if (!childTerminal)
        {
            await EmitConversationEvent(db, conv, now, "AgentProgress", new { taskId = task.Id, invocationId = inv.Id, safeText = $"Run {status}" }, $"run-progress:{runId:D}:{status}:{now.Ticks}");
            if (task.Status is "ACTIVE" or "ACCEPTED")
            {
                task.Status = "WAITING_CHILD";
                task.UpdatedAt = now;
            }
            conv.UpdatedAt = now;
            return;
        }

        var checks = new[] { new { name = "run", outcome = status == "FAILED" ? "failed" : "not_run", explanation = "Projected from Run status; OpenCode check evidence not re-fetched here" } };
        inv.Status = status == "UNKNOWN" ? "UNKNOWN" : status;
        inv.ResultJson = Wire.Serialize(new { runId, status, errorCode, checks });
        inv.UpdatedAt = now;
        // Child completion must not terminalize the dialog Task — only wake workflow.
        if (!States.Terminal(task.Status))
        {
            task.Status = "WAITING_CHILD";
            task.IsActive = true;
            task.UpdatedAt = now;
        }
        await EmitConversationEvent(db, conv, now, "InvocationCompleted", new
        {
            invocationId = inv.Id,
            runId,
            status,
            errorCode,
            checks
        }, $"run-proj:{runId:D}:{status}");
        await EmitConversationEvent(db, conv, now, "TaskStatusChanged", new { taskId = task.Id, status = task.Status }, $"task-waiting-child:{runId:D}:{task.Status}");
        var wakeupId = DeterministicGuid(task.Id, "child-done", runId.ToString("D"));
        if (await db.ConversationCommands.FindAsync(conv.OwnerSubject, wakeupId) == null)
        {
            db.ConversationCommands.Add(new ConversationCommandRow
            {
                CommandId = wakeupId,
                OwnerSubject = conv.OwnerSubject,
                ConversationId = conv.Id,
                RequestHash = Wire.Hash($"child-done:{runId:D}:{status}"),
                AcceptedResourceId = task.Id,
                Status = "PENDING",
                Kind = "SIGNAL_CHILD_COMPLETED",
                CreatedAt = now
            });
        }
        conv.UpdatedAt = now;
    });

    public Task ReconcileTaskChildren(Guid taskId) => Write(async (db, now) =>
    {
        var task = await db.AgentTasks.SingleOrDefaultAsync(x => x.Id == taskId);
        if (task == null || States.Terminal(task.Status)) return;
        if (task.Status == "WAITING_INTERACTION") return;
        var children = await db.Invocations
            .Where(x => x.TaskId == taskId && x.Capability != "chat.root")
            .ToListAsync();
        var unfinished = children.Where(c => c.Status is "ACCEPTED" or "RUNNING").ToList();
        if (unfinished.Count > 0)
        {
            task.Status = "WAITING_CHILD";
            task.IsActive = true;
            task.UpdatedAt = now;
            return;
        }
        await ApplyPendingSteers(db, task, now);
        var conv = await db.Conversations.SingleAsync(x => x.Id == task.ConversationId);
        await RequeueRootClaim(db, task, conv, now, $"task-reconcile:{task.Id:D}", enqueueSignal: false);
    });

    public async Task<IReadOnlyList<(Guid RunId, string Owner)>> ListLinkedRunsForAbort(Guid taskId)
    {
        await using var db = await factory.CreateDbContextAsync();
        var task = await db.AgentTasks.SingleOrDefaultAsync(x => x.Id == taskId);
        if (task == null) return [];
        var conv = await db.Conversations.SingleAsync(x => x.Id == task.ConversationId);
        var runs = await db.Invocations
            .Where(x => x.TaskId == taskId && x.RunId != null)
            .Select(x => x.RunId!.Value)
            .Distinct()
            .ToListAsync();
        return runs.Select(r => (r, conv.OwnerSubject)).ToList();
    }

    static async Task ApplyPendingSteers(PlatformDb db, AgentTaskRow task, DateTime now)
    {
        var pending = await db.TaskInputs
            .Where(x => x.TaskId == task.Id && x.Disposition == "steer_pending" && x.AppliedAt == null)
            .OrderBy(x => x.Revision)
            .ThenBy(x => x.Id)
            .ToListAsync();
        if (pending.Count == 0) return;
        foreach (var input in pending)
        {
            var msg = await db.Messages.SingleOrDefaultAsync(x => x.Id == input.MessageId);
            if (msg != null && !string.IsNullOrWhiteSpace(msg.Content))
                task.Goal = msg.Content.Trim();
            task.GoalRevision += 1;
            input.Revision = task.GoalRevision;
            input.AppliedAt = now;
            input.Disposition = "steer_applied";
            var conv = await db.Conversations.SingleAsync(x => x.Id == task.ConversationId);
            await EmitConversationEvent(db, conv, now, "InputApplied", new
            {
                taskId = task.Id,
                messageId = input.MessageId,
                revision = task.GoalRevision,
                disposition = "steer_applied"
            }, $"steer-applied:{input.Id:D}");
        }
        task.UpdatedAt = now;
    }

    static async Task<string> BuildResumeJson(PlatformDb db, AgentTaskRow task)
    {
        var children = await db.Invocations
            .Where(x => x.TaskId == task.Id && x.Capability != "chat.root" && x.ResultJson != null)
            .OrderByDescending(x => x.UpdatedAt)
            .Take(5)
            .ToListAsync();
        var interactionIds = await db.InteractionRequests.Where(i => i.TaskId == task.Id).Select(i => i.Id).ToListAsync();
        var decisions = interactionIds.Count == 0
            ? []
            : await db.InteractionDecisions
                .Where(d => interactionIds.Contains(d.InteractionId))
                .OrderByDescending(d => d.DecidedAt)
                .Take(3)
                .ToListAsync();
        if (children.Count == 0 && decisions.Count == 0) return "";
        return Wire.Serialize(new
        {
            children = children.Select(x => new { invocationId = x.Id, capability = x.Capability, status = x.Status, runId = x.RunId, resultJson = x.ResultJson }),
            decisions = decisions.Select(d => new { interactionId = d.InteractionId, decision = d.Decision, decidedAt = d.DecidedAt })
        });
    }

    static async Task RequeueRootClaim(PlatformDb db, AgentTaskRow task, ConversationRow conv, DateTime now, string sourceKey, bool enqueueSignal = true)
    {
        if (States.Terminal(task.Status)) return;
        if (task.RootInvocationId is Guid rootId)
        {
            var root = await db.Invocations.SingleAsync(x => x.Id == rootId);
            if (!States.Terminal(root.Status))
            {
                root.Status = "ACCEPTED";
                root.UpdatedAt = now;
                var exec = await db.AgentExecutions.FindAsync(rootId);
                if (exec != null)
                {
                    exec.Status = "RELEASED";
                    exec.LeaseUntil = now;
                }
            }
        }
        task.Status = "ACTIVE";
        task.IsActive = true;
        task.UpdatedAt = now;
        await EmitConversationEvent(db, conv, now, "TaskStatusChanged", new { taskId = task.Id, status = task.Status }, $"{sourceKey}:status");
        if (enqueueSignal)
        {
            var wakeupId = DeterministicGuid(task.Id, "wake", sourceKey);
            if (await db.ConversationCommands.FindAsync(conv.OwnerSubject, wakeupId) == null)
            {
                db.ConversationCommands.Add(new ConversationCommandRow
                {
                    CommandId = wakeupId,
                    OwnerSubject = conv.OwnerSubject,
                    ConversationId = conv.Id,
                    RequestHash = Wire.Hash($"wake:{sourceKey}"),
                    AcceptedResourceId = task.Id,
                    Status = "PENDING",
                    Kind = "SIGNAL_CHILD_COMPLETED",
                    CreatedAt = now
                });
            }
        }
        conv.UpdatedAt = now;
    }

    static bool IsStatusQuery(string text)
    {
        var t = text.Trim().ToLowerInvariant();
        return t is "статус" or "status" or "?" or "как дела";
    }

    static ConversationView View(ConversationRow row) =>
        new(row.Id, row.Title, row.CreatedAt, row.UpdatedAt, row.NextEventSequence.ToString());

    static async Task<ConversationRow> OwnedConversation(PlatformDb db, string owner, Guid id) =>
        await db.Conversations.SingleOrDefaultAsync(x => x.Id == id && x.OwnerSubject == owner)
            ?? throw new PlatformException("NOT_FOUND", 404);

    static async Task EmitConversationEvent(PlatformDb db, ConversationRow conv, DateTime now, string kind, object payload, string sourceKey)
    {
        if (await db.ConversationEvents.AnyAsync(x => x.SourceEventKey == sourceKey)) return;
        conv.NextEventSequence += 1;
        db.ConversationEvents.Add(new ConversationEventRow
        {
            ConversationId = conv.Id,
            Sequence = conv.NextEventSequence,
            EventId = Guid.NewGuid(),
            Kind = kind,
            Payload = Wire.Serialize(payload),
            SourceEventKey = sourceKey,
            CreatedAt = now
        });
    }

    static Guid DeterministicGuid(Guid taskId, string checkpointId, string toolCallId)
    {
        var bytes = System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes($"{taskId:D}:{checkpointId}:{toolCallId}"));
        Span<byte> g = stackalloc byte[16];
        bytes.AsSpan(0, 16).CopyTo(g);
        g[7] = (byte)((g[7] & 0x0f) | 0x40);
        g[8] = (byte)((g[8] & 0x3f) | 0x80);
        return new Guid(g);
    }

    async Task Write(Func<PlatformDb, DateTime, Task> action)
    {
        await using var db = await factory.CreateDbContextAsync();
        await using var tx = await db.Database.BeginTransactionAsync();
        await action(db, DateTime.UtcNow);
        await db.SaveChangesAsync();
        await tx.CommitAsync();
    }

    async Task<T> Write<T>(Func<PlatformDb, DateTime, Task<T>> action)
    {
        await using var db = await factory.CreateDbContextAsync();
        await using var tx = await db.Database.BeginTransactionAsync();
        var result = await action(db, DateTime.UtcNow);
        await db.SaveChangesAsync();
        await tx.CommitAsync();
        return result;
    }
}
