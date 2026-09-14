import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import dev


def test_rider_export_uses_dotnet_keys_and_private_files(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, "ROOT", tmp_path)
    monkeypatch.setattr(dev, "environments", lambda *_: {
        "api": {"ConnectionStrings__Platform": "private", "Runner__AllowedThumbprints__0": "ABC"},
        "worker": {"Temporal__Endpoint": "localhost:7233"}})
    dev.export_appsettings({"oidc": {}})
    target = tmp_path / "src/Platform.Api/appsettings.Development.json"
    assert json.loads(target.read_text()) == {"ConnectionStrings": {"Platform": "private"}, "Runner": {"AllowedThumbprints": ["ABC"]}, "Oidc": {"AllowLoopbackHttp": False}}
    assert target.stat().st_mode & 0o777 == 0o600
    assert json.loads((tmp_path / "src/Platform.Worker/appsettings.Development.json").read_text())["Temporal"]["Endpoint"] == "localhost:7233"
