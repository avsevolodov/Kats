import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import dev
import test_env


def test_setup_preserves_secrets_and_existing_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, "init", lambda: None)
    monkeypatch.setattr(dev, "export_appsettings", lambda *args: None)
    monkeypatch.setattr(test_env, "LOCAL", tmp_path)
    monkeypatch.setattr(test_env, "INFRA", tmp_path / "test-infra")
    monkeypatch.setattr(test_env, "SETTINGS", tmp_path / "test-settings.json")
    test_env.configure()
    first = (tmp_path / "test-infra/credentials.json").read_bytes()
    settings = json.loads((tmp_path / "test-settings.json").read_text())
    assert settings["runner"]["mode"] == "fake"
    assert settings["oidc"]["allowLoopbackHttp"] is True
    assert "User Id=kats_dev;" in settings["database"]
    settings["runner"]["model"] = "custom-model"
    (tmp_path / "test-settings.json").write_text(json.dumps(settings))
    test_env.configure()
    assert (tmp_path / "test-infra/credentials.json").read_bytes() == first
    assert json.loads((tmp_path / "test-settings.json").read_text())["runner"]["model"] == "custom-model"
    realm = json.loads((tmp_path / "test-infra/realm/kats-dev-realm.json").read_text())
    assert {u["username"] for u in realm["users"]} == {"admin", "developer", "other"}
    assert "admin" in {r["name"] for r in realm["roles"]["realm"]}
    assert realm["users"][0]["username"] == "admin" and "admin" in realm["users"][0]["realmRoles"]
    assert realm["clients"][0]["directAccessGrantsEnabled"] is False
    assert realm["clients"][0]["protocolMappers"][0]["config"]["claim.name"] == "roles"


def test_down_preserves_volumes(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "argv", ["test_env.py", "down"])
    monkeypatch.setattr(test_env, "compose", lambda *args: calls.append(args))
    test_env.main()
    assert calls == [("down",)]
