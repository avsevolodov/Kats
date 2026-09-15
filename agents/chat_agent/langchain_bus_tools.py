"""LangChain tools that only call EnsureInvocation on the agent.v1 bus."""

from __future__ import annotations

import json
import uuid
from typing import Any, Awaitable, Callable

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from chat_agent.bus_tools import IntentKey


class CatalogSearchInput(BaseModel):
    query: str = Field(description="Search query for repositories")


class DescribeInput(BaseModel):
    repository_id: str


class ResolveRefInput(BaseModel):
    repository_id: str
    ref: str = "main"


class CodeSearchInput(BaseModel):
    repository_id: str
    query: str


class CodingExecuteInput(BaseModel):
    repository_id: str
    base_commit: str = Field(description="Immutable 40-char SHA")
    prompt: str


EnsureFn = Callable[[IntentKey, str, str, dict[str, Any]], Awaitable[dict[str, Any]]]


def build_bus_tools(
    *,
    task_id: str,
    ensure: EnsureFn,
    checkpoint_id_provider: Callable[[], str],
    graph_task_path: str = "agent",
) -> list[StructuredTool]:
    async def _call(capability: str, payload: dict[str, Any]) -> str:
        intent = IntentKey(task_id, checkpoint_id_provider(), graph_task_path, str(uuid.uuid4()))
        # Prefer stable tool_call_id from payload if graph supplies one later.
        tool_call_id = payload.pop("_tool_call_id", None) or intent.tool_call_id
        intent = IntentKey(task_id, intent.checkpoint_id, graph_task_path, tool_call_id)
        result = await ensure(intent, capability, "1", payload)
        return json.dumps(result, ensure_ascii=False)

    async def catalog_search(query: str) -> str:
        return await _call("catalog.search", {"query": query})

    async def describe(repository_id: str) -> str:
        return await _call("repositories.describe", {"repositoryId": repository_id})

    async def resolve_ref(repository_id: str, ref: str = "main") -> str:
        return await _call("repositories.resolve_ref", {"repositoryId": repository_id, "ref": ref})

    async def code_search(repository_id: str, query: str) -> str:
        return await _call("code.search", {"repositoryId": repository_id, "query": query})

    async def coding_execute(repository_id: str, base_commit: str, prompt: str) -> str:
        return await _call(
            "coding.execute",
            {"repositoryId": repository_id, "baseCommit": base_commit, "prompt": prompt},
        )

    return [
        StructuredTool.from_function(coroutine=catalog_search, name="catalog_search", description="Search accessible repositories", args_schema=CatalogSearchInput),
        StructuredTool.from_function(coroutine=describe, name="repositories_describe", description="Describe one accessible repository", args_schema=DescribeInput),
        StructuredTool.from_function(coroutine=resolve_ref, name="repositories_resolve_ref", description="Resolve ref to immutable commit when possible", args_schema=ResolveRefInput),
        StructuredTool.from_function(coroutine=code_search, name="code_search", description="Bounded code search", args_schema=CodeSearchInput),
        StructuredTool.from_function(coroutine=coding_execute, name="coding_execute", description="Start one coding Run via platform bus", args_schema=CodingExecuteInput),
    ]
