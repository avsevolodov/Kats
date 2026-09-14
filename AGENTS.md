# Инструкции агенту-реализатору

Работай по `specs/001-temporal-mvp/tasks.md`; отмечай пункт выполненным только после его acceptance evidence. Пользователь заказал реализацию ограниченного MVP, не всей платформы v0.2.

1. Сначала прочитай constitution, spec, plan, workflow и contracts. При противоречии между техническими файлами зарегистрируй дефект спецификации; не выдумывай гарантию восстановления.
2. C#/.NET — API, persistence, Temporal workflows/activities и UI. Python — только runner/OpenCode adapter. Сам Temporal Server остаётся штатным компонентом.
3. Не добавляй Redis, Kafka, RabbitMQ, PVC, hostPath, in-cluster БД или обязательный S3.
4. MSSQL — прикладная БД. Не реализуй неофициальный MSSQL persistence plugin Temporal. Внешний Temporal endpoint/поддерживаемая БД — prerequisite, см. research.
5. Никаких network/SQL/filesystem/DateTime.Now/Task.Run в workflow-коде. Недетерминированные действия выполняются activities. Используй supported SDK APIs и replay tests.
6. Не превращай повтор activity в повтор prompt. OperationId стабилен; RUNNING/UNKNOWN не диспетчеризуются заново.
7. Не объявляй восстановление OpenCode после потери pod реализованным. MVP recovery capabilities: survives gateway/core-worker reconnect while runner alive; runner loss requires attention.
8. Не запускай push, создание PR, внешние shell-действия и дочерних агентов. Git credentials только read-only. Не включай автоматические внешние публикации OpenCode.
9. Секреты не попадают в repo, image, command output, stream или artifacts. Helm ссылается на существующие Secrets.
10. Не строй generic plugin framework, универсальный DSL, routing mesh и abstraction для гипотетических backend. Достаточно границ IRunEventStore/IArtifactStore/IOpenCodeAdapter.
11. Релизы и image digests закрепляются после проверки в `docs/versions.md`. Не копируй пример API из main-ветки, если он отсутствует в выбранном release.
12. Параллельные задачи `[P]` обозначают независимость, а не разрешение автоматически создавать субагентов.
13. Доказательства: unit для автомата/канонизации, integration на реальном MSSQL и Temporal, protocol cross-language test, UI и crash tests. In-memory mock не доказывает транзакционные гарантии.
14. Если infrastructure недоступна, продолжай код, deterministic tests и manifests; в итоговом отчёте отдельно перечисли непроведённые live gates. Не выдавай mock за production validation.
15. Обновляй `docs/implementation-status.md`: done, test evidence, remaining, infrastructure blockers. Не меняй требования ради зелёных тестов.
