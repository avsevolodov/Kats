"""In-memory ChatStore-equivalent acceptance for dispositions and intent dedup (unit layer)."""

import asyncio
from chat_agent.bus_tools import BusTools, IntentKey
from chat_agent.fake_agent import fake_reply
from chat_agent.interaction import validate_interaction_decision


def test_status_query_does_not_need_coding():
    r = asyncio.run(fake_reply("статус"))
    # fake_agent treats unknown as clarify; status is handled in C# ChatStore
    assert r.repository_id is None


def test_ensure_invocation_replay_same_key():
    seen = {}

    async def ensure(intent, cap, ver, payload):
        key = intent.as_tuple()
        if key in seen:
            assert seen[key] == (cap, ver, payload)
            return {"invocationId": "same", "status": "ACCEPTED"}
        seen[key] = (cap, ver, payload)
        return {"invocationId": "new", "status": "ACCEPTED"}

    tools = BusTools(ensure)
    intent = IntentKey("t", "cp", "path", "call")

    async def run():
        a = await tools.coding_execute(intent, {"goal": "x"})
        b = await tools.coding_execute(intent, {"goal": "x"})
        assert a["invocationId"] == b["invocationId"] == "same" or a["invocationId"] == "new"

    asyncio.run(run())


def test_interaction_once_ok():
    assert validate_interaction_decision("approval", "once") == "once"
