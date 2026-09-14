"""Bounded tool labels for UI; never forward raw metadata or reasoning."""
import re


def clean(value):
    return re.sub(r"[\x00-\x1f\x7f]", " ", value)[:200] if isinstance(value, str) else ""


def format_cli_event(kind, part):
    if kind == "step_start":
        return "[шаг] начало\n"
    if kind == "step_finish":
        return f"[шаг] завершён ({clean(part.get('reason', ''))})\n"
    if kind == "tool":
        name = clean(part.get("tool", "tool"))
        state = part.get("state", {})
        inputs = part.get("input", state.get("input", {}) if isinstance(state, dict) else {})
        detail = ""
        if isinstance(inputs, dict):
            for key in ("path", "filePath", "pattern"):
                if isinstance(inputs.get(key), str):
                    detail = f" {('path' if key == 'filePath' else key)}={clean(inputs[key])}"
                    break
        return f"[tool:{name}]{detail}\n"
    return ""


def format_new_message_parts(parts, seen):
    result = []
    for part in parts:
        if not isinstance(part, dict) or not part.get("id") or part["id"] in seen:
            continue
        seen.add(part["id"])
        marker = format_cli_event(part.get("type", "").replace("-", "_"), part)
        if marker:
            result.append(marker)
    return result
