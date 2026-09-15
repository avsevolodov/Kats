"""Follow-up task uses predecessor artifact metadata; workspace not assumed live (T019)."""

from dataclasses import dataclass


@dataclass
class PredecessorPatch:
    artifact_id: str
    sha256: str
    base_commit: str
    expires_at_unix: int


def validate_follow_up(pred: PredecessorPatch, *, now: int, allowed: bool) -> None:
    if not allowed:
        raise PermissionError("ACL_DENIED")
    if pred.expires_at_unix <= now:
        raise ValueError("ARTIFACT_EXPIRED")
    if len(pred.sha256) != 64:
        raise ValueError("INVALID_HASH")
    if not pred.base_commit:
        raise ValueError("BASE_REQUIRED")


def test_follow_up_rejects_expired():
    try:
        validate_follow_up(
            PredecessorPatch("a", "a" * 64, "main", 1),
            now=10,
            allowed=True,
        )
        raise AssertionError("fail")
    except ValueError as e:
        assert "EXPIRED" in str(e)


def test_follow_up_ok():
    validate_follow_up(PredecessorPatch("a", "b" * 64, "main", 100), now=10, allowed=True)
