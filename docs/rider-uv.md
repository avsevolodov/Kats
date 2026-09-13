# Rider + uv: запуск разработчика

Откройте `AgentPlatform.slnx` в Rider. Python runner использует uv workspace и uv.lock.

## Подготовка в WSL

```bash
uv sync --locked
uv run --locked scripts/test_env.py up
```

Команда создаёт инфраструктуру и `appsettings.Development.json` в проектах
`src/Platform.Api` и `src/Platform.Worker`. В Rider запускайте профили **Kats API**
и **Kats Worker**. Оба выбирают `Development`. UI отдельно запускать не нужно:
API отдаёт Blazor WASM по https://localhost:8443/.

Для своих MSSQL/Temporal/OIDC:

```bash
uv run --locked scripts/dev.py init
# Настройте .local/settings.json
uv run --locked scripts/dev.py appsettings
```

Можно вместо генератора скопировать `appsettings.Development.example.json` в
`appsettings.Development.json` в каждом проекте и заполнить значения самостоятельно.
После генерации редактируйте C# настройки непосредственно в этих файлах.
Обычный запуск из Rider или `dev.py run` их не перезаписывает.
Повторные `test_env.py configure`, `test_env.py up` и `dev.py appsettings`
**перезаписывают Development-файлы** из соответствующего `.local/*settings.json`.
Выберите, где поддерживать свои изменения, перед повторной генерацией.
`dev.py rider` оставлен как alias команды `appsettings`.

## Стандартная конфигурация .NET

| Файл в каждом серверном проекте | Назначение |
|---|---|
| `appsettings.json` | Общие настройки и значения по умолчанию |
| `appsettings.Development.json` | Локальные подключения и сертификаты; генерируется, исключён из Git |
| `appsettings.Development.example.json` | Шаблон без секретов; автоматически не загружается |
| `appsettings.Staging.json` | Переопределения для тестовой среды |
| `appsettings.Production.json` | Переопределения для production |

Используется штатная загрузка `WebApplication.CreateBuilder` / `Host.CreateApplicationBuilder`:
общий JSON → JSON выбранной среды → User Secrets в Development (если задан UserSecretsId)
→ переменные окружения → аргументы командной строки. Например,
`ConnectionStrings__Platform` переопределяет `ConnectionStrings:Platform` из JSON.
JSON секции объединяются по ключам; файлы Staging и Production не наследуются друг от друга.
В этой версии UserSecretsId не задан: локальные секреты хранятся в приватном Development-файле.

Для контейнеров задавайте `DOTNET_ENVIRONMENT=Staging` или `Production`; для API
можно также задать `ASPNETCORE_ENVIRONMENT` с тем же значением. Без выбора среды
используется Production. В Kubernetes подключения, пароли и пути к сертификатам
поступают через существующие Secrets/env. Общие настройки сред можно менять в JSON.
Не сохраняйте реальные секреты в отслеживаемых файлах.

Development-файлы исключены из Docker context и publish output. Base/Staging/Production
доставляются с приложением. Для опубликованного приложения настройки ищутся в content root:
запускайте его из каталога publish. Настройки API/Worker не передаются в Blazor-клиент.
После изменения подключений или сертификатов перезапустите процесс.

На Windows используйте Rider с .NET toolchain/backend в том же WSL, где выполнена
подготовка. Если используете Windows CLR, укажите доступные ему пути сертификатов
в Development-файлах. Генерация в WSL создаёт абсолютные Linux paths.

## Python runner и проверки

### Проверка загрузки UI

API регистрирует `MapStaticAssets`: fingerprinted `/_framework/` URL обслуживаются
через endpoint manifest .NET 10. `UseStaticFiles` сам по себе не обслуживает такие
псевдонимы. См. [документацию Microsoft](https://learn.microsoft.com/en-us/aspnet/core/fundamentals/static-files?view=aspnetcore-10.0).

В `Platform.Ui` для hosted Debug задано `WasmEnableHotReload=false`: иначе boot config
запрашивает fingerprinted Hot Reload `*.lib.module.js` из NuGet, а API-хост с
`ReferenceOutputAssembly=false` не отдаёт его надёжно (404 и срыв старта WASM).
Hot Reload для Blazor WASM в этом MVP не требуется.

После обновления остановите API и выполните Rebuild Solution в Rider. Если ошибка
остаётся, удалите только `bin` и `obj` проектов Platform.Api и Platform.Ui,
повторите сборку и откройте страницу с отключённым кешем (Ctrl+Shift+R).
Не удаляйте .local и appsettings.Development.json.

При запущенном API можно проверить запуск WASM и CSS без входа, SQL и runner:

```bash
uv sync --locked --group browser
uv run --locked --group browser playwright install chromium
uv run --locked --group browser scripts/smoke_ui.py
```

Скрипт ожидает настоящий заголовок Blazor, проверяет CSS и ошибки ресурсов
`/_content/`, `/_framework/`. Ответ 401 от бизнес-API до входа ожидаем.

### Runner

```bash
uv run --locked scripts/test_env.py run runner
uv run --locked pytest tests/runner tests/dev -q
```

Первый сценарий использует fake-runner. Для OpenCode CLI задайте `runner.mode=real`,
`runner.backend=cli` в `.local/test-settings.json`, настройте provider/model/репозиторий.
Python продолжает использовать настройки wrapper; appsettings относится к C# сервисам.

```bash
uv sync --locked --group browser
uv run --locked --group browser playwright install --with-deps chromium
uv run --locked --group browser scripts/smoke_local.py
dotnet publish src/Platform.Api/Platform.Api.csproj -c Release -o artifacts/api
```

API ссылается на Platform.Ui и обслуживает static web assets: index.html, `/_framework/*`,
CSS и SPA fallback. REST/WebSocket используют тот же origin. В publish должны быть
`wwwroot/index.html` и `wwwroot/_framework`. Проверки и ограничения среды зафиксированы
в [implementation-status.md](implementation-status.md).
