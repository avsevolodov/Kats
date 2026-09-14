# Тестовый стенд разработчика: WSL2 + Docker Compose

Основной сценарий — Windows x64, WSL2 Ubuntu 24.04, Docker Desktop с WSL integration
либо Docker Engine внутри WSL. Исходники и процессы приложения находятся в WSL.
Работайте из Linux-каталога (например `/home/<user>/src/Kats`), не `/mnt/c`.

| Компонент | Где | Адрес с машины разработчика |
|---|---|---|
| MSSQL Developer, БД KatsDev | Compose | localhost,14333 |
| Temporal dev server + UI | Compose | localhost:7233 / http://localhost:8233 |
| Keycloak, realm kats-dev | Compose | http://localhost:8180 |
| C# API + Blazor | WSL/native | https://localhost:8443 |
| C# Temporal worker | WSL/native | Без входящего порта |
| Python wrapper, fake или OpenCode CLI | WSL/native | Исходящий mTLS к API:8081 (localhost или IP Windows-хоста из WSL) |

Выделите Docker/WSL ориентировочно 4 CPU и 8 ГБ RAM, оставьте место для SQL image
и NuGet-кэша. Нужны Git, Python 3.12 с venv, OpenSSL, .NET SDK из `global.json`,
Docker Compose 2.30+. OpenCode для первого smoke не требуется.
Контейнер MSSQL рассчитан на amd64; ARM-ноутбуки этим профилем не проверены.

## Первый запуск

В WSL из корня клона:

```bash
uv sync --locked
uv run --locked scripts/test_env.py up
```

Команда создаёт локальные сертификаты, уникальные пароли, realm/client и двух
пользователей, запускает контейнеры с ожиданием healthchecks, создаёт БД/таблицы
и SQL login `kats_dev` с правами чтения/записи. SA используется только для bootstrap.
В таблицу репозиториев добавляется **Fake smoke fixture**; его URL фиктивный,
fake-runner не выполняет Git fetch и не вызывает модель.

Конфигурация тестового профиля: `.local/test-settings.json`.
Пароли: `.local/test-infra/credentials.json` — `developer`, `other`, `admin`.
Открывайте этот файл локально; не копируйте его в тикеты/логи. Повторный `up`
сохраняет пароли и пользовательские настройки. Обычный `.local/settings.json`
не перезаписывается. Каталог `.local` исключён из Git и Docker build context.

Добавьте `.local/certs/ca.crt` в доверенные сертификаты браузера Windows.
Например скопируйте файл в Windows и выполните в терминале Windows:

```powershell
certutil -user -addstore Root C:\path\to\ca.crt
```

Это CA только для локального теста; сертификаты действуют 30 дней.
Для ручных curl-проверок достаточно `--cacert .local/certs/ca.crt`.

Запустите три процесса в отдельных WSL-терминалах:

```bash
uv run --locked scripts/test_env.py run api
uv run --locked scripts/test_env.py run worker
uv run --locked scripts/test_env.py run runner
```

Откройте https://localhost:8443/login, войдите как `developer` с созданным паролем.
Выберите Fake smoke fixture, укажите 40 букв `a` в Commit и произвольную задачу.
Ожидается SUCCEEDED примерно за 10–20 секунд и summary с явной пометкой Fake.
MSSQL, Temporal, gRPC, OIDC и браузер работают реально; заменён только агент/LLM.

## Автоматическая проверка

Инфраструктура:

```bash
uv run --locked scripts/test_env.py check
curl --cacert .local/certs/ca.crt https://localhost:8443/health/ready
```

Browser smoke при работающих API, worker и fake-runner:

```bash
uv sync --locked --group browser
uv run --locked --group browser playwright install --with-deps chromium
uv run --locked --group browser scripts/smoke_local.py
```

Smoke проверяет OIDC login → UI Start → SUCCEEDED → reload → скачивание summary,
а также запрет чтения Run/artifact вторым пользователем. Созданный Run остаётся
в истории. Тест не сохраняет browser state, пароль или trace. Игнорирование ошибки
dev-сертификата ограничено отдельным Playwright context.

Быстрые тесты без Docker:

```bash
uv run --locked pytest tests/runner tests/dev -q
```

## Реальный OpenCode

После успешного fake smoke остановите runner. Установите в WSL поддерживаемую
версию OpenCode и настройте provider по [инструкции CLI](local-development.md).
В `.local/test-settings.json` измените `runner.mode` на `real`, оставьте `backend=cli`,
задайте provider/model и путь `local.opencode`. Добавьте реальный разрешённый
репозиторий в MSSQL (пример SQL в той же инструкции), укажите полный commit.
`Fake smoke fixture` для этого режима не подходит. Затем запустите runner снова.
API/worker не требуют смены режима и могут продолжать работать.

## Остановка, данные и диагностика

Ctrl+C останавливает native-процессы. Контейнеры:

```bash
uv run --locked scripts/test_env.py down
```

Named volumes SQL, Temporal и Keycloak сохраняются. Не удаляйте `.local` отдельно
от данных: там пароли и ключи, соответствующие сохранённым БД. Автоматического reset
с удалением volumes нет. Import Keycloak не обновляет уже существующий realm;
его ручные изменения делайте через admin UI.

Если up завершился ошибкой:

```bash
docker compose -f compose.infra.yaml ps
docker compose -f compose.infra.yaml logs --tail 100 temporal keycloak
```

Проверьте WSL integration, доступ к image registry, свободные порты и RAM.
Windows браузер и WSL должны оба видеть localhost:8180 и localhost:8443 через
стандартный localhost forwarding WSL2. При VPN/сетевых ограничениях сначала
проверьте доступность этих адресов с обеих сторон. Не меняйте issuer только в API:
адрес OIDC должен совпадать с issuer Keycloak и быть доступен браузеру.
Для закрытого контура images можно задать переменными MSSQL_IMAGE, TEMPORAL_IMAGE,
KEYCLOAK_IMAGE с фиксированными версиями из зеркала; пакеты/Chromium также нужны в зеркалах.

## Границы профиля

Это отдельный локальный тестовый профиль по запросу пользователя: допускает
БД в Compose, named volumes и Temporal dev persistence SQLite. Он не используется
в Kubernetes и не заменяет production persistence Temporal. MSSQL Developer предназначен
для разработки/тестов; Compose задаёт ACCEPT_EULA=Y. Redis не добавляется.
Keycloak работает по HTTP только на loopback; API разрешает это только при
Development + явном AllowLoopbackHttp. UI остаётся HTTPS, runner — mTLS.
Отказ worker/runner и гонки отмены требуют отдельных crash tests.

В текущей среде Docker отсутствует: полноценный up и browser smoke ещё не запускались.
Проверки генерации/идемпотентности — в `docs/implementation-status.md`.

Источники: [Temporal CLI](https://docs.temporal.io/cli),
[Keycloak containers](https://www.keycloak.org/server/containers),
[SQL Server containers](https://learn.microsoft.com/en-us/sql/linux/sql-server-linux-docker-container-configure?view=sql-server-ver17).
