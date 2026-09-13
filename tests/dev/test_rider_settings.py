import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import dev


def test_rider_export_uses_dotnet_keys_and_private_files(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, "LOCAL", tmp_path)
    monkeypatch.setattr(dev, "environments", lambda *_: {
        "api": {"ConnectionStrings__Platform": "private", "Runner__AllowedThumbprints__0": "ABC"},
        "worker": {"Temporal__Endpoint": "localhost:7233"}})
    dev.export_rider({}, "test")
    target = tmp_path / "rider-test-api.json"
    assert json.loads(target.read_text()) == {"ConnectionStrings:Platform": "private", "Runner:AllowedThumbprints:0": "ABC"}
    assert target.stat().st_mode & 0o777 == 0o600
    assert "Temporal:Endpoint" in json.loads((tmp_path / "rider-test-worker.json").read_text())
