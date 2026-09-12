# Статус реализации

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
