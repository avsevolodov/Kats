# MVP contracts

`runner.proto` — proposed normative wire contract для C#↔Python. Реализатор генерирует stubs и проводит cross-language test. `openapi.yaml` — REST contract. `browser-stream.md` — WebSocket JSON framing.

Protocol version 1. UUID передаются canonical lowercase строкой, timestamps epoch milliseconds UTC, sequence/fence — 64-bit. JSON browser cursor/fence передаются decimal string, чтобы не зависеть от точности JavaScript number. SQL и C# используют bigint/long.

Runner WorkChannel long-lived duplex: Hello первым, затем Claim/Resume, Begin, Heartbeat, Output, Complete. Workload identity из mTLS, BootId генерируется при старте Python процесса и не восстанавливается на другом процессе. Gateway не доверяет self-declared identity.

Assignment выдаётся только после committed claim. Begin переводит operation в RUNNING и разрешает prompt после AckPersisted. Начало prompt не равно записи Begin: если процесс упал между ними, всё равно UNKNOWN, не автоматический retry.

Output и Complete используют одну последовательность ProducerSequence; Begin/Heartbeat/Resume имеют MessageId, но не потребляют producer sequence. Повтор message с тем же ID и изменённым payload — конфликт. Lease и state проверяются на каждом изменяющем сообщении, включая HTTP/DB error recovery.

Ack для Output/Complete выдаётся после SQL commit, с last accepted producer sequence и last run event sequence. Runner хранит неACKнутый batch в bounded памяти и повторяет при reconnect. Исчерпание памяти приводит к прекращению presentation forwarding, затем явному OutputTruncated; control/completion имеют отдельный резерв. Durable result нельзя выбросить как preview.

Нельзя отбрасывать уже получивший ProducerSequence неподтверждённый batch: это создаст непреодолимый разрыв. Отбрасывать/coalesce можно только ещё не пронумерованные preview. Сначала доставить предыдущие номера, затем OutputTruncated/Complete. Зависший SQL ограничивает локальное ожидание lease safety deadline.

Committed receipt идентичного Complete может быть ACKнут после terminal/lease expiry при прежних workload/BootId/Fence: это чтение сохранённого исхода, не новое действие. При Resume terminal snapshot не побуждает к новому prompt.

Server Error: INVALID_ARGUMENT, UNAUTHENTICATED, PERMISSION_DENIED, CONFLICT, EXPECTED_SEQUENCE, FENCED, LEASE_EXPIRED, PAYLOAD_TOO_LARGE, UNAVAILABLE. Error.retryable разрешает повтор доставки, не повтор prompt. gRPC transport max receive/send 6 MiB; application limits ниже. Compression не позволяет обойти uncompressed size limits.

Публикация output не является tool invocation. OpenCode model/tool calls внутри operation не получают отдельных durable guarantees. Полный AgentTransport Envelope концепта отложен; MVP proto не надо расширять десятками неиспользуемых сообщений.

Result hash: lowercase hex SHA-256(concat(len(summary), summary, len(patch), patch, len(base_commit), base_commit)); len — unsigned 64-bit big-endian byte length, text — UTF-8 без BOM. PayloadHash для dedup охватывает весь typed message, включая outcome/error, по закреплённой canonical JSON схеме с фиксированным порядком полей; golden vectors одинаковы в C# и Python. Result hash не используется вместо полного payload hash.
