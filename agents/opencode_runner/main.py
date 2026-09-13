import asyncio
import os
import sys
import time
import uuid
from . import runner_pb2 as pb
from .core import RunnerError, clip_utf8, result_hash
from .transport import Transport
from .workspace import Workspace
from .opencode import OpenCode
from .cli import OpenCodeCli


def status(message: str) -> None:
    print(f"runner: {message}", file=sys.stderr, flush=True)


async def process(t, assignment, code, workspace):
    key = assignment.key
    t.abort.clear()
    sequence = 0
    safe_until = time.monotonic() + 35
    completed = False
    last_output = 0.0
    outcome = pb.OPERATION_OUTCOME_FAILED
    summary = patch = error = ""
    status(f"claimed run={assignment.run_id} operation={key.operation_id} fence={key.fence}")

    async def heartbeat():
        nonlocal safe_until
        while not completed:
            start = time.monotonic()
            try:
                await t.request("heartbeat", pb.Heartbeat(key=key), timeout=8)
                safe_until = start + 35
            except (RunnerError, TimeoutError):
                if time.monotonic() >= safe_until:
                    t.abort.set()
            await asyncio.sleep(5)

    async def emit(text):
        nonlocal sequence, last_output
        if not text:
            return
        await asyncio.sleep(max(0, 1 - (time.monotonic()-last_output)))
        sequence += 1
        await t.request("output", pb.OutputBatch(key=key, producer_sequence=sequence, kind="preview", text=clip_utf8(text)), timeout=30)
        last_output = time.monotonic()

    heart = asyncio.create_task(heartbeat())
    try:
        if os.environ.get("RUNNER_MODE") == "fake":
            await t.request("begin", pb.BeginOperation(key=key, opencode_session_id="fake-"+key.operation_id))
            for i in range(int(os.environ.get("FAKE_STEPS", "10"))):
                if t.abort.is_set(): raise RunnerError("CANCELLED")
                await emit("[шаг] начало\n")
                await emit(f"[tool:read] path=src/step-{i+1}.cs\n")
                await emit(f"Результат шага {i+1}\n")
                await emit("[шаг] завершён (stop)\n")
            summary = "Fake runner completed. No model was called."
        else:
            status("preparing workspace")
            await workspace.prepare(assignment, t)
            session = await code.create()
            ack = await t.request("begin", pb.BeginOperation(key=key, opencode_session_id=session))
            if not ack.ack.begin_authorized:
                raise RunnerError("BEGIN_NOT_AUTHORIZED")
            status("running OpenCode")
            summary = await code.run(assignment.prompt, emit, t.abort)
            patch = await workspace.patch()
            if len(summary.encode()) > 262144: raise RunnerError("RESULT_TOO_LARGE")
        outcome = pb.OPERATION_OUTCOME_SUCCEEDED
    except Exception as exc:
        error = str(exc) if isinstance(exc, RunnerError) else "RUNNER_FAILURE"
        # Best effort stop; keep the original failure code when abort itself is unconfirmed.
        if code and code.session:
            try:
                aborted = await code.abort()
            except Exception:
                aborted = False
            if not aborted and error != "CANCELLED":
                error = f"{error}+ABORT_UNCONFIRMED"
        root = error.split("+", 1)[0]
        if root == "CANCELLED":
            outcome = pb.OPERATION_OUTCOME_CANCELLED
        elif root in {"ABORT_UNCONFIRMED", "OPENCODE_TIMEOUT", "FENCED", "LEASE_EXPIRED", "RUNNER_FAILURE",
                      "OPENCODE_CLI_INCOMPLETE", "OPENCODE_CLI_EXIT_FAILED", "OPENCODE_CLI_INVALID_JSON", "OPENCODE_CLI_ERROR"} or "ABORT_UNCONFIRMED" in error:
            outcome = pb.OPERATION_OUTCOME_UNKNOWN
        summary = patch = ""
    finally:
        completed = True
        heart.cancel()
        try: await heart
        except asyncio.CancelledError: pass
    sequence += 1
    completion = pb.CompleteOperation(key=key, producer_sequence=sequence, outcome=outcome, summary=summary, patch=patch, base_commit=assignment.base_commit, error_code=error, result_sha256=result_hash(summary, patch, assignment.base_commit))
    await t.request("complete", completion, timeout=40)
    status(f"completed outcome={pb.OperationOutcome.Name(outcome)}" + (f" error={error}" if error else ""))


async def run():
    backend = os.environ.get("OPENCODE_BACKEND", "server")
    mode = os.environ.get("RUNNER_MODE", "real")
    target = os.environ["PLATFORM_GRPC"]
    if backend not in {"server", "cli"}:
        raise RunnerError("INVALID_OPENCODE_BACKEND")
    code = None if mode == "fake" else (
        OpenCodeCli() if backend == "cli" else OpenCode(os.environ.get("OPENCODE_URL", "http://127.0.0.1:4096")))
    status(f"starting mode={mode} backend={backend} grpc={target}")
    if code and backend == "cli":
        await code.health()
        status(f"OpenCode CLI ready version={code.version}")
    elif code:
        # Startup readiness only: never retry submitting an operation/prompt here.
        try:
            async with asyncio.timeout(60):
                while True:
                    try:
                        await code.health()
                        break
                    except Exception:
                        await asyncio.sleep(1)
        except TimeoutError:
            await code.close()
            raise RunnerError("OPENCODE_STARTUP_TIMEOUT") from None
        # Fail closed on leftover sessions after Python restart: pod recreation required.
        response = await code.http.get("/session", params={"directory": code.directory})
        response.raise_for_status()
        if response.json(): raise RunnerError("LEFTOVER_SESSIONS_RECREATE_POD")
        status(f"OpenCode server ready version={code.version}")
    boot = str(uuid.uuid4())
    status(f"boot={boot[:8]} connecting")
    t = Transport(target, os.environ["RUNNER_CA"], os.environ["RUNNER_CERT"], os.environ["RUNNER_KEY"], boot, code.version if code else "fake")
    connection = asyncio.create_task(t.run())
    idle_since = time.monotonic()
    last_idle_log = 0.0
    try:
        while True:
            assignment = await t.request("claim", pb.Claim(), timeout=120)
            if assignment.HasField("no_work"):
                now = time.monotonic()
                if now - last_idle_log >= 30:
                    status(f"connected, waiting for work ({int(now - idle_since)}s)")
                    last_idle_log = now
                await asyncio.sleep(assignment.no_work.retry_after_ms / 1000); continue
            idle_since = time.monotonic()
            last_idle_log = 0.0
            await process(t, assignment.assignment, code, Workspace(os.environ.get("WORKSPACE_ROOT", "/workspace")))
            if code and code.session:
                await code.cleanup()
    finally:
        status("shutting down")
        await t.close(); connection.cancel()
        try: await connection
        except asyncio.CancelledError: pass
        if code: await code.close()


def main():
    # Turn SIGTERM into orderly cancellation so owned CLI children are stopped.
    import signal
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try: asyncio.run(run())
    except KeyboardInterrupt:
        status("interrupted")
    except RunnerError as exc:
        status(f"fatal {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
