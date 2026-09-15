"""T025–T028 unit semantics: interaction wake, steer apply markers, cancel, resume parse."""

from __future__ import annotations

import json
from pathlib import Path

from chat_agent.live_agent import RESUME_MARKER, split_goal_resume, summarize_resume, is_child_terminal


def test_split_goal_resume():
    goal, resume = split_goal_resume("fix reconnect")
    assert goal == "fix reconnect"
    assert resume is None
    raw = 'цель\n\n[[KATS_RESUME]]{"children":[{"status":"SUCCEEDED","capability":"coding.execute"}],"decisions":[]}'
    g, r = split_goal_resume(raw)
    assert g == "цель"
    assert r["children"][0]["status"] == "SUCCEEDED"


def test_resume_summary_honest_failed():
    s = summarize_resume({"children": [{"capability": "coding.execute", "status": "FAILED"}], "decisions": []})
    assert "FAILED" in s
    assert "honest:FAILED" in s


def test_respond_interaction_requeues_in_chatstore():
    text = Path("src/Platform.Infrastructure/ChatStore.cs").read_text(encoding="utf-8")
    assert "RequeueRootClaim" in text
    assert "interaction-answered:" in text
    assert 'Kind = "ABORT_TASK_RUNS"' in text
    assert "ApplyPendingSteers" in text
    assert "steer_applied" in text
    assert "BuildResumeJson" in text


def test_worker_abort_task_runs():
    text = Path("src/Platform.Worker/Program.cs").read_text(encoding="utf-8")
    assert "ABORT_TASK_RUNS" in text
    assert "ListLinkedRunsForAbort" in text


def test_agentservice_resume_marker():
    text = Path("src/Platform.Api/AgentService.cs").read_text(encoding="utf-8")
    assert "[[KATS_RESUME]]" in text


def test_child_terminal_helper():
    assert is_child_terminal("SUCCEEDED")
    assert not is_child_terminal("RUNNING")
