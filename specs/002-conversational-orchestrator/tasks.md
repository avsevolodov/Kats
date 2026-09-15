# Исполняемый backlog

Два уровня evidence:

| Уровень | Значение |
| --- | --- |
| `[x]` code/unit | Типы, handlers, harness, UI, unit/protocol tests. **Не** закрывает live A01–A18. |
| Live / staging | MSSQL, Temporal, browser, real LLM, OpenCode — только по [acceptance.md](checklists/acceptance.md) и status. |

Источник blockers: [docs/implementation-status.md](../../docs/implementation-status.md) (**002 Progress Map**).

## Сделанные срезы (code/unit, 2026-09-15)

1. **M0–M5 scaffold** — SQL 005–007, ChatStore, `/api/v2`, agent.v1, TaskWorkflow, Conversations UI, fake agent, helm/ops stubs (T001–T024 code).
2. **1B + bus** — Deep Agents HarnessProfile; EnsureInvocation→CapabilityHandlers; coding.execute Start(CommandId=RunId); Conversations WS/cards.
3. **Child wait loop** — ProjectRunStatus не терминализует Task; `SIGNAL_CHILD_COMPLETED`; ReconcileTaskChildren; coding `RUNNING`; Suspend; Python skip Complete.

## T001–T024 (code evidence)

| ID | Milestone / задача | Depends | FR | Acceptance evidence |
| --- | --- | --- | --- | --- |
| [x] T001 | M0: baseline/AGENTS/constitution/status | — | FR-215 | docs/implementation-status.md T001; no git SHA |
| [x] T002 | M0: HITL bridge | T001 | FR-209 | tests/runner/test_hitl_bridge_002.py; ADR-206 T002; Always rejected in Interaction v2 |
| [x] T003 | M0: pin Deep Agents/LangGraph | T001 | FR-204, FR-214 | uv.lock deepagents 0.7.12 / langgraph 1.2.11; tests/chat_agent/test_harness_t003.py; docs/versions.md; live LLM tool-call open |
| [x] T004 | M0: checkpointer prototype | T003 | FR-207, FR-208 | sql/005; ChatStore Put/Get; tests/chat_agent/test_checkpointer_t004.py; **live MSSQL roundtrip open** |
| [x] T005 | M1: Conversation/Task SQL | T001 | FR-201, FR-211 | sql/006 + ChatEntities; unit migration tests; **live SQL duplicate/active-task open** |
| [x] T006 | M1: chat REST | T005 | FR-201, FR-216 | /api/v2 in Program.cs; openapi-chat.yaml; ChatStore PostMessage 202 PERSISTED |
| [x] T007 | M2: agent.v1 proto + golden | T003 | FR-204, FR-205 | contracts/agent.proto; CanonicalHash; test_agent_protocol_t007.py; frames helper |
| [x] T008 | M2: Invocation/DispatchIntent | T005, T007 | FR-205, FR-208 | sql/007; EnsureInvocation + deterministic RunId; test_dispatch_intent.py |
| [x] T009 | M1/M2: TaskWorkflow | T006, T008 | FR-212 | TaskWorkflow.cs (no LLM); Worker registers workflow; **Temporal replay live open** |
| [x] T010 | M1: fake agent + Blazor chat | T006 | FR-202, FR-210 | Conversations.razor default `/`; fake_agent.py; Runs moved to `/runs` |
| [x] T011 | M2: catalog ACL | T005 | FR-203, FR-216 | RepositoryAccess + ListAccessibleRepositoryIds |
| [x] T012 | M2: catalog handlers | T008, T011 | FR-203, FR-204 | CapabilityHandlers catalog/describe/resolve_ref/code.search |
| [x] T013 | M2: coding.execute adapter | T008, T009 | FR-206, FR-217 | Start(CommandId=RunId) + RUNNING until Run projects; **live OpenCode open** |
| [x] T014 | M3: production checkpointer path | T004, T008 | FR-207 | internal /checkpoints API + codec gate; **live SQL conformance open** |
| [x] T015 | M3: harness + bus tools | T003, T009, T012, T013, T014 | FR-202, FR-204, FR-208 | Deep Agents HarnessProfile + bus tools (1B); **real-model open** |
| [x] T016 | M3: Interaction bridge | T002, T008, T013 | FR-209 | InteractionRules + RespondInteraction; once/reject only |
| [x] T017 | M3/M4: ConversationEvent cursor | T009, T015, T016 | FR-210 | ConversationEvents + GET events + Conversations WS `/api/v2/stream`; **multi-replica / browser live open** |
| [x] T018 | M4: disposition/steer/status | T015, T017 | FR-211 | PostMessage dispositions new_task/steer_pending/status_query |
| [x] T019 | M4: follow-up patch validation | T013, T018 | FR-213 | test_followup_t019.py; **fresh workspace E2E open** |
| [x] T020 | M4: UI cards + diagnostics | T010, T016, T017, T018, T019 | FR-202, FR-209, FR-210, FR-217 | Conversations cards + WS + legacy Run diagnostics; **browser scenarios open** |
| [x] T021 | M5: eval dataset | T015, T020 | FR-203, FR-214 | eval_dataset.json + scripts/run_eval_recorded.py; **per-model live results open** |
| [x] T022 | M5: crash suite (unit) | T014–T019 | FR-208, FR-212 | test_crash_semantics_t022 + test_child_wait (suspend/RUNNING≠Complete); **live A04–A16 open** |
| [x] T023 | M5: deploy/dev scripts | T014, T017, T020 | FR-215, FR-216 | helm chat-agent; docs/chat-agent-ops.md (live/fake); scripts/run_chat_agent.ps1; **helm render/native smoke open** |
| [x] T024 | M5: status + FR/A checklist | T021–T023 | FR-201–217 | docs/implementation-status.md 1B/2B + A01–A18 blockers; **staging E2E NOT RUN** |

## Remaining T025–T029

| ID | Задача | Depends | FR / A | Acceptance evidence |
| --- | --- | --- | --- | --- |
| [x] T025 | Interaction respond → wakeup / re-claim root | T016, T022 | FR-209; A10/A11 | RequeueRootClaim + SIGNAL wake; unit test_t025_t028; **live A10 open** |
| [x] T026 | Steer apply (`GoalRevision` / `AppliedAt` on boundary) | T018, T025 | FR-211; A13 | ApplyPendingSteers on claim/reconcile; InputApplied; **live A13 open** |
| [x] T027 | Cancel → child CancelDesired + Run RequestAbort | T009, T013 | FR-212; A16 | CancelTask + ABORT_TASK_RUNS → SqlStore.Cancel; **live A16 open** |
| [x] T028 | Resume after child: consume GetInvocation into second claim | T013, T022 | FR-206/208; A06 | BuildResumeJson + [[KATS_RESUME]] on claim; live_agent resume-child; **live A06 open** |
| [ ] T029 | Staging live gate pack | T025–T028 | A01–A18 | MSSQL 005–007, Temporal signal/replay, real model, browser, OpenCode — checklist PASS; **не mock** |

## Первый законченный срез

Код M0–M5 каркаса + Deep Agents bus + child wait поставлен; unit/protocol evidence зелёный. Полный product acceptance = T025–T028 (код) затем T029 (live), не только docs/unit.
