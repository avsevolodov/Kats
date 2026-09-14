# 002 — Conversational Orchestrator

Дата: 2026-09-14. Статус: спецификация следующего этапа; реализация не начата.
База анализа: main, commit ba62859117a4bf3d2ddc1c96b9c09e0d3623ca57.
Основание: пользователь согласовал переход от UI запуска OpenCode к диалоговому агенту и подготовку документации/плана.

Kats принимает цель на естественном языке. Chat Agent выбирает инструменты, контекст и репозиторий, вызывает Coding Agent через шину и возвращает результат в диалог. UI не определяет репозиторий и не составляет coding prompt.

## Порядок чтения

1. [Требования](spec.md).
2. [Архитектура](architecture.md), [решения и исследования](research.md).
3. [Модель данных](data-model.md), [выполнение и восстановление](workflow.md).
4. [Протокол шины](contracts/agent-transport.md), [API и события UI](contracts/chat-api.md), [инструменты](contracts/capabilities.md).
5. [UX](ui.md), [план](plan.md), [задачи](tasks.md).
6. [Приёмка](checklists/acceptance.md), [задание реализатору](IMPLEMENTATION-PROMPT.md).

## Граница поставки

Обязательный результат: чат без RepositoryId на входе → discovery → подтверждённый контекст → один coding invocation → существующий Run/OpenCode → patch и ответ. Обычный вопрос не требует репозитория или OpenCode.

Включены повторные сообщения, вопросы, разрешения once/reject, статус, отмена, история, checkpoint Chat Agent, межрепличное восстановление. Research Agent и внешние документы — следующая поставка после этого вертикального сценария.

Сохраняются C#/.NET 10, Blazor, Temporal, внешний MSSQL, gRPC bidi, WebSocket. Добавляется Python Chat Agent на Deep Agents/LangGraph. Redis, новая прикладная БД, обязательный S3/PVC не требуются.

Push/PR/CI side effects, произвольные плагины, запись в нескольких репозиториях в одной задаче и прозрачное восстановление потерянного OpenCode workspace не входят.

Спецификация 001 остаётся baseline Coding Run. Правила 002 имеют приоритет только для перечисленных расширений; гарантии runner 001 не усиливаются автоматически.

## Известные расхождения baseline

- Models.cs и RunWorkflow.cs описывают один coding Run, без Conversation/Task.
- docs/permissions.md описывает once/reject и local backend, runtime main.py на просмотренной базе принимает server/cli; proto содержит два семейства permission/confirmation.
- Program.cs на этой базе публикует /runs/{id}/confirm; отдельные permission endpoints из docs/permissions.md в нём не найдены.
- Есть sql/004-permissions.sql и sql/004-operation-confirmations.sql. Нельзя выбирать историю миграций только по числовому префиксу.
- docs/implementation-status.md содержит исторические записи restore/rollback и не является доказательством актуального live поведения.

Этап T002 сверяет реальные маршруты, схему и runner. Этот пакет не объявляет перечисленные дефекты исправленными.
