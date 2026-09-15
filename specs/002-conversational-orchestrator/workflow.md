# Выполнение, ожидания и recovery

## Start

1. API authorizes owner, принимает Message + CommandId, транзакционно сохраняет сообщение, task либо queued TaskInput, событие и inbox.
2. HTTP 202 означает PERSISTED. Оно не означает начало LLM.
3. Dispatcher стартует TaskWorkflow с ID task-{TaskId}. Уже существующий workflow сверяется с task, повтор не создаёт новый.
4. Workflow activity создаёт root Chat invocation, очередной AgentExecution и публикует task ACTIVE.
5. Python claim получает fenced execution, загружает checkpoint либо init context, выполняет шаг графа.

## Dispatch child

1. LLM output с tool calls сохраняется checkpoint; ещё нет внешнего действия.
2. Adapter вызывает EnsureInvocation с CheckpointId, GraphTaskPath и ToolCallId.
3. SQL атомарно сохраняет DispatchIntent, Invocation и command для handler. Ack после commit.
4. coding handler обеспечивает один Run через stable CommandId/RunId. Созданный Run использует baseline workflow и runner.
5. Граф сохраняет WAITING_CHILD; execution lease освобождается только после checkpoint commit.
6. Terminal child result в SQL создаёт wakeup. Dispatcher schedule/claim одного execution; graph читает result по InvocationId.
7. Повтор wakeup безопасен. Checkpoint хранит consumed result IDs; tool результат не дублируется в messages.

Race «child завершился до записи WAITING_CHILD»: при переходе wait проверяется terminal child и pending wakeup в той же транзакции. Periodic reconciler находит waiting графы с готовыми dependencies.

*Реализация code/unit (2026-09-15):* `SIGNAL_CHILD_COMPLETED` + `ReconcileTaskChildren` + Suspend; live Temporal/SQL — T029. Consume child result на втором claim — T028.

## Статусы

Task: ACCEPTED → ACTIVE ↔ WAITING_USER/WAITING_CHILD → SUCCEEDED | FAILED | CANCELLED | NEEDS_ATTENTION.
CANCEL_REQUESTED — промежуточное состояние. Task terminal публикует только TaskWorkflow.
Invocation: ACCEPTED → RUNNING ↔ WAITING → SUCCEEDED | FAILED | CANCELLED | UNKNOWN.
Invocation UNKNOWN отображается для task как NEEDS_ATTENTION; ответ агента может объяснить причину, но не превращает исход в SUCCEEDED.

## Interaction

Clarification Chat Agent: checkpoint interrupt с InteractionId, release execution; user answer сохраняется независимо от наличия Python pod; wakeup resume по ID.
Approval OpenCode: существующий процесс продолжает heartbeat, lease и baseline deadline. Это не suspended durable workspace.
Decision принимается только если interaction pending, срок не истёк, task не отменена, scope/request hash совпадает. Same decision retry возвращает receipt, иное решение 409.
Ответ фиксируется до external reply. При потере external reply outcome → unknown; не повторять POST только потому, что delivery receipt не получен.
Clarification expiry: задача заканчивается CANCELLED с USER_RESPONSE_TIMEOUT, если нет неизвестных children; иначе NEEDS_ATTENTION.

## Steering и follow-up

Сообщения во время работы всегда сохраняются. Disposition queued/status/steer/interaction_response виден UI.
Steer повышает GoalRevision; текущий coding input immutable. Агент применяет изменение после результата child либо спрашивает пользователя об отмене текущего шага.
При несовместимом изменении текущий Run не получает второй prompt автоматически.
После terminal task follow-up создаёт новую task с predecessor ref. Для правок уже полученного patch используется явный patch continuation из architecture.md.
Status не запускает новый Coding Run.

## Cancel

Ingress атомарно фиксирует CancelDesired и запрещает новые claims/dispatch intents. Workflow доставляет abort всем живым children, после чего root не планирует новые действия.
Поздний child completion принимается как реальный результат; отмена не откатывает patch.
Если final task committed раньше cancel — возвращается terminal receipt. Если cancel принят первым — task не становится SUCCEEDED; известные завершённые результаты сохраняются, итог CANCELLED после остановки всех детей.
Если хотя бы один effect неизвестен после abort grace 30 s — NEEDS_ATTENTION.
Coding Run сохраняет собственную baseline completion race; task и child могут иметь разные terminal statuses.

## Таймеры

Execution lease 45 s / heartbeat 5 s / safety margin 10 s. Для Chat Agent execution lease отделён от logical invocation lifetime.
Waiting Chat execution не занимает lease; после reactivation новый fence.
Task wall deadline 24 h; waiting не останавливает wall clock. Coding deadline 20 min не продлевается ожиданием пользователя.
Poll/reconcile интервал 5 s. TaskWorkflow использует Continue-As-New на границе safe wait при 1000 итерациях; переносит IDs/flags/deadlines, не prompt/token history. Точный SDK паттерн и сигнал handoff проверяются replay тестом.

## Матрица отказов

| Сбой | Действие |
| --- | --- |
| API умер после inbox commit | Повтор CommandId возвращает прежний ресурс |
| Ответ EnsureInvocation потерян | Lookup того же intent, не новый child |
| Chat pod умер до tool checkpoint | Чистый LLM шаг может быть повторён; tool не был отправлен |
| Chat pod умер после child dispatch | Новый fenced writer читает intent и тот же child result |
| Child завершился во время потери Chat pod | Durable result + reconciler возобновляют граф |
| Старый Chat pod вернулся | Fence запрещает checkpoint/dispatch |
| Temporal worker умер | Replay task и run workflows; I/O только activities |
| OpenCode runner потерян | UNKNOWN/NEEDS_ATTENTION; не повторять prompt |
| SQL недоступен | Нет durable ack/renew; bounded waiting, остановка новых действий |
| Browser reconnect | Snapshot + events после conversation cursor |
| Checkpoint codec несовместим | CHECKPOINT_VERSION_UNSUPPORTED, drain или прежний image; не начинать task заново |
| ACL отозван во время ожидания | Новые вызовы/чтения запрещены, controlled terminal; секреты из старого контекста не выдаются |
