import asyncio
from types import SimpleNamespace
import httpx
import pytest
from opencode_runner.permissions import Permissions
from opencode_runner.core import RunnerError


def test_wait_decision_delivery_and_session_isolation():
    async def exercise():
        pending = [{"id": "per_1", "sessionID": "ours", "permission": "edit", "patterns": ["a.cs"]},
                   {"id": "per_other", "sessionID": "other", "permission": "bash", "patterns": ["evil"]}]
        posts, exchanges = [], []
        decision = ""
        async def handler(req):
            assert req.url.params["directory"] == "/work"
            if req.method == "GET": return httpx.Response(200, json=pending)
            posts.append(req)
            pending.pop(0)
            return httpx.Response(200, json=True)
        async def exchange(id, description, phase):
            assert id == "per_1" and "evil" not in description
            exchanges.append(phase)
            return SimpleNamespace(status="decided" if decision else "pending", decision=decision)
        async with httpx.AsyncClient(base_url="http://local", transport=httpx.MockTransport(handler)) as http:
            p = Permissions(SimpleNamespace(http=http, session="ours", directory="/work"), exchange)
            await p.poll(asyncio.Event())
            assert not posts
            decision = "once"
            await p.poll(asyncio.Event())
            await p.poll(asyncio.Event())
            assert len(posts) == 1 and posts[0].url.path == "/permission/per_1/reply"
            assert exchanges == ["pending", "pending", "applied"]
    asyncio.run(exercise())


@pytest.mark.parametrize("decision", ["once", "reject"])
def test_ambiguous_reply_is_not_retried(decision):
    async def exercise():
        phases, posts = [], []
        async def handler(req):
            if req.method == "GET": return httpx.Response(200, json=[{"id": "per_1", "sessionID": "s", "permission": "edit", "patterns": ["a"]}])
            posts.append(req)
            raise httpx.ReadTimeout("lost response")
        async def exchange(id, description, phase):
            phases.append(phase)
            return SimpleNamespace(status="decided", decision=decision)
        async with httpx.AsyncClient(base_url="http://local", transport=httpx.MockTransport(handler)) as http:
            p = Permissions(SimpleNamespace(http=http, session="s", directory="/work"), exchange)
            with pytest.raises(RunnerError, match="PERMISSION_REPLY_UNKNOWN"):
                await p.poll(asyncio.Event())
            assert phases == ["pending", "unknown"] and len(posts) == 1
    asyncio.run(exercise())


def test_cancel_prevents_reply_after_decision_and_missing_request_expires():
    async def exercise():
        abort = asyncio.Event()
        pending = [{"id": "per_1", "sessionID": "s", "permission": "edit", "patterns": ["a"]}]
        phases = []
        async def handler(req):
            assert req.method == "GET"
            return httpx.Response(200, json=pending)
        async def exchange(id, description, phase):
            phases.append(phase)
            abort.set()
            return SimpleNamespace(status="decided", decision="once")
        async with httpx.AsyncClient(base_url="http://local", transport=httpx.MockTransport(handler)) as http:
            p = Permissions(SimpleNamespace(http=http, session="s", directory="/work"), exchange)
            await p.poll(abort)
            pending.clear()
            await p.poll(abort)
            assert phases == ["pending", "expired"]
    asyncio.run(exercise())
