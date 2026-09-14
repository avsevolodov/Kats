import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_runner_proto_declares_confirmation_frames():
    text = (ROOT / "contracts/runner.proto").read_text(encoding="utf-8")
    assert "ConfirmationRequired" in text
    assert "ConfirmationReply" in text
    assert "confirmation_required" in text
    assert "confirmation_reply" in text
    assert "pending_confirmation_request_id" in text


def test_browser_stream_declares_confirm_command_and_events():
    text = (ROOT / "specs/001-temporal-mvp/contracts/browser-stream.md").read_text(encoding="utf-8")
    assert "ConfirmationRequired" in text
    assert "ConfirmationResolved" in text
    assert '"type":"confirm"' in text or "confirm" in text


def test_openapi_confirm_schema():
    text = (ROOT / "specs/001-temporal-mvp/contracts/openapi.yaml").read_text(encoding="utf-8")
    assert "/api/v1/runs/{runId}/confirm" in text
    assert "ConfirmRun:" in text
    assert "once" in text and "always" in text


def test_python_pb2_exposes_confirmation_types():
    from opencode_runner import runner_pb2 as pb
    assert hasattr(pb, "ConfirmationRequired")
    assert hasattr(pb, "ConfirmationReply")
    msg = pb.ConfirmationRequired(request_id="p1", kind="permission", safe_payload_json="{}")
    assert msg.request_id == "p1"
    reply = pb.ConfirmationReply(request_id="p1", decision="once", answers_json="")
    assert reply.decision == "once"


def test_sql_migration_operation_confirmations_exists():
    text = (ROOT / "sql/004-operation-confirmations.sql").read_text(encoding="utf-8")
    assert "OperationConfirmations" in text
    assert "PENDING" not in text or "Status" in text
