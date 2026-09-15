from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_agent_service_and_stream_exist():
    assert (ROOT / "src/Platform.Api/AgentService.cs").exists()
    assert (ROOT / "src/Platform.Api/ConversationStream.cs").exists()
    program = (ROOT / "src/Platform.Api/Program.cs").read_text(encoding="utf-8")
    assert "MapGrpcService<AgentService>" in program
    assert "ConversationStream.Handle" in program


def test_worker_dispatch_chat():
    text = (ROOT / "src/Platform.Worker/Program.cs").read_text(encoding="utf-8")
    assert "DispatchChat" in text
    assert "START_TASK" in text
    assert "TaskWorkflow" in text


def test_chat_store_claim_complete():
    text = (ROOT / "src/Platform.Infrastructure/ChatStore.cs").read_text(encoding="utf-8")
    assert "ClaimChatExecution" in text
    assert "CompleteChatExecution" in text
    assert "START_TASK" in text
