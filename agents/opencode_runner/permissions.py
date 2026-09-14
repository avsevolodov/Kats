"""OpenCode v1.2.27 permission API; replies never resubmit a prompt."""
import json
import re
from urllib.parse import quote
import httpx
from .core import RunnerError


class Permissions:
    def __init__(self, code, exchange):
        self.code, self.exchange = code, exchange
        self.open = {}

    async def poll(self, aborted):
        code = self.code
        result = await code.http.get("/permission", params={"directory": code.directory})
        result.raise_for_status()
        pending = {p["id"]: p for p in result.json() if p.get("sessionID") == code.session}
        for request_id, description in list(self.open.items()):
            if request_id not in pending:
                await self.exchange(request_id, description, "expired")
                del self.open[request_id]
        for request_id, request in pending.items():
            if aborted.is_set():
                return
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", request_id):
                raise RunnerError("INVALID_PERMISSION")
            # Only decision-relevant fields; no arbitrary tool metadata or credentials.
            description = json.dumps({"permission": request.get("permission"), "patterns": request.get("patterns", [])}, ensure_ascii=False, sort_keys=True)
            if len(description) > 8192:
                raise RunnerError("PERMISSION_TOO_LARGE")
            self.open[request_id] = description
            response = await self.exchange(request_id, description, "pending")
            if response.status == "pending":
                continue
            if response.status != "decided" or response.decision not in {"once", "reject"}:
                raise RunnerError("PERMISSION_STATE_UNKNOWN")
            if aborted.is_set():
                return
            # Same request ID scopes permission to this suspended tool call.
            # Never retry POST on an ambiguous response; require operator attention.
            try:
                reply = await code.http.post(f"/permission/{quote(request_id, safe='')}/reply",
                    params={"directory": code.directory}, json={"reply": response.decision})
                reply.raise_for_status()
                if reply.json() is not True:
                    raise ValueError("unexpected reply")
            except (httpx.HTTPError, ValueError):
                await self.exchange(request_id, description, "unknown")
                raise RunnerError("PERMISSION_REPLY_UNKNOWN") from None
            await self.exchange(request_id, description, "applied")
            del self.open[request_id]
