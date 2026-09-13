# Статус реализации

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
