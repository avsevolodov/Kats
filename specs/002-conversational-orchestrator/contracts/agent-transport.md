# AgentTransport v1 — нормативная семантика для 002

Это новый контракт agent.v1. Исполняемый protobuf и generated stubs — результат T007.
runner.v1 не переименовывается; coding adapter переводит вызов в baseline Run.
Transport: один outbound gRPC bidi AgentChannel на Python process. Internal persistence RPC использует ту же workload authentication.
Внешние действия не отправляются direct из Python в Git/дочерний runner.

## Envelope

| Поле | Тип | Правило |
| --- | --- | --- |
| protocolVersion | uint32 | 1, несовместимое значение отвергается |
| messageId | UUID | Dedup доставки |
| correlationId | UUID optional | ID запроса, которому соответствует ответ |
| conversationId / taskId | UUID | Scope, проверяется сервером |
| invocationId / parentInvocationId | UUID / optional UUID | Существующие parent связи |
| bootId / fence | UUID / int64 | Для сообщений активного execution |
| streamId / producerSequence | UUID / int64 optional | Только ordered output |
| payload | typed oneof | Не произвольный исполняемый JSON |

Identity извлекается из mTLS, OwnerSubject и authorization scope — из task. Self-declared roles/token metadata не принимаются.
UUID canonical lower-case; UTC epoch milliseconds; int64 в browser JSON — decimal strings.
Контракт версии capability независим от версии transport.

## Сообщения

| Направление | Payload | Смысл |
| --- | --- | --- |
| Agent → Gateway | Hello(version, bootId, supportedDefinitions) | Регистрация; capabilities пересекаются с server allowlist |
| Agent → Gateway | Claim / ResumeExecution | Получить fenced execution или восстановить transport |
| Gateway → Agent | Assignment / NoWork | InvocationId, checkpoint ref, definition/model profile |
| Agent → Gateway | Heartbeat | Продление compute lease |
| Agent → Gateway | EnsureInvocation(intentKey, capability, version, input) | Durable child call; возврат existing child при повторе |
| Gateway → Agent | InvocationAccepted(id, status) | PERSISTED, не execution success |
| Agent → Gateway | GetInvocation(id) | Snapshot и result references |
| Agent → Gateway | OutputBatch | Preview/progress; sequence, payload bounds |
| Agent → Gateway | CreateInteraction(id, kind, payload, expiry) | Durable вопрос/approval |
| Agent → Gateway | Suspend(checkpointId, dependencyIds) | Только после durable checkpoint; race-safe wait |
| Gateway → Agent | Wakeup / CancelRequested | Advisory delivery; authoritative state в SQL |
| Agent → Gateway | Complete(result) | Durable structured root result |
| Gateway → Agent | AckPersisted / Error | Ack только после commit |

User RespondInteraction идёт через REST. Ответ доставляется execution после wakeup/read; OpenCode reply — через legacy bridge.

## Persistence RPC (внутренний)

CheckpointGet(thread, namespace, id?), CheckpointList(cursor, limit),
CheckpointPut(expectedFence, checkpoint, metadata, parent, channelVersions),
CheckpointPutWrites(checkpointId, graphTaskId, writes), ExecutionSuspend(...).
ThreadId равен root InvocationId; namespace принадлежит только текущей definition. Список/чтение ограничены assigned scope.
Checkpoint и pending writes ordering соответствуют pinned adapter API; операции не должны имитировать транзакцию, которой нет в LangGraph.

## Delivery / ACK / replay

MessageId повтор с тем же canonical payload → прежний receipt; изменённый payload → CONFLICT.
Canonical hash: SHA-256 по RFC 8785 canonical JSON нормализованной typed DTO; IDs lower-case, int64 string, absent optionals omitted, без transport retry timestamps. C#/Python golden vectors обязательны.
Invocation dedup не зависит только от MessageId: stable intent key сохраняется между checkpoint replay.
ProducerSequence монотонен внутри StreamId; reconnect того же execution продолжает его. Новый execution создаёт новый StreamId.
ConversationEvent.Sequence — отдельный SQL порядок committed events; не сравнивать sequence разных producers.
Unacked numbered batches нельзя выбрасывать. Coalesce/drop только unnumbered preview; control/result отдельный резерв. OutputTruncated обязателен.
Application frame ≤256 KiB, preview batch ≤8 KiB; крупные artifacts через store API. Checkpoint RPC ≤2 MiB.
При retention gap возвращается HISTORY_EXPIRED с earliest cursor и snapshot reference.

## Errors

INVALID_ARGUMENT, UNAUTHENTICATED, PERMISSION_DENIED, CAPABILITY_UNAVAILABLE,
CONTRACT_VERSION_UNSUPPORTED, CONFLICT, FENCED, LEASE_EXPIRED, EXPECTED_SEQUENCE,
BUDGET_EXCEEDED, RESULT_TOO_LARGE, HISTORY_EXPIRED, UNAVAILABLE.
retryable означает повтор безопасной доставки/чтения. Не означает разрешение повторить внешний effect.

## Result

status + summary + artifactRefs + checks[] + unresolvedQuestions[] + errorCode?.
checks: name, outcome passed/failed/not_run, evidenceRef?, explanation?.
SUCCEEDED coding invocation требует persisted baseline result; отсутствие проверок допускается только явно checks=not_run, а не выдуманным passed.
