from opencode_runner.presentation import (
    clip_summary_for_preview,
    format_cli_event,
    format_new_message_parts,
    format_runner,
    format_tool,
    safe_arg_summary,
)


def test_safe_arg_summary_keeps_paths_and_hides_secrets():
    assert "path=src/a.cs" in safe_arg_summary({"path": "src/a.cs", "pattern": "*.cs"})
    assert safe_arg_summary({"token": "super-secret", "path": "x"}) == "path=x"
    assert "super-secret" not in safe_arg_summary({"password": "super-secret"})
    assert safe_arg_summary({"password": "super-secret"}) == "(скрыто)"
    nested = {"state": {"input": {"path": "readme.md", "api_key": "leak"}}}
    summary = safe_arg_summary(nested)
    assert "path=readme.md" in summary
    assert "leak" not in summary


def test_format_tool_and_cli_events():
    assert format_tool({"tool": "read", "input": {"path": "a.txt"}}) == "[tool:read] path=a.txt\n"
    assert format_cli_event("step_start", {}) == "[шаг] начало\n"
    assert format_cli_event("step_finish", {"reason": "stop"}) == "[шаг] завершён (stop)\n"
    assert format_cli_event("reasoning", {"text": "think"}) is None
    tool = format_cli_event("tool", {"tool": "grep", "input": {"pattern": "TODO", "path": "."}})
    assert tool.startswith("[tool:grep]")
    assert "TODO" in tool
    assert format_cli_event("tool", {"type": "tool", "name": "edit", "input": {"file": "x.py"}}) == "[tool:edit] file=x.py\n"


def test_message_parts_emit_once_and_skip_reasoning():
    seen: set[str] = set()
    parts = [
        {"id": "t1", "type": "tool", "tool": "read", "input": {"path": "a", "token": "secret"}},
        {"id": "r1", "type": "reasoning", "text": "hidden chain"},
        {"id": "x1", "type": "text", "text": "hello"},
        {"id": "t1", "type": "tool", "tool": "read", "input": {"path": "a"}},
    ]
    lines = format_new_message_parts(parts, seen)
    assert lines == ["[tool:read] path=a\n"]
    assert "secret" not in "".join(lines)
    assert "hidden" not in "".join(lines)
    assert format_new_message_parts(parts, seen) == []


def test_format_runner_lifecycle_markers():
    assert format_runner("подготовка репозитория…") == "[runner] подготовка репозитория…\n"
    assert format_runner("ожидание модели…") == "[runner] ожидание модели…\n"
    assert format_runner("  ") == ""
    assert format_runner("a\nb\tc") == "[runner] a b c\n"


def test_clip_summary_for_preview():
    assert clip_summary_for_preview("") == ""
    assert clip_summary_for_preview("  done  ") == "done\n"
    assert clip_summary_for_preview("line\n") == "line\n"
    long = "x" * 9000
    clipped = clip_summary_for_preview(long, limit=100)
    assert clipped.endswith("…\n")
    assert len(clipped.encode("utf-8")) <= 100
    # Multi-byte: truncate without raising.
    multi = "я" * 100
    out = clip_summary_for_preview(multi, limit=10)
    assert out.endswith("…\n")
    out.encode("utf-8")
