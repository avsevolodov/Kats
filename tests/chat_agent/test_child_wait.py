"""Child wait / suspend semantics (code-only; live Temporal NOT RUN)."""

from __future__ import annotations

import asyncio
import json

from chat_agent.live_agent import is_child_terminal, wait_or_suspend_coding


class FakeSnap:
    def __init__(self, status: str, result_json: str = "{}"):
        self.status = status
        self.result_json = result_json


class FakeFrame:
    def __init__(self, **fields):
        self._fields = fields

    def HasField(self, name: str) -> bool:
        return name in self._fields

    def __getattr__(self, name: str):
        return self._fields[name]


class FakeTransport:
    def __init__(self, child_status: str = "RUNNING"):
        self.child_status = child_status
        self.suspended = None

    async def get_invocation(self, invocation_id: str):
        return FakeFrame(
            invocation_snapshot=FakeSnap(
                self.child_status,
                json.dumps({"status": "ACCEPTED", "checks": [{"outcome": "not_run"}]}),
            )
        )

    async def suspend(self, invocation_id: str, checkpoint_id: str, dependency_ids=None):
        self.suspended = (invocation_id, checkpoint_id, list(dependency_ids or []))
        return FakeFrame(ack=object())


def test_running_not_terminal():
    assert not is_child_terminal("RUNNING")
    assert not is_child_terminal("ACCEPTED")
    assert is_child_terminal("SUCCEEDED")
    assert is_child_terminal("FAILED")
    assert is_child_terminal("UNKNOWN")


def test_wait_or_suspend_when_running():
    t = FakeTransport("RUNNING")

    async def run():
        out = await wait_or_suspend_coding(
            transport=t,
            root_invocation_id="root-1",
            child_invocation_id="child-1",
            checkpoint_id="cp-1",
        )
        assert out["disposition"] == "suspended"
        assert out["status"] == "RUNNING"
        assert t.suspended == ("root-1", "cp-1", ["child-1"])

    asyncio.run(run())


def test_wait_or_suspend_when_child_terminal():
    t = FakeTransport("SUCCEEDED")

    async def run():
        out = await wait_or_suspend_coding(
            transport=t,
            root_invocation_id="root-1",
            child_invocation_id="child-1",
            checkpoint_id="cp-1",
        )
        assert out["disposition"] == "child_terminal"
        assert out["status"] == "SUCCEEDED"
        assert t.suspended is None

    asyncio.run(run())


def test_worker_reconcile_not_noop():
    from pathlib import Path

    text = Path("src/Platform.Worker/Program.cs").read_text(encoding="utf-8")
    assert "chat.ReconcileTaskChildren" in text
    assert "SIGNAL_CHILD_COMPLETED" in text
    assert "ChildCompleted" in text


def test_agentservice_coding_not_succeeded_at_start():
    from pathlib import Path

    text = Path("src/Platform.Api/AgentService.cs").read_text(encoding="utf-8")
    assert 'request.Capability == "coding.execute" ? "RUNNING"' in text
    assert "SuspendExecution" in text


def test_project_run_does_not_terminalize_task():
    from pathlib import Path

    text = Path("src/Platform.Infrastructure/ChatStore.cs").read_text(encoding="utf-8")
    assert 'task.Status = "WAITING_CHILD"' in text
    assert "SIGNAL_CHILD_COMPLETED" in text
    # Must not set IsActive=false inside ProjectRunStatus body for child success
    proj = text.split("public Task ProjectRunStatus")[1].split("public Task ReconcileTaskChildren")[0]
    assert "IsActive = false" not in proj
