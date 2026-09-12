import asyncio
import os
import time
import uuid
from . import runner_pb2 as pb
from .core import RunnerError, clip_utf8, result_hash
from .transport import Transport
from .workspace import Workspace
from .opencode import OpenCode
from .cli import OpenCodeCli


async def process(t, assignment, code, workspace):
    key = assignment.key
    t.abort.clear()
    sequence = 0
    safe_until = time.monotonic() + 35
    completed = False
    last_output = 0.0
    outcome = pb.OPERATION_OUTCOME_FAILED
    summary = patch = error = ""

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
                await emit(f"Шаг {i+1}\n")
            summary = "Fake runner completed. No model was called."
        else:
            await workspace.prepare(assignment)
            session = await code.create()
            ack = await t.request("begin", pb.BeginOperation(key=key, opencode_session_id=session))
            if not ack.ack.begin_authorized:
                raise RunnerError("BEGIN_NOT_AUTHORIZED")
            summary = await code.run(assignment.prompt, emit, t.abort)
            patch = await workspace.patch()
            if len(summary.encode()) > 262144: raise RunnerError("RESULT_TOO_LARGE")
        outcome = pb.OPERATION_OUTCOME_SUCCEEDED
    except Exception as exc:
        error = str(exc) if isinstance(exc, RunnerError) else "RUNNER_FAILURE"
        # Best effort stop on every non-success; never erase unknown external outcome.
        if code and code.session:
            try:
                if not await code.abort(): error = "ABORT_UNCONFIRMED"
            except Exception: error = "ABORT_UNCONFIRMED"
        if error == "CANCELLED": outcome = pb.OPERATION_OUTCOME_CANCELLED
        elif error in {"ABORT_UNCONFIRMED", "OPENCODE_TIMEOUT", "FENCED", "LEASE_EXPIRED", "RUNNER_FAILURE", "OPENCODE_CLI_INCOMPLETE", "OPENCODE_CLI_EXIT_FAILED", "OPENCODE_CLI_INVALID_JSON", "OPENCODE_CLI_ERROR"}: outcome = pb.OPERATION_OUTCOME_UNKNOWN
        summary = patch = ""
    finally:
        completed = True
        heart.cancel()
        try: await heart
        except asyncio.CancelledError: pass
    sequence += 1
    completion = pb.CompleteOperation(key=key, producer_sequence=sequence, outcome=outcome, summary=summary, patch=patch, base_commit=assignment.base_commit, error_code=error, result_sha256=result_hash(summary, patch, assignment.base_commit))
    await t.request("complete", completion, timeout=40)


async def run():
    backend = os.environ.get("OPENCODE_BACKEND", "server")
    if backend not in {"server", "cli"}:
        raise RunnerError("INVALID_OPENCODE_BACKEND")
    code = None if os.environ.get("RUNNER_MODE") == "fake" else (
        OpenCodeCli() if backend == "cli" else OpenCode(os.environ.get("OPENCODE_URL", "http://127.0.0.1:4096")))
    if code and backend == "cli":
        await code.health()
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
    t = Transport(os.environ["PLATFORM_GRPC"], os.environ["RUNNER_CA"], os.environ["RUNNER_CERT"], os.environ["RUNNER_KEY"], str(uuid.uuid4()), code.version if code else "fake")
    connection = asyncio.create_task(t.run())
    try:
        while True:
            assignment = await t.request("claim", pb.Claim(), timeout=120)
            if assignment.HasField("no_work"):
                await asyncio.sleep(assignment.no_work.retry_after_ms / 1000); continue
            await process(t, assignment.assignment, code, Workspace(os.environ.get("WORKSPACE_ROOT", "/workspace")))
            if code and code.session:
                await code.cleanup()
    finally:
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
    except KeyboardInterrupt: pass


if __name__ == "__main__":
    main()
