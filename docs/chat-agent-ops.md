# Chat Agent workload notes (T023)

Feature flag: `Chat:Enabled` (default true in Development; set false for rollback of new chat tasks).

## Prerequisites (local)

1. MSSQL: applied `sql/005` → `006` → `007` (иначе Worker: `ConversationCommands` missing). See [local-development.md](local-development.md).
2. Running **API** (`:8443` / gRPC `:8081`) and **Worker** (TaskWorkflow + chat inbox).
3. Same mTLS material as OpenCode runner (`RUNNER_CA`, `RUNNER_CERT`, `RUNNER_KEY`); thumbprint in `Chat:AllowedThumbprints` or `Runner:AllowedThumbprints`.
4. Optional for coding: runner + OpenCode (or CLI backend).
5. **Required for `--mode live`:** `chatAgent` in `.local/settings.json` (`provider`, `model`, `baseUrl`) plus API key via `CHAT_AGENT_API_KEY` or file `.local/chat-agent/api-key` (chmod 600). Without model config the agent sends `Complete(FAILED, error_code=MODEL_NOT_CONFIGURED)` — there is **no** recorded-fallback / «Уточните цель…» reply on the bus path.

## Native run (after uv sync)

Preferred (sets mTLS + PLATFORM_GRPC like OpenCode runner; strips HTTP_PROXY):

```bash
CHAT_AGENT_MODE=fake uv run --locked scripts/dev.py run chat-agent
CHAT_AGENT_MODE=live uv run --locked scripts/dev.py run chat-agent
```

Direct `uv run --locked chat-agent --mode live` also reads `local.platformGrpc` from `.local/settings.json` (e.g. `172.17.112.1:8081` on WSL) and disables gRPC HTTP proxy. Do not rely on `localhost:8081` from WSL NAT.

Deep Agents profile `kats-chat-v1` excludes ls/read_file/write_file/edit_file/delete/glob/grep/execute/task and disables general-purpose subagent. Bus tools only.

Recorded eval (no live model):

```text
"C:\Program Files\uv\uv.exe" run --locked python scripts/run_eval_recorded.py
```

`CHAT_AGENT_MODE=fake` without gRPC remains a local smoke (`fake_reply("ping")` only). On a bus-connected agent (`dev.py run chat-agent`), **live** requires LLM config; missing config → `Complete(FAILED)` + ConversationEvent `AgentError`, not a fabricated assistant success. When coding is needed after a real model turn, the agent **Suspend**s the root invocation (`WAITING_CHILD`) instead of `Complete(SUCCEEDED)`. Resume after `SIGNAL_CHILD_COMPLETED` → `ReconcileTaskChildren` re-queues root claim (`[[KATS_RESUME]]` on next Assignment). Live Temporal/OpenCode gates remain open until staging (T029).

Environment:

- `CHAT_AGENT_MODE=fake|live`
- `CHAT_AGENT_PROVIDER` / `CHAT_AGENT_MODEL` / `CHAT_AGENT_BASE_URL` (from `settings.chatAgent` via `dev.py`)
- `CHAT_AGENT_API_KEY` (env or `.local/chat-agent/api-key`; never in settings.json)
- Gateway mTLS same class as runner (internal)

## UI / streams

- Default page: Conversations `/` (no RepositoryId required).
- Diagnostics: `/runs` and `/runs/{id}` (legacy Run stream `/api/v1/stream`).
- Chat events: `/api/v2/stream` (WS) + REST `.../events?afterSequence=`.

Helm: add Deployment `chat-agent` referencing existing Secrets for model credentials; no Redis/PVC/S3 required.
Drain active chat executions before incompatible graph/codec upgrade (definition version on AgentTasks).

Rollout: additive SQL 005–007 → ChatEnabled=false → enable handlers → fake chat-agent → pilot allowlist → ChatEnabled=true.
Rollback: ChatEnabled=false stops new tasks; history and `/api/v1/runs` remain.
