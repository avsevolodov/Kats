# Модель данных

Логическая схема; исполняемые EF/SQL migrations создаются T005–T008 после аудита истории миграций. C# domain name AgentTask избегает конфликта с System.Threading.Tasks.Task.

| Таблица | Ключ и важные поля |
| --- | --- |
| Conversations | Id UUID, OwnerSubject, Title, CreatedAt, UpdatedAt, NextEventSequence bigint, SummaryCursor bigint, RowVersion |
| Messages | Id UUID, ConversationId FK, Role, Content, TaskId nullable FK, SourceKey, CreatedAt, ReplyToInteractionId nullable |
| ConversationCommands | CommandId, OwnerSubject, ConversationId, RequestHash, AcceptedResourceId, Status, DispatchLease |
| AgentTasks | Id UUID, ConversationId FK, Goal, GoalRevision, Status, RootInvocationId, WorkflowId, WallDeadline, CancelDesired, DefinitionVersion |
| TaskInputs | Id, TaskId FK, MessageId unique FK, Revision, Disposition, AppliedAt nullable |
| Invocations | Id UUID, TaskId FK, ParentId nullable FK, Kind agent/tool, Capability, Version, RequestHash, Status, RunId nullable, ResultRef nullable, CancelDesired |
| DispatchIntents | TaskId, CheckpointId, GraphTaskPath, ToolCallId, InvocationId, InputHash |
| AgentExecutions | InvocationId, BootId, Fence bigint, LeaseUntil, CheckpointId, Status |
| InteractionRequests | Id UUID, TaskId, OriginInvocationId, ExternalRequestId nullable, Kind, Payload, PayloadHash, Status, ExpiresAt, DeliveryStatus |
| InteractionDecisions | InteractionId unique FK, CommandId, Decision, AnswersJson nullable, ActorSubject, DecidedAt, DecisionHash |
| ContextBindings | Id, TaskId, RepositoryId, BaseCommit, EvidenceRefs, CatalogVersion, SelectedAt, TaskRevision |
| RepositoryMetadata | RepositoryId FK, Description, AliasesJson, ServiceNamesJson, ComponentsJson, DefaultRef, SourceRefs, UpdatedAt, CatalogVersion |
| RepositoryAccess | RepositoryId, PrincipalKind user/group, PrincipalId, Action read/run/admin |
| GraphCheckpoints | ThreadId, Namespace, CheckpointId, ParentCheckpointId, DefinitionVersion, CodecVersion, Payload, Metadata, CreatedAt |
| GraphPendingWrites | ThreadId, Namespace, CheckpointId, GraphTaskId, WriteIndex, Channel, Value |
| ConversationEvents | ConversationId, Sequence bigint, EventId UUID, TaskId nullable, InvocationId nullable, Kind, Payload, SourceEventKey unique, CreatedAt |
| ModelAttempts | Id, TaskId, CheckpointId, ModelProfile, StartedAt, CompletedAt, Outcome, Usage |
| Artifacts | Используется baseline store; scope/owner проверяются через Task/Invocation/Run |

## Ограничения и транзакции

- Unique (OwnerSubject, CommandId) и сохранённый request hash. Повтор возвращает исходный ресурс, иной payload → 409.
- Unique filtered ConversationId по IsActive=1 в AgentTasks. State transition обновляет Status и IsActive в одной транзакции.
- Unique DispatchIntents(TaskId, CheckpointId, GraphTaskPath, ToolCallId). Повтор ID с другим InputHash — конфликт.
- Unique Invocations.RunId where not null; coding adapter использует заранее сохранённый RunId/CommandId.
- ParentId обязан ссылаться на invocation той же Task; циклы запрещены, parent должен существовать.
- AgentExecutions write требует текущие BootId/Fence/lease. Старая реплика не пишет checkpoint и не отправляет intent.
- GraphCheckpoints immutable. PendingWrites unique по composite key, идентичный повтор допустим, иной payload — конфликт.
- Запись child result, terminal invocation и outbox notification атомарна.
- Запись сообщения/решения и соответствующего события атомарна.
- Сохранённое approval decision не означает delivery applied.
- Run terminal отражается в invocation идемпотентно после чтения authoritative результата.
- Conversation Sequence выделяется внутри SQL транзакции с блокировкой строки conversation; rolled-back номера не выдаются клиенту.
- Projector source key предотвращает дубли при повторном переносе RunEvent в ConversationEvent.
- ACL проверяется при поиске, чтении источника, вызове и загрузке артефакта; каталог не отдаёт кандидатов до фильтрации доступа.

## Checkpoint payload

Graph state содержит messages/summary cursor, plan, input revision, references, pending tool calls и interaction IDs. Не содержит Git credentials, bearer tokens или приватный ключ.
C# рассматривает graph payload как ограниченные сериализованные данные. Семантика channels/versions остаётся в adapter LangGraph.
Нельзя подменять полноценный checkpointer таблицей только с последним текстом сообщений.

## Retention и бюджеты

Исходные значения: conversation/messages/events 30 дней после последней активности; checkpoints не удалять у активной task, после terminal 7 дней; artifacts — baseline 7 дней.
UI показывает artifact expiry отдельно от срока жизни диалога.
Checkpoint ≤2 MiB; суммарный checkpoint budget task ≤64 MiB, pending writes включены. При необходимости compaction допускается только с сохранением reachable parent/pending references; иначе явный limit error.
После pruning detailed graph сохраняется terminal result и idempotency tombstones. Tombstones живут не меньше максимального command retry/retention окна (30 дней); старые команды вне окна отвергаются, а не создают новые задачи.
Event cursor до EarliestAvailableSequence возвращает HISTORY_EXPIRED и snapshot route.
