# Статус реализации

## UI permissions (2026-09-14)

Реализовано: durable PermissionRow + SQL 004, gRPC PermissionExchange/Result,
owner-only GET/POST с CSRF, карточки once/reject в UI, аудит решений, проверки
SessionId/BootId/Fence/lease/deadline/cancel. Поллинг OpenCode pending permissions
не зависит от доставки SSE. Неизвестный ответ permission reply не повторяется.
Новый backend local управляет установленным opencode serve на приватном loopback
с одноразовым паролем и cleanup процесса. Старый cli сохранён.

Проверено: uv sync --locked; 25 Python tests passed, включая HTTP permission
контракт, session isolation, ожидание/отмену/исчезновение запроса, потерю ACK без
повтора POST, запуск/остановку локального fixture server и фильтрацию env секретов.
Contracts/Infrastructure собраны без ошибок; Compile target UI прошёл. Полная
API/WASM сборка во время реализации упиралась в MSB4216/MSB4027 task host.
Полный SQL + real OpenCode + Rider/browser acceptance пока не выполнен.

В upstream main были ссылки на отсутствующие presentation.py и SQL 002/003;
файлы восстановлены, существующие runner/dev tests проходят.
Инструкция миграции и ограничения: [permissions.md](permissions.md).
Ожидание входит в прежний 20-минутный deadline; question, always и recovery
процесса OpenCode не входят в этап. Mock-тесты не доказывают live SQL гарантии.

## WSL developer test environment

Добавлен compose.infra.yaml (MSSQL Developer, Temporal dev/SQLite, Keycloak).
test_env.py configure/up/check/down/run подготавливает отдельные settings/credentials,
realm с двумя пользователями, schema bootstrap и app SQL login. Пароли и settings
сохраняются при повторном configure; down не удаляет volumes. В API HTTP OIDC
разрешён только явным opt-in в Development на loopback authority.

Evidence: 18 Python tests passed, включая повторный configure с сохранением
секретов/изменений и nondestructive down; реальная генерация тестовых файлов и
парсинг YAML. smoke_local.py реализует browser login, Start, completion, reload,
artifact download и cross-owner denial, но live не запускался. Docker/WSL и
browser E2E в этой среде недоступны. Полный .NET build ранее блокировал MSBuild
task host; этот infrastructure change не подтверждает исправление сборки.

## Native OpenCode CLI

Добавлен opt-in `runner.backend=cli`: локальный executable, prompt по stdin, JSON
preview, рабочий каталог checkout, ограниченный stdout и summary, exit/deadline/cancel.
Server backend остаётся default. SQL Begin предшествует subprocess; повтор prompt
запрещён. `cli-UUID` в session-поле — execution token. Неопределённые CLI исходы
переходят в UNKNOWN/NEEDS_ATTENTION. SIGTERM wrapper обрабатывается с cleanup.

Evidence: 16 Python tests passed, включая 6 CLI subprocess fixtures: literal stdin,
непередача Git credential env, запрет повтора, invalid JSON, incomplete output,
nonzero exit, отмена и timeout с ожиданием завершения дочернего процесса.
Формат сверён с исходником OpenCode v1.2.27. Реальный binary/LLM smoke не выполнен:
OpenCode не установлен в среде. Fake executable проверяет wrapper, не совместимость
со всеми версиями OpenCode или внешние SQL/Temporal гарантии.

## Docker Compose / native development

Добавлены compose.yaml, генератор dev-сертификатов/config и launcher четырёх native
процессов; HTTPS browser listener; WORKSPACE_ROOT для всех OpenCode directory запросов.
Существующие .NET Dockerfile используют SDK 10.0.100, согласованный с global.json;
image args позволяют использовать внутренние зеркала. Эти default images предназначены
для dev и должны пройти проверку/обновление перед production release.

Инфраструктурные prerequisites: MSSQL со схемой, Temporal namespace, OIDC client,
проверенный OpenCode CLI/image и provider config. Redis отсутствует.

Evidence: 10 Python tests passed (включая directory propagation в native workspace);
dev init, повторный init, render local/compose; OpenSSL verify server/client EKU и
localhost SAN; YAML parsing. NuGet restore прошёл, но API build не завершён:
Blazor MSBuild task host в этой среде падает с MSB4216/MSB4027.
Docker отсутствует, Compose config/build/up не выполнялись.
Не выполнены: OIDC browser login, real MSSQL/Temporal/LLM и crash acceptance.
Наличие launcher не означает готовность этих live gates.

## uv, Rider и hosted Blazor WASM

Python workspace и uv.lock добавлены; native launcher и Dockerfile.runner используют uv.
API/Worker получили launchSettings.json для test/local и загрузку приватных настроек
из .local. API явно подключает static web assets в Development; UI собирается вместе
с API и обслуживается с того же origin. Инструкция: docs/rider-uv.md.

Evidence: uv 0.12.11 lock/sync прошли, 19 Python tests passed; генерация test Rider
JSON прошла. Smoke дополнен проверкой WASM loader, но live browser smoke не выполнен.
Worker успешно собран .NET SDK 10.0.100: 0 warnings, 0 errors.
Полная API/WASM сборка остаётся заблокирована ошибками MSB4216/MSB4027 task host.
Docker build и запуск Rider в этой среде не проверены.

## Стандартные appsettings

API/Worker используют штатную конфигурацию .NET: base JSON, JSON среды, env, CLI.
Кастомный LocalDevelopmentSettings удалён. Rider выбирает Development; генератор
пишет вложенный appsettings.Development.json в каждый серверный проект. Добавлены
base/Staging/Production и Development example без секретов. Native run читает те же
JSON, без скрытой подстановки C# настроек из Python settings. Compose/Helm сохраняют env overrides.

Evidence: 19 Python tests passed; configure сгенерировал файлы с правами 0600.
MSBuild Content metadata API и Worker подтверждает CopyToPublishDirectory=Never
для Development и example; base/Staging/Production имеют PreserveNewest.
Development исключён из Git и Docker context. Live API/WASM/Rider startup не проверен.
После восстановления NuGet packages Worker собран .NET SDK 10.0.100:
0 warnings, 0 errors. Полная API/WASM сборка остаётся отдельным открытым gate.

## Hosted WASM: fingerprinted module 404

Исправлена отсутствующая регистрация MapStaticAssets в API: fingerprinted URL
Hot Reload initializer требует endpoint manifest, а не только UseStaticFiles.
Добавлен scripts/smoke_ui.py: anonymous browser startup, CSS и ошибки загрузки
/_framework/ и /_content/; проверка не требует SQL/Temporal/OIDC login.

Evidence: Python syntax compile и git diff --check прошли. В текущей среде отсутствует
NuGet cache; build остановлен во время восстановления зависимостей без результата.
Реальный browser/Rider smoke не выполнен, работоспособность у пользователя ещё
требует проверки. Hot Reload не отключён; статические файлы не копируются вручную.

## Correction: framework branch and endpoint routing

Пользовательский запуск выявил конфликт оставленного UseBlazorFrameworkFiles
с MapStaticAssets: запрос попадал в отдельную ветку, не исполняющую выбранный endpoint.
UseBlazorFrameworkFiles удалён. Framework/fingerprinted assets обслуживаются
MapStaticAssets, обычные файлы и SPA fallback сохраняются. Это исправление предыдущего
изменения, а не проблема Windows paths или MSSQL.
Evidence: diff check; полный build/browser smoke в текущей среде не подтверждён.

## Correction: WASM Hot Reload 404 on Debug startup

Пользовательский Debug на https://localhost:8443 показал fatal 404 на
`/_content/Microsoft.DotNet.HotReload.WebAssembly.Browser/*.lib.module.js`:
MapStaticAssets недостаточен для hosted UI с `ReferenceOutputAssembly=false`.
В Platform.Ui задано `WasmEnableHotReload=false`, чтобы Debug boot config не
требовал этот initializer. Favicon 404 подавлен пустым `rel=icon` в index.html.
MapStaticAssets для `/_framework/` сохранён.

Evidence: правка csproj/index.html/docs. Live `dotnet build` в агентской Windows-среде
остановлен: global.json требует SDK 10.0.100, установлены 9.0.x / 10.0.303 / 10.0.400.
Browser/smoke_ui.py после Rebuild Api+Ui — на машине разработчика с pinned SDK.
Не считать mock live pass.

## Correction: login button after OIDC

После Keycloak cookie сессия работала, но UI всегда показывал «Войти»: ссылка
была статической. Runs/Run определяют вход по 401/200 API и показывают
«Выйти» (`/logout` — SignOut cookie + OIDC) либо «Войти». Кнопка запуска
блокируется без сессии.

Evidence: правки Program.cs и Blazor pages; live browser smoke на машине
разработчика после Rebuild.

## Correction: Keycloak logout id_token_hint

Federated `/logout` падал в Keycloak («Missing parameters: id_token_hint»),
потому что `SaveTokens=false` не сохранял id_token. Включены SaveTokens,
openid/profile scopes и RedirectUri на SignOut; в test realm — post.logout.redirect.uris.
Нужен повторный login после обновления (старая cookie без id_token). Переимпорт
realm или правка client attributes — для нового post-logout URI.

Evidence: код Program.cs и test_env realm; live logout — после Rebuild API и
нового входа на стенде разработчика.

## Correction: base ref accepts branch

Пользовательский Start с именем ветки получал INVALID_COMMIT: валидация и runner
требовали только SHA. По запросу UX `baseCommit` принимает полный SHA или безопасный
git ref (ветка/tag). Runner fetch/checkout tip; COMMIT_MISMATCH только для SHA.
OpenAPI/UI/tests обновлены. Это ослабление FR-012 «только immutable commit» —
зафиксировано как осознанное отклонение: tip ветки фиксируется в момент fetch,
в Run сохраняется запрошенный ref.

Evidence: unit test ValidBaseRef/main и reject `../evil`; Python workspace path
изменён; live git fetch ветки — на стенде разработчика.

## Global repositories + PAT credentials

Глобальный allowlist: OpenAPI POST/PUT/DELETE `/api/v1/repositories` и UI
`/repositories` для любого authenticated пользователя. GET list без секретов;
PAT в `CredentialCipher` через Data Protection (`GitCredentials.v1`). Assignment
несёт `auth_kind`; runner запрашивает `FetchGitCredential` и удаляет temp askpass
после fetch. Legacy `CredentialRef` file mount сохранён. Kerberos не реализовывался.
(Ранее CRUD был только у admin — ограничение снято по запросу.)

Evidence: OpenAPI/proto/SQL/data-model обновлены; unit Rules host/credential
(15 Platform.Tests checks); Python wipe/anonymous + realm tests (5 passed via
`C:\Program Files\uv\uv.exe`); Infrastructure/Api/Worker build succeeded with
installed SDK roll-forward. Добавлен идемпотентный `sql/002-repository-credentials.sql`
для уже существующих БД без AuthKind/ProviderHint/CredentialCipher.
Live MSSQL/OIDC/admin UI и real GitHub PAT clone в этой среде не подтверждены.

## Admin connected runners UI

Реализована таблица `RunnerSessions` (`sql/003-runner-sessions.sql`): upsert на
Hello и каждом gRPC frame, online = LastSeenAt ≤15 s. Admin-only
`GET /api/v1/runners` join к LEASED/RUNNING operations; UI `/agents` с poll 5 s.
Таблица не используется для Claim/affinity. OpenAPI Runner/Runners добавлены.
test_env bootstrap включает 003.

Evidence: Platform.Tests runner view wire (19 checks, hint без полного thumbprint,
idle/busy, freshness=15); DDL + bootstrap tests (`tests/dev/test_test_env.py` 3 passed).
Infrastructure/Api build succeeded with SDK 10.0.400 roll-forward. Live MSSQL
touch/list, multi-replica presence и browser admin smoke в этой среде не подтверждены.
После добавления RunnerSessions Start падал на FK Commands/Events→Runs: EF не знал
порядок INSERT. В OnModelCreating объявлены Restrict FK по схеме SQL.

## UI agent execution timeline

Страница Run показывает хронологический ход: platform-события (accepted/started/
status/cancel/completed) и лог агента из OutputBatch. Баннеры reconnect и
истёкшей истории; текст экранируется Blazor. Runner форвардит в preview
санитизированные step/tool markers (CLI и server message parts) без новых
durable tool-event kinds и без raw payloads/reasoning. Fake mode эмитит
маркеры для проверки UI без LLM.

Evidence: добавлены `presentation.py` и `tests/runner/test_presentation.py`;
обновлены CLI/server adapters и `test_cli`/`test_opencode_contract`.
`uv run pytest` (presentation + opencode contract): 5 passed.
CLI subprocess fixtures требуют POSIX — на этой Windows-среде не гонялись.
T023 не закрыт: нужен browser smoke (fake runner → WS → timeline).

## Correction: empty Run timeline while events exist

Live run `cedf5f6d-…` имел 7 SQL Events (Accepted→…→RunCompleted/NEEDS_ATTENTION),
но UI показывал пустой «Ход выполнения» при корректном статусе из GET /runs.
Причины: `GetFromJsonAsync<JsonElement>` глотал ошибки; REST poll отключался при
«Подключено»; при уже terminal статусе WS сразу выходил без догрузки истории.
Исправлено: `JsonDocument` + явные HTTP ошибки, REST poll ~500 ms параллельно с WS,
догрузка истории на terminal; `Events(after >= NextSequence)` → пустая страница
вместо INVALID_CURSOR.

Evidence: MSSQL select по run id подтвердил 7 events / NextSequence=8; browser
smoke после Rebuild API+UI — на стенде разработчика.

## Correction: WebSocket stream 405

DevTools: `Error during WebSocket handshake: Unexpected response code: 405` на
`/api/v1/stream` при живом Worker/runner. HTTP/2 WebSocket = CONNECT; `MapGet` /
method-filtered endpoint даёт 405 до handler. Исправлено: stream обрабатывается
middleware после auth (GET+CONNECT), без endpoint method metadata; browser HTTPS
оставлен на HTTP/1.1. CA trust (`.local/certs/ca.crt`) не связан с 405.

Evidence: правка Program.cs; нужен полный Restart API (не hot reload) и проверка
Network: `stream` → 101.
