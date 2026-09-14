# Версии тестовой инфраструктуры

| Компонент | Фиксация | Проверка |
|---|---|---|
| MSSQL Developer | mcr.microsoft.com/mssql/server:2022-CU18-ubuntu-22.04 | Compose подготовлен; pull/start ещё не выполнены |
| Temporal CLI/dev server | temporalio/temporal:1.4.1 | Release и Docker Hub tag найдены; start не выполнен |
| Keycloak | quay.io/keycloak/keycloak:26.1.4 | Compose подготовлен; import/login ещё не выполнены |
| Playwright smoke | Python playwright==1.55.0 | Скрипт подготовлен; browser E2E не выполнен |
| OpenCode | 1.2.27 | Server HITL: SSE permission.asked/question.asked + POST /permission/{id}/reply и /question/{id}/reply\|reject; CLI без HITL-моста |
| Compose | 2.30+ | Нужен raw env_file; локально Docker отсутствует |

Это dev baseline, не production compatibility approval. Остальные существующие
версии находятся в global.json, Directory.Packages.props и agents/pyproject.toml.
Для корпоративного зеркала закрепите digest выбранных images после pull/smoke.
Live gates T001/DEV006 остаются открытыми до проверки на машине разработчика.
