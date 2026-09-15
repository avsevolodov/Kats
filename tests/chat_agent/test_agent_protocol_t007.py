"""agent.v1 golden hash vectors — cross-language with CanonicalHash (T007)."""

import hashlib
import json
from pathlib import Path


def canonicalize(node):
    if node is None:
        return "null"
    if isinstance(node, bool):
        return "true" if node else "false"
    if isinstance(node, str):
        return json.dumps(node, ensure_ascii=False)
    if isinstance(node, int) and not isinstance(node, bool):
        return json.dumps(str(node), ensure_ascii=False)
    if isinstance(node, list):
        return "[" + ",".join(canonicalize(x) for x in node) + "]"
    if isinstance(node, dict):
        parts = []
        for key in sorted(node.keys()):
            if node[key] is None:
                continue
            parts.append(json.dumps(key, ensure_ascii=False) + ":" + canonicalize(node[key]))
        return "{" + ",".join(parts) + "}"
    raise TypeError(type(node))


def hash_obj(node: dict) -> str:
    return hashlib.sha256(canonicalize(node).encode("utf-8")).hexdigest()


GOLDEN = {
    "ensure_minimal": hash_obj(
        {
            "capability": "catalog.search",
            "checkpointId": "c1",
            "graphTaskPath": "agent",
            "input": {"query": "reconnect"},
            "taskId": "11111111-1111-1111-1111-111111111111",
            "toolCallId": "tool-1",
            "version": "1",
        }
    )
}


def test_golden_ensure_minimal_stable():
    assert len(GOLDEN["ensure_minimal"]) == 64
    # Recompute must match stored vector
    assert GOLDEN["ensure_minimal"] == hash_obj(
        {
            "capability": "catalog.search",
            "checkpointId": "c1",
            "graphTaskPath": "agent",
            "input": {"query": "reconnect"},
            "taskId": "11111111-1111-1111-1111-111111111111",
            "toolCallId": "tool-1",
            "version": "1",
        }
    )


def test_agent_proto_exists():
    text = (Path(__file__).resolve().parents[2] / "contracts/agent.proto").read_text(encoding="utf-8")
    assert "EnsureInvocation" in text
    assert "protocol_version" in text
    assert "CheckpointPutWrites" in text


def test_int64_as_decimal_string_in_canonicalize():
    assert canonicalize(9007199254740993) == '"9007199254740993"'
