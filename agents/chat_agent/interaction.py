"""002 Interaction decisions: once/reject (+ answer for clarification). Always is excluded (ADR-206)."""

ALLOWED = {
    "permission": frozenset({"once", "reject"}),
    "approval": frozenset({"once", "reject"}),
    "clarification": frozenset({"answer", "reject"}),
    "question": frozenset({"answer", "reject"}),
}


def validate_interaction_decision(kind: str, decision: str) -> str:
    d = (decision or "").strip().lower()
    k = (kind or "").strip().lower()
    if d == "always":
        raise ValueError("ALWAYS_NOT_ALLOWED")
    allowed = ALLOWED.get(k)
    if allowed is None:
        raise ValueError("INVALID_INTERACTION_KIND")
    if d not in allowed:
        raise ValueError("INVALID_DECISION")
    return d
