import asyncio
import httpx
from opencode_runner.opencode import OpenCode


def test_pinned_api_adapter_sends_only_one_prompt(monkeypatch):
    calls = []
    async def handler(request):
        calls.append((request.method, request.url.path))
        path = request.url.path
        if path == "/global/health": return httpx.Response(200,json={"healthy":True,"version":"fixture"})
        if path == "/session": return httpx.Response(200,json={"id":"s1"})
        if path.endswith("prompt_async"): return httpx.Response(204)
        if path.endswith("/message"): return httpx.Response(200,json=[{"info":{"role":"assistant","finish":"stop","time":{"completed":1}},"parts":[{"type":"text","text":"done"}]}])
        if path == "/session/status": return httpx.Response(200,json={})
        if path == "/event": return httpx.Response(200,text="data: {\"type\":\"server.connected\"}\n\n")
        return httpx.Response(404)
    async def exercise():
        code=OpenCode(transport=httpx.MockTransport(handler));await code.health();await code.create()
        async def emit(text): pass
        assert await code.run("change",emit,asyncio.Event()) == "done"
        await code.close()
    asyncio.run(exercise())
    assert calls.count(("POST","/session/s1/prompt_async")) == 1


def test_lost_submit_response_is_not_retried():
    sends=[]
    async def handler(request):
        path=request.url.path
        if path=="/session": return httpx.Response(200,json={"id":"s"})
        if path.endswith("prompt_async"):
            sends.append(1);raise httpx.ReadTimeout("lost",request=request)
        if path.endswith("/message"):return httpx.Response(200,json=[{"info":{"role":"assistant","finish":"stop","time":{"completed":1}},"parts":[{"type":"text","text":"saved result"}]}])
        if path=="/session/status":return httpx.Response(200,json={})
        return httpx.Response(200,text="")
    async def exercise():
        code=OpenCode(transport=httpx.MockTransport(handler));await code.create()
        async def emit(text):pass
        assert await code.run("x",emit,asyncio.Event())=="saved result"
        await code.close()
    asyncio.run(exercise());assert len(sends)==1
