import asyncio
import json
import os
import time
from pathlib import Path
import httpx
from .core import RunnerError, PromptGuard
from .presentation import format_new_message_parts, format_runner

_WAIT_PROGRESS_S = 20
_CONFIRM_TIMEOUT_S = 5 * 60


def sanitize_ask_payload(kind: str, properties: dict) -> dict:
    """Safe UI payload: no secrets, bounded size."""
    if kind == "permission":
        patterns = properties.get("patterns") or []
        if not isinstance(patterns, list):
            patterns = []
        patterns = [str(p)[:200] for p in patterns[:20]]
        tool = properties.get("tool")
        return {
            "permission": str(properties.get("permission") or properties.get("permissionID") or "")[:200],
            "patterns": patterns,
            "tool": str(tool)[:200] if tool is not None else None,
        }
    questions = properties.get("questions") or []
    if not isinstance(questions, list):
        questions = []
    safe_questions = []
    for q in questions[:10]:
        if not isinstance(q, dict):
            continue
        safe_questions.append({
            "header": str(q.get("header") or "")[:200],
            "question": str(q.get("question") or "")[:1000],
            "options": [str(o)[:200] for o in (q.get("options") or [])[:20]] if isinstance(q.get("options"), list) else [],
        })
    return {"questions": safe_questions}


class OpenCode:
    def __init__(self, url="http://127.0.0.1:4096", transport=None):
        auth = ("opencode", os.environ["OPENCODE_SERVER_PASSWORD"]) if os.environ.get("OPENCODE_SERVER_PASSWORD") else None
        self.http = httpx.AsyncClient(base_url=url, auth=auth, transport=transport, timeout=10)
        self.directory = str(Path(os.environ.get("WORKSPACE_ROOT", "/workspace")).resolve() / "current")
        self.session = None
        self.version = "unknown"
        self.guard = PromptGuard()
        self._asks: asyncio.Queue | None = None
        self.event_channel_failed = False

    async def health(self):
        r = await self.http.get("/global/health"); r.raise_for_status()
        if not r.json().get("healthy"):
            raise RunnerError("OPENCODE_UNHEALTHY")
        self.version = r.json().get("version", "unknown")

    async def create(self):
        self.guard = PromptGuard()
        self.event_channel_failed = False
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

    async def reply_permission(self, request_id: str, decision: str):
        r = await self.http.post(
            f"/permission/{request_id}/reply",
            params={"directory": self.directory},
            json={"reply": decision},
        )
        r.raise_for_status()

    async def reply_question(self, request_id: str, decision: str, answers_json: str = ""):
        if decision == "reject":
            r = await self.http.post(f"/question/{request_id}/reject", params={"directory": self.directory})
        else:
            answers = json.loads(answers_json or "[]")
            r = await self.http.post(
                f"/question/{request_id}/reply",
                params={"directory": self.directory},
                json={"answers": answers},
            )
        r.raise_for_status()

    async def run(self, prompt, emit, abort_requested, *, request_confirmation=None, wait_confirmation=None):
        self.guard.begin_send()
        provider = os.environ.get("OPENCODE_PROVIDER", "internal")
        model = os.environ.get("OPENCODE_MODEL", "")
        uncertain = False
        self._asks = asyncio.Queue()
        try:
            r = await self.http.post(f"/session/{self.session}/prompt_async", params={"directory": self.directory}, json={"parts": [{"type": "text", "text": prompt}], "model": {"providerID": provider, "modelID": model}})
            r.raise_for_status()
        except (httpx.TimeoutException, httpx.TransportError):
            uncertain = True  # query the same session; NEVER send prompt again
        deadline = time.monotonic() + 20*60
        last_text = ""
        seen_parts: set[str] = set()
        last_activity = time.monotonic()
        # Message polling is the reliable source for text + sanitized tool/step markers.
        # SSE carries permission/question asks for HITL (not a second prompt path).
        events = asyncio.create_task(self.events(abort_requested))
        try:
            while time.monotonic() < deadline:
                if self.event_channel_failed:
                    stopped = await self.abort()
                    raise RunnerError("PERMISSION_CHANNEL_LOST" if stopped else "ABORT_UNCONFIRMED")
                if abort_requested.is_set():
                    stopped = await self.abort()
                    raise RunnerError("CANCELLED" if stopped else "ABORT_UNCONFIRMED")
                while self._asks is not None and not self._asks.empty():
                    ask = self._asks.get_nowait()
                    await self._handle_ask(ask, abort_requested, request_confirmation, wait_confirmation)
                r = await self.http.get(f"/session/{self.session}/message", params={"directory": self.directory}); r.raise_for_status()
                assistants = [m for m in r.json() if m.get("info", {}).get("role") == "assistant"]
                progressed = False
                if assistants:
                    msg = assistants[-1]; info = msg["info"]
                    parts = msg.get("parts", [])
                    for marker in format_new_message_parts(parts, seen_parts):
                        await emit(marker)
                        progressed = True
                    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text")
                    if text != last_text:
                        await emit(text[len(last_text):] if text.startswith(last_text) else text)
                        last_text = text
                        progressed = True
                    if info.get("error"):
                        raise RunnerError("MODEL_ERROR")
                    state = await self.http.get("/session/status", params={"directory": self.directory}); state.raise_for_status()
                    busy = state.json().get(self.session, {}).get("type", "idle") != "idle"
                    if info.get("time", {}).get("completed") and info.get("finish") != "tool-calls" and not busy:
                        return text
                if uncertain and not assistants:
                    # A lost submit response does not justify a new generation.
                    await emit("Ожидание подтверждения результата OpenCode…\n")
                    progressed = True
                if progressed:
                    last_activity = time.monotonic()
                elif time.monotonic() - last_activity >= _WAIT_PROGRESS_S:
                    await emit(format_runner("ожидание модели…"))
                    last_activity = time.monotonic()
                await asyncio.sleep(1)
            raise RunnerError("OPENCODE_TIMEOUT")
        finally:
            events.cancel()
            try: await events
            except asyncio.CancelledError: pass
            self._asks = None

    async def _handle_ask(self, ask, abort_requested, request_confirmation, wait_confirmation):
        if request_confirmation is None or wait_confirmation is None:
            raise RunnerError("PERMISSION_REQUIRED_UNSUPPORTED")
        kind, request_id, payload = ask["kind"], ask["request_id"], ask["payload"]
        await request_confirmation(request_id, kind, json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        reply = await wait_confirmation(request_id, abort_requested, _CONFIRM_TIMEOUT_S)
        if reply is None:
            # Cancel or channel abort while waiting.
            if abort_requested.is_set():
                stopped = await self.abort()
                raise RunnerError("CANCELLED" if stopped else "ABORT_UNCONFIRMED")
            raise RunnerError("PERMISSION_TIMEOUT")
        decision = reply.get("decision") or "reject"
        answers_json = reply.get("answers_json") or ""
        try:
            if kind == "permission":
                if decision not in {"once", "always", "reject"}:
                    decision = "reject"
                await self.reply_permission(request_id, decision)
            else:
                if decision not in {"answer", "reject"}:
                    decision = "reject"
                await self.reply_question(request_id, decision, answers_json)
        except httpx.HTTPError as exc:
            raise RunnerError("PERMISSION_REPLY_FAILED") from exc

    async def events(self, abort_requested):
        try:
            async with self.http.stream("GET", "/event", params={"directory": self.directory}, timeout=None) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = json.loads(line[5:]); properties = data.get("properties", {})
                    if properties.get("sessionID") != self.session:
                        continue
                    event_type = data.get("type")
                    if event_type in {"permission.asked", "question.asked"}:
                        kind = "permission" if event_type == "permission.asked" else "question"
                        request_id = str(properties.get("id") or "")
                        if not request_id or self._asks is None:
                            continue
                        await self._asks.put({
                            "kind": kind,
                            "request_id": request_id,
                            "payload": sanitize_ask_payload(kind, properties),
                        })
        except (httpx.HTTPError, json.JSONDecodeError):
            # A failed permission event channel is not safe for unattended execution.
            self.event_channel_failed = True
            abort_requested.set()

    async def close(self):
        await self.http.aclose()

    async def cleanup(self):
        if self.session:
            result = await self.http.delete(f"/session/{self.session}", params={"directory": self.directory})
            result.raise_for_status()
            self.session = None
