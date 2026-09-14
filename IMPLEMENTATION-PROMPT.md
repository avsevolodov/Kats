# Задание агенту

Реализуй первый MVP Agent Transport Platform по этому Spec Kit package.

Прочитай `AGENTS.md`, `.specify/memory/constitution.md`, затем `specs/001-temporal-mvp/{spec,plan,research,workflow,data-model,tasks}.md` и contracts. Выполняй tasks по зависимостям. Не перегенерируй спецификацию с нуля.

Создай C#/.NET 10 ASP.NET Core API и Temporal worker, Blazor WASM UI, Python runner с локальным OpenCode server, внешним MSSQL и Helm без PVC и Redis. Спроектированная единица исполнения — один OpenCode operation на Run. Агент выдаёт summary и patch без push/PR.

Первым действием реализации закрепи совместимые released-версии и проверь Temporal .NET, MSSQL transactions, Python gRPC и локальное OpenCode API. Используй готовый Temporal endpoint; если его нет, подготовь deployment профиль Temporal с внешней поддерживаемой БД. MSSQL для самого Temporal не поддерживается — не создавай обходной persistence driver.

Собери вертикальный срез с fake runner, затем подключи реальный OpenCode. Обязательно проверь дедупликацию Start/Cancel, stable OperationId, durable ACK, restart Gateway/Core worker без второго prompt живому runner. После уничтожения Python pod зафиксируй NEEDS_ATTENTION без автоматической новой генерации.

Нужны готовые solution/projects, tests, containers, charts, local developer profile, runbooks и обновлённый quickstart. Каждую отмеченную задачу подкрепляй проверкой. Не останавливай разработку из-за отсутствия deployment credentials; отдельно отрази непроведённые live checks. Не деплой внешнюю БД и не публикуй код без соответствующей авторизации.
