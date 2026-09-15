"""Bus tool wrappers — all external effects go through EnsureInvocation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Awaitable


@dataclass(frozen=True)
class IntentKey:
    task_id: str
    checkpoint_id: str
    graph_task_path: str
    tool_call_id: str

    def as_tuple(self) -> tuple[str, str, str, str]:
        return (self.task_id, self.checkpoint_id, self.graph_task_path, self.tool_call_id)


class BusTools:
    def __init__(self, ensure_invocation: Callable[[IntentKey, str, str, dict[str, Any]], Awaitable[dict[str, Any]]]):
        self._ensure = ensure_invocation

    async def catalog_search(self, intent: IntentKey, query: str) -> dict[str, Any]:
        return await self._ensure(intent, "catalog.search", "1", {"query": query})

    async def repositories_describe(self, intent: IntentKey, repository_id: str) -> dict[str, Any]:
        return await self._ensure(intent, "repositories.describe", "1", {"repositoryId": repository_id})

    async def repositories_resolve_ref(self, intent: IntentKey, repository_id: str, ref: str) -> dict[str, Any]:
        return await self._ensure(intent, "repositories.resolve_ref", "1", {"repositoryId": repository_id, "ref": ref})

    async def code_search(self, intent: IntentKey, repository_id: str, query: str) -> dict[str, Any]:
        return await self._ensure(intent, "code.search", "1", {"repositoryId": repository_id, "query": query})

    async def coding_execute(self, intent: IntentKey, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._ensure(intent, "coding.execute", "1", payload)
