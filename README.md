# Agent Platform MVP — пакет GitHub Spec Kit

## Запуск приложения

Для локально установленного OpenCode без `serve` выберите в `.local/settings.json`
`runner.backend: "cli"` и запускайте `python3 scripts/dev.py run runner`.
Wrapper сам вызывает CLI; подробности и ограничения — в инструкции ниже.

Добавлены [Docker Compose и локальный запуск](docs/local-development.md):
`python3 scripts/dev.py init`, настройка `.local/settings.json`, затем
`python3 scripts/dev.py render compose` и
`docker compose --env-file .local/compose.env up --build -d`.
Native: `python3 scripts/dev.py run api|worker|opencode|runner` (по одному процессу в терминале).
Требуются MSSQL, Temporal, OIDC и настроенный OpenCode; UI — https://localhost:8443.
Актуальные ограничения проверки: [implementation-status.md](docs/implementation-status.md).

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
