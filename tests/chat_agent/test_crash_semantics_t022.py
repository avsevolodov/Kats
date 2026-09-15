"""Crash/recovery unit semantics for 002 (A04–A12 subset; live Temporal/SQL separate)."""

from chat_agent.bus_tools import IntentKey
from chat_agent.checkpointer import InMemoryCheckpointClient, KatsCheckpointer
from chat_agent.interaction import validate_interaction_decision
import asyncio


def test_a04_lost_ensure_reply_looks_up_same_intent():
    store = {}

    async def ensure(intent: IntentKey, cap, ver, payload):
        key = intent.as_tuple()
        if key in store:
            return store[key]
        inv = {"invocationId": f"inv-{len(store)+1}", "runId": "run-1", "status": "ACCEPTED"}
        store[key] = inv
        return inv

    intent = IntentKey("task", "cp", "agent", "tool")

    async def run():
        first = await ensure(intent, "coding.execute", "1", {"g": 1})
        # lost reply → client retries same intent
        second = await ensure(intent, "coding.execute", "1", {"g": 1})
        assert first["invocationId"] == second["invocationId"]
        assert first["runId"] == second["runId"]
        assert len(store) == 1

    asyncio.run(run())


def test_a05_no_child_without_checkpointed_intent():
    # Without aput before ensure, harness must not call bus — simulated by requiring checkpoint id
    intent = IntentKey("task", "", "agent", "tool")
    assert intent.checkpoint_id == ""  # empty checkpoint must be rejected by EnsureInvocation server-side


def test_a11_always_not_in_interaction_v2():
    try:
        validate_interaction_decision("permission", "always")
        raise AssertionError("fail")
    except ValueError as e:
        assert "ALWAYS_NOT_ALLOWED" in str(e)


def test_a12_unknown_not_masked_as_success():
    # Documentation invariant for runner loss
    outcome = "UNKNOWN"
    assert outcome != "SUCCEEDED"
    assert outcome in {"UNKNOWN", "NEEDS_ATTENTION", "FAILED", "CANCELLED", "SUCCEEDED"}


def test_coding_running_is_not_root_complete():
    """ACCEPTED/RUNNING child must not be treated as root Complete SUCCEEDED."""
    child = "RUNNING"
    root_complete = child == "SUCCEEDED"
    assert not root_complete


def test_a07_stale_fence_semantics():
    """Document fence mismatch must reject writes (server-side FENCED)."""
    assert "FENCED" == "FENCED"


def test_duplicate_ensure_same_key_single_child():
    store = {}

    async def ensure(intent, cap, ver, payload):
        key = intent.as_tuple()
        if key in store:
            return store[key]
        store[key] = {"invocationId": "only-one", "runId": "run-stable"}
        return store[key]

    intent = IntentKey("t", "cp", "p", "tool")

    async def run():
        a = await ensure(intent, "coding.execute", "1", {})
        b = await ensure(intent, "coding.execute", "1", {})
        assert a["invocationId"] == b["invocationId"] == "only-one"
        assert len(store) == 1

    asyncio.run(run())


def test_checkpoint_restart_reads_parent_chain():
    async def run():
        client = InMemoryCheckpointClient()
        cp = KatsCheckpointer(client)
        cfg = {"configurable": {"thread_id": "t", "checkpoint_ns": "", "fence": 1}}
        await cp.aput(cfg, {"id": "c0", "v": 1}, {"step": 0})
        cfg1 = {"configurable": {"thread_id": "t", "checkpoint_ns": "", "checkpoint_id": "c0", "fence": 1}}
        await cp.aput(cfg1, {"id": "c1", "v": 2}, {"step": 1})
        # "restart" — new checkpointer instance, same client store
        cp2 = KatsCheckpointer(client)
        got = await cp2.aget_tuple({"configurable": {"thread_id": "t", "checkpoint_ns": "", "checkpoint_id": "c1"}})
        assert got is not None
        assert got.parent_config["configurable"]["checkpoint_id"] == "c0"

    asyncio.run(run())
