# Chat REST API и browser stream

Нормативный контракт 002; OpenAPI и server DTO генерируются/сверяются в T006. Prefix /api/v2.
Auth: существующая OIDC cookie + antiforgery для мутаций; OwnerSubject из server principal.
UUID строки; cursors/int64 decimal strings; timestamp RFC3339 UTC.
Unknown/inaccessible owned resource → 404. Нет body поля owner или permissions.

## Endpoints

| Method / route | Request | Response |
| --- | --- | --- |
| POST /conversations | commandId, title? | 201: conversationId, createdAt |
| GET /conversations?cursor=&limit= | limit 1..100 | items[], nextCursor |
| GET /conversations/{id} | — | conversation, activeTask?, pendingInteractions[], highWatermark |
| POST /conversations/{id}/messages | commandId, text, replyToInteractionId?, contextHints? | 202: messageId, taskId?, disposition, ack=PERSISTED |
| GET /conversations/{id}/messages?cursor=&limit= | — | items[], nextCursor |
| GET /conversations/{id}/events?afterSequence=&limit= | — | items[], highWatermark, earliestAvailableSequence, hasMore |
| GET /tasks/{id} | — | task status, revision, child summaries, artifacts, input dispositions |
| POST /tasks/{id}/cancel | commandId | 202: commandId, taskId, ack=PERSISTED |
| POST /interactions/{id}/responses | commandId, payloadHash, decision, answers? | 202: interactionId, decisionStatus, deliveryStatus |
| GET /invocations/{id} | — | capability, status, progress, result? |
| GET /artifacts/{id} | — | authorized download либо expiry error |

contextHints — только подсказки resource IDs/URLs из allowlist, проверяются сервером. Полный произвольный URL не даёт разрешение fetch.
В первой поставке attachments — ссылки на существующие authorized artifacts. Загрузка произвольных файлов отложена.

disposition: new_task, queued, steer_pending, interaction_response, status_query.
Первый pending message становится new_task транзакционно. Status query не запускает параллельный граф; UI показывает snapshot немедленно.
Conversation snapshot включает highWatermark, согласованный с состоянием через SQL snapshot transaction. Live после него читает events > highWatermark.

## Response examples

```json
{
  "commandId": "10000000-0000-0000-0000-000000000001",
  "text": "В Kats после переподключения пропадает прогресс. Подготовь исправление."
}
```

```json
{
  "messageId": "20000000-0000-0000-0000-000000000001",
  "taskId": "30000000-0000-0000-0000-000000000001",
  "disposition": "new_task",
  "ack": "PERSISTED"
}
```

Approval decision once/reject; clarification answer/reject. answers — массив ответов по questionId, соответствующий сохранённой форме. payloadHash связывает решение с показанным запросом.
Ответ на clarification текстом с replyToInteractionId использует ту же транзакцию и validation, что /responses.
Несколько pending interactions: свободное «да» не трактуется как blanket approval.

Errors: 400 invalid input, 401 unauthenticated, 404 not found, 409 duplicate conflict/stale interaction, 410 expired artifact/history, 413 payload too large, 429 budget/rate, 503 transient unavailable.
Идентичный повтор команды возвращает исходный receipt; для completed response допускается 200.

## WebSocket /api/v2/stream

Существующий browser auth/origin/token expiry контроль сохраняется. Открытие stream не стартует task.
Client: Subscribe(conversationId, afterSequence).
Server: EventBatch(items, highWatermark), CaughtUp(cursor), HistoryExpired(earliest, snapshotUrl), Error.
Reconnect: snapshot при первом входе; дальше persisted cursor. При пропуске sequence перечитать REST. REST polling fallback с теми же cursors.
Expired auth закрывает stream; после reauth re-subscribe, не resubmit message.

## Event kinds

| Kind | Payload |
| --- | --- |
| MessageAccepted | messageId, disposition |
| TaskStatusChanged | taskId, status, reason? |
| ContextSelected | taskId, repositoryId, baseCommit, evidenceRefs |
| InvocationStarted / InvocationCompleted | invocationId, parentId, capability, status, resultRefs? |
| AgentProgress | taskId, invocationId, safeText |
| AssistantMessageDelta | messageId, generationId, text |
| AssistantGenerationInterrupted | messageId, generationId |
| AssistantMessageCompleted | messageId, finalContent |
| InteractionRequested | interactionId, kind, safePayload, expiresAt |
| InteractionDecided / InteractionDeliveryChanged | interactionId, status |
| InputApplied | messageId, taskRevision |
| ArtifactAvailable | artifactId, kind, expiresAt |
| OutputTruncated | scopeId, reason |

Delta только presentation. Completed message authoritative; UI заменяет draft итогом по MessageId. Повтор LLM после crash создаёт новый generationId и явно закрывает старый draft.
Raw chain-of-thought, secrets, неподготовленный HTML и полный tool payload в UI не отправляются.
