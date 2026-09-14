import asyncio
import json
import httpx
import pytest
from opencode_runner.opencode import OpenCode, sanitize_ask_payload
from opencode_runner.core import RunnerError


def test_sanitize_permission_strips_metadata():
    payload = sanitize_ask_payload("permission", {
        "permission": "bash",
        "patterns": ["rm *", "secret"],
        "tool": "bash",
        "metadata": {"token": "secret-value"},
    })
    assert payload == {"permission": "bash", "patterns": ["rm *", "secret"], "tool": "bash"}
    assert "token" not in json.dumps(payload)


def test_permission_ask_waits_for_ui_reply_then_continues():
    calls = []
    replies = {"posted": False}
    async def handler(request):
        calls.append((request.method, request.url.path))
        path = request.url.path
        if path == "/global/health":
            return httpx.Response(200, json={"healthy": True, "version": "1.2.27"})
        if path == "/session":
            return httpx.Response(200, json={"id": "s1"})
        if path.endswith("prompt_async"):
            return httpx.Response(204)
        if path == "/event":
            body = (
                'data: {"type":"permission.asked","properties":{"id":"perm1","sessionID":"s1","permission":"bash","patterns":["ls"]}}\n\n'
                'data: {"type":"server.connected","properties":{}}\n\n'
            )
            return httpx.Response(200, text=body)
        if path == "/permission/perm1/reply":
            replies["posted"] = True
            return httpx.Response(204)
        if path.endswith("/message"):
            if not replies["posted"]:
                return httpx.Response(200, json=[{"info": {"role": "assistant", "finish": "tool-calls"}, "parts": []}])
            return httpx.Response(200, json=[{
                "info": {"role": "assistant", "finish": "stop", "time": {"completed": 1}},
                "parts": [{"type": "text", "text": "done after confirm"}],
            }])
        if path == "/session/status":
            return httpx.Response(200, json={"s1": {"type": "idle" if replies["posted"] else "busy"}})
        if path.endswith("/abort"):
            return httpx.Response(204)
        return httpx.Response(404)

    async def exercise():
        code = OpenCode(transport=httpx.MockTransport(handler))
        await code.create()
        asked = []
        async def request_confirmation(request_id, kind, payload):
            asked.append((request_id, kind, json.loads(payload)))
        async def wait_confirmation(request_id, abort, timeout):
            await asyncio.sleep(0)
            return {"request_id": request_id, "decision": "once", "answers_json": ""}
        preview = []
        async def emit(text):
            preview.append(text)
        result = await code.run("x", emit, asyncio.Event(), request_confirmation=request_confirmation, wait_confirmation=wait_confirmation)
        await code.close()
        assert result == "done after confirm"
        assert asked == [("perm1", "permission", {"permission": "bash", "patterns": ["ls"], "tool": None})]
        assert replies["posted"]
        assert ("POST", "/permission/perm1/reply") in calls

    asyncio.run(exercise())


def test_sse_channel_loss_fail_closed():
    async def handler(request):
        path = request.url.path
        if path == "/session":
            return httpx.Response(200, json={"id": "s1"})
        if path.endswith("prompt_async"):
            return httpx.Response(204)
        if path == "/event":
            return httpx.Response(500)
        if path.endswith("/message"):
            return httpx.Response(200, json=[])
        if path == "/session/status":
            return httpx.Response(200, json={"s1": {"type": "idle"}})
        if path.endswith("/abort"):
            return httpx.Response(204)
        return httpx.Response(404)

    async def exercise():
        code = OpenCode(transport=httpx.MockTransport(handler))
        await code.create()
        async def emit(text):
            pass
        with pytest.raises(RunnerError, match="PERMISSION_CHANNEL_LOST"):
            await code.run(
                "x",
                emit,
                asyncio.Event(),
                request_confirmation=lambda *a, **k: asyncio.sleep(0),
                wait_confirmation=lambda *a, **k: asyncio.sleep(0),
            )
        await code.close()

    asyncio.run(exercise())
