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
from .presentation import format_cli_event


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
        try:
            p = await asyncio.create_subprocess_exec(self.executable, "--version",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                env=self.environment(), limit=4096)
        except OSError:
            raise RunnerError("OPENCODE_CLI_NOT_FOUND") from None
        try:
            async with asyncio.timeout(60):
                version = await p.stdout.read(4097)
                await p.wait()
        except TimeoutError:
            p.kill(); await p.wait()
            raise RunnerError("OPENCODE_CLI_VERSION_TIMEOUT") from None
        if p.returncode or len(version) > 4096:
            raise RunnerError("OPENCODE_CLI_VERSION_FAILED")
        self.version = version.decode("utf-8", errors="replace").strip()
        expected = os.environ.get("OPENCODE_CLI_VERSION", "1.2.27")
        if self.version != expected:
            raise RunnerError(f"OPENCODE_CLI_VERSION_MISMATCH: got {self.version!r}, expected {expected!r}")

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
