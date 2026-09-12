import asyncio
import json
import os
import time
import httpx
from .core import RunnerError, PromptGuard


class OpenCode:
    def __init__(self, url="http://127.0.0.1:4096", transport=None):
        auth = ("opencode", os.environ["OPENCODE_SERVER_PASSWORD"]) if os.environ.get("OPENCODE_SERVER_PASSWORD") else None
        self.http = httpx.AsyncClient(base_url=url, auth=auth, transport=transport, timeout=10)
        self.directory = "/workspace/current"
        self.session = None
        self.version = "unknown"
        self.guard = PromptGuard()

    async def health(self):
        r = await self.http.get("/global/health"); r.raise_for_status()
        if not r.json().get("healthy"):
            raise RunnerError("OPENCODE_UNHEALTHY")
        self.version = r.json().get("version", "unknown")

    async def create(self):
        self.guard = PromptGuard()
        r = await self.http.post("/session", params={"directory": self.directory}, json={"title": "Agent Platform operation"})
        r.raise_for_status(); self.session = r.json()["id"]
        return self.session

    async def abort(self):
        if not self.session:
            return True
        r = await self.http.post(f"/session/{self.session}/abort", params={"directory": self.directory})
        r.raise_for_status()
        # HTTP acceptance alone does not establish the operation stopped.
        for _ in range(15):
            s = await self.http.get("/session/status", params={"directory": self.directory}); s.raise_for_status()
            status = s.json().get(self.session, {}).get("type", "idle")
            if status == "idle":
                return True
            await asyncio.sleep(1)
        return False

    async def run(self, prompt, emit, abort_requested):
        self.guard.begin_send()
        provider = os.environ.get("OPENCODE_PROVIDER", "internal")
        model = os.environ.get("OPENCODE_MODEL", "")
        uncertain = False
        try:
            r = await self.http.post(f"/session/{self.session}/prompt_async", params={"directory": self.directory}, json={"parts": [{"type": "text", "text": prompt}], "model": {"providerID": provider, "modelID": model}})
            r.raise_for_status()
        except (httpx.TimeoutException, httpx.TransportError):
            uncertain = True  # query the same session; NEVER send prompt again
        deadline = time.monotonic() + 20*60
        last_text = ""
        # Message polling is the reliable fallback; SSE supplies progress previews only.
        events = asyncio.create_task(self.events(emit, abort_requested))
        try:
            while time.monotonic() < deadline:
                if abort_requested.is_set():
                    stopped = await self.abort()
                    raise RunnerError("CANCELLED" if stopped else "ABORT_UNCONFIRMED")
                r = await self.http.get(f"/session/{self.session}/message", params={"directory": self.directory}); r.raise_for_status()
                assistants = [m for m in r.json() if m.get("info", {}).get("role") == "assistant"]
                if assistants:
                    msg = assistants[-1]; info = msg["info"]
                    text = "".join(p.get("text", "") for p in msg.get("parts", []) if p.get("type") == "text")
                    if text != last_text:
                        await emit(text[len(last_text):] if text.startswith(last_text) else text)
                        last_text = text
                    if info.get("error"):
                        raise RunnerError("MODEL_ERROR")
                    state = await self.http.get("/session/status", params={"directory": self.directory}); state.raise_for_status()
                    busy = state.json().get(self.session, {}).get("type", "idle") != "idle"
                    if info.get("time", {}).get("completed") and info.get("finish") != "tool-calls" and not busy:
                        return text
                if uncertain and not assistants:
                    # A lost submit response does not justify a new generation.
                    await emit("Ожидание подтверждения результата OpenCode…\n")
                await asyncio.sleep(1)
            raise RunnerError("OPENCODE_TIMEOUT")
        finally:
            events.cancel()
            try: await events
            except asyncio.CancelledError: pass

    async def events(self, emit, abort_requested):
        try:
            async with self.http.stream("GET", "/event", params={"directory": self.directory}, timeout=None) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = json.loads(line[5:]); properties = data.get("properties", {})
                    if properties.get("sessionID") != self.session:
                        continue
                    if data.get("type") in {"permission.asked", "question.asked"}:
                        self.permission_required = True
                        abort_requested.set()
        except (httpx.HTTPError, json.JSONDecodeError):
            # A failed permission event channel is not safe for unattended execution.
            self.event_channel_failed = True
            abort_requested.set()

    async def close(self):
        await self.http.aclose()
