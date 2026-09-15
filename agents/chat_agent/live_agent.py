"""Live Chat Agent graph runner: checkpoint before bus dispatch; real model required on bus path."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from chat_agent.checkpointer import InMemoryCheckpointClient, KatsCheckpointer
from chat_agent.config import ChatAgentConfigError, build_model
from chat_agent.harness import ChatHarness, HarnessConfig
from chat_agent.langchain_bus_tools import build_bus_tools

# Child statuses that mean coding.execute is still in flight.
_NON_TERMINAL = frozenset({"ACCEPTED", "RUNNING", "LEASED", "QUEUED"})


async def run_recorded_turn(
    *,
    task_id: str,
    goal: str,
    ensure_calls: list[tuple],
) -> dict[str, Any]:
    """Exercise harness + bus tools + checkpoint-before-ensure without live LLM."""
    client = InMemoryCheckpointClient()
    cp = KatsCheckpointer(client)
    checkpoint_id = {"value": "c0"}

    async def ensure(intent, cap, ver, payload):
        await cp.aput(
            {"configurable": {"thread_id": task_id, "checkpoint_ns": "", "fence": 1}},
            {"id": checkpoint_id["value"], "pending": [intent.tool_call_id]},
            {"step": len(ensure_calls)},
        )
        ensure_calls.append((intent.as_tuple(), cap, ver, payload))
        if cap == "catalog.search":
            return {"invocationId": "inv-cat", "status": "SUCCEEDED", "result": {"items": [{"repositoryId": "r1"}]}}
        if cap == "coding.execute":
            return {
                "invocationId": "inv-code",
                "status": "RUNNING",
                "runId": "run-1",
                "result": {"status": "ACCEPTED", "checks": [{"outcome": "not_run"}]},
            }
        return {"invocationId": "inv-x", "status": "SUCCEEDED", "result": {}}

    def next_checkpoint():
        checkpoint_id["value"] = f"c{len(ensure_calls)}"
        return checkpoint_id["value"]

    tools = build_bus_tools(task_id=task_id, ensure=ensure, checkpoint_id_provider=next_checkpoint)
    harness = ChatHarness(HarnessConfig())
    profile = harness.register_profile()
    out = await tools[0].ainvoke({"query": "reconnect"})
    assert ensure_calls, "bus tool must call ensure"
    await tools[0].ainvoke({"query": "reconnect"})
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    agent = harness.create_agent(
        model=FakeListChatModel(responses=["ok"]),
        tools=tools,
        checkpointer=True,
    )
    return {
        "profile": profile,
        "ensure_count": len(ensure_calls),
        "tool_names": [t.name for t in tools],
        "first_result": out,
        "excluded": harness.create_agent_kwargs()["excluded_tools"],
        "goal": goal,
        "agent_name": getattr(agent, "name", None) or profile,
    }


def build_openai_model():
    """Require full LLM config; raises ChatAgentConfigError (no recorded-fallback)."""
    return build_model()


def is_child_terminal(status: str) -> bool:
    return status not in _NON_TERMINAL and status != ""


RESUME_MARKER = "[[KATS_RESUME]]"


def split_goal_resume(raw_goal: str) -> tuple[str, dict[str, Any] | None]:
    """T028: Assignment.Goal may carry [[KATS_RESUME]]{json} from ClaimChatExecution."""
    text = raw_goal or ""
    if RESUME_MARKER not in text:
        return text, None
    goal, _, rest = text.partition(RESUME_MARKER)
    try:
        resume = json.loads(rest.strip()) if rest.strip() else None
    except json.JSONDecodeError:
        resume = None
    return goal.strip(), resume


def summarize_resume(resume: dict[str, Any] | None) -> str:
    if not resume:
        return ""
    parts = []
    for c in resume.get("children") or []:
        status = c.get("status")
        cap = c.get("capability")
        parts.append(f"{cap}:{status}")
        if status and is_child_terminal(status) and status != "SUCCEEDED":
            parts.append(f"(honest:{status})")
    for d in resume.get("decisions") or []:
        parts.append(f"decision:{d.get('decision')}")
    return "; ".join(parts)


async def wait_or_suspend_coding(
    *,
    transport,
    root_invocation_id: str,
    child_invocation_id: str,
    checkpoint_id: str,
    poll_once: bool = True,
) -> dict[str, Any]:
    """Poll GetInvocation once (or use suspend). Never treat RUNNING as root success."""
    snap = await transport.get_invocation(child_invocation_id)
    status = ""
    result: dict[str, Any] = {}
    if snap.HasField("invocation_snapshot"):
        status = snap.invocation_snapshot.status
        if snap.invocation_snapshot.result_json:
            result = json.loads(snap.invocation_snapshot.result_json)
    if is_child_terminal(status):
        return {"disposition": "child_terminal", "status": status, "result": result, "invocationId": child_invocation_id}
    # Child still running — suspend root; Temporal/reconcile will re-claim later.
    await transport.suspend(root_invocation_id, checkpoint_id, [child_invocation_id])
    return {
        "disposition": "suspended",
        "status": status or "RUNNING",
        "result": result,
        "invocationId": child_invocation_id,
        "poll_once": poll_once,
    }


async def run_live_assignment(transport, assignment) -> dict[str, Any]:
    """Claimed assignment: may return disposition=suspended instead of terminal root result."""
    from chat_agent import agent_pb2 as pb

    task_id = assignment.task_id
    goal, resume = split_goal_resume(assignment.goal or "")
    resume_summary = summarize_resume(resume)
    ensure_log: list[str] = []
    last_cp = {"id": f"cp-{uuid.uuid4()}"}
    pending_coding: dict[str, Any] | None = None

    # T028: second claim after child terminal — complete with consumed result, no new Start SUCCEEDED.
    if resume and any(
        is_child_terminal(str(c.get("status") or ""))
        for c in (resume.get("children") or [])
    ):
        child = (resume.get("children") or [None])[0] or {}
        status = str(child.get("status") or "UNKNOWN")
        result_raw = child.get("resultJson") or "{}"
        try:
            result = json.loads(result_raw) if isinstance(result_raw, str) else result_raw
        except json.JSONDecodeError:
            result = {}
        checks = result.get("checks") if isinstance(result, dict) else None
        if not checks:
            checks = [{"name": "build", "outcome": "not_run" if status != "FAILED" else "failed"}]
        text = f"Coding child {status}."
        if resume_summary:
            text += f" ({resume_summary})"
        if status == "SUCCEEDED":
            text = "Задача coding завершена." + (f" {resume_summary}" if resume_summary else "")
        return {
            "assistantText": text,
            "needsCoding": False,
            "mode": "resume-child",
            "disposition": "complete",
            "ensure_log": ensure_log,
            "resume": resume,
            "checks": checks,
            "childStatus": status,
        }

    if resume and (resume.get("decisions") or []):
        dec = resume["decisions"][0]
        return {
            "assistantText": f"Учтено решение interaction: {dec.get('decision')}.",
            "needsCoding": False,
            "mode": "resume-interaction",
            "disposition": "complete",
            "ensure_log": ensure_log,
            "resume": resume,
            "checks": [{"name": "build", "outcome": "not_run"}],
        }

    async def ensure(intent, cap, ver, payload):
        nonlocal pending_coding
        put = await transport.request(
            checkpoint_put=pb.CheckpointPut(
                thread_id=assignment.invocation_id,
                namespace="",
                checkpoint_id=intent.checkpoint_id,
                parent_checkpoint_id="",
                codec_version="kats-checkpoint-v1",
                payload_json=json.dumps(
                    {"tool_call_id": intent.tool_call_id, "capability": cap},
                    separators=(",", ":"),
                ),
                metadata_json=json.dumps({"task_id": task_id}, separators=(",", ":")),
                fence=assignment.fence,
            )
        )
        if put.HasField("error"):
            raise RuntimeError(put.error.code)
        last_cp["id"] = intent.checkpoint_id
        frame = await transport.ensure_invocation(
            task_id,
            intent.checkpoint_id,
            intent.graph_task_path,
            intent.tool_call_id,
            cap,
            ver,
            payload,
        )
        ensure_log.append(cap)
        if frame.HasField("error"):
            raise RuntimeError(frame.error.code)
        result = {}
        status = "UNKNOWN"
        inv_id = ""
        run_id = ""
        if frame.HasField("invocation_accepted"):
            inv_id = frame.invocation_accepted.invocation_id
            status = frame.invocation_accepted.status
            run_id = frame.invocation_accepted.run_id
            snap = await transport.get_invocation(inv_id)
            if snap.HasField("invocation_snapshot") and snap.invocation_snapshot.result_json:
                result = json.loads(snap.invocation_snapshot.result_json)
                status = snap.invocation_snapshot.status or status
        if cap == "coding.execute" and not is_child_terminal(status):
            pending_coding = {
                "invocationId": inv_id,
                "status": status,
                "runId": run_id,
                "result": result,
                "checkpointId": intent.checkpoint_id,
            }
        return {
            "invocationId": inv_id,
            "status": status,
            "runId": run_id,
            "result": result,
        }

    try:
        model = build_openai_model()
    except ChatAgentConfigError:
        raise
    except Exception as exc:  # noqa: BLE001 — surface as bus-safe MODEL_UNAVAILABLE
        raise ChatAgentConfigError(
            "MODEL_UNAVAILABLE",
            "Chat Agent LLM client failed to initialize.",
        ) from exc

    harness = ChatHarness(
        HarnessConfig(model=os.environ.get("CHAT_AGENT_MODEL") or os.environ.get("CHAT_MODEL", "openai-compatible"))
    )

    def next_cp():
        last_cp["id"] = f"cp-{uuid.uuid4()}"
        return last_cp["id"]

    tools = build_bus_tools(task_id=task_id, ensure=ensure, checkpoint_id_provider=next_cp)
    agent = harness.create_agent(model=model, tools=tools, checkpointer=True)
    result = await agent.ainvoke({"messages": [{"role": "user", "content": goal}]})
    messages = result.get("messages") or []
    content = ""
    for m in reversed(messages):
        c = getattr(m, "content", None)
        if isinstance(c, str) and c:
            content = c
            break

    if pending_coding is not None:
        wait = await wait_or_suspend_coding(
            transport=transport,
            root_invocation_id=assignment.invocation_id,
            child_invocation_id=pending_coding["invocationId"],
            checkpoint_id=pending_coding.get("checkpointId") or last_cp["id"],
        )
        if wait["disposition"] == "suspended":
            return {
                "assistantText": content or "Ожидаю coding.execute…",
                "needsCoding": True,
                "mode": "live",
                "disposition": "suspended",
                "ensure_log": ensure_log,
                "pendingCoding": pending_coding,
                "checks": [{"name": "build", "outcome": "not_run"}],
            }

    return {
        "assistantText": content or "Завершено.",
        "needsCoding": False,
        "mode": "live",
        "disposition": "complete",
        "ensure_log": ensure_log,
        "checks": [{"name": "build", "outcome": "not_run"}],
    }
