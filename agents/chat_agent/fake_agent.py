"""Fake Chat Agent for M1/M2 without requiring a live LLM (T010/T015 path)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FakeChatResult:
    text: str
    repository_id: str | None = None
    needs_coding: bool = False
    capability: str | None = None


async def fake_reply(user_text: str) -> FakeChatResult:
    lowered = (user_text or "").lower()
    stripped = (user_text or "").strip().lower()
    if stripped in {"статус", "status", "?", "как дела"}:
        return FakeChatResult(text="Статус: нет активного task в этом fake-ответе.")
    if any(k in lowered for k in ("архитектур", "что такое", "объясни")):
        return FakeChatResult(text="Краткий ответ без репозитория и без OpenCode.")
    if "https://" in lowered and "evil" in lowered:
        return FakeChatResult(text="Нельзя сфабриковать URL; нужен ACL catalog.search.")
    if any(k in lowered for k in ("исправ", "fix", "баг", "почин", "deadlock")):
        return FakeChatResult(
            text="Нужен coding.execute после выбора репозитория.",
            needs_coding=True,
            capability="coding.execute",
        )
    return FakeChatResult(text="Уточните цель; репозиторий не выбран UI.")
