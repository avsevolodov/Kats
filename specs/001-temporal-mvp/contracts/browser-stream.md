# Browser WebSocket contract v1

Endpoint `/api/v1/stream`, same-origin authenticated cookie; check Origin allowlist. REST mutation endpoints require antiforgery token. No bearer tokens in query strings.

One subscription per socket in MVP. Client can issue Subscribe, Cancel, Confirm, Ping. Start через REST. Это прикладной duplex канал, а не SSE; сервер передаёт события, клиент — управление.

```json
{"type":"subscribe","protocolVersion":1,"runId":"00000000-0000-0000-0000-000000000001","afterSequence":"15"}
```

После owner authorization сервер передаёт subscribed с snapshot из согласованной read transaction:

```json
{"type":"subscribed","runId":"00000000-0000-0000-0000-000000000001","earliestAvailableSequence":"1","highWatermark":"18","status":"RUNNING"}
```

Затем events с Sequence >15. HighWatermark не сдвигает клиентский cursor автоматически: cursor сдвигается только после применения каждого события. Snapshot статуса не заменяет пропущенный вывод.

```json
{"type":"event","runId":"00000000-0000-0000-0000-000000000001","sequence":"16","kind":"OutputBatch","payload":{"text":"Updating parser..."}}
```

```json
{"type":"cancel","commandId":"00000000-0000-0000-0000-000000000002","runId":"00000000-0000-0000-0000-000000000001"}
```

Cancel использует тот же application handler, dedup и authorization, что REST. Ack `persisted` возвращается после command inbox commit; false completion не сообщается. WS origin + authenticated connection проверяются для всех commands; не принимать RunId вне разрешённой подписки.

```json
{"type":"confirm","commandId":"00000000-0000-0000-0000-000000000003","runId":"00000000-0000-0000-0000-000000000001","requestId":"perm_1","decision":"once"}
```

Confirm: `decision` = `once`|`always`|`reject` для permission; `answer`|`reject` для question (`answers` — JSON string[][] при `answer`). Тот же owner/dedup/antiforgery (REST), что Cancel.

При устаревшем cursor — `cursor_expired` с earliestAvailableSequence и artifact links; клиент явно показывает неполную историю и переподписывается после согласованного сброса. При cursor выше highWatermark — INVALID_CURSOR. Пустой/новый UI начинает с 0.

Ограничение: page ≤100 событий, server outbound buffer ≤256 KiB. Slow consumer: закрытие с кодом 1013 и reconnect; последнее применённое sequence сохраняется клиентом. Если backlog >лимита буфера, чтение SQL приостанавливается, события не теряются, пока сохранены retention.

Разрешённые event kinds: RunAccepted, RunStatusChanged, OperationStarted, OutputBatch, OutputTruncated, CancelRequested, ConfirmationRequired, ConfirmationResolved, OperationCompleted, RunCompleted. Текст всегда рендерится escaped; Markdown/HTML агента не исполняется. Payload ConfirmationRequired: `{ requestId, kind, payload }`; ConfirmationResolved: `{ requestId, decision, status }`.

Cookie expiry/revocation: сервер периодически проверяет сессию и закрывает socket при истечении/отзыве; reconnect снова авторизуется. API не принимает OwnerSubject из JSON.
