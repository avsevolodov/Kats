# План разработки

Порядок основан на зависимостях. Оценки предварительные, в инженерных днях, без ожидания доступа к инфраструктуре; это не календарное обещание.
Owner — роль/компетенция, а не назначенный сотрудник. Задачи и FR traceability: [tasks.md](tasks.md).
Статус реализации: [docs/implementation-status.md](../../docs/implementation-status.md) (**002 Progress Map**).

| Milestone | Scope | Зависимость | Owner | Оценка | Выход | Status (2026-09-15) |
| --- | --- | --- | --- | --- | --- | --- |
| M0 | Baseline audit, pinned SDK/model, checkpointer spike, HITL decision | — | Architect + Python + C# | 4–6 | Compatibility evidence и согласованный контракт | **code done**; live LLM/SQL open |
| M1 | Conversation/task persistence, API, fake agent и базовый чат | M0 | C# + Blazor | 5–8 | Диалог без repo, durable history | **code done**; live SQL/browser open |
| M2 | Invocation bus, catalog/ACL, coding adapter | M1 | C# + Python | 7–11 | Fake orchestrator → один реальный Coding Run | **code done**; live OpenCode open |
| M3 | Deep Agents integration, checkpoints, discovery, interaction | M2 | Python + C# | 7–11 | Естественный запрос → результат | **code done** (recorded model); live model open |
| M4 | Steering, patch follow-up, UX/reconnect | M3 | Blazor + Python | 4–7 | Полный пользовательский цикл | **code done** T025–T028; live A* open |
| M5 | Failure tests, rollout, эксплуатация | M4 | C# + Python + QA/DevOps | 5–8 | Staging evidence и release readiness | **unit/ops stubs**; staging → T029 |

Сумма 32–51 инженерный день (оценка исходная). Календарный срок зависит от состава команды и доступа к стенду.

## Next engineering slices

Поставлено code/unit: T025–T028 (interaction wake, steer apply, cancel→abort, resume consume).

**Дальше только:**

5. **T029** — Staging live gate pack (SQL 005–007, Temporal, model, browser, OpenCode) — закрывает A01–A18; mock не засчитывается.

## Изменения по проектам

| Путь | Изменение |
| --- | --- |
| src/Platform.Contracts | AgentTask/Conversation/Invocation/Interaction DTO, generated agent protocol |
| src/Platform.Application | Policy, command validation, routing/disposition services |
| src/Platform.Infrastructure | SQL entities/migrations, inbox/outbox, checkpoint service, catalog ACL |
| src/Platform.Api | Chat endpoints, conversation stream, agent gateway |
| src/Platform.Workflows | TaskWorkflow с wait/cancel/deadline; baseline RunWorkflow сохранён |
| src/Platform.Worker | Invocation handlers/dispatcher/reconciler, catalog tools |
| src/Platform.Ui | Conversation pages и interaction/artifact cards |
| agents/chat_agent | Deep Agents harness, bus adapter, checkpointer, bounded context |
| agents/opencode_runner | Единый interaction bridge, predecessor patch, structured evidence |
| contracts | Новый agent protocol; legacy wire compatibility tests |
| deploy/helm/platform | Chat workload, internal model config/Secrets refs, limits |
| scripts | Native/WSL/Compose запуск chat-agent и smoke сценариев |
| tests | SQL, Temporal, protocol, agent eval, browser и crash acceptance |

## Rollout

1. Additive migrations; сначала схему и совместимые server readers.
2. Deploy agent gateway/handlers с feature flag ChatEnabled=false.
3. Deploy Python workload закреплённой версии; fake first.
4. Pilot allowlist пользователей; chat entry включается только для них.
5. Existing /api/v1/runs и Run detail остаются работоспособны.
6. Drain active chat executions перед несовместимым graph upgrade; definition version/image сохранять до завершения tasks.
7. Rollback выключает создание новых chat tasks, сохраняет history и работу baseline Run. Active tasks дренируются старой версией либо явно NEEDS_ATTENTION. SQL tables не удаляются.

## Эксплуатация

Health разделяет process liveness и model/gateway readiness. Секреты только внешние Secrets/Vault references.
Метрики: accepted→first progress, model latency/usage, invocation queue delay, pending interactions, checkpoint size/failures, stale fence rejections, UNKNOWN rate, SQL stream reads.
OTEL correlation: ConversationId/TaskId/InvocationId/OperationId; без prompt/secrets по умолчанию.
MSSQL load измеряется при 10 tasks; per-token SQL writes не допускаются.
Release gate — [acceptance](checklists/acceptance.md), не только unit tests.
