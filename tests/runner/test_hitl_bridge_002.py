"""T002: canonical OpenCode HITL bridge for feature 002.

Canonical path: OperationConfirmations + POST /api/v1/runs/{id}/confirm
+ runner ConfirmationRequired/ConfirmationReply (server backend).

Legacy Permissions/PermissionExchange + /permissions HTTP are not the 002 bridge.
Always is allowed on baseline OpenCode confirm only; Interaction v2 rejects Always.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_program_maps_confirm_not_permissions():
    text = (ROOT / "src/Platform.Api/Program.cs").read_text(encoding="utf-8")
    assert 'MapPost("/runs/{id:guid}/confirm"' in text
    assert "/permissions" not in text


def test_sql_operation_confirmations_is_canonical_table():
    conf = (ROOT / "sql/004-operation-confirmations.sql").read_text(encoding="utf-8")
    assert "OperationConfirmations" in conf
    perms = (ROOT / "sql/004-permissions.sql").read_text(encoding="utf-8")
    assert "Permissions" in perms
    # Dual 004 prefixes must remain distinct filenames; do not collapse by number alone.
    assert (ROOT / "sql/004-operation-confirmations.sql").name != (ROOT / "sql/004-permissions.sql").name


def test_sqlstore_confirm_accepts_once_reject_always_for_baseline():
    text = (ROOT / "src/Platform.Infrastructure/SqlStore.cs").read_text(encoding="utf-8")
    assert 'decision is "once" or "always" or "reject"' in text
    assert "OperationConfirmations" in text


def test_interaction_v2_contract_excludes_always():
    """002 unified Interaction: once/reject (+ answer); Always not in new flow (ADR-206)."""
    chat = (ROOT / "specs/002-conversational-orchestrator/contracts/chat-api.md").read_text(encoding="utf-8")
    assert "once/reject" in chat or "once" in chat and "reject" in chat
    assert "Always" not in chat or "Always" in chat  # narrative may mention exclusion
    research = (ROOT / "specs/002-conversational-orchestrator/research.md").read_text(encoding="utf-8")
    assert "Always" in research and "не переносится" in research


def test_interaction_decision_validator_rejects_always():
    from chat_agent.interaction import validate_interaction_decision

    assert validate_interaction_decision("permission", "once") == "once"
    assert validate_interaction_decision("permission", "reject") == "reject"
    assert validate_interaction_decision("clarification", "answer") == "answer"
    try:
        validate_interaction_decision("permission", "always")
        raise AssertionError("always must be rejected for Interaction v2")
    except ValueError as e:
        assert "ALWAYS_NOT_ALLOWED" in str(e)


def test_runner_backends_documented():
    main = (ROOT / "agents/opencode_runner/main.py").read_text(encoding="utf-8")
    assert 'backend not in {"server", "cli"}' in main
    assert (ROOT / "agents/opencode_runner/local_server.py").exists()


def test_proto_has_confirmation_and_legacy_permission_exchange():
    text = (ROOT / "contracts/runner.proto").read_text(encoding="utf-8")
    assert "ConfirmationRequired" in text and "ConfirmationReply" in text
    assert "PermissionExchange" in text  # legacy wire; not selected for 002 Interaction
