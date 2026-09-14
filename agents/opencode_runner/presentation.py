"""Sanitize OpenCode step/tool activity into OutputBatch presentation text.

Durable tool interception is out of MVP; this is UI-only preview text.
Raw reasoning, stderr, credentials and full tool payloads are never forwarded.
"""
from __future__ import annotations

SAFE_ARG_KEYS = ("path", "file", "filepath", "pattern", "glob", "query", "include", "exclude")
_SECRET_FRAGMENTS = (
    "password", "passwd", "token", "secret", "credential", "authorization",
    "api_key", "apikey", "bearer", "cookie", "private_key",
)


def _looks_secret(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(fragment in lowered for fragment in _SECRET_FRAGMENTS)


def _clip(value: str, limit: int = 120) -> str:
    text = value.replace("\n", " ").strip()
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def safe_arg_summary(data) -> str:
    """Extract short non-secret path/pattern fields from tool input/state."""
    if not isinstance(data, dict):
        return ""
    source = data
    for nest in ("input", "args", "state"):
        nested = data.get(nest)
        if isinstance(nested, dict):
            # Prefer nested input when present; state may also hold input.
            if nest == "state" and isinstance(nested.get("input"), dict):
                source = nested["input"]
            elif nest in {"input", "args"}:
                source = nested
            break
    parts = []
    for key in SAFE_ARG_KEYS:
        if key not in source or _looks_secret(key):
            continue
        value = source[key]
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            parts.append(f"{key}={_clip(str(value))}")
        if len(parts) >= 3:
            break
    # Refuse to echo arbitrary blobs that might contain secrets.
    for key, value in source.items():
        if _looks_secret(key) and value not in (None, ""):
            return " ".join(parts) if parts else "(скрыто)"
    return " ".join(parts)


def format_step_start() -> str:
    return "[шаг] начало\n"


def format_step_finish(reason=None) -> str:
    if isinstance(reason, str) and reason.strip():
        return f"[шаг] завершён ({_clip(reason, 40)})\n"
    return "[шаг] завершён\n"


def format_runner(message: str) -> str:
    """Lifecycle/progress line for the UI timeline (not ops logs)."""
    text = " ".join(str(message).split()).strip()
    if not text:
        return ""
    return f"[runner] {_clip(text, 200)}\n"


def clip_summary_for_preview(summary: str, limit: int = 8192) -> str:
    """One preview frame from the durable summary; never forwards secrets by key."""
    if not isinstance(summary, str) or not summary.strip():
        return ""
    text = summary.strip()
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text + ("\n" if not text.endswith("\n") else "")
    suffix = "…\n"
    suffix_bytes = suffix.encode("utf-8")
    if limit <= len(suffix_bytes):
        return ""
    # Truncate on UTF-8 boundaries for the OutputBatch byte cap.
    cut = encoded[: limit - len(suffix_bytes)]
    while cut:
        try:
            return cut.decode("utf-8") + suffix
        except UnicodeDecodeError:
            cut = cut[:-1]
    return ""


def tool_name(part: dict) -> str:
    for key in ("tool", "name", "toolName", "tool_name"):
        value = part.get(key)
        if isinstance(value, str) and value.strip():
            return _clip(value.strip(), 64)
    return "unknown"


def format_tool(part: dict) -> str:
    name = tool_name(part)
    summary = safe_arg_summary(part)
    if summary:
        return f"[tool:{name}] {summary}\n"
    return f"[tool:{name}]\n"


def format_cli_event(kind: str, part) -> str | None:
    """Map a CLI NDJSON event to presentation text, or None to skip."""
    if kind == "step_start":
        return format_step_start()
    if kind == "step_finish":
        reason = part.get("reason") if isinstance(part, dict) else None
        return format_step_finish(reason)
    if kind == "tool" or (isinstance(part, dict) and part.get("type") == "tool"):
        if not isinstance(part, dict):
            return "[tool:unknown]\n"
        return format_tool(part)
    if kind in {"reasoning", "error"}:
        return None
    return None


def part_fingerprint(part: dict, index: int) -> str:
    part_id = part.get("id")
    if isinstance(part_id, str) and part_id:
        return part_id
    kind = part.get("type", "part")
    name = tool_name(part) if kind == "tool" else ""
    return f"{index}:{kind}:{name}"


def format_new_message_parts(parts, seen: set[str]) -> list[str]:
    """Return presentation lines for newly seen non-text message parts."""
    lines = []
    if not isinstance(parts, list):
        return lines
    for index, part in enumerate(parts):
        if not isinstance(part, dict):
            continue
        kind = part.get("type")
        if kind == "text":
            continue
        if kind in {"reasoning", "step-start", "step-finish"}:
            # Server may use hyphenated step markers; emit once.
            if kind == "step-start":
                marker = format_step_start()
            elif kind == "step-finish":
                marker = format_step_finish(part.get("reason"))
            else:
                continue
            key = part_fingerprint(part, index)
            if key in seen:
                continue
            seen.add(key)
            lines.append(marker)
            continue
        if kind != "tool":
            continue
        key = part_fingerprint(part, index)
        if key in seen:
            continue
        seen.add(key)
        lines.append(format_tool(part))
    return lines
