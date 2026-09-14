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

Один coding Run, один OpenCode operation, summary/patch, live UI, cancel/reconnect. Допускается ограниченный HITL permission/question OpenCode через platform UI (без auto-allow). Без agent-to-agent, arbitrary user tool registration, push/PR, generic HITL и полного FastForward.

## VI. Проверяемость

Каждый FR связан с задачей и acceptance check. Обязательны потеря ACK, конкурентный claim, reconnect через другую API replica, restart core-worker, runner loss и cross-owner denial. Ложные заявления exactly-once запрещены.

## VII. Изоляция

Owner authorization на всех чтениях и WebSocket, workload auth на gRPC, read-only repo credentials, ограниченные permissions OpenCode, allowlisted model/repository endpoints и ограничение ресурсов. K8s Secrets/CA — внешняя конфигурация, не содержимое пакета.

## VIII. Управление изменениями

MVP spec конкретизирует и сужает общий концепт v0.2. Изменение базы Temporal, режима восстановления, внешних side effects или состава инфраструктуры требует обновления ADR. Названия методов уточняются по pinned SDK, но семантика acceptance сохраняется.

## IX. Amendment 1.1.0 — Conversational Orchestrator (2026-09-14)

Основание: пользователь согласовал Chat Agent с самостоятельным выбором репозитория и вызовами tools/дочерних agents через шину. Traceability: specs/002-conversational-orchestrator/spec.md FR-201–217 и research.md ADR-201–208.

Для feature 002 принцип I дополняется TaskWorkflow как владельцем task lifecycle, LangGraph как владельцем reasoning checkpoints и MSSQL как владельцем invocation receipts. Conversation не является бесконечным workflow. API не завершает Task самостоятельно.

Принцип IV допускает отдельный Python Chat Agent и custom checkpoint adapter через C# persistence service в MSSQL. Новая прикладная БД не вводится.

Принцип V для 002 расширяется диалогами, registered tool/Coding invocations, clarification/approval и восстановлением Chat Agent на границах checkpoint. Push/PR/CI, arbitrary plugins, multi-repo writing и восстановление потерянного OpenCode workspace остаются вне scope.

Принципы II, III, VI и VII сохраняются; stable dispatch intents и fencing распространяют их на Chat Agent. Повтор чистого model шага допустим только по правилам ADR-204, без повторного внешнего effect. Спецификация 001 остаётся baseline, amendment не объявляет 002 реализованным.
