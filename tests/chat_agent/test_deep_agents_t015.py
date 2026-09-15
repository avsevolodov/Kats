import asyncio
from chat_agent.harness import ChatHarness, EXCLUDED_BUILTIN_TOOLS
from chat_agent.live_agent import run_recorded_turn


def test_harness_profile_excludes_shell_and_task():
    h = ChatHarness()
    name = h.register_profile()
    assert name == "kats-chat-v1"
    excluded = set(h.create_agent_kwargs()["excluded_tools"])
    assert "execute" in excluded
    assert "task" in excluded
    assert "read_file" in excluded
    assert EXCLUDED_BUILTIN_TOOLS <= excluded


def test_recorded_turn_checkpoints_before_ensure_and_bus_only():
    calls = []

    async def run():
        return await run_recorded_turn(task_id="11111111-1111-1111-1111-111111111111", goal="fix reconnect", ensure_calls=calls)

    out = asyncio.run(run())
    assert out["ensure_count"] >= 2
    assert out["tool_names"] == [
        "catalog_search",
        "repositories_describe",
        "repositories_resolve_ref",
        "code_search",
        "coding_execute",
    ]
    assert "execute" in out["excluded"]
    assert calls[0][1] == "catalog.search"
