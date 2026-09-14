# Исполняемый backlog

Все задачи не выполнены. [ ] меняется на [x] только после сохранённого acceptance evidence.
Порядок dependencies обязателен. Независимость задач не является разрешением запускать субагентов.

| ID | Milestone / задача | Depends | FR | Acceptance evidence |
| --- | --- | --- | --- | --- |
| T001 | M0: сверить main/AGENTS/constitution и текущий status; записать baseline SHA | — | FR-215 | Diff scope и список расхождений |
| T002 | M0: аудит actual HITL routes/proto/SQL/server/local/cli; выбрать единый bridge | T001 | FR-209 | Контрактный тест реального маршрута; Always не входит в новый flow |
| T003 | M0: pinned Deep Agents/LangGraph/OpenAI-compatible client; model и remote-tool spike | T001 | FR-204, FR-214 | Версии/lock; tool calling, interrupt, disable built-in delegation/shell проверены |
| T004 | M0: custom checkpointer conformance prototype через C# internal API/MSSQL | T003 | FR-207, FR-208 | Pending writes, parent checkpoints, restart и serializer roundtrip на SQL |
| T005 | M1: Conversation/Message/AgentTask/TaskInput + additive migrations | T001 | FR-201, FR-211 | Реальный SQL duplicate/conflict и unique active task |
| T006 | M1: chat REST DTO/OpenAPI, inbox dispatcher и owner auth | T005 | FR-201, FR-216 | 202 PERSISTED, lost response retry, cross-owner denial |
| T007 | M2: agent.v1 protobuf + C#/Python codegen + golden vectors | T003 | FR-204, FR-205 | Cross-language frames/hash/int64/invalid version |
| T008 | M2: Invocation/DispatchIntent, results/outbox, fenced execution leases | T005, T007 | FR-205, FR-208 | Concurrent claim, changed payload conflict, stale writer rejection |
| T009 | M1/M2: TaskWorkflow, task start/cancel dispatcher, waiting/reconciler | T006, T008 | FR-212 | Temporal replay, duplicate Start/Signal, early wakeup, deadline |
| T010 | M1: fake Chat Agent + minimal Blazor conversation/messages | T006 | FR-202, FR-210 | Fake response без RepositoryId, refresh/history |
| T011 | M2: metadata catalog, repository read/run/admin ACL | T005 | FR-203, FR-216 | Search/read/run denial до утечки metadata |
| T012 | M2: catalog/describe/resolve_ref/code.search handlers | T008, T011 | FR-203, FR-204 | Immutable SHA, bounded search, ambiguous fixtures |
| T013 | M2: coding.execute adapter к existing Run + structured result | T008, T009 | FR-206, FR-217 | Lost Start response → один Run; summary/patch + honest not_run |
| T014 | M3: production checkpoint adapter, codec versions, limits, scope auth | T004, T008 | FR-207 | SQL integration conformance, fence/CAS, restart, incompatible codec |
| T015 | M3: Deep Agents harness / bus tools / persisted dispatch intents | T003, T009, T012, T013, T014 | FR-202, FR-204, FR-208 | Real model chooses repo, checkpoint before dispatch, duplicate recovery |
| T016 | M3: unified Interaction + OpenCode bridge, reply delivery status | T002, T008, T013 | FR-209 | once/reject/answer, duplicate conflict, expired/cancelled, lost reply unknown |
| T017 | M3/M4: ConversationEvent projection, WS/REST cursor, final messages | T009, T015, T016 | FR-210 | Cursor gap, reconnect another API, result/delta dedup, early completion |
| T018 | M4: input disposition/revision, status/steer/queued handling | T015, T017 | FR-211 | Status не создаёт Run; steer applied только на boundary |
| T019 | M4: follow-up с predecessor patch в fresh workspace | T013, T018 | FR-213 | Hash/base/ACL/expiry validation; совокупный patch после второго task |
| T020 | M4: UI context/progress/interaction/artifact cards + diagnostics | T010, T016, T017, T018, T019 | FR-202, FR-209, FR-210, FR-217 | Browser сценарии ui.md, keyboard/focus, no unsafe HTML |
| T021 | M5: model/discovery evaluation и budgets | T015, T020 | FR-203, FR-214 | Dataset + per-model results; no fabricated repo/checks |
| T022 | M5: crash/lease/cancel/recovery suite | T014, T015, T016, T017, T019 | FR-208, FR-212 | A04–A12, A16 из acceptance |
| T023 | M5: deployment/dev scripts/OTEL/retention/rollout | T014, T017, T020 | FR-215, FR-216 | Helm render, native smoke, checkpoint drain, old Run regression |
| T024 | M5: staging E2E и итоговый status | T021, T022, T023 | FR-201–FR-217 | Все обязательные A01–A18 с evidence links, blockers перечислены |

## Первый законченный срез

T001–T004 → T005–T008 → T009–T013.
На этом срезе тестовый оркестратор выбирает registered capability и запускает один Coding Run; LLM ещё не является обязательной частью acceptance. Это промежуточный технический результат, не завершённый feature 002.

Полный feature заканчивается T024. Research Agent и push/PR не добавлять внутрь этих задач.

## Evidence формат

Для каждой задачи: commit/ref, test command или сценарий, окружение и версии, outcome, artifact/log ref, оставшиеся ограничения.
Unit/mock, SQL integration, Temporal replay, real-model, browser и crash evidence отмечаются отдельно.
Не менять FR ради зелёного теста. При несовместимом API обновить research/контракт с объяснением и повторить затронутые acceptance checks.
