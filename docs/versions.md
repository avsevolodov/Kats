# Версии тестовой инфраструктуры

| Компонент | Фиксация | Проверка |
|---|---|---|
| MSSQL Developer | mcr.microsoft.com/mssql/server:2022-CU18-ubuntu-22.04 | Compose подготовлен; pull/start ещё не выполнены |
| Temporal CLI/dev server | temporalio/temporal:1.4.1 | Release и Docker Hub tag найдены; start не выполнен |
| Keycloak | quay.io/keycloak/keycloak:26.1.4 | Compose подготовлен; import/login ещё не выполнены |
| Playwright smoke | Python playwright==1.55.0 | Скрипт подготовлен; browser E2E не выполнен |
| OpenCode | 1.2.27 | Server HITL: SSE permission.asked/question.asked + POST /permission/{id}/reply и /question/{id}/reply\|reject; CLI без HITL-моста |
| Compose | 2.30+ | Нужен raw env_file; локально Docker отсутствует |
| uv (Windows agent) | C:\Program Files\uv\uv.exe → 0.12.13 | sync/lock 2026-09-15 |
| deepagents | 0.7.12 | pinned after uv lock; HarnessProfile kats-chat-v1 excludes shell/FS/execute/task |
| langgraph | 1.2.11 | via lock; checkpointer adapter kats-checkpoint-v1 |
| langchain-core | 1.6.3 | via lock |
| langchain-openai | 0.3.34 | OpenAI-compatible client when CHAT_AGENT_BASE_URL / chatAgent.baseUrl set |


Feature 002 pins above are post-smoke for import/harness/profile; live LLM tool-calling eval (T021) remains open without model endpoint (2B).

Это dev baseline, не production compatibility approval. Остальные существующие
версии находятся в global.json, Directory.Packages.props и agents/pyproject.toml.
Для корпоративного зеркала закрепите digest выбранных images после pull/smoke.
Live gates T001/DEV006 остаются открытыми до проверки на машине разработчика.
