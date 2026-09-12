# Tasks: 001-temporal-mvp

Формат `- [ ] Tnnn [P] [USn]`. `[P]` — независимая задача после общих prerequisites; не разрешение на автоматическую делегацию. Все пути относительно корня будущего repo. Истории/FR определены в spec.md. Каждая задача закрывается доказательством в docs/implementation-status.md.

## Phase 0 — Compatibility gate (до business code)

- [ ] T001 [US5] Создать `docs/versions.md`: закрепить released .NET SDK/NuGet, Python/grpcio/protobuf, OpenCode image, Temporal server/.NET SDK, Helm chart. Доказательство: restore/build smoke и совместимость native runtime в целевом Linux image. FR-001, FR-017.
- [ ] T002 [US5] Зафиксировать INF-001 в `docs/infrastructure.md`: ready Temporal endpoint или approved external-supported-DB profile; MSSQL приложение отдельно. Проверить доступ/namespace/TLS либо явно отметить live blocker. Не поднимать БД. FR-015.
- [ ] T003 [US1] Создать `tests/runner/test_opencode_contract.py` и fixture pinned API: health/create/prompt/events/status/abort с внутренней моделью; offline fake fixture отдельно. Зафиксировать, какие проверки live не проведены. FR-003, FR-017.
- [ ] T004 [US4] Проверить `contracts/runner.proto` генерацией C#/Python и duplex round-trip; SQL prototype unique insert/atomic claim/commit order в integration test. FR-004, FR-006, FR-008.

Exit: нет неизвестной несовместимости стека; отсутствующие endpoints не препятствуют дальнейшей разработке, но остаются незакрытыми live gates.

## Phase 1 — Foundation (depends T001–T004 design outputs)

- [ ] T005 [US1] Создать solution/projects из plan.md, shared DTO, central package management, Python package и reproducible locks. Успешные dotnet build и Python import smoke. FR-001, FR-003.
- [ ] T006 [US1] Создать EF Core migrations в `src/Platform.Infrastructure/Persistence`: data-model.md, ограничения и индексы, rowversion, watermark, OpenCodeSessionId, Artifact manifest linkage. Проверить clean migration и idempotent upgrade script на MSSQL. FR-004, FR-009, FR-018.
- [ ] T007 [US1] Реализовать Start/Cancel inbox transactions + canonical request hashes + atomic admission limit в `Platform.Application/Commands`; tests identical/conflicting/concurrent commands. FR-004, FR-010.
- [ ] T008 [US4] Реализовать OperationStore: claim, Begin, renewal, stale fence, cancel guard, completion-from-LEASED error. Конкурентный тест через две instances. FR-005, FR-006, FR-011.
- [ ] T009 [US2] Реализовать RunEventStore и ProducerReceipts: commit-order sequence, exact duplicate ACK, conflict, unexpected sequence, payload caps. Integration test задержанного commit не теряет event. FR-007, FR-008.
- [ ] T010 [US1] Реализовать ArtifactStore/Complete transaction, UTF-8 sizes/hash и отсутствие partial success. Tests ACK loss, oversize и immutable duplicate completion. FR-009, FR-018.
- [ ] T011 [P] [US5] Реализовать config validation, structured logs/correlation, readiness/liveness и metrics skeleton. No secret output test. FR-013, FR-016.

Exit: SQL guarantees доказаны на реальной БД, не InMemory provider.

## Phase 2 — C# orchestration (depends T006–T010)

- [ ] T012 [US1] `RunWorkflow` и activities EnsureOperation/PollOperation/PublishStatus/PublishTerminal, стабильные IDs, timer loop 5 s, deadline. Workflow unit/time-skipping tests. FR-001, FR-005.
- [ ] T013 [US1] Hosted inbox dispatcher: SQL lease, stable Temporal WorkflowId, reject reuse, AlreadyStarted verification, backoff; lost start response integration test. FR-004, FR-005.
- [ ] T014 [US3] RequestCancel signal/dedup, Cancel dispatcher, SetOperationCancel, before-start guard, abort grace, terminal race tests. FR-010.
- [ ] T015 [US4] Lease reaper/UNKNOWN → NEEDS_ATTENTION, no requeue, stale result rejection. Test expired LEASED and RUNNING. FR-011.
- [ ] T016 [US4] Capture/replay workflow history и simulate lost activity completion: no duplicate operation/status event. Restart C# worker against same running fake operation. FR-005, FR-016.

Exit: workflow не содержит недетерминированного I/O; retries не вызывают prompt.

## Phase 3 — API and duplex (depends T007–T016)

- [ ] T017 [US1] REST endpoints по openapi.yaml, validation/problem details, pagination/owner scope. Generated implementation OpenAPI сравнить с contract. FR-004, FR-012.
- [ ] T018 [US2] WebSocket по browser-stream.md: subscribe/cancel, cursor replay, bounded buffer, expired cursor, heartbeat, no local affinity. FR-007, FR-008.
- [ ] T019 [US4] gRPC gateway runner.proto: Hello/Claim/Begin/Heartbeat/Resume/Output/Complete; common SQL handlers, auth binding и abort delivery после reconnect. FR-006, FR-010.
- [ ] T020 [US4] Fake runner executable с observable prompt counter, delay/failure knobs; multi-replica ACK-loss/reconnect tests. FR-006, FR-016.
- [ ] T021 [US5] Auth: OIDC cookie BFF, antiforgery/Origin checks, shared Data Protection keys in MSSQL with Secret certificate; workload mTLS. Тест API replica switch и запрета cross-owner reads/downloads/WS. FR-013.

Exit: один и тот же Run доступен через любую API replica, без Redis.

## Phase 4 — Blazor UI (depends T017–T021)

- [ ] T022 [US1] `Platform.Ui/Pages/Runs`: list/create, repository selector, commit validation, prompt validation, generating/reusing CommandId until known acceptance. FR-002, FR-004.
- [ ] T023 [US2] Detail page и stream client: run/operation statuses, escaped preview, cursor apply/dedup, reconnect banner, truncated/expired history. FR-002, FR-007.
- [ ] T024 [US3] Cancel UI и artifact download/summary/patch/base commit. NEEDS_ATTENTION поясняет потерю runner и явный новый Run, не автоматический Retry. FR-002, FR-009, FR-010, FR-011.
- [ ] T025 [US2] Browser tests Start/result, reload, cancel и API switch; cookie истечение закрывает streaming и запрашивает login. FR-002, FR-013, FR-016.

Exit: full fake-runner vertical slice демонстрируется из браузера.

## Phase 5 — Python/OpenCode (depends T003,T019,T020)

- [ ] T026 [US1] Python async gRPC client с BootId, lease/fence, bounded output buffer, serial producer sequence, independent heartbeat/control tasks. Unit tests reconnect/ACK conflict. FR-003, FR-006.
- [ ] T027 [US1] Workspace manager: read-only clone, immutable commit, size limit, clean operation directory, запрет LFS/submodules, no credentials in config. FR-012, FR-014.
- [ ] T028 [US1] OpenCode sidecar health/session/prompt/status/SSE adapter. Begin ACK before single prompt, no blind resend on HTTP uncertainty. Tests fixture и live smoke. FR-003, FR-017.
- [ ] T029 [US1] Output batching/truncation и final patch, including added text files; verify patch applies to clean base. Complete retry after lost ACK does not rerun model. FR-008, FR-009.
- [ ] T030 [US3] Abort integration, unexpected permission/question fail-closed, OpenCode sidecar loss UNKNOWN, lease safety deadline. FR-010, FR-011, FR-013.
- [ ] T031 [US5] Harden sidecar: explicit permissions, trusted config, no sharing/plugins override, no runner/Git certs in OpenCode, allowlisted egress. Проверить repo-supplied config bypass; document pilot restrictions if gate fails. FR-012, FR-013.

Exit: реальная модель возвращает применимый patch; Python process loss не маскируется как recovery.

## Phase 6 — Delivery (depends runnable vertical slice)

- [ ] T032 [US5] Multi-stage Dockerfiles для API/worker/runner/OpenCode, pinned images, non-root; build через доступные mirrors. No secret layer inspection. FR-014, FR-017.
- [ ] T033 [US5] Application Helm chart из kubernetes.md: 2 API/2 worker, runner sidecar, external Secrets, service ports, emptyDir/resources, probes/PDB/graceful stop. FR-014.
- [ ] T034 [US5] Optional Temporal profile для выбранного chart с external supported DB и отключёнными persistent subcharts; render validation. Live blocked без INF-001. FR-015.
- [ ] T035 [US5] Dev Compose external-service profile, config examples без secrets, migrations release step, actual quickstart commands. FR-014, FR-017.
- [ ] T036 [US5] Cleanup jobs/services: 7-day output/artifact, 30-day receipt policy, cursor expiry, active Run protection. Retention integration tests. FR-018.
- [ ] T037 [US5] Metrics/alerts и runbooks: pending inbox, stale heartbeat, UNKNOWN, SQL outage, Temporal outage, output cap, rollback compatibility. FR-016.

## Phase 7 — Acceptance (depends all above)

- [ ] T038 [US4] Fault test: API dies during live run; reconnect other replica, same operation/session/prompt count, committed cursor preserved. FR-006, FR-007, FR-016.
- [ ] T039 [US4] Fault test: C# worker dies, Temporal unavailable temporarily, command response lost; history/SQL converge without duplicate OpenCode prompt. FR-004, FR-005, FR-016.
- [ ] T040 [US4] Fault test: Python process and whole pod deleted; UNKNOWN/NEEDS_ATTENTION ≤60 s, no reassign/prompt retry; test lease partition >45 s separately. FR-011, FR-016.
- [ ] T041 [US3] Fault test: cancel-before-begin, cancel-running, completion race, lost abort ACK; unknown abort never labelled successful cancellation. FR-010, FR-016.
- [ ] T042 [US1] Real end-to-end fixture: create/run/result; clean checkout applies patch and passes allowed tests; no push/PR traffic. FR-003, FR-009, FR-012.
- [ ] T043 [US5] Load test 10 active fake Run: acceptance/delivery p95, SQL RPS/locks, workflow history size, buffer/ephemeral-storage limits. Не использовать model latency как transport metric. FR-008, FR-016.
- [ ] T044 [US5] Security/storage gates: no PVC/hostPath/Redis/deployed DB, owner isolation, cookie across replicas, secret redaction, sidecar privilege boundaries. FR-013, FR-014, FR-015.
- [ ] T045 [US5] Финальный handover: docs/implementation-status.md, versions, commands, test evidence, unresolved infra/live gates. Сверить checklists/acceptance.md, не утверждать live готовность по mocks. FR-017, FR-018.

## Dependency summary

T001–T004 → T005–T011 → T012–T016 → T017–T021 → T022–T025. Python T026–T031 начинается после protocol/fake slice. Delivery T032–T037 готовится на runnable slice. T038–T045 — общие gates. UI и Python могут разрабатываться независимо по зафиксированным contracts; изменение contract требует согласованного обновления обеих сторон.
