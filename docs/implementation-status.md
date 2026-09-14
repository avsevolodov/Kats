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

## Correction: WebSocket stream 405 on HTTP/2

`/api/v1/stream` был `MapGet`: на HTTPS с HTTP/2 браузер шлёт CONNECT
(RFC 8441) → 405 Method Not Allowed до handler. Заменено на `Map` без
фильтра метода (GET + CONNECT), порт 8443 остаётся Http1AndHttp2.

Evidence: правка Program.cs; live — после Stop/Rebuild/Run API в Network у
`stream` должен быть 101, не 405.

## Restore: local stream/timeline fixes after workspace rollback

Рабочая копия откатилась (пропали timeline UI, BrowserStream Origin/ExpiresUtc,
REST poll, default `main`). Восстановлено: BrowserStream, Http1 на 8443,
`Map(/stream)`, Events caught-up cursor, Run.razor timeline+REST poll,
Runs default branch `main`, CSS/JS scroll helper.

Не восстановлено в этом шаге (нужно отдельно, если ещё нужно): Agents/RunnerSessions,
Repositories UI/CRUD, PAT credentials, OIDC SaveTokens logout.

## Restore: Agents / Repositories / PAT / OIDC after rollback

Восстановлено: RunnerSessions + Agents UI (admin), repositories CRUD для
authenticated users, CredentialCipher/PAT + FetchGitCredential, OIDC SaveTokens
+ shared logout RedirectUri, Admin policy на `/runners`, branch/ref в workspace,
proto `auth_kind` / FetchGitCredential, Worker DataProtection для SqlStore ctor,
test_env bootstrap 002+003.

Evidence: unit Platform.Tests + build Api/Ui/Worker; live SQL apply 002/003 и browser
smoke — на стенде разработчика.

Align: CredentialCipher = varbinary/byte[] + ProtectPat; AdminRole under Security;
Git:AllowedHosts server-side validation (from transcript restore).
## Correction: login button after OIDC

После Keycloak cookie-сессия работала, но UI всегда показывал «Войти»: ссылка
была статической. Runs/Run определяют вход по 401/200 API и показывают
«Выйти» (`/logout`) либо «Войти». Кнопка «Запустить» блокируется без сессии.

Evidence: правки Program.cs и Blazor pages; live browser — после Rebuild Api+Ui.

## Correction: WSL runner → Windows API gRPC

При API на Windows и runner в WSL `localhost:8081` указывает на Linux; корпоративный
`HTTP_PROXY` давал gRPC 502 на `127.0.0.1:3128`. `dev.py` вычисляет IP хоста из
`/etc/resolv.conf` (часто `172.x`) или, при DNS stub `10.255.255.254`, из default
gateway; задаёт `PLATFORM_GRPC` и `PLATFORM_GRPC_SSL_NAME=localhost`, снимает proxy.
Override: `local.platformGrpc`. Mirrored (nameserver loopback) → `localhost:8081`.

Evidence: unit tests `tests/dev/test_wsl_grpc.py`; live — повтор `dev.py run runner`
после открытого 8081 на Windows. Transport пишет `gateway reconnect: …`
в stderr при сбое HELLO (код без секретов), чтобы отличи TimeoutError на claim.

## Runner CLI health observability

`opencode --version` health (timeout **20s**, `VERSION_TIMEOUT_S`) логирует bin до
старта, bounded stdout/stderr на timeout/failure, принимает версию со stderr;
mismatch/ok явно. Увеличено с 10s: cold start OpenCode в WSL ~20s.
`logutil` + INFO stderr в main/transport: mode/backend/grpc/ssl_name, CLI health,
gateway dial/hello/reconnect, claim idle, operation start/complete/errors.
`RunnerError` на старте → `runner error: CODE` без полного traceback.
Не чинит зависание самого OpenCode >20s; run timeout (20*60) не менялся.

Evidence: добавлены `tests/runner/test_cli.py` (timeout + stderr version);
агентская Windows-среда без uv/WSL — прогон у пользователя:
`uv run --locked pytest tests/runner/test_cli.py -q` и live
`time opencode --version` + `uv run --locked scripts/dev.py run runner`.

## UI agent execution timeline

Страница Run показывает хронологический ход: platform-события (accepted/started/
status/cancel/completed) и лог агента из OutputBatch. Баннеры reconnect и
истёкшей истории; текст экранируется Blazor. Runner форвардит в preview
санитизированные step/tool markers (CLI и server message parts) без новых
durable tool-event kinds и без raw payloads/reasoning. Fake mode эмитит
маркеры для проверки UI без LLM.

Evidence: `presentation.py` + `tests/runner/test_presentation.py`; CLI/server
adapters и contract tests. T023 не закрыт без browser smoke
(fake runner → WS/REST → timeline).

## Correction: status-only Run timeline (OpenCode logs)

Симптом: в UI видны только статусы платформы, без текста агента. Причины:
`emit()` мог не вызываться во время prepare/ожидания модели; summary уходил
только в artifact; REST `/events` не дочитывал `hasMore`; пустой OutputBatch
молча пропускался.

Исправлено: lifecycle/progress маркеры `[runner] …` (prepare, prompt, ожидание
модели ~20s, CLI start); перед `complete` — один clipped summary в OutputBatch;
`Run.razor` drain `hasMore` (до 50 страниц), case-insensitive `text`, notice на
пустой batch; подзаголовок «статусы + лог агента». Без raw stderr/reasoning и
без новых event kinds.

Evidence: расширен `test_presentation.py` (format_runner, clip_summary_for_preview);
`uv run --locked pytest tests/runner/test_presentation.py -q` → 5 passed.
T023 по-прежнему не закрыт: нужен browser smoke fake → WS/REST → timeline с
`[runner]`/`[шаг]` строками.

## OpenCode server HITL confirmation

Ограниченный HITL: OpenCode server `permission.asked` / `question.asked` → durable
`OperationConfirmations` + browser events `ConfirmationRequired` /
`ConfirmationResolved` → owner Once/Always/Reject (или Answer/Reject) →
`ConfirmationReply` runner → OpenCode `/permission/{id}/reply` или question reply.
Timeout 5 минут → reject. Cancel supersedes pending. CLI backend без HITL-моста.
Constitution carve-out; Temporal не участвует в confirmation signals.

Evidence: proto/SQL/openapi/browser-stream обновлены; runner `test_hitl.py` +
`test_confirmation_protocol.py`; UI панель в `Run.razor`. Live OpenCode 1.2.27 ask
smoke и browser E2E не выполнялись в этой среде. На существующей БД примените
`sql/004-operation-confirmations.sql`.

## Restore: repository credentials (partial rollback)

Восстановлены откатившиеся артефакты: `sql/001-initial.sql` с AuthKind/ProviderHint/CredentialCipher,
OpenAPI CRUD + SecurityMe, realm admin/roles/post.logout, `test_workspace_credentials.py`,
DEV007 и data-model. Runtime C#/UI/runner для repositories в основном уже был на месте.
На существующей БД при ошибке Invalid column name выполните `sql/002-repository-credentials.sql`.
