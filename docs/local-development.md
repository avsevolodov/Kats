# Запуск Kats без Kubernetes

Два режима используют тот же код и протоколы: Docker Compose запускает API с Blazor,
Temporal worker, Python runner и OpenCode; native запускает эти четыре процесса из терминалов.
Требуются доступные MSSQL, Temporal и HTTPS OIDC provider. Базы не создаются автоматически.
Redis отсутствует. Это дополнительный профиль разработки; требования Helm не изменены.

## Подготовка

Поддерживаемый host: Linux, macOS или WSL2. На Windows используйте WSL2 для runner
(Git sandbox рассчитан на POSIX). Нужны Python 3.12+, OpenSSL, Git.
Для Compose — Docker с Compose **2.30+** (`env_file.format: raw` сохраняет `$` в секретах).
Для native — .NET SDK из `global.json`, uv и проверенная версия OpenCode CLI.

Из корня репозитория:

```bash
uv run --locked scripts/dev.py init
uv sync --locked
chmod +x scripts/git-askpass.py
```

`init` создаёт `.local/settings.json`, каталоги и сертификаты разработки на 30 дней.
Повторный запуск сохраняет существующие настройки/сертификаты. CA private key не сохраняется.
Для ротации остановите процессы, переместите `.local/certs` в отдельный архив и повторите `init`.
Добавьте `.local/certs/ca.crt` в доверенные CA браузера/ОС. Сертификат API покрывает `localhost`,
`127.0.0.1` и Compose DNS `api`. Runner использует mTLS и allowlist thumbprint и в dev.

Отредактируйте `.local/settings.json`:

| Поле | Значение |
|---|---|
| `database` | Строка подключения к существующей MSSQL БД |
| `temporal.endpoint`, `namespace` | Существующий Temporal endpoint и namespace |
| `temporal.mtls` | При `true` положите `tls.crt`, `tls.key`, `ca.crt` в `.local/temporal` |
| `oidc` | HTTPS authority, client ID и secret |
| `runner.allowedHosts` | Разрешённые Git hostname через запятую |
| `runner.provider`, `model` | ID provider/model из конфигурации OpenCode |
| `images.opencode` | Доступный проверенный image с фиксированным tag/digest, содержащий команду `opencode` |
| `local` | Пути к dotnet/OpenCode; Python runner запускается через uv |

Зарегистрируйте OIDC redirect URI **`https://localhost:8443/signin-oidc`**.
Отключать проверку TLS или авторизацию не требуется. UI доступен на `https://localhost:8443`,
вход — `/login`, gRPC — `localhost:8081`. HTTPS позволяет работать secure-cookie и WebSocket.

Выполните `sql/001-initial.sql` в выбранной БД через SSMS/sqlcmd до запуска API/worker.
Учётная запись приложения должна иметь права на чтение/изменение таблиц; schema setup
выполняется отдельно пользователем с DDL правами. Скрипт создания таблиц повторяемый.
Добавьте разрешённый репозиторий (используйте собственные URL и ID):

```sql
INSERT INTO dbo.Repositories (Id, DisplayName, CloneUrl, CredentialRef, Enabled)
VALUES (NEWID(), N'Sample', N'https://github.com/your-account/sample.git', N'', 1);
```

Для приватного repo `CredentialRef` — имя файла в `.local/git-credentials`, например `sample`;
содержимое файла: JSON с `username` и `password` (read-only token), права `600`.
В UI укажите полный commit SHA доступного репозитория. Runner отклоняет репозитории
с `.opencode`, `opencode.json`, `opencode.jsonc`, symlinks, submodules и LFS по правилам MVP.

Положите проверенный provider configuration в `.local/provider/opencode.json`.
Используйте те же provider/model и ограничения инструментов, что в Kubernetes Secret
`opencode-provider`: разрешённые read/edit, запрет push/PR и произвольного shell.
Установка OpenCode/провайдера и выбор image остаются явными prerequisites — скрипт не
скачивает непроверенный `latest`. Пароль OpenCode автоматически создан в settings;
он одинаков для runner и server. Native OpenCode работает с полномочиями локального
пользователя: используйте отдельную dev-учётную запись/WSL, без рабочих секретов.

## Docker Compose

```bash
uv run --locked scripts/dev.py render compose
docker compose --env-file .local/compose.env config --quiet
docker compose --env-file .local/compose.env up --build -d
docker compose --env-file .local/compose.env logs -f
```

Не выводите полный `compose config`: он раскрывает значения env. Каталог `.local`
исключён и из Git, и из Docker build context. Настройки монтируются/передаются при запуске.
API и gRPC опубликованы только на loopback host; OpenCode не публикует порт на host.
Runner и OpenCode используют одинаковый UID/GID host и общую `.local/workspace`.
Это dev bind mount, не изменение запрета PVC/hostPath для Kubernetes.
Одновременно запускайте один runner: каталог `current` заменяется на каждой операции.

Внутри контейнера `localhost` обозначает сам контейнер. Для MSSQL/Temporal на host
укажите `host.docker.internal` в settings перед render; native использует адрес host
(например `localhost`). OIDC authority должен быть доступен под **одним HTTPS-именем**
из браузера и контейнеров. При внутренней CA используйте доверенный base image с вашей CA.
Worker запускайте при доступном Temporal; если он завершился при старте зависимости,
после её восстановления выполните `docker compose --env-file .local/compose.env up -d worker`.
Runner ждёт готовность OpenCode до 60 секунд, затем завершает запуск с явной ошибкой.
Автоматический restart runner не настроен, чтобы не скрывать потерю процесса.

Остановка:

```bash
docker compose --env-file .local/compose.env down
```

Файлы `.local` и внешние БД остаются. Не используйте `--scale runner`: каждому runner
нужны отдельные workspace и OpenCode instance.

## Native: четыре терминала

Перед первым запуском C# выполните `uv run --locked scripts/dev.py appsettings`.
API и Worker читают стандартные appsettings.json + appsettings.Development.json,
как при запуске из Rider. Последующие run не перезаписывают JSON.
Подробности и override-файлы: [Rider + uv](rider-uv.md).

### CLI: без отдельного OpenCode server

В `.local/settings.json` задайте `runner.backend: "cli"`, `runner.cliVersion: "1.2.27"`
и `local.opencode` — путь к установленному executable (или `opencode` из PATH).
Сохраните остальные поля. Запускайте только API, worker и runner:

```bash
uv run --locked scripts/dev.py run runner
```

Wrapper сам вызывает `opencode run --format json --model provider/model --title <execution-token>`
в каталоге checkout. Prompt передаётся через stdin, не через shell/аргументы процесса.
Отдельный `opencode serve`, HTTP endpoint и Docker для этого режима не нужны.
Можно подключить runner к удалённой платформе через обычные env
`OPENCODE_BACKEND=cli`, `OPENCODE_BIN`, `OPENCODE_CLI_VERSION`, `PLATFORM_GRPC` и mTLS
параметры, запустив `agent-runner` напрямую; dev launcher рассчитан на локальный API.

Путь provider config и XDG-каталоги такие же, как у dev OpenCode server. CLI-процесс
не наследует параметры платформенной БД, OIDC и Git credentials wrapper.
Разрешены read/glob/grep/edit; прочие permissions запрещены. Raw stderr, tool payloads
и reasoning не пересылаются в UI. Preview/summary формируются из JSON text events;
patch вычисляет существующий Workspace. Успех требует exit code 0 и финального
`step_finish.reason=stop`. Неполный/некорректный вывод даёт UNKNOWN.

BeginOperation сохраняется до запуска CLI. Поле session ID содержит `cli-<UUID>` —
локальный execution token wrapper, не ID сессии OpenCode. CLI не запускается повторно
для того же operation; `--continue`, `--attach`, `--share` не используются.
Отмена/таймаут завершают POSIX process group (TERM, затем KILL). После старта процесса
отмена считается неподтверждённой и даёт NEEDS_ATTENTION: внешний запрос мог продолжиться.
После аварийного SIGKILL wrapper проверьте оставшиеся процессы перед новым запуском;
автоматического восстановления сессии и workspace нет.

Совместимость JSON/stdin сверена с
[OpenCode v1.2.27 run.ts](https://github.com/anomalyco/opencode/blob/v1.2.27/packages/opencode/src/cli/cmd/run.ts).
На старте проверяется `--version`; для другой версии сначала проверьте CLI-контракт
и измените `runner.cliVersion`. Реальный OpenCode/LLM smoke ещё обязателен.
Compose продолжает использовать backend `server`: CLI-профиль предназначен для native.
Для возврата к прежнему поведению задайте `runner.backend: "server"` (default).

### Server API

Остановите Compose, настройте адреса зависимостей для host. Для каждого процесса
launcher читает settings и передаёт только его конфигурацию; source env-файлов не нужен.

```bash
# Терминал 1: API + Blazor
uv run --locked scripts/dev.py run api
# Терминал 2: Temporal worker
uv run --locked scripts/dev.py run worker
# Терминал 3: OpenCode, loopback:4096
uv run --locked scripts/dev.py run opencode
# Терминал 4: Python runner
uv run --locked scripts/dev.py run runner
```

Остановка — Ctrl+C в каждом терминале. Не запускайте native и Compose одновременно:
они используют одни host-порты и workspace. Для отладки из IDE можно выполнить
`uv run --locked scripts/dev.py render local` и импортировать `.local/local-<component>.env`
как literal environment (не исполнять через shell). Native рабочая директория
OpenCode теперь совпадает с `<repo>/.local/workspace/current`.

## Проверка и границы

```bash
curl --cacert .local/certs/ca.crt https://localhost:8443/health/live
curl --cacert .local/certs/ca.crt https://localhost:8443/health/ready
```

Затем `/login` → создать Run → preview → summary/patch. Повторите Cancel и reconnect.
`runner.mode=fake` позволяет проверить платформенный путь без модели; результат явно
обозначен fake. В текущем Compose OpenCode service всё равно запускается, поэтому
для fake без image используйте native API/worker/runner (терминал OpenCode пропустите).

Потеря runner даёт UNKNOWN/NEEDS_ATTENTION. Сохранённый dev workspace не обеспечивает
checkpoint/recovery. Если обнаружены leftover sessions, завершите активные Run и
остановите runner/OpenCode; архивируйте `.local/opencode-data` и создайте пустой каталог,
затем запустите новую пару. Не повторяйте prompt старого Run автоматически.

Источники: [Compose env_file](https://docs.docker.com/reference/compose-file/services/#env_file),
[OpenCode server](https://opencode.ai/docs/server/).
