# Agent Platform MVP — пакет GitHub Spec Kit

## Запуск приложения

Основной сценарий разработки: [Rider + uv](docs/rider-uv.md).
Следующий этап: [разрешения OpenCode через UI и локальный server wrapper](docs/permissions.md).
API запускает hosted Blazor WASM: отдельный UI-процесс не нужен.

Для нового разработчика: [тестовый стенд WSL2](docs/developer-test-environment.md).
`uv run --locked scripts/test_env.py up` поднимает MSSQL, Temporal и Keycloak, создаёт БД
и пользователей; далее процессы ниже в отдельных терминалах.
Первый тест coding Run работает без OpenCode/LLM; затем можно включить CLI backend.

Для локально установленного OpenCode без `serve` выберите в `.local/settings.json`
`runner.backend: "cli"` и запускайте `uv run --locked scripts/dev.py run runner`.
Wrapper сам вызывает CLI; подробности и ограничения — в [local-development.md](docs/local-development.md).

Добавлены [Docker Compose и локальный запуск](docs/local-development.md):
`uv run --locked scripts/dev.py init`, настройка `.local/settings.json`, затем
`uv run --locked scripts/dev.py render compose` и
`docker compose --env-file .local/compose.env up --build -d`.

**Native (по одному процессу в терминале):**

| # | Процесс | Команда / заметка |
| --- | --- | --- |
| 1 | API + Blazor | `uv run --locked scripts/dev.py run api` — UI `https://localhost:8443/` (чат), `/runs` |
| 2 | Worker | `uv run --locked scripts/dev.py run worker` — RunWorkflow + TaskWorkflow |
| 3 | OpenCode | `uv run --locked scripts/dev.py run opencode` — для coding / legacy Run |
| 4 | OpenCode runner | `uv run --locked scripts/dev.py run runner` — claim **Run**, не чат |
| 5 | **Chat Agent** | `uv run --locked scripts/dev.py run chat-agent` — claim **`chat.root`**; без него диалог после `START_TASK` не обрабатывается |

Требуются MSSQL (схема до `sql/007`), Temporal, OIDC; для coding — OpenCode.  
Актуальный статус: [implementation-status.md](docs/implementation-status.md).

### Chat Agent (обязателен для диалога `/`)

OpenCode runner **не** видит задачи чата. После `START_TASK` в Worker нужен отдельный Chat Agent
(сертификаты те же, что у runner — `dev.py` подставляет `.local/certs/runner/*`):

```bash
# предпочтительно (WSL: берёт local.platformGrpc, например 172.x:8081, снимает HTTP_PROXY)
CHAT_AGENT_MODE=fake uv run --locked scripts/dev.py run chat-agent
CHAT_AGENT_MODE=live uv run --locked scripts/dev.py run chat-agent

# прямой запуск: читает .local/settings.json → local.platformGrpc, grpc.enable_http_proxy=0
uv run --locked chat-agent --mode live
```

В `.local/settings.json` для WSL+API на Windows и для LLM Chat Agent:

```json
"local": { "platformGrpc": "172.17.112.1:8081" },
"chatAgent": {
  "provider": "kaspersky_llm",
  "model": "qwen3.6-35b-a3b",
  "baseUrl": "https://llm.example.internal/v1"
}
```

API key **не** в JSON: `CHAT_AGENT_API_KEY` или файл `.local/chat-agent/api-key`. Без `chatAgent` / key при `--mode live` задача завершится `FAILED` (`MODEL_NOT_CONFIGURED`), без fake «Уточните цель…».

Не используйте `localhost:8081` из WSL NAT — это Linux, не Windows. Корпоративный `HTTP_PROXY` для gRPC снимается автоматически.

Версия пакета: 1.0 • 12.09.2026 • Статус: спецификация для реализации, не готовое приложение.

## Зафиксированный стек

| Слой | MVP |
| --- | --- |
| API, orchestration, Temporal workflows/activities | C# / .NET 10 |
| UI | Blazor WebAssembly / C#, ASP.NET Core host |
| Агент | Python wrapper + OpenCode server sidecar |
| Orchestration backend | Temporal Server |
| Данные платформы, журнал, ограниченные artifacts | Внешний MSSQL |
| Streaming | gRPC bidi runner↔API; WebSocket browser↔API; MSSQL replay |
| Размещение | Kubernetes, Helm, без PVC/hostPath |
| Временные данные | emptyDir с лимитами; потеря pod допустима только с явным состоянием результата |
| Redis | Отсутствует во всех профилях MVP |

**Инфраструктурное ограничение:** штатный Temporal Server не поддерживает MSSQL persistence. Для выбранного Temporal требуется либо готовый внешний Temporal endpoint, либо Temporal в Kubernetes с внешней поддерживаемой БД (предлагается PostgreSQL для persistence и visibility). Это новая инфраструктурная предпосылка, а не согласованная замена MSSQL. При запрете любой дополнительной БД и отсутствии готового Temporal endpoint требования несовместимы. Агент продолжает разработку, но не объявляет deployment готовым и не разворачивает PostgreSQL самовольно. Подробнее: [research.md](specs/001-temporal-mvp/research.md).

## Что реализовать

Первый вертикальный сценарий: пользователь выбирает зарегистрированный read-only Git-репозиторий и commit, задаёт изменение, видит прогресс Python/OpenCode, получает summary и patch. Пользователь может отменить Run или восстановить UI после обрыва. Gateway и C# worker можно перезапускать без повторной отправки prompt живому OpenCode. При потере Python pod Run требует внимания; незавершённые tools/LLM не переисполняются автоматически.

Push, PR, CI-интеграция, дочерние агенты и прозрачное восстановление OpenCode после потери pod — за границами MVP. Это намеренное сужение большого концепта.

## Порядок чтения

1. [AGENTS.md](AGENTS.md) и [.specify/memory/constitution.md](.specify/memory/constitution.md).
2. [spec.md](specs/001-temporal-mvp/spec.md) — пользовательские истории и требования.
3. [plan.md](specs/001-temporal-mvp/plan.md), [research.md](specs/001-temporal-mvp/research.md).
4. [data-model.md](specs/001-temporal-mvp/data-model.md), [workflow.md](specs/001-temporal-mvp/workflow.md), [contracts](specs/001-temporal-mvp/contracts/README.md).
5. [opencode-adapter.md](specs/001-temporal-mvp/opencode-adapter.md), [kubernetes.md](specs/001-temporal-mvp/kubernetes.md).
6. [tasks.md](specs/001-temporal-mvp/tasks.md) — исполняемый порядок реализации.
7. [quickstart.md](specs/001-temporal-mvp/quickstart.md), [acceptance.md](specs/001-temporal-mvp/checklists/acceptance.md).

Готовое задание агенту: [IMPLEMENTATION-PROMPT.md](IMPLEMENTATION-PROMPT.md).

## Использование со Spec Kit

Это заполненный feature package в структуре Spec Kit: constitution, spec, plan, research, data-model, contracts, quickstart, tasks. Официальные CLI-скрипты и шаблоны Spec Kit не скопированы и не установлены в архив; можно реализовывать по документам напрямую.

Если нужен официальный harness, сначала выберите и закрепите release Specify CLI во внутреннем зеркале. Проверьте `specify init --help` именно этой версии, создайте scaffolding в отдельной временной директории с нужной agent integration и перенесите команды/скрипты без перезаписи заполненных документов. Не используйте force-init поверх пакета. У разных версий отличаются параметры и имена slash-команд; используйте фактически сгенерированные. [Официальный Spec Kit](https://github.com/github/spec-kit)

Feature branch: `001-temporal-mvp`. Следующий шаг harness — анализ согласованности уже заполненных spec/plan/tasks и реализация, а не повторная генерация требований с потерей решений.

## Ограничение готовности

Документы и контракты проверены структурно. Приложение, gRPC code generation, Helm deployment и live OpenCode в рамках подготовки пакета не запускались. Точные released-версии зависимостей фиксирует агент в T001–T004 после smoke tests; использование `latest` запрещено.

## Следующий этап: диалоговый оркестратор

[Спецификация 002](specs/002-conversational-orchestrator/README.md): чат → контекст/репозиторий → шина → Coding Agent → ответ. Code/unit в дереве; live A01–A18 открыты — [Progress Map](docs/implementation-status.md).

**Локально:** SQL `005`–`007` → API + Worker → **Chat Agent (терминал 5)** → UI `/`. Runner/OpenCode нужны для `coding.execute`, не для claim чата. См. раздел «Chat Agent» выше и [local-development.md](docs/local-development.md) / [chat-agent-ops.md](docs/chat-agent-ops.md).
