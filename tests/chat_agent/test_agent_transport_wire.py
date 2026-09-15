"""Unit tests for chat agent transport/proto wiring."""

from chat_agent import agent_pb2 as pb


def test_assignment_includes_goal():
    a = pb.Assignment(
        invocation_id="i",
        task_id="t",
        conversation_id="c",
        definition_version="chat-v1",
        model_profile="fake",
        fence=1,
        goal="Исправь баг",
    )
    assert a.goal.startswith("Исправ")


def test_ensure_invocation_fields():
    e = pb.EnsureInvocation(
        task_id="t",
        checkpoint_id="cp",
        graph_task_path="agent",
        tool_call_id="tool-1",
        capability="coding.execute",
        version="1",
        input_json="{}",
    )
    assert e.capability == "coding.execute"


def test_agent_channel_stub_exists():
    from chat_agent import agent_pb2_grpc as rpc
    assert hasattr(rpc, "AgentChannelStub")
