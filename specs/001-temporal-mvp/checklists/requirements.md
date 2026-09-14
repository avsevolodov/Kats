# Specification readiness

- [x] Язык основного слоя, UI и агентного адаптера определён.
- [x] Temporal выбран, а incompatibility MSSQL persistence явно выделена как INF-001.
- [x] Redis и PVC исключены из MVP/deployment.
- [x] MVP сужен до одного operation, summary/patch без push/PR.
- [x] Durable acceptance отделён от workflow start и completion.
- [x] API/C# worker recovery отделён от Python/OpenCode pod loss.
- [x] Есть stable IDs, cancel race, lease fencing и lost ACK semantics.
- [x] Есть machine-readable REST/protobuf и browser-stream contract.
- [x] Все FR-001–FR-018 сопоставлены с tasks/acceptance.
- [x] Временное хранение результатов в MSSQL ограничено и отмечено как MVP deviation от S3-концепта.
- [ ] INF-001 фактически обеспечен владельцем окружения.
- [ ] T001–T004 подтвердили версии и live integration.

Незаполненные пункты — gates реализации/окружения. Структурная готовность документов не равна готовности deployment.
