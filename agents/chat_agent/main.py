"""Chat Agent process: fake / live Deep Agents loop over agent.v1."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path

from chat_agent.fake_agent import fake_reply
from chat_agent.harness import ChatHarness, HarnessConfig
from chat_agent.config import ChatAgentConfigError

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CERT_DIR = _REPO_ROOT / ".local" / "certs" / "runner"


def _mtls_path(env_key: str, filename: str) -> str:
    value = os.environ.get(env_key)
    if value:
        return value
    candidate = _DEFAULT_CERT_DIR / filename
    if candidate.is_file():
        return str(candidate)
    raise SystemExit(
        f"Missing {env_key} (and no {candidate}). "
        f"Run: CHAT_AGENT_MODE=fake uv run --locked scripts/dev.py run chat-agent\n"
        f"Or set RUNNER_CA / RUNNER_CERT / RUNNER_KEY (same as OpenCode runner)."
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="chat-agent")
    parser.add_argument("--mode", choices=("fake", "live"), default=os.environ.get("CHAT_AGENT_MODE", "fake"))
    args = parser.parse_args(argv)
    harness = ChatHarness(
        HarnessConfig(model=os.environ.get("CHAT_AGENT_MODEL") or os.environ.get("CHAT_MODEL", "openai-compatible"))
    )
    harness.assert_safe_defaults()
    if args.mode == "fake" and not os.environ.get("PLATFORM_GRPC") and not (_DEFAULT_CERT_DIR / "ca.crt").is_file():
        result = asyncio.run(fake_reply("ping"))
        print(result.text, flush=True)
        return
    asyncio.run(run_loop(args.mode))


async def run_loop(mode: str) -> None:
    from chat_agent.grpc_env import resolve_platform_grpc, scrub_proxy_env
    from chat_agent.live_agent import run_live_assignment
    from chat_agent.transport import AgentTransport

    target, ssl_name = resolve_platform_grpc()
    scrub_proxy_env(target)
    os.environ["PLATFORM_GRPC"] = target
    if ssl_name:
        os.environ["PLATFORM_GRPC_SSL_NAME"] = ssl_name
    ca = _mtls_path("RUNNER_CA", "ca.crt")
    cert = _mtls_path("RUNNER_CERT", "tls.crt")
    key = _mtls_path("RUNNER_KEY", "tls.key")
    boot = str(uuid.uuid4())
    print(f"chat-agent connecting target={target} ssl_name={ssl_name or '-'}", file=sys.stderr, flush=True)
    t = AgentTransport(target, ca, cert, key, boot)
    reader = asyncio.create_task(t.run_reader())
    try:
        await t.wait_ready(60)
    except TimeoutError:
        t.closing = True
        reader.cancel()
        raise SystemExit(
            f"chat-agent: gRPC hello timeout to {target}. "
            f"Check API on Windows, local.platformGrpc in .local/settings.json, and that HTTP_PROXY is not used."
        ) from None
    print(f"chat-agent connected mode={mode} target={target}", file=sys.stderr, flush=True)
    idle_ticks = 0
    try:
        while True:
            frame = await t.claim()
            if frame.HasField("no_work"):
                idle_ticks += 1
                if idle_ticks == 1 or idle_ticks % 30 == 0:
                    print(f"chat-agent idle (no claimable chat.root) ticks={idle_ticks}", file=sys.stderr, flush=True)
                await asyncio.sleep(1)
                continue
            idle_ticks = 0
            if frame.HasField("error"):
                print(f"claim error {frame.error.code}", file=sys.stderr, flush=True)
                await asyncio.sleep(1)
                continue
            a = frame.assignment
            print(f"chat-agent claimed task={a.task_id} invocation={a.invocation_id}", file=sys.stderr, flush=True)
            await t.heartbeat(a.invocation_id, a.fence)
            try:
                if mode == "live":
                    outcome = await run_live_assignment(t, a)
                else:
                    from chat_agent.live_agent import split_goal_resume, summarize_resume

                    goal, resume = split_goal_resume(a.goal or "")
                    if resume and (resume.get("children") or resume.get("decisions")):
                        summary = summarize_resume(resume)
                        outcome = {
                            "assistantText": f"Resume: {summary}" if summary else "Resume after wait.",
                            "needsCoding": False,
                            "mode": "fake-resume",
                            "disposition": "complete",
                            "checks": [{"name": "build", "outcome": "not_run"}],
                            "resume": resume,
                        }
                    else:
                        reply = await fake_reply(goal)
                        if reply.needs_coding:
                            await t.suspend(a.invocation_id, f"cp-fake-{a.invocation_id}", [])
                            print(f"suspended invocation={a.invocation_id} mode=fake-coding", file=sys.stderr, flush=True)
                            continue
                        outcome = {
                            "assistantText": reply.text,
                            "needsCoding": reply.needs_coding,
                            "capability": reply.capability,
                            "checks": [{"name": "build", "outcome": "not_run"}],
                            "mode": "fake",
                            "disposition": "complete",
                        }
            except ChatAgentConfigError as cfg_err:
                print(
                    f"chat-agent config/llm error code={cfg_err.code} invocation={a.invocation_id}",
                    file=sys.stderr,
                    flush=True,
                )
                fail_result = {
                    "assistantText": cfg_err.safe_message,
                    "errorCode": cfg_err.code,
                    "checks": [{"name": "build", "outcome": "not_run"}],
                    "mode": mode,
                    "disposition": "failed",
                }
                await t.complete(
                    a.invocation_id,
                    "FAILED",
                    fail_result,
                    error_code=cfg_err.code,
                    safe_message=cfg_err.safe_message,
                )
                print(f"completed FAILED invocation={a.invocation_id} code={cfg_err.code}", file=sys.stderr, flush=True)
                continue
            except Exception as exc:  # noqa: BLE001
                print(
                    f"chat-agent assignment error type={type(exc).__name__} invocation={a.invocation_id}",
                    file=sys.stderr,
                    flush=True,
                )
                safe = "Chat Agent failed while processing the task."
                fail_result = {
                    "assistantText": safe,
                    "errorCode": "MODEL_UNAVAILABLE",
                    "checks": [{"name": "build", "outcome": "not_run"}],
                    "mode": mode,
                    "disposition": "failed",
                }
                await t.complete(
                    a.invocation_id,
                    "FAILED",
                    fail_result,
                    error_code="MODEL_UNAVAILABLE",
                    safe_message=safe,
                )
                print(f"completed FAILED invocation={a.invocation_id} code=MODEL_UNAVAILABLE", file=sys.stderr, flush=True)
                continue
            if outcome.get("disposition") == "suspended":
                print(f"suspended invocation={a.invocation_id} mode={outcome.get('mode')}", file=sys.stderr, flush=True)
                continue
            await t.complete(a.invocation_id, "SUCCEEDED", outcome)
            print(f"completed invocation={a.invocation_id} mode={outcome.get('mode')}", file=sys.stderr, flush=True)

    finally:
        t.closing = True
        reader.cancel()


if __name__ == "__main__":
    main()
