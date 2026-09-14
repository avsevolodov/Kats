# Constitution — Agent Platform MVP

Version 1.0.0 • Ratified 2026-09-12 • Amendment policy: явное изменение requirements/ADR с traceability.

## I. Один владелец каждого состояния

Temporal владеет orchestration Run: последовательностью шагов, timers и завершением. MSSQL владеет command inbox, operation delivery/lease и сохранёнными результатами. RunView — обновляемая идемпотентными activities проекция. API не завершает Run независимо от workflow. Граница operation state и workflow state описана явно; распределённая транзакция не предполагается.

## II. Безопасный повтор

CommandId/OperationId устойчивы. Повтор доставки возвращает прежний результат. Новый attempt не запускает заново начатый OpenCode prompt. UNKNOWN и NEEDS_ATTENTION являются допустимыми итогами MVP, не маскируются автоматическим retry.

## III. Реалистичная durability

PERSISTED означает commit MSSQL inbox, не старт workflow и не завершение работы. Сохранённый результат и событие completion атомарны в MSSQL. Gateway и Temporal worker не владеют незаменимым runtime state. Python/OpenCode emptyDir эфемерен; его потеря не считается прозрачным recovery.

## IV. Стек и инфраструктура

C#/.NET 10, Blazor WASM, Python/OpenCode, Temporal, external MSSQL. Без Redis и PVC. Для Temporal разрешён документированный prerequisite внешнего сервиса; новая поддерживаемая БД нуждается в инфраструктурном решении владельца окружения. Нельзя тихо заменить MSSQL или запустить dev SQLite Temporal в k8s.

## V. Минимальная поверхность

Один coding Run, один OpenCode operation, summary/patch, live UI, cancel/reconnect. Без agent-to-agent, arbitrary user tool registration, push/PR, HITL и полного FastForward.

## VI. Проверяемость

Каждый FR связан с задачей и acceptance check. Обязательны потеря ACK, конкурентный claim, reconnect через другую API replica, restart core-worker, runner loss и cross-owner denial. Ложные заявления exactly-once запрещены.

## VII. Изоляция

Owner authorization на всех чтениях и WebSocket, workload auth на gRPC, read-only repo credentials, ограниченные permissions OpenCode, allowlisted model/repository endpoints и ограничение ресурсов. K8s Secrets/CA — внешняя конфигурация, не содержимое пакета.

## VIII. Управление изменениями

MVP spec конкретизирует и сужает общий концепт v0.2. Изменение базы Temporal, режима восстановления, внешних side effects или состава инфраструктуры требует обновления ADR. Названия методов уточняются по pinned SDK, но семантика acceptance сохраняется.
