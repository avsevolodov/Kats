import asyncio
import httpx
from opencode_runner.opencode import OpenCode
from opencode_runner.workspace import Workspace


def test_native_directory_matches_checkout_for_all_requests(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path / "workspace with spaces"))
    workspace = Workspace(str(tmp_path / "workspace with spaces"))
    seen = []

    async def handler(request):
        seen.append(request.url.params.get("directory"))
        if request.url.path == "/session":
            return httpx.Response(200, json={"id": "local"})
        if request.url.path == "/session/status":
            return httpx.Response(200, json={})
        return httpx.Response(200, json=True)

    async def exercise():
        code = OpenCode(transport=httpx.MockTransport(handler))
        assert code.directory == str(workspace.repo)
        await code.create()
        assert await code.abort()
        await code.close()

    asyncio.run(exercise())
    assert seen == [str(workspace.repo)] * 3
