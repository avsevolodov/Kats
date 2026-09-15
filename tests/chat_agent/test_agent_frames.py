from chat_agent.agent_frames import EnsureInvocationFrame, PROTOCOL_VERSION


def test_valid_frame():
    EnsureInvocationFrame(PROTOCOL_VERSION, "m", "t", "c", "p", "tool", "catalog.search", "1", "{}").validate()


def test_missing_checkpoint_rejected():
    try:
        EnsureInvocationFrame(PROTOCOL_VERSION, "m", "t", "", "p", "tool", "catalog.search", "1", "{}").validate()
        raise AssertionError("fail")
    except ValueError as e:
        assert "INVALID_ARGUMENT" in str(e)
