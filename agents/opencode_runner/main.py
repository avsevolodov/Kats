import asyncio
import os
import sys
import time
import uuid
from . import runner_pb2 as pb
from .core import RunnerError, clip_utf8, result_hash
from .logutil import LOG, configure
from .presentation import clip_summary_for_preview, format_runner
from .transport import Transport
from .workspace import Workspace
from .opencode import OpenCode
from .cli import OpenCodeCli
from .local_server import LocalOpenCode


def status(message: str) -> None:
    print(f"runner: {message}", file=sys.stderr, flush=True)


async def process(t, assignment, code, workspace):
    key = assignment.key
    LOG.info("operation start id=%s", key.operation_id)
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
            await emit(format_runner("prompt отправлен"))
            for i in range(int(os.environ.get("FAKE_STEPS", "10"))):
                if t.abort.is_set(): raise RunnerError("CANCELLED")
                await emit("[шаг] начало\n")
                await emit(f"[tool:read] path=src/step-{i+1}.cs\n")
                await emit(f"Результат шага {i+1}\n")
                await emit("[шаг] завершён (stop)\n")
            summary = "Fake runner completed. No model was called."
        else:
            await emit(format_runner("подготовка репозитория…"))
            await workspace.prepare(assignment, t)
            await emit(format_runner("репозиторий готов"))
            session = await code.create()
            ack = await t.request("begin", pb.BeginOperation(key=key, opencode_session_id=session))
            if not ack.ack.begin_authorized:
                raise RunnerError("BEGIN_NOT_AUTHORIZED")
            await emit(format_runner("prompt отправлен"))
            if isinstance(code, OpenCode):
                async def request_confirmation(request_id, kind, safe_payload_json):
                    nonlocal sequence
                    sequence += 1
                    await t.request(
                        "confirmation_required",
                        pb.ConfirmationRequired(
                            key=key,
                            producer_sequence=sequence,
                            request_id=request_id,
                            kind=kind,
                            safe_payload_json=safe_payload_json,
                        ),
                        timeout=30,
                    )
                async def wait_confirmation(request_id, abort_event, timeout):
                    return await t.wait_confirmation(request_id, abort_event, timeout)
                summary = await code.run(
                    assignment.prompt,
                    emit,
                    t.abort,
                    request_confirmation=request_confirmation,
                    wait_confirmation=wait_confirmation,
                )
            else:
                summary = await code.run(assignment.prompt, emit, t.abort)
            patch = await workspace.patch()
            if len(summary.encode()) > 262144: raise RunnerError("RESULT_TOO_LARGE")
        outcome = pb.OPERATION_OUTCOME_SUCCEEDED
    except Exception as exc:
        error = str(exc) if isinstance(exc, RunnerError) else "RUNNER_FAILURE"
        if error != "CANCELLED":
            LOG.error("operation error id=%s code=%s", key.operation_id, error)
        # Best effort stop on every non-success; never erase a classified error with ABORT_UNCONFIRMED.
        if code and getattr(code, "session", None):
            try:
                confirmed = await code.abort()
            except Exception:
                confirmed = False
            if not confirmed and error in {"", "CANCELLED"}:
                error = "ABORT_UNCONFIRMED"
        if error == "CANCELLED": outcome = pb.OPERATION_OUTCOME_CANCELLED
        elif error in {"PERMISSION_TIMEOUT", "PERMISSION_REQUIRED_UNSUPPORTED", "PERMISSION_REPLY_FAILED", "PERMISSION_CHANNEL_LOST", "MODEL_ERROR", "OPENCODE_MODEL_REQUIRED", "OPENCODE_CONFIG_MISSING"}:
            outcome = pb.OPERATION_OUTCOME_FAILED
        elif error in {"ABORT_UNCONFIRMED", "OPENCODE_TIMEOUT", "FENCED", "LEASE_EXPIRED", "RUNNER_FAILURE", "OPENCODE_CLI_INCOMPLETE", "OPENCODE_CLI_EXIT_FAILED", "OPENCODE_CLI_INVALID_JSON", "OPENCODE_CLI_ERROR"}: outcome = pb.OPERATION_OUTCOME_UNKNOWN
        summary = patch = ""
    finally:
        completed = True
        heart.cancel()
        try: await heart
        except asyncio.CancelledError: pass
    # Mirror summary into the timeline so SUCCEEDED is not status-only.
    preview = clip_summary_for_preview(summary)
    if preview:
        try:
            await emit(preview)
        except (RunnerError, TimeoutError):
            LOG.warning("summary preview emit failed id=%s", key.operation_id)
    sequence += 1
    completion = pb.CompleteOperation(key=key, producer_sequence=sequence, outcome=outcome, summary=summary, patch=patch, base_commit=assignment.base_commit, error_code=error, result_sha256=result_hash(summary, patch, assignment.base_commit))
    await t.request("complete", completion, timeout=40)
    LOG.info("operation complete id=%s outcome=%s error=%s", key.operation_id, outcome, error or "-")


async def run():
    mode = os.environ.get("RUNNER_MODE", "real")
    backend = os.environ.get("OPENCODE_BACKEND", "server")
    grpc_target = os.environ.get("PLATFORM_GRPC", "")
    ssl_name = os.environ.get("PLATFORM_GRPC_SSL_NAME") or "-"
    LOG.info("runner start mode=%s backend=%s grpc=%s ssl_name=%s", mode, backend, grpc_target, ssl_name)
    if backend not in {"server", "cli"}:
        raise RunnerError("INVALID_OPENCODE_BACKEND")
    code = None if mode == "fake" else (
        OpenCodeCli() if backend == "cli" else OpenCode(os.environ.get("OPENCODE_URL", "http://127.0.0.1:4096")))
    if code and backend == "cli":
        LOG.info("OpenCode CLI health check")
        await code.health()
        status(f"OpenCode CLI ready version={code.version}")
    elif code:
        # Startup readiness only: never retry submitting an operation/prompt here.
        LOG.info("OpenCode server health wait timeout=60s")
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
        except BaseException:
            await code.close()
            raise
        # Fail closed on leftover sessions after Python restart: pod recreation required.
        response = await code.http.get("/session", params={"directory": code.directory})
        response.raise_for_status()
        if response.json(): raise RunnerError("LEFTOVER_SESSIONS_RECREATE_POD")
        LOG.info("OpenCode server health ok")
    t = Transport(os.environ["PLATFORM_GRPC"], os.environ["RUNNER_CA"], os.environ["RUNNER_CERT"], os.environ["RUNNER_KEY"], str(uuid.uuid4()), code.version if code else "fake")
    connection = asyncio.create_task(t.run())
    # Idle heartbeat: one line on enter, then every IDLE_LOG_INTERVAL_S (ops liveness without claim spam).
    idle_since = None
    idle_logged_at = None
    idle_log_interval = float(os.environ.get("RUNNER_IDLE_LOG_INTERVAL_S", "30"))
    try:
        while True:
            assignment = await t.request("claim", pb.Claim(), timeout=120)
            if assignment.HasField("no_work"):
                now = time.monotonic()
                if idle_since is None:
                    idle_since = idle_logged_at = now
                    LOG.info("waiting for work")
                elif now - idle_logged_at >= idle_log_interval:
                    idle_logged_at = now
                    LOG.info("still idle for %.0fs", now - idle_since)
                await asyncio.sleep(assignment.no_work.retry_after_ms / 1000); continue
            if idle_since is not None:
                LOG.info("work received after %.0fs idle", time.monotonic() - idle_since)
                idle_since = idle_logged_at = None
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
    configure()
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    except RunnerError as exc:
        # One-line ops signal; traceback still available via logging if re-raised elsewhere.
        print(f"runner error: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
