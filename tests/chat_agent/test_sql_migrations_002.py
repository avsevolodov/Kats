from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_additive_migrations_unique_after_dual_004():
    sql = sorted(p.name for p in (ROOT / "sql").glob("*.sql"))
    assert "004-permissions.sql" in sql
    assert "004-operation-confirmations.sql" in sql
    assert "005-graph-checkpoints.sql" in sql
    assert "006-conversations-tasks.sql" in sql
    assert "007-invocations-interactions.sql" in sql
    # No third 004-*
    assert len([n for n in sql if n.startswith("004-")]) == 2


def test_checkpoint_sql_has_pending_writes():
    text = (ROOT / "sql/005-graph-checkpoints.sql").read_text(encoding="utf-8")
    assert "GraphCheckpoints" in text
    assert "GraphPendingWrites" in text


def test_conversation_unique_active_task_filter():
    text = (ROOT / "sql/006-conversations-tasks.sql").read_text(encoding="utf-8")
    assert "UQ_AgentTasks_ActiveConversation" in text
    assert "IsActive=1" in text


def test_dispatch_intent_pk():
    text = (ROOT / "sql/007-invocations-interactions.sql").read_text(encoding="utf-8")
    assert "PK_DispatchIntents" in text
    assert "InteractionRequests" in text
