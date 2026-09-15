"""T004 checkpointer conformance (in-memory client). Live MSSQL is a separate gate."""

import asyncio
from chat_agent.checkpointer import (
    CODEC_VERSION,
    InMemoryCheckpointClient,
    KatsCheckpointer,
    decode_payload,
    encode_payload,
)


def test_codec_roundtrip():
    raw = encode_payload({"messages": [{"role": "user", "content": "hi"}]})
    body = decode_payload(raw)
    assert body["messages"][0]["content"] == "hi"


def test_incompatible_codec_rejected():
    bad = b'{"codec":"other","body":{}}'
    try:
        decode_payload(bad)
        raise AssertionError("expected incompatible")
    except ValueError as e:
        assert "INCOMPATIBLE_CODEC" in str(e)


def test_put_get_parent_and_pending_writes():
    async def run():
        client = InMemoryCheckpointClient()
        cp = KatsCheckpointer(client)
        parent = {
            "configurable": {"thread_id": "t1", "checkpoint_ns": "", "fence": 1},
        }
        parent_ckpt = {"id": "c0", "channel_values": {"x": 1}}
        cfg0 = await cp.aput(parent, parent_ckpt, {"step": 0})
        child_cfg = {
            "configurable": {
                "thread_id": "t1",
                "checkpoint_ns": "",
                "checkpoint_id": "c0",
                "fence": 1,
            }
        }
        child_ckpt = {"id": "c1", "channel_values": {"x": 2}}
        cfg1 = await cp.aput(child_cfg, child_ckpt, {"step": 1})
        await cp.aput_writes(cfg1, [("tools", {"name": "catalog.search"})], task_id="node-a")
        got = await cp.aget_tuple(cfg1)
        assert got is not None
        assert got.checkpoint["id"] == "c1"
        assert got.parent_config["configurable"]["checkpoint_id"] == "c0"
        assert got.pending_writes
        assert got.metadata["step"] == 1
        listed = await cp.alist({"configurable": {"thread_id": "t1", "checkpoint_ns": ""}})
        assert len(listed) >= 2
        # identical replay ok
        await cp.aput(child_cfg, child_ckpt, {"step": 1})
        # conflict on changed payload
        try:
            await cp.aput(child_cfg, {"id": "c1", "channel_values": {"x": 99}}, {"step": 1})
            raise AssertionError("conflict expected")
        except ValueError as e:
            assert "CONFLICT" in str(e)
        assert CODEC_VERSION.startswith("kats-checkpoint")

    asyncio.run(run())


def test_memory_client_not_sql_evidence():
    """Document that this file alone must not close T004 live SQL gate."""
    assert "InMemoryCheckpointClient" == InMemoryCheckpointClient.__name__
