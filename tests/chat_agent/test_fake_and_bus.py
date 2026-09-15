from chat_agent.fake_agent import fake_reply
from chat_agent.bus_tools import BusTools, IntentKey
from chat_agent.interaction import validate_interaction_decision
import asyncio


def test_fake_reply_no_repo_for_architecture_question():
    r = asyncio.run(fake_reply("Объясни архитектуру Kats"))
    assert r.repository_id is None
    assert not r.needs_coding


def test_fake_reply_coding_intent():
    r = asyncio.run(fake_reply("Исправь баг reconnect"))
    assert r.needs_coding
    assert r.capability == "coding.execute"


def test_bus_tools_stable_intent_key():
    calls = []

    async def ensure(intent, cap, ver, payload):
        calls.append((intent.as_tuple(), cap, ver, payload))
        return {"invocationId": "inv-1", "status": "PERSISTED"}

    tools = BusTools(ensure)
    intent = IntentKey("task", "cp1", "agent", "tool-1")

    async def run():
        await tools.catalog_search(intent, "reconnect")
        await tools.coding_execute(intent, {"goal": "fix"})

    asyncio.run(run())
    assert calls[0][0] == ("task", "cp1", "agent", "tool-1")
    assert calls[0][1] == "catalog.search"
    assert calls[1][1] == "coding.execute"


def test_always_rejected():
    try:
        validate_interaction_decision("permission", "always")
        raise AssertionError("fail")
    except ValueError as e:
        assert "ALWAYS_NOT_ALLOWED" in str(e)
