# Research and architecture decisions

Проверено по официальным источникам 12.09.2026. Точные версии для закрытого контура фиксируются реализацией, не выбираются по номерам из main README.

## ADR-MVP-001 — C# Temporal application

Decision: workflows, activities и client на официальном Temporal .NET SDK. Python Temporal SDK не нужен. Штатный Temporal Server — отдельный продукт. Native runtime-зависимости SDK проверяются в целевом Linux image; сначала Debian/Ubuntu-based .NET image, не предполагать Alpine compatibility. [SDK](https://github.com/temporalio/sdk-dotnet)

## ADR-MVP-002 — INF-001: persistence Temporal

Официальная документация перечисляет Cassandra, PostgreSQL и MySQL; SQLite предназначен для development/testing. MSSQL не является штатным backend Temporal. [Persistence](https://docs.temporal.io/temporal-service/persistence)

Режим A (предпочтителен для пакета): готовый внешний Temporal endpoint, инфраструктура его storage вне приложения.

Режим B: штатные Temporal pods в k8s, внешний PostgreSQL для default/visibility stores; provisioning внешней БД — отдельная задача инфраструктурной команды, не автоматическое действие агента. Deployment остаётся blocked до предоставления БД/доступа. MSSQL приложения не меняется.

Режим C (MSSQL-only и нет готового Temporal) невозможен со штатным выбранным стеком. Не обходить ограничение временной in-memory/SQLite БД на k8s и не называть это durable MVP.

Без PVC возможно размещать Temporal service pods с внешним persistence. Helm chart и server version выбираются совместимой парой. [Deployment](https://docs.temporal.io/self-hosted-guide/deployment), [Visibility](https://docs.temporal.io/self-hosted-guide/visibility)

## ADR-MVP-003 — API и browser

Decision: Blazor WASM hosted by ASP.NET Core. Browser WebSocket имеет собственный JSON contract; не использовать Blazor Server/SignalR scale-out/backplane. Runner binding — gRPC bidi. Оба используют один SQL event store, но их wire schemas различаются.

## ADR-MVP-004 — Единица durable исполнения

Decision: один OpenCode operation на Run. Temporal оркестрирует операцию целиком, не внутренние LLM/tools OpenCode. Это исключает неподтверждённую интеграцию interception из критического пути. Без прозрачного recovery потерянного Python pod, child runs и HITL.

## ADR-MVP-005 — OpenCode integration

У OpenCode есть server HTTP API и SSE events, endpoints для sessions, prompt и abort. Wrapper использует pinned runtime OpenAPI/contract fixture. Внутреннее SSE не мешает внешнему bidi каналу платформы. [Server](https://opencode.ai/docs/server/)

CLI поддерживает export/import session, но это не доказательство восстановления незавершённого исполнения и filesystem. Поэтому export/import не используются как обещание recovery MVP. [CLI](https://opencode.ai/docs/cli/)

Permission defaults не считаются достаточной защитой: конфигурация формируется платформой, неожиданные вопросы завершаются fail-closed. [Permissions](https://opencode.ai/docs/permissions/)

## ADR-MVP-006 — SQL instead of Redis/S3 for bounded MVP

Decision: batch preview + semantic events в MSSQL; большие output ограничены. SQL idempotency receipts хранятся дольше replay data. Cleanup не удаляет записи активного Run. Сегменты не управляют агентной логикой: streaming только presentation.

## Что агент должен подтвердить spike-тестами

- Released .NET SDK/build image и Temporal service compatibility.
- MSSQL database version/compatibility level, row locks, isolation и migrations.
- Python grpcio/protobuf interoperability с C# stubs.
- Реальная версия OpenCode: health, create session, async prompt, idle/completion detection, SSE, abort.
- Ограничение permissions и исключение внешнего push/PR в тестовом repo.
- DNS/TLS/CA до MSSQL/Temporal/LLM/Git в namespace.
- Способ реальной OIDC browser auth и mTLS workload identity в окружении.

Spec Kit package следует стандартному разделению specification → plan → tasks; CLI-generated harness не включён. [Spec Kit](https://github.com/github/spec-kit)
