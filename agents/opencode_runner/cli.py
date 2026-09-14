"""Local OpenCode CLI adapter. POSIX process groups; no server/attach or replay.

Wire fixture: OpenCode v1.2.27 run.ts (NDJSON text/step_finish/error).
"""
import asyncio
import json
import os
from pathlib import Path
import signal
import uuid
from .core import PromptGuard, RunnerError
from .logutil import LOG
from .presentation import format_cli_event, format_runner

_VERSION_BYTES = 4096
_DIAG_SNIP = 512
VERSION_TIMEOUT_S = 20  # product default; tests may monkeypatch


def _diag_snip(data: bytes) -> str:
    """Bounded one-line snippet for logs; never treat as secret channel."""
    text = data[:_DIAG_SNIP].decode("utf-8", errors="replace")
    return " ".join(text.split())


class OpenCodeCli:
    def __init__(self):
        self.executable = os.environ.get("OPENCODE_BIN", "opencode")
        self.directory = str(Path(os.environ.get("WORKSPACE_ROOT", "/workspace")).resolve() / "current")
        self.version = "unknown"
        self.session = None  # Wrapper execution token, NOT an OpenCode session ID.
        self.process = None
        self.guard = PromptGuard()
        self.interrupted = False
        self.timeout = 20 * 60

    def environment(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith(
            ("ConnectionStrings__", "Oidc__", "Security__", "Runner__", "Temporal__",
             "RUNNER_", "PLATFORM_", "GIT_"))}
        env.pop("OPENCODE_SERVER_PASSWORD", None)
        # Match MVP tool scope; provider configuration is supplied by the operator.
        env["OPENCODE_PERMISSION"] = json.dumps({"*": "deny", "read": "allow",
            "glob": "allow", "grep": "allow", "edit": "allow"})
        return env

    async def health(self):
        if os.name != "posix":
            raise RunnerError("CLI_REQUIRES_POSIX_OR_WSL")
        LOG.info("OpenCode CLI version check starting bin=%s timeout=%ss",
                 self.executable, VERSION_TIMEOUT_S)
        try:
            p = await asyncio.create_subprocess_exec(
                self.executable, "--version",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                env=self.environment(), limit=_VERSION_BYTES)
        except OSError:
            LOG.error("OpenCode CLI not found bin=%s", self.executable)
            raise RunnerError("OPENCODE_CLI_NOT_FOUND") from None
        out = err = b""
        try:
            async with asyncio.timeout(VERSION_TIMEOUT_S):
                out, err = await p.communicate()
        except TimeoutError:
            p.kill()
            try:
                out, err = await asyncio.wait_for(p.communicate(), 1)
            except TimeoutError:
                try:
                    await asyncio.wait_for(p.wait(), 1)
                except TimeoutError:
                    pass
                out, err = out or b"", err or b""
            LOG.error(
                "OpenCode CLI version timeout bin=%s stdout=%r stderr=%r",
                self.executable, _diag_snip(out or b""), _diag_snip(err or b""))
            raise RunnerError("OPENCODE_CLI_VERSION_TIMEOUT") from None
        out = out or b""
        err = err or b""
        if p.returncode or len(out) > _VERSION_BYTES or len(err) > _VERSION_BYTES:
            LOG.error(
                "OpenCode CLI version failed bin=%s rc=%s stdout=%r stderr=%r",
                self.executable, p.returncode, _diag_snip(out), _diag_snip(err))
            raise RunnerError("OPENCODE_CLI_VERSION_FAILED")
        # Some CLIs print --version to stderr; prefer stdout when present.
        stdout_text = out.decode("utf-8", errors="replace").strip()
        stderr_text = err.decode("utf-8", errors="replace").strip()
        self.version = stdout_text or stderr_text
        if not self.version:
            LOG.error("OpenCode CLI version empty bin=%s", self.executable)
            raise RunnerError("OPENCODE_CLI_VERSION_FAILED")
        self.version = version.decode("utf-8", errors="replace").strip()
        expected = os.environ.get("OPENCODE_CLI_VERSION", "1.2.27")
        if self.version != expected:
            LOG.error(
                "OpenCode CLI version mismatch got=%r expected=%r bin=%s",
                self.version, expected, self.executable)
            raise RunnerError("OPENCODE_CLI_VERSION_MISMATCH")
        LOG.info("OpenCode CLI version ok %s bin=%s", self.version, self.executable)

    async def create(self):
        self.guard = PromptGuard()
        self.process = None
        self.interrupted = False
        self.session = "cli-" + str(uuid.uuid4())
        return self.session

    async def run(self, prompt, emit, abort_requested):
        if abort_requested.is_set():
            raise RunnerError("CANCELLED")
        self.guard.begin_send()
        model = os.environ.get("OPENCODE_MODEL", "")
        provider = os.environ.get("OPENCODE_PROVIDER", "internal")
        if not model:
            raise RunnerError("OPENCODE_MODEL_REQUIRED")
        try:
            self.process = await asyncio.create_subprocess_exec(
                self.executable, "run", "--format", "json", "--model", f"{provider}/{model}",
                "--title", self.session, cwd=self.directory, env=self.environment(),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, start_new_session=True, limit=1024*1024)
        except OSError:
            raise RunnerError("OPENCODE_CLI_START_FAILED") from None
        p = self.process
        await emit(format_runner("CLI запущен"))

        async def collect():
            p.stdin.write(prompt.encode("utf-8"))
            await p.stdin.drain()
            p.stdin.close()
            parts = []
            size = 0
            reason = None
            while line := await p.stdout.readline():
                try:
                    event = json.loads(line)
                    if not isinstance(event, dict):
                        raise ValueError()
                except (ValueError, UnicodeDecodeError):
                    raise RunnerError("OPENCODE_CLI_INVALID_JSON") from None
                kind = event.get("type")
                part = event.get("part", {})
                if kind == "error":
                    raise RunnerError("OPENCODE_CLI_ERROR")
                if kind == "text":
                    text = part.get("text")
                    if not isinstance(text, str):
                        raise RunnerError("OPENCODE_CLI_INVALID_JSON")
                    size += len(text.encode("utf-8"))
                    if size > 262144:
                        raise RunnerError("RESULT_TOO_LARGE")
                    parts.append(text)
                    # Keep platform preview frame limits independent of CLI text size.
                    for offset in range(0, len(text), 2048):
                        await emit(text[offset:offset+2048])
                elif kind == "step_finish":
                    reason = part.get("reason") if isinstance(part, dict) else None
                    marker = format_cli_event(kind, part if isinstance(part, dict) else {})
                    if marker:
                        await emit(marker)
                elif kind == "step_start":
                    reason = None
                    marker = format_cli_event(kind, part if isinstance(part, dict) else {})
                    if marker:
                        await emit(marker)
                elif kind == "tool" or (isinstance(part, dict) and part.get("type") == "tool"):
                    # Sanitized name + path/pattern only; never raw payloads or reasoning.
                    marker = format_cli_event("tool", part if isinstance(part, dict) else {})
                    if marker:
                        await emit(marker)
                # Reasoning and raw stderr stay off the UI stream.
            await p.wait()
            if p.returncode != 0:
                raise RunnerError("OPENCODE_CLI_EXIT_FAILED")
            if reason != "stop":
                raise RunnerError("OPENCODE_CLI_INCOMPLETE")
            return "".join(parts)

        work = asyncio.create_task(collect())
        cancelled = asyncio.create_task(abort_requested.wait())
        try:
            async with asyncio.timeout(self.timeout):
                done, _ = await asyncio.wait((work, cancelled), return_when=asyncio.FIRST_COMPLETED)
                if work in done:
                    return await work
                await self.abort()
                raise RunnerError("ABORT_UNCONFIRMED")
        except TimeoutError:
            raise RunnerError("OPENCODE_TIMEOUT") from None
        finally:
            await self.abort()
            work.cancel(); cancelled.cancel()
            await asyncio.gather(work, cancelled, return_exceptions=True)

    async def abort(self):
        p = self.process
        if p is not None and p.returncode is None:
            self.interrupted = True
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(p.wait(), 3)
            except TimeoutError:
                pass
            # Also terminate children remaining in the group after leader exit.
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await p.wait()
        return not self.interrupted

    async def cleanup(self):
        await self.abort()
        self.session = None

    async def close(self):
        await self.abort()
