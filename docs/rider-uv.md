# Rider + uv: запуск разработчика

Откройте `AgentPlatform.slnx` в Rider. Python-зависимости управляются **uv**:
корневой pyproject.toml объединяет runner в workspace, uv.lock фиксирует зависимости.
Отдельные pip install и ручное создание venv не нужны.

## Подготовка

Из корня репозитория в WSL:

```bash
uv sync --locked
uv run --locked scripts/test_env.py up
```

Скрипт также создаёт `.local/rider-test-api.json` и `.local/rider-test-worker.json`.
После изменения `.local/test-settings.json` обновите файлы:

```bash
uv run --locked scripts/test_env.py configure
```

Для собственных внешних зависимостей и `.local/settings.json`:

```bash
uv run --locked scripts/dev.py init
# Настройте .local/settings.json
uv run --locked scripts/dev.py rider
```

## Запуск C# из Rider

В проектах добавлены `Properties/launchSettings.json`:

| Проект | Профиль тестового стенда | Профиль своих зависимостей |
|---|---|---|
| Platform.Api | Kats API (test) | Kats API (local) |
| Platform.Worker | Kats Worker (test) | Kats Worker (local) |

Rider импортирует эти launch profiles. При необходимости создайте Run Configuration
типа **.NET Launch Settings Profile**, укажите соответствующий проект/профиль.
Запускайте API и worker через Run или Debug; можно объединить их в Compound configuration.
Platform.Ui отдельно запускать не нужно. API открывает https://localhost:8443/.

Профили содержат только Development и имя локального профиля. Код находит корень
checkout и загружает сгенерированный JSON из `.local`; env/command-line имеют приоритет.
Production не разрешает KATS_LOCAL_PROFILE. Сертификаты и строки подключения в Git
не попадают. Файлы не перечитываются на лету: после изменения конфигурации перезапустите процессы.

Рекомендуемый вариант Windows — Rider с backend/toolchain в WSL, где выполнялась
подготовка: сгенерированные certificate paths — абсолютные Linux paths.
Если C# запускается Windows CLR, сгенерируйте Rider JSON на Windows с uv и доступным
OpenSSL (либо исправьте certificate paths в локальных Rider JSON на Windows paths).
localhost-адреса инфраструктуры сохраняются через WSL forwarding. Эти JSON не являются
общими между Windows и Linux; запускайте генератор для выбранной ОС.

## Python runner

В терминале:

```bash
uv run --locked scripts/test_env.py run runner
```

Первый сценарий использует fake-runner. Для OpenCode CLI установите `runner.mode=real`,
`runner.backend=cli` в test-settings.json и настройте provider/model/репозиторий.
Wrapper запускается через `uv run --locked --no-dev agent-runner`.

Тесты:

```bash
uv run --locked pytest tests/runner tests/dev -q
uv sync --locked --group browser
uv run --locked --group browser playwright install --with-deps chromium
uv run --locked --group browser scripts/smoke_local.py
```

## Как UI попадает в браузер

Platform.Api ссылается на Platform.Ui как на Blazor WebAssembly project. Build/publish
API собирает клиент и включает его static web assets. В Development API явно
подключает manifest этих assets, включая запуск из Rider. `UseBlazorFrameworkFiles`,
`UseStaticFiles` и SPA fallback обслуживают index.html, `/_framework/*`, CSS и deep links.
Браузер скачивает runtime и сборки и выполняет UI на клиенте. REST/WebSocket используют
тот же origin, дополнительный сервер UI/CORS не требуется.

После старта API проверьте в Network браузера `/_framework/blazor.webassembly.js`
и последующие WASM-запросы. Browser smoke проверяет loader и реальную работу UI.
Release выполняется через publish API:

```bash
dotnet publish src/Platform.Api/Platform.Api.csproj -c Release -o artifacts/api
```

В output должны присутствовать wwwroot/index.html и wwwroot/_framework.
Если их нет, release gate не пройден. Полный build/serve проверяйте по актуальному
docs/implementation-status.md; наличие профилей само по себе не подтверждает live startup.
