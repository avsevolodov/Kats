import asyncio
import json
from pathlib import Path
from opencode_runner import runner_pb2 as pb
from opencode_runner.workspace import Workspace


class FakeTransport:
    def __init__(self, username="x-access-token", password="secret-token"):
        self.username, self.password = username, password
        self.calls = 0

    async def request(self, field, payload, **kwargs):
        self.calls += 1
        assert field == "fetch_git_credential"
        return pb.GatewayFrame(git_credential=pb.GitCredential(auth_kind="pat", username=self.username, password=self.password))


def test_pat_fetch_writes_and_wipes_temp_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_ALLOWED_HOSTS", "github.com")
    monkeypatch.setenv("GIT_ASKPASS", str(tmp_path / "askpass"))
    (tmp_path / "askpass").write_text("#!/bin/sh\n")
    seen = {}

    async def fake_git(self, *args, cwd=None, env=None):
        if args and args[0] == "fetch":
            seen["env"] = dict(env or {})
            path = Path(env["GIT_CREDENTIAL_FILE"])
            seen["secret"] = path.read_text(encoding="utf-8")
            seen["path"] = path
            return b""
        if args[:1] == ("init",):
            return b""
        if args[:1] == ("checkout",):
            return b""
        if args[:2] == ("rev-parse", "HEAD"):
            return b"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        return b""

    monkeypatch.setattr(Workspace, "git", fake_git)
    workspace = Workspace(str(tmp_path / "ws"))
    assignment = pb.Assignment(
        key=pb.OperationKey(operation_id="11111111-1111-4111-8111-111111111111", boot_id="boot", fence=1),
        clone_url="https://github.com/org/repo.git",
        base_commit="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        auth_kind="pat",
        credential_ref="",
    )
    transport = FakeTransport()
    asyncio.run(workspace.prepare(assignment, transport))
    assert transport.calls == 1
    assert json.loads(seen["secret"]) == {"username": "x-access-token", "password": "secret-token"}
    assert not seen["path"].exists()


def test_anonymous_skips_askpass(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_ALLOWED_HOSTS", "example.invalid")
    seen = {}

    async def fake_git(self, *args, cwd=None, env=None):
        if args and args[0] == "fetch":
            seen["env"] = dict(env or {})
            return b""
        if args[:1] == ("init",):
            return b""
        if args[:1] == ("checkout",):
            return b""
        if args[:2] == ("rev-parse", "HEAD"):
            return b"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n"
        return b""

    monkeypatch.setattr(Workspace, "git", fake_git)
    workspace = Workspace(str(tmp_path / "ws"))
    assignment = pb.Assignment(
        clone_url="https://example.invalid/repo.git",
        base_commit="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        auth_kind="anonymous",
    )
    asyncio.run(workspace.prepare(assignment, FakeTransport()))
    assert "GIT_ASKPASS" not in seen["env"]
    assert "GIT_CREDENTIAL_FILE" not in seen["env"]
