import asyncio
import os
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit
from .core import RunnerError


class Workspace:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.repo = self.root / "current"

    async def git(self, *args, cwd=None, env=None):
        process = await asyncio.create_subprocess_exec("git", "-c", "core.hooksPath=/dev/null", "-c", "protocol.file.allow=never", *args,
            cwd=cwd, env=env or self.environment(), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            out, _ = await asyncio.wait_for(process.communicate(), 90)
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
        if process.returncode:
            raise RunnerError("GIT_FAILED")
        return out

    def environment(self):
        # No inherited credential helper, proxy auth, hooks, or Git global config.
        return {"PATH": os.environ["PATH"], "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "LANG": "C.UTF-8"}

    async def prepare(self, assignment):
        url = urlsplit(assignment.clone_url)
        allowed = set(filter(None, os.environ.get("GIT_ALLOWED_HOSTS", "").split(",")))
        if url.scheme != "https" or url.username or url.password or url.hostname not in allowed:
            raise RunnerError("REPOSITORY_NOT_ALLOWED")
        if not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", assignment.base_commit):
            raise RunnerError("INVALID_COMMIT")
        if self.repo.exists():
            shutil.rmtree(self.repo)
        self.root.mkdir(parents=True, exist_ok=True)
        self.repo.mkdir()
        await self.git("init", str(self.repo))
        env = self.environment()
        # Optional askpass is mounted into Python only; never write credentials into .git/config.
        if assignment.credential_ref:
            if not re.fullmatch(r"[A-Za-z0-9_-]+", assignment.credential_ref):
                raise RunnerError("INVALID_CREDENTIAL_REF")
            env["GIT_ASKPASS"] = os.environ["GIT_ASKPASS"]
            env["GIT_CREDENTIAL_FILE"] = str(Path(os.environ["GIT_CREDENTIAL_DIR"]) / assignment.credential_ref)
        await self.git("fetch", "--depth=1", assignment.clone_url, assignment.base_commit, cwd=self.repo, env=env)
        await self.git("checkout", "--detach", "FETCH_HEAD", cwd=self.repo)
        head = (await self.git("rev-parse", "HEAD", cwd=self.repo)).decode().strip()
        if head != assignment.base_commit:
            raise RunnerError("COMMIT_MISMATCH")
        for p in self.repo.rglob("*"):
            if p.is_symlink():
                raise RunnerError("SYMLINK_UNSUPPORTED")
        if (self.repo / ".gitmodules").exists():
            raise RunnerError("SUBMODULE_UNSUPPORTED")
        # Conservative pilot gate: do not execute repository-provided OpenCode configuration.
        if any((self.repo / n).exists() for n in [".opencode", "opencode.json", "opencode.jsonc"]):
            raise RunnerError("REPOSITORY_AGENT_CONFIG_UNSUPPORTED")
        for p in self.repo.rglob(".gitattributes"):
            if "filter=lfs" in p.read_text(errors="ignore"):
                raise RunnerError("LFS_UNSUPPORTED")
        if sum(p.stat().st_size for p in self.repo.rglob("*") if p.is_file()) > 512*1024*1024:
            raise RunnerError("REPOSITORY_TOO_LARGE")

    async def patch(self):
        for p in self.repo.rglob("*"):
            if p.is_symlink():
                raise RunnerError("SYMLINK_UNSUPPORTED")
        await self.git("add", "--intent-to-add", "--all", cwd=self.repo)
        # Includes newly-created text files; refuses binary changes.
        raw = await self.git("diff", "--no-ext-diff", "--no-textconv", "HEAD", "--", cwd=self.repo)
        if b"Binary files " in raw or b"GIT binary patch" in raw:
            raise RunnerError("BINARY_PATCH_UNSUPPORTED")
        if len(raw) > 4*1024*1024:
            raise RunnerError("RESULT_TOO_LARGE")
        return raw.decode("utf-8", errors="strict")
