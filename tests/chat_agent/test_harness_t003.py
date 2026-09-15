"""T003 spike: harness safety + optional deepagents/langgraph import smoke."""

from chat_agent.harness import ChatHarness, HarnessConfig


def test_harness_rejects_built_in_shell():
    h = ChatHarness(HarnessConfig(allow_built_in_shell=True))
    try:
        h.assert_safe_defaults()
        raise AssertionError("expected forbid")
    except RuntimeError as e:
        assert "SHELL" in str(e)


def test_harness_rejects_built_in_delegation():
    h = ChatHarness(HarnessConfig(allow_built_in_delegation=True))
    try:
        h.assert_safe_defaults()
        raise AssertionError("expected forbid")
    except RuntimeError as e:
        assert "DELEGATION" in str(e)


def test_create_agent_kwargs_disable_flags():
    kwargs = ChatHarness().create_agent_kwargs()
    assert kwargs["disable_shell"] is True
    assert kwargs["disable_subagents"] is True
    assert "execute" in kwargs["excluded_tools"]
    assert kwargs["builtin_tools"] == []


def test_langgraph_import_smoke():
    import langgraph
    import langchain_core
    import langgraph.checkpoint
    assert langchain_core is not None
    assert langgraph.checkpoint is not None
    from langgraph.checkpoint.base import BaseCheckpointSaver
    assert BaseCheckpointSaver is not None


def test_deepagents_import_or_skip():
    try:
        import deepagents  # noqa: F401
    except Exception as e:
        # Pin may need adjustment after uv sync; surface clearly for T003 evidence
        raise AssertionError(f"deepagents import failed: {e}") from e
