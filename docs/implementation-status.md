# Статус реализации

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
