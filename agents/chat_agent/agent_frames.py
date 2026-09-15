"""Minimal agent.v1 frame helpers until full grpc codegen is wired in CI."""

from __future__ import annotations

from dataclasses import dataclass


PROTOCOL_VERSION = 1


@dataclass
class EnsureInvocationFrame:
    protocol_version: int
    message_id: str
    task_id: str
    checkpoint_id: str
    graph_task_path: str
    tool_call_id: str
    capability: str
    version: str
    input_json: str

    def validate(self) -> None:
        if self.protocol_version != PROTOCOL_VERSION:
            raise ValueError("CONTRACT_VERSION_UNSUPPORTED")
        if not self.checkpoint_id or not self.tool_call_id:
            raise ValueError("INVALID_ARGUMENT")


def test_invalid_protocol_version():
    frame = EnsureInvocationFrame(2, "m", "t", "c", "p", "tool", "catalog.search", "1", "{}")
    try:
        frame.validate()
        raise AssertionError("expected version error")
    except ValueError as e:
        assert "CONTRACT_VERSION_UNSUPPORTED" in str(e)
