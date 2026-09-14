# Temporal execution contract

## Ownership

Temporal owns Run orchestration. SQL owns durable inbound commands, operation reservation/execution receipt и artifacts. Это не два конкурирующих Run scheduler: SQL claim обслуживает единственный operation, созданный workflow activity.

## Durable Start и dispatcher

API commit MSSQL → HTTP 202 ack=PERSISTED. Background dispatcher claim Commands с коротким lease и вызывает Temporal Start с WorkflowId `run-{RunId}`. Reuse policy запрещает повтор закрытого workflow; при AlreadyStarted проверяется соответствие исходному Run, затем команда DISPATCHED. Потеря ответа Temporal устраняется повтором того же ID, не новым workflow. Отказ Temporal оставляет команду pending с bounded backoff и ошибкой в diagnostics.

API не держит SQL transaction во время Temporal RPC. Dispatcher имеет несколько replicas, SQL lease защищает эффективность, ID защищает корректность.

## RunWorkflow (C#)

Input: RunId, RepositoryId, BaseCommit, DefinitionVersion, OperationId и deadline; prompt берётся activity из SQL, не многократно пишется в history. Result: terminal status + artifact IDs.

1. Publish STARTING идемпотентной activity.
2. EnsureOperation(RunId, OperationId) activity: insert-if-absent. OperationId выбирается до workflow start и стабилен во всех retries.
3. PollOperation activity читает компактный status/result references каждые 5 секунд через durable timer. Вне poll нет I/O в workflow. При queue/running изменении публикуется проекция.
4. Signal RequestCancel(CommandId) устанавливает workflow flag с dedup. Workflow вызывает SetOperationCancel activity и продолжает ждать известного исхода. SQL desired flag установлен уже в ingress, поэтому claim/start не обходят pending cancel.
5. SUCCEEDED/FAILED/CANCELLED/UNKNOWN преобразуются в соответствующий Run terminal (UNKNOWN → NEEDS_ATTENTION), PublishTerminal activity, return.
6. Deadline 20 минут: RequestAbort activity; grace 30 секунд. При неизвестном исходе → operation UNKNOWN и Run NEEDS_ATTENTION. При известном abort → CANCELLED с причиной DEADLINE. Не выдавать FAILED как доказательство отсутствия эффектов.

Poll каждые 5 s даёт ≤240 итераций для 20-минутного Run; измерить history size и установить guard. Continue-As-New и бесконечные workflows в MVP не нужны. Signals содержат только ID/команды, tokens никогда не попадают в workflow history.

Activities имеют конечные timeouts/retry backoff и idempotency: SQL transient retry допустим. EnsureOperation никогда не отправляет prompt непосредственно. PollOperation никогда не перезапускает runner. Если SQL временно недоступен, workflow не придумывает статус; инфраструктурное ожидание видно отдельно и проверяется recovery test.

## Cancel dispatcher

Cancel command ссылается на существующий owned Run. Пока Start не dispatched, cancel сохраняется и предотвращает prompt через SQL guard. После известного WorkflowId dispatcher доставляет signal с CommandId и отмечает DISPATCHED. Повтор signal безопасен. Для завершённого Run команда получает PROCESSED с уже завершённым исходом; completion не отменяется задним числом. Reconciler не должен бесконечно signal missing workflow после terminal retention: опирается на Runs/Commands.

## Runner lifetime

Heartbeat 5 s, lease 45 s (SQL server time), runner renew timeout safety margin 10 s. Если runner не смог подтвердить renewal до локального безопасного deadline, он пытается abort и не начинает новых действий. Это не гарантирует физической остановки уже выполняющегося model request. Reaper переводит просроченный operation в UNKNOWN. Нового исполнителя ему не назначают.

Reconnect транспорта не отменяет operation. Same BootId/Fence может продолжить, пока lease действителен. После UNKNOWN stale messages отвергаются. Контрольный тест должен оборвать канал меньше чем на 45 s и проверить отсутствие второго prompt; длительный partition должен дать NEEDS_ATTENTION.

## Completion/cancellation race

Первый committed operation terminal побеждает. Если SUCCEEDED раньше обработки abort, workflow возвращает SUCCEEDED с признаком поздней отмены. Если abort подтверждён раньше completion, subsequent completion отвергается. CANCEL_REQUESTED UI не означает, что уже совершённая локальная работа исчезла.

## Failure matrix

| Failure | Action |
| --- | --- |
| API dies | Reconnect to another replica, SQL cursor/lease |
| Temporal worker dies | Replay workflow; poll same operation |
| Temporal service unavailable | Commands остаются в SQL, начатый runner может закончить в SQL |
| SQL unavailable | No durable ACK/claim/renew; bounded buffers, eventual abort/UNKNOWN |
| OpenCode HTTP response lost | Query same session; no blind prompt resend |
| Python/OpenCode process lost | UNKNOWN → NEEDS_ATTENTION |
| Completion SQL committed, ACK lost | Duplicate returns committed result |

## Mandatory workflow tests

Replay captured history, lost activity completion for EnsureOperation/PublishTerminal, duplicate signal, cancellation before start, deadline, terminal race, restart worker with running fake operation. Использовать Temporal testing support, а SQL transaction guarantees проверять отдельными integration tests.
