import asyncio
import json
import sys
import pytest
import opencode_runner.cli as cli_mod
from opencode_runner.cli import OpenCodeCli
from opencode_runner.core import RunnerError


@pytest.fixture
def cli(tmp_path, monkeypatch):
    root = tmp_path / "work with spaces"
    (root / "current").mkdir(parents=True)
    binary = tmp_path / "fake opencode"
    binary.write_text(f"#!{sys.executable}\n" + '''
import json, os, sys, time
if sys.argv[1:] == ["--version"]:
    mode = os.environ.get("TEST_VERSION_MODE", "stdout")
    if mode == "sleep":
        time.sleep(60)
    if mode == "stderr":
        print("1.2.27", file=sys.stderr); sys.exit(0)
    print("1.2.27"); sys.exit(0)
with open("capture.json", "w") as f:
    json.dump({"args":sys.argv[1:], "prompt":sys.stdin.read(),
               "credential":os.environ.get("GIT_CREDENTIAL_FILE"),
               "permission":json.loads(os.environ["OPENCODE_PERMISSION"])}, f)
mode=os.environ.get("TEST_CLI_MODE", "ok")
if mode == "sleep": time.sleep(60)
if mode == "bad": print("not json"); sys.exit(0)
print(json.dumps({"type":"step_start", "part":{}}), flush=True)
print(json.dumps({"type":"tool", "part":{"tool":"read","input":{"path":"src/a.cs","token":"must-not-leak"}}}), flush=True)
print(json.dumps({"type":"text", "part":{"text":"result"}}), flush=True)
if mode == "exit": sys.exit(3)
if mode == "error":
    print(json.dumps({"type":"error","error":{"name":"ProviderError","data":{"message":"model unavailable"}}}), flush=True)
    sys.exit(0)
if mode != "partial": print(json.dumps({"type":"step_finish", "part":{"reason":"stop"}}))
''')
    binary.chmod(0o755)
    monkeypatch.setenv("OPENCODE_BIN", str(binary))
    monkeypatch.setenv("WORKSPACE_ROOT", str(root))
    monkeypatch.setenv("OPENCODE_MODEL", "model")
    monkeypatch.setenv("GIT_CREDENTIAL_FILE", "must-not-be-inherited")
    return OpenCodeCli()


@pytest.mark.skipif(sys.platform == "win32", reason="CLI health requires POSIX/WSL")
def test_cli_version_timeout(cli, monkeypatch):
    monkeypatch.setenv("TEST_VERSION_MODE", "sleep")
    monkeypatch.setattr(cli_mod, "VERSION_TIMEOUT_S", 0.05)
    with pytest.raises(RunnerError, match="OPENCODE_CLI_VERSION_TIMEOUT"):
        asyncio.run(cli.health())


@pytest.mark.skipif(sys.platform == "win32", reason="CLI health requires POSIX/WSL")
def test_cli_version_on_stderr_accepted(cli, monkeypatch):
    monkeypatch.setenv("TEST_VERSION_MODE", "stderr")
    asyncio.run(cli.health())
    assert cli.version == "1.2.27"


def test_cli_stdin_json_and_no_repeat(cli):
    async def exercise():
        await cli.health()
        assert (await cli.create()).startswith("cli-")
        preview = []
        async def emit(text): preview.append(text)
        prompt = '--bad "quotes" $HOME $(touch unwanted)\nnext'
        assert await cli.run(prompt, emit, asyncio.Event()) == "result"
        from pathlib import Path
        capture = json.loads((Path(cli.directory) / "capture.json").read_text())
        assert capture["prompt"] == prompt
        assert prompt not in capture["args"]
        assert "--attach" not in capture["args"]
        assert capture["credential"] is None
        assert capture["permission"]["*"] == "deny"
        assert preview[0] == "[шаг] начало\n"
        assert preview[1] == "[tool:read] path=src/a.cs\n"
        assert "must-not-leak" not in "".join(preview)
        assert "result" in preview
        assert preview[-1] == "[шаг] завершён (stop)\n"
        with pytest.raises(RunnerError, match="PROMPT_ALREADY_SENT"):
            await cli.run(prompt, emit, asyncio.Event())
        await cli.cleanup()
    asyncio.run(exercise())


@pytest.mark.parametrize("mode,error", [
    ("bad", "INVALID_JSON"),
    ("partial", "INCOMPLETE"),
    ("exit", "EXIT_FAILED"),
    ("error", "OPENCODE_CLI_ERROR"),
])
def test_cli_failure_is_not_success(cli, monkeypatch, mode, error):
    monkeypatch.setenv("TEST_CLI_MODE", mode)
    async def exercise():
        await cli.create()
        async def emit(text): pass
        with pytest.raises(RunnerError, match=error):
            await cli.run("x", emit, asyncio.Event())
        assert cli.process.returncode is not None
    asyncio.run(exercise())


def test_cli_cancel_stops_process_but_does_not_claim_remote_abort(cli, monkeypatch):
    monkeypatch.setenv("TEST_CLI_MODE", "sleep")
    async def exercise():
        await cli.create()
        stop = asyncio.Event()
        async def emit(text): pass
        task = asyncio.create_task(cli.run("x", emit, stop))
        while cli.process is None: await asyncio.sleep(.01)
        stop.set()
        with pytest.raises(RunnerError, match="ABORT_UNCONFIRMED"):
            await task
        assert cli.process.returncode is not None
        assert not await cli.abort()
    asyncio.run(exercise())


def test_cli_deadline_reaps_child(cli, monkeypatch):
    monkeypatch.setenv("TEST_CLI_MODE", "sleep")
    cli.timeout = .05
    async def exercise():
        await cli.create()
        async def emit(text): pass
        with pytest.raises(RunnerError, match="OPENCODE_TIMEOUT"):
            await cli.run("x", emit, asyncio.Event())
        assert cli.process.returncode is not None
    asyncio.run(exercise())
