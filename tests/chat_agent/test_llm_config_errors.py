"""Unit: missing LLM config → MODEL_NOT_CONFIGURED; no recorded-fallback text."""

from __future__ import annotations

import asyncio
import json
import os

import pytest

from chat_agent.config import ChatAgentConfigError, load_llm_config
from chat_agent import agent_pb2 as pb


def test_load_llm_config_missing_base_url(monkeypatch):
    monkeypatch.delenv("CHAT_AGENT_BASE_URL", raising=False)
    monkeypatch.delenv("CHAT_MODEL_BASE_URL", raising=False)
    monkeypatch.setenv("CHAT_AGENT_MODEL", "m1")
    monkeypatch.setenv("CHAT_AGENT_API_KEY", "k1")
    with pytest.raises(ChatAgentConfigError) as ei:
        load_llm_config()
    assert ei.value.code == "MODEL_NOT_CONFIGURED"
    assert "baseUrl" in ei.value.safe_message


def test_complete_proto_error_fields_roundtrip():
    msg = pb.Complete(
        invocation_id="11111111-1111-1111-1111-111111111111",
        status="FAILED",
        result_json='{"errorCode":"MODEL_NOT_CONFIGURED"}',
        error_code="MODEL_NOT_CONFIGURED",
        safe_message="Chat Agent LLM is not configured.",
    )
    wire = msg.SerializeToString()
    back = pb.Complete()
    back.ParseFromString(wire)
    assert back.error_code == "MODEL_NOT_CONFIGURED"
    assert back.safe_message.startswith("Chat Agent")
    assert back.status == "FAILED"


def test_live_assignment_fails_without_model_no_fake_fallback(monkeypatch):
    monkeypatch.delenv("CHAT_AGENT_BASE_URL", raising=False)
    monkeypatch.delenv("CHAT_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("CHAT_AGENT_MODEL", raising=False)
    monkeypatch.delenv("CHAT_MODEL", raising=False)
    monkeypatch.delenv("CHAT_AGENT_API_KEY", raising=False)
    monkeypatch.delenv("CHAT_MODEL_API_KEY", raising=False)

    from chat_agent.live_agent import run_live_assignment

    class _A:
        task_id = "t1"
        invocation_id = "i1"
        fence = 1
        goal = "Объясни архитектуру"

    with pytest.raises(ChatAgentConfigError) as ei:
        asyncio.run(run_live_assignment(None, _A()))
    assert ei.value.code == "MODEL_NOT_CONFIGURED"
    assert "Уточните цель" not in ei.value.safe_message
    assert "репозиторий не выбран" not in ei.value.safe_message.lower()


def test_transport_complete_includes_error_fields():
    msg = pb.Complete(
        invocation_id="i",
        status="FAILED",
        result_json="{}",
        error_code="MODEL_NOT_CONFIGURED",
        safe_message="missing",
    )
    assert "error_code" in [f.name for f in pb.Complete.DESCRIPTOR.fields]
    dumped = json.loads(msg.result_json or "{}")
    assert dumped == {}
