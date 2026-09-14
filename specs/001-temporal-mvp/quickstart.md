# Quickstart для реализации и передачи

Это последовательность, которую реализация должна сделать воспроизводимой. Команды сборки приложения добавляются агентом после создания проектов; сейчас их существование не заявляется.

## 1. Предпосылки

- .NET 10 SDK, Python и dependency tools pinned в `docs/versions.md`.
- Внешний тестовый MSSQL с двумя credentials: schema migration и runtime.
- Готовый Temporal endpoint/namespace; альтернатива — согласованный Temporal profile с external supported DB.
- Внутренний container registry, NuGet/PyPI/image mirrors, внутренний LLM endpoint.
- Зарегистрированный тестовый Git repository с read-only credentials и immutable commit.
- OIDC issuer/client и внутренний CA; dev fake identity только на localhost в явно включённом Development profile, никогда в k8s values.

## 2. Первое выполнение

1. Прочитать IMPLEMENTATION-PROMPT.md и выполнить T001–T004.
2. Создать solution и fake-runner vertical slice.
3. Применить SQL migrations контролируемым шагом.
4. Запустить API/worker/fake runner с real MSSQL/Temporal.
5. Выполнить Start → output → Complete, duplicate command, Cancel.
6. Подключить real OpenCode sidecar и внутреннюю модель.
7. Пройти restart/crash tests, собрать images/charts и staging profile.

## 3. Developer profile

Подготовить Docker Compose для API, worker и runner, подключающийся к внешним MSSQL/Temporal через env/secret files. Redis/database containers не включать. Если нужен disposable local Temporal dev server, это отдельный opt-in профиль тестирования, не k8s и не durability acceptance. Никакие local volumes не переносятся в Helm.

## 4. Демонстрационный сценарий

В fixture repository есть небольшой парсер и unit test. Пользователь просит добавить обработку пустой строки. OpenCode изменяет код, запускает разрешённую локальную проверку и возвращает patch. На отдельной чистой копии base commit patch применяется и тесты проходят. Preview не содержит credentials. Действий push/PR нет.

## 5. Отказоустойчивость

Во время длинного fake или real запроса удалить API pod, затем restart C# worker. Проверить счётчик prompt_sent=1 и непрерывность cursor. Отдельно удалить runner pod: ожидается NEEDS_ATTENTION, автоматического второго prompt нет. Это разные acceptance criteria.

## 6. Definition of handover

`docs/implementation-status.md` содержит версии, результаты проверок, измеренные latency, подтверждённую deployment топологию, инфраструктурные ограничения и список невыполненных live gates. README содержит фактические команды build/test/run/migrate/package/deploy. Нельзя объявить MVP завершённым только по fake runner tests.
