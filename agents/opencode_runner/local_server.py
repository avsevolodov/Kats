"""Run an installed OpenCode as a private local HTTP process (WSL/POSIX)."""
import asyncio
import json
import os
import secrets
import signal
import socket
from pathlib import Path
import httpx
from .cli import OpenCodeCli
from .core import RunnerError
from .opencode import OpenCode


class LocalOpenCode(OpenCode):
    def __init__(self):
        super().__init__(trust_env=False)
        self.child = None

    async def health(self):
        if self.child is None:
            cli = OpenCodeCli()
            await cli.health()
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            password = secrets.token_urlsafe(32)
            Path(self.directory).mkdir(parents=True, exist_ok=True)
            env = cli.environment()
            env["OPENCODE_SERVER_PASSWORD"] = password
            env["OPENCODE_SERVER_USERNAME"] = "opencode"
            env["OPENCODE_PERMISSION"] = json.dumps({"*": "ask", "read": "allow", "glob": "allow", "grep": "allow", "task": "deny", "question": "deny"})
            self.child = await asyncio.create_subprocess_exec(cli.executable, "serve", "--hostname", "127.0.0.1", "--port", str(port),
                env=env, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL, start_new_session=True)
            await self.http.aclose()
            self.http = httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", auth=("opencode", password), timeout=10, trust_env=False)
        if self.child.returncode is not None:
            raise RunnerError("LOCAL_OPENCODE_EXITED")
        await super().health()

    async def close(self):
        try:
            await super().close()
        finally:
            if self.child and self.child.returncode is None:
                try:
                    os.killpg(self.child.pid, signal.SIGTERM)
                    await asyncio.wait_for(self.child.wait(), 5)
                except TimeoutError:
                    os.killpg(self.child.pid, signal.SIGKILL)
                    await self.child.wait()
                except ProcessLookupError:
                    await self.child.wait()
