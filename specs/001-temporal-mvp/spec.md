# Feature specification: 001-temporal-mvp

Branch: `001-temporal-mvp` • Status: Ready for implementation with infrastructure prerequisite INF-001.

## Пользовательская цель

Запустить coding-задачу в зарегистрированном репозитории, наблюдать работу и получить проверяемые изменения, сохранив результат и историю при закрытии браузера или перезапуске платформенного worker.

## User stories

### US1 — Запустить и получить результат (P1)

Пользователь выбирает RepositoryId, immutable commit и текст задачи. Видит Run и получает summary/patch.

- Given разрешённый репозиторий и commit, when Start принят, then возвращается один RunId и статус ACCEPTED; выполнение происходит асинхронно.
- Given повтор того же CommandId и payload, then тот же RunId; изменённый payload с тем же ключом даёт 409.
- Given OpenCode завершён, then result записан до SUCCEEDED; patch можно скачать и применить к указанному base commit.
- Given отключена модель или неверные credentials, then известная ошибка видна, а Run не остаётся вечным RUNNING.

### US2 — Прогресс и reconnect (P1)

- UI получает последовательные событийные batches и финальные ссылки.
- После reconnect к другой API replica применяется только хвост после последнего cursor.
- Закрытие UI не отменяет Run и не запускает его повторно.

### US3 — Отмена (P1)

- Cancel durable принимается с CommandId; повтор безопасен.
- До запуска operation отмена исключает prompt; во время работы запрашивается abort OpenCode.
- Неизвестный исход abort даёт NEEDS_ATTENTION, а не ложный CANCELLED.

### US4 — Восстановление платформы (P1)

- Убийство API replica не убивает OpenCode; runner переподключается и продолжает тот же operation.
- Убийство C# Temporal worker восстанавливает workflow без повторного prompt.
- Потеря Python pod даёт operation UNKNOWN и Run NEEDS_ATTENTION. Пользователь видит причину и может создать новый Run явно.

### US5 — Эксплуатация без PVC/Redis (P1)

- Charts не создают PVC, hostPath, Redis или in-cluster databases.
- Весь authoritative результат хранится вне pod; readiness/liveness и logs позволяют определить сбой.

## Functional requirements

### US6 — Development без Kubernetes (дополнение)

По отдельному запросу пользователя добавлен локальный тестовый профиль с MSSQL,
Temporal dev server и Keycloak в Docker Compose на WSL. Это исключение только для
developer testing: не расширяет разрешения Helm на in-cluster БД/PVC/hostPath.
Fake-runner — первый smoke, затем реальный CLI. Описание: `docs/developer-test-environment.md`.

Native также поддерживает `OPENCODE_BACKEND=cli`: локальный `opencode run` через
stdin/NDJSON вместо server API. Begin хранит wrapper execution token; CLI cancellation
после старта даёт UNKNOWN, а не подтверждённый CANCELLED. Это расширение FR-003
для native, существующий server backend остаётся default.

По запросу пользователя поддерживаются Docker Compose и native Linux/macOS/WSL:
одинаковые API/worker/runner, конфигурируемый workspace, HTTPS UI и mTLS runner.
MSSQL/Temporal/OIDC — внешние prerequisites. Dev bind mounts разрешены только в
Compose; ограничение Kubernetes PVC/hostPath сохраняется. Не добавляются Redis и
автоматическое восстановление Python/OpenCode. Подробности: `docs/local-development.md`.


| ID | Требование |
| --- | --- |
| FR-001 | Основная платформа на C#/.NET 10; официальные Temporal .NET workflows/activities |
| FR-002 | UI Blazor WASM: список, создание, detail, live output, cancel, artifacts, pending OpenCode confirmation + answer |
| FR-019 | OpenCode server: permission/question escalate to durable UI confirm; CLI remains fail-closed without HITL bridge |
| FR-003 | Python wrapper вызывает реальный OpenCode server по localhost HTTP/SSE |
| FR-004 | Start/Cancel имеют устойчивый CommandId, request hash и durable SQL acceptance |
| FR-005 | Один workflow на Run, один стабильный OpenCode OperationId; dispatch через идемпотентную activity |
| FR-006 | Runner соединяется outbound gRPC bidi; lease, reconnect и ACK не зависят от API replica |
| FR-007 | UI использует WebSocket + SQL event cursor; Redis отсутствует |
| FR-008 | SQL event batches ограничены по размеру/частоте; порядок и dedup определены |
| FR-009 | Result summary/patch сохраняются атомарно с operation completion; workflow отражает итог в RunView |
| FR-010 | Cancel фиксируется, доставляется после reconnect, проверяется до prompt |
| FR-011 | OpenCode pod loss/lease expiration не инициирует автоматический повтор RUNNING operation |
| FR-012 | Repo allowlist + commit validation; нет Git push, PR, CI side effects |
| FR-013 | Owner authorization, workload auth, secret redaction и sandbox restrictions |
| FR-014 | Helm использует emptyDir и external MSSQL/Temporal; никакого PVC/hostPath |
| FR-015 | External Temporal prerequisite задокументирован; unsupported MSSQL Temporal не допускается |
| FR-016 | Измерения/health и воспроизводимые crash acceptance tests |
| FR-017 | Released-версии pinned; real OpenCode API contract test, нет неподтверждённого transparent recovery |
| FR-018 | Раздельные истории/retention, cleanup и bounded artifacts в MSSQL |

## MVP limits (настраиваемые исходные значения)

10 одновременных Run на окружение, 1 operation на Python pod, до 20 минут Run, prompt ≤16 KiB UTF-8, preview batch ≤8 KiB и не чаще 1/s, preview на Run ≤2 MiB. Summary ≤256 KiB, patch ≤4 MiB, полный result ≤5 MiB; бинарные изменения не поддерживаются. Workspace emptyDir ≤2 GiB и repo checkout ≤512 MiB. Лимиты служат начальной рамкой, не заявленной производительностью.

При превышении preview budget — одно OutputTruncated, финальный result остаётся обязательным. При превышении result limit — FAILED с RESULT_TOO_LARGE, не SUCCEEDED с потерянной частью patch. Git LFS/submodules запрещены в MVP.

## Success criteria

SC-001: все US1–US5 проходят на staging с реальными MSSQL, Temporal, OpenCode и внутренней моделью.

SC-002: при 10 Run p95 durable acceptance <1 s и p95 доставка уже принятого SQL event в UI <2 s в стенде без искусственного отказа; это цели приёмки, не гарантия времени LLM.

SC-003: duplicate Start и restart API/C# worker не увеличивают счётчик отправленных prompt для живого operation.

SC-004: при потере runner обнаружение ≤60 s после последнего подтверждённого heartbeat при доступных SQL/Temporal.

SC-005: `helm template` и dependency manifests не содержат запрещённых storage/Redis компонентов.

## За пределами MVP

Дочерние агенты, generic HITL вне OpenCode permission/question, полнофункциональный protocol v0.2, token-exact replay, model/tool-level durable interception, Redis/S3, Kerberos delegation, multi-tenant administration, multi-region DR и автоматическое восстановление Python workspace. OpenCode permission/question на server backend эскалируются в UI; auto-allow запрещён. CLI backend без HITL-моста: deny/reject only. Потеря SSE permission channel — fail-closed.
