"""Deep Agents / LangGraph harness with bus-only tools (no local shell/delegation)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Sequence

PROFILE_NAME = "kats-chat-v1"

EXCLUDED_BUILTIN_TOOLS = frozenset(
    {
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "delete",
        "glob",
        "grep",
        "execute",
        "task",
    }
)


@dataclass
class HarnessConfig:
    model: str = "openai-compatible"
    allow_built_in_shell: bool = False
    allow_built_in_delegation: bool = False
    bus_tools_only: bool = True


@dataclass
class ChatHarness:
    """Production entry disables Deep Agents default shell/subagent paths."""

    config: HarnessConfig = field(default_factory=HarnessConfig)
    bus_invoke: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] | None = None

    def assert_safe_defaults(self) -> None:
        if self.config.allow_built_in_shell:
            raise RuntimeError("BUILT_IN_SHELL_FORBIDDEN")
        if self.config.allow_built_in_delegation:
            raise RuntimeError("BUILT_IN_DELEGATION_FORBIDDEN")
        if not self.config.bus_tools_only:
            raise RuntimeError("BUS_TOOLS_REQUIRED")

    def register_profile(self) -> str:
        """Register Deep Agents HarnessProfile that hides FS/shell/execute and GP subagent."""
        self.assert_safe_defaults()
        from deepagents import (
            GeneralPurposeSubagentProfile,
            HarnessProfile,
            register_harness_profile,
        )

        register_harness_profile(
            PROFILE_NAME,
            HarnessProfile(
                excluded_tools=EXCLUDED_BUILTIN_TOOLS,
                general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
                system_prompt_suffix=(
                    "You are Kats Chat Agent. Use only registered bus tools. "
                    "Never invent repository URLs or claim checks passed without tool evidence. "
                    "If coding is needed, call coding.execute after resolve_ref returns an immutable SHA."
                ),
            ),
        )
        return PROFILE_NAME

    def create_agent(self, *, model: Any, tools: Sequence[Any], checkpointer: Any | None = None):
        self.assert_safe_defaults()
        self.register_profile()
        from deepagents import create_deep_agent

        return create_deep_agent(
            model=model,
            tools=list(tools),
            checkpointer=checkpointer,
            subagents=[],
            name=PROFILE_NAME,
        )

    def create_agent_kwargs(self) -> dict[str, Any]:
        """Legacy smoke markers + profile name for tests."""
        self.assert_safe_defaults()
        return {
            "tools": [],
            "builtin_tools": [],
            "disable_shell": True,
            "disable_subagents": True,
            "excluded_tools": sorted(EXCLUDED_BUILTIN_TOOLS),
            "profile": PROFILE_NAME,
            "model": self.config.model,
        }

    async def call_bus_tool(self, capability: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.assert_safe_defaults()
        if self.bus_invoke is None:
            raise RuntimeError("BUS_NOT_CONFIGURED")
        return await self.bus_invoke(capability, payload)
