# ADR и исследования

Дата проверки источников: 2026-09-14. Ни один пример API из latest не является pinned dependency.
Решения относятся к feature 002. Compatibility gates не закрыты.

## ADR-201: Chat Agent поверх Deep Agents / LangGraph

Решение: отдельный Python workload; C# сохраняет API, persistence services и Temporal workflows.
Deep Agents — harness над LangGraph; предоставляет управление контекстом и делегирование.
Следствие: нужна интеграция remote tools, а не запуск default локальных subagents.
Гейт T003 фиксирует release и проверяет отключение встроенных shell/delegation путей, async calls и model compatibility.
Источник: [Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview).

## ADR-202: Раздельные владельцы execution и reasoning

Temporal владеет task lifecycle; LangGraph — reasoning checkpoints; SQL — delivery receipts.
Граф может ждать child, не удерживая Python process. TaskWorkflow не знает внутренние узлы графа.
Нет распределённой транзакции SQL–Temporal: inbox, устойчивый workflow ID и reconciler закрывают потерю ответа.

## ADR-203: Checkpointer через C# persistence service в MSSQL

Python реализует adapter checkpointer API закреплённого LangGraph release. C# internal RPC сохраняет сериализованные checkpoints, channel versions, metadata, parent refs и pending writes.
Нужны get/list/put/put_writes semantics выбранной версии; отдельный adapter conformance suite обязателен.
Это custom adapter проекта, не заявление о встроенной MSSQL поддержке LangGraph.
Нет pickle/untrusted executable deserialization; ограниченный versioned codec, JSON/binary allowlisted types, payload bounds.
Источник: [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence).

## ADR-204: Durable dispatch перед side effect

После генерации tool calls сохраняется checkpoint/intent. Ключ invocation выводится из сохранённых TaskId, graph checkpoint/task path, tool call ID; сгенерированный заново случайный ID при retry запрещён.
Child acceptance и intent binding атомарны в MSSQL. Потеря ответа приводит к lookup, не новому вызову.
Code перед interrupt может исполняться снова при resume; поэтому там только идемпотентные действия.
Источник: [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts).

Повтор чистого LLM шага без сохранённого результата допускается с новым ModelAttemptId и расходом бюджета; частичный preview закрывается как interrupted. Это не token-exact recovery. Внешний tool никогда не запускается до persisted intent.

## ADR-205: Узкий invocation protocol

Новый agent.v1 рядом с runner.v1; registered capability handlers. Без универсального routing mesh/plugin DSL.
Root Chat Agent может вызывать tools и Coding Agent; Research Agent добавляется отдельно.
Сохраняем single Operation/Run механизм baseline, связываем его с invocation через unique RunId/source key.

## ADR-206: Interaction унифицируется

Один persisted InteractionRequest: clarification или approval. Decision once/reject; answer для clarification.
Always из старых ветвей не переносится в новый контракт. Решение не зависит от свободного текста «да» без однозначного InteractionId.
Неизвестный OpenCode permission reply остаётся unknown и требует внимания; checkpoint не разрешает повтор.

### T002 decision (2026-09-15)

Канонический OpenCode HITL bridge: `OperationConfirmations` + `POST /api/v1/runs/{id}/confirm` + runner `ConfirmationRequired`/`ConfirmationReply`.
Legacy `Permissions`/`PermissionExchange` и docs/permissions.md endpoints не являются bridge для 002 Interaction.
Baseline Run UI may still offer Always for OpenCode server; Interaction v2 validator rejects Always (`ALWAYS_NOT_ALLOWED`).
Evidence: `tests/runner/test_hitl_bridge_002.py`, `chat_agent.interaction`.

## ADR-207: Scope amendment

По запросу пользователя 002 разрешает Python Chat Agent, ограниченные child invocations и общий HITL.
Сохраняются запрет внешних Git side effects в продукте, read-only Git credentials и существующие recovery ограничения OpenCode.
Нет изменения инфраструктуры Temporal или перехода прикладной БД с MSSQL.

## ADR-208: Модель и оценка

Один configurable chat model endpoint в первой поставке; отдельный классификатор не обязателен.
Сравнить доступные внутренние модели на tool schemas, русском диалоге, ambiguous discovery, latency и budget. Название модели само по себе не доказывает качество.
Выбрать default по evaluation, зафиксировать модель/параметры/prompt version на task. Переключение при retry не должно повторять tool side effects.
Cloud telemetry отключена; OTEL экспорт только во внутренний endpoint.

## Решения, отложенные за границы

Research/document connectors, отдельная малая модель маршрутизации, cross-task memory beyond summaries, multi-repo writing, push/PR/CI и session resurrection. Их отсутствие не блокирует обязательный сценарий 002.
