# 002 — Conversational Orchestrator

Дата спеки: 2026-09-14. **Статус реализации (2026-09-15): code/unit в рабочем дереве; live A01–A18 NOT RUN.**
База анализа: main, commit ba62859117a4bf3d2ddc1c96b9c09e0d3623ca57.
Основание: пользователь согласовал переход от UI запуска OpenCode к диалоговому агенту.

Kats принимает цель на естественном языке. Chat Agent выбирает инструменты, контекст и репозиторий, вызывает Coding Agent через шину и возвращает результат в диалог. UI не определяет репозиторий и не составляет coding prompt.

Актуальный прогресс и blockers: [docs/implementation-status.md](../../docs/implementation-status.md) (секция **002 Progress Map**). Исполняемый backlog: [tasks.md](tasks.md) (T001–T024 code evidence; T025–T029 remaining).

## Порядок чтения

1. [Требования](spec.md).
2. [Архитектура](architecture.md), [решения и исследования](research.md).
3. [Модель данных](data-model.md), [выполнение и восстановление](workflow.md).
4. [Протокол шины](contracts/agent-transport.md), [API и события UI](contracts/chat-api.md), [инструменты](contracts/capabilities.md).
5. [UX](ui.md), [план](plan.md), [задачи](tasks.md).
6. [Приёмка](checklists/acceptance.md), [задание реализатору](IMPLEMENTATION-PROMPT.md).

## Прогресс (code / unit)

Сделано в дереве (не live acceptance):

| Срез | Содержание |
| --- | --- |
| M0–M5 scaffold | SQL 005–007, ChatStore/API v2, agent.v1, TaskWorkflow, Conversations UI, fake agent, helm/ops stubs |
| 1B Deep Agents | HarnessProfile без shell/FS/execute; bus LangChain tools; checkpoint-before-ensure; recorded tests |
| Bus → handlers | EnsureInvocation → CapabilityHandlers; catalog ACL; coding.execute → Start(CommandId=RunId) |
| UI events | `/api/v2/stream` + cards; Run→ConversationEvents; once\|reject |
| Child wait loop | ProjectRunStatus не терминализует Task; SIGNAL_CHILD_COMPLETED; ReconcileTaskChildren; coding RUNNING; Suspend |

Evidence ориентир: pytest `tests/chat_agent` (~51), Platform.Tests (~30), build Api/Worker/Ui. `[x]` в tasks.md = code/unit evidence, **не** закрытие A01–A18.

## Осталось

**Код T025–T028:** поставлен (interaction wake, steer apply, cancel→abort runs, resume `[[KATS_RESUME]]`).

**Live / staging (T029):** apply SQL 005–007, Temporal replay+signal, реальный LLM, browser E2E, OpenCode smoke — закрывает [acceptance](checklists/acceptance.md) A01–A18. Mock/in-memory не заменяет.

## Граница поставки

Обязательный результат: чат без RepositoryId на входе → discovery → подтверждённый контекст → один coding invocation → существующий Run/OpenCode → patch и ответ. Обычный вопрос не требует репозитория или OpenCode.

Включены повторные сообщения, вопросы, разрешения once/reject, статус, отмена, история, checkpoint Chat Agent, межрепличное восстановление. Research Agent и внешние документы — следующая поставка после этого вертикального сценария.

Сохраняются C#/.NET 10, Blazor, Temporal, внешний MSSQL, gRPC bidi, WebSocket. Добавляется Python Chat Agent на Deep Agents/LangGraph. Redis, новая прикладная БД, обязательный S3/PVC не требуются.

Push/PR/CI side effects, произвольные плагины, запись в нескольких репозиториях в одной задаче и прозрачное восстановление потерянного OpenCode workspace не входят.

Спецификация 001 остаётся baseline Coding Run. Правила 002 имеют приоритет только для перечисленных расширений; гарантии runner 001 не усиливаются автоматически.

## Известные расхождения baseline

Исторический аудит на ba628591 (см. T001 в status). В текущем дереве Conversation/Task/agent.v1/chat_agent уже присутствуют; dual `sql/004-*` naming сохраняется — additive только `005+`.

- HITL canon для Interaction v2: once/reject; Always запрещён (ADR-206). Baseline Run panel может ещё предлагать Always — не расширять в chat.
- Live HITL OpenCode: `POST /api/v1/runs/{id}/confirm` + OperationConfirmations.
- docs/implementation-status.md содержит исторические записи 001 и не является доказательством live без явной строки NOT RUN / PASS.

Этап T002 зафиксировал bridge; live staging (T029) подтверждает на стенде.
