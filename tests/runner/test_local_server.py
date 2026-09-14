import asyncio
import os
from pathlib import Path
import pytest
from opencode_runner.local_server import LocalOpenCode


@pytest.mark.skipif(os.name != "posix", reason="WSL/POSIX backend")
def test_local_server_start_stop_and_private_environment(tmp_path, monkeypatch):
    executable = tmp_path / "opencode"
    executable.write_text('''#!/usr/bin/env python3
import sys,json,os
from http.server import BaseHTTPRequestHandler,HTTPServer
if sys.argv[1] == "--version": print("1.2.27"); sys.exit(0)
assert "GIT_PASSWORD" not in os.environ
assert "RUNNER_KEY" not in os.environ
assert os.environ["OPENCODE_SERVER_PASSWORD"]
assert json.loads(os.environ["OPENCODE_PERMISSION"])["*"] == "ask"
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.end_headers();self.wfile.write(b'{"healthy":true,"version":"1.2.27"}')
 def log_message(self,*args): pass
HTTPServer(("127.0.0.1",int(sys.argv[-1])),Handler).serve_forever()
''')
    executable.chmod(0o755)
    monkeypatch.setenv("OPENCODE_BIN", str(executable))
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("GIT_PASSWORD", "not-for-opencode")
    monkeypatch.setenv("RUNNER_KEY", "not-for-opencode")
    monkeypatch.setenv("OPENCODE_CLI_VERSION", "1.2.27")
    async def exercise():
        code = LocalOpenCode()
        try:
            async with asyncio.timeout(10):
                while True:
                    try:
                        await code.health()
                        break
                    except Exception:
                        await asyncio.sleep(.05)
            assert code.version == "1.2.27"
            child = code.child
        finally:
            await code.close()
        assert child.returncode is not None
    asyncio.run(exercise())
