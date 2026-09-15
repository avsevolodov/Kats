"""Chat Agent LLM settings from env (set by scripts/dev.py from settings.chatAgent)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_API_KEY_FILE = _REPO / ".local" / "chat-agent" / "api-key"


class ChatAgentConfigError(Exception):
    """Bus-facing config/LLM failure: Complete(FAILED) with error_code + safe_message."""

    def __init__(self, code: str, safe_message: str):
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


@dataclass(frozen=True)
class LlmConfig:
    provider: str
    model: str
    base_url: str
    api_key: str


def _read_api_key() -> str:
    key = (os.environ.get("CHAT_AGENT_API_KEY") or os.environ.get("CHAT_MODEL_API_KEY") or "").strip()
    if key:
        return key
    if _API_KEY_FILE.is_file():
        return _API_KEY_FILE.read_text(encoding="utf-8").strip()
    return ""


def load_llm_config() -> LlmConfig:
    """Require provider/model/baseUrl + API key for bus-connected live path."""
    provider = (
        os.environ.get("CHAT_AGENT_PROVIDER")
        or os.environ.get("CHAT_MODEL_PROVIDER")
        or ""
    ).strip()
    model = (os.environ.get("CHAT_AGENT_MODEL") or os.environ.get("CHAT_MODEL") or "").strip()
    base_url = (
        os.environ.get("CHAT_AGENT_BASE_URL") or os.environ.get("CHAT_MODEL_BASE_URL") or ""
    ).strip()
    api_key = _read_api_key()
    missing = []
    if not base_url:
        missing.append("baseUrl")
    if not model:
        missing.append("model")
    if not api_key:
        missing.append("apiKey")
    if missing:
        raise ChatAgentConfigError(
            "MODEL_NOT_CONFIGURED",
            "Chat Agent LLM is not configured ("
            + ", ".join(missing)
            + "). Set chatAgent in settings and CHAT_AGENT_API_KEY (or .local/chat-agent/api-key).",
        )
    return LlmConfig(
        provider=provider or "openai_compatible",
        model=model,
        base_url=base_url,
        api_key=api_key,
    )


def build_model():
    """Build OpenAI-compatible chat model; raises ChatAgentConfigError if incomplete."""
    cfg = load_llm_config()
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=cfg.model,
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        temperature=0,
    )
