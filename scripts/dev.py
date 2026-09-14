#!/usr/bin/env python3
"""Prepare dev settings/certificates and run one service without shell evaluation.

Python 3.12+, OpenSSL and (for native components) Linux/macOS/WSL.
Never prints configuration values. Each native service runs in its own terminal.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
COMPONENTS = ("api", "worker", "runner", "opencode")


def export_appsettings(settings):
    envs = environments(settings, "local")
    for name in ("api", "worker"):
        values = {}
        for key, value in envs[name].items():
            if key == "ASPNETCORE_ENVIRONMENT":
                continue
            parts = key.split("__")
            node = values
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = value
        if name == "api":
            values["Runner"]["AllowedThumbprints"] = list(values["Runner"]["AllowedThumbprints"].values())
            values.setdefault("Oidc", {})["AllowLoopbackHttp"] = settings["oidc"].get("allowLoopbackHttp", False)
        project = "Platform.Api" if name == "api" else "Platform.Worker"
        write_private(ROOT / "src" / project / "appsettings.Development.json", json.dumps(values, indent=2) + "\n")


def write_private(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)


def init():
    LOCAL.mkdir(exist_ok=True, mode=0o700)
    config = LOCAL / "settings.json"
    if not config.exists():
        settings = json.loads((ROOT / "deploy/local/settings.example.json").read_text())
        settings["opencodePassword"] = secrets.token_urlsafe(32)
        write_private(config, json.dumps(settings, indent=2) + "\n")
    for directory in ("workspace", "git-credentials", "provider", "temporal",
                      "opencode-data", "opencode-config", "opencode-cache"):
        (LOCAL / directory).mkdir(exist_ok=True)
    certs = LOCAL / "certs"
    if certs.exists():
        print("Existing certificates preserved. Edit .local/settings.json.")
        return
    if not shutil.which("openssl"):
        raise ValueError("OpenSSL required to generate development certificates")
    # Stage generation; a failed command must not leave apparently complete certs.
    import tempfile
    with tempfile.TemporaryDirectory(dir=LOCAL) as temp:
        stage = Path(temp)
        (stage / "api").mkdir()
        (stage / "runner").mkdir()
        def ssl(*args):
            subprocess.run(["openssl", *args], cwd=stage, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "30",
            "-subj", "/CN=Kats development CA", "-keyout", "ca.key", "-out", "ca.crt",
            "-addext", "basicConstraints=critical,CA:TRUE")
        for name, eku, san in (("api", "serverAuth", "DNS:api,DNS:localhost,IP:127.0.0.1"),
                               ("runner", "clientAuth", "DNS:kats-dev-runner")):
            ssl("req", "-newkey", "rsa:2048", "-nodes", "-subj", f"/CN={name}",
                "-keyout", f"{name}/tls.key", "-out", f"{name}.csr")
            (stage / "extensions").write_text(
                f"basicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage={eku}\nsubjectAltName={san}\n")
            ssl("x509", "-req", "-in", f"{name}.csr", "-CA", "ca.crt", "-CAkey", "ca.key",
                "-CAcreateserial", "-days", "30", "-extfile", "extensions", "-out", f"{name}/tls.crt")
        ssl("pkcs12", "-export", "-inkey", "api/tls.key", "-in", "api/tls.crt",
            "-certfile", "ca.crt", "-out", "api/server.pfx", "-passout", "pass:")
        # API container user differs from host; parent .local stays host-private.
        (stage / "api/server.pfx").chmod(0o644)
        (stage / "runner/tls.key").chmod(0o600)
        certs.mkdir()
        shutil.copytree(stage / "api", certs / "api")
        shutil.copytree(stage / "runner", certs / "runner")
        shutil.copy(stage / "ca.crt", certs / "ca.crt")
        shutil.copy(stage / "ca.crt", certs / "runner/ca.crt")
    print("Created .local/settings.json and 30-day development certificates.")


def environments(settings, mode):
    docker = mode == "compose"
    def path(native, container):
        return container if docker else str(LOCAL / native)
    der = subprocess.check_output(["openssl", "x509", "-in", str(LOCAL / "certs/runner/tls.crt"), "-outform", "DER"])
    thumb = hashlib.sha1(der).hexdigest().upper()
    database = {"ConnectionStrings__Platform": settings["database"]}
    api = {**database, "ASPNETCORE_ENVIRONMENT": "Development",
           "Browser__ServerCertificate": path("certs/api/server.pfx", "/certs/api/server.pfx"),
           "Runner__ServerCertificate": path("certs/api/server.pfx", "/certs/api/server.pfx"),
           "Runner__AllowedThumbprints__0": thumb,
           "Security__PublicOrigin": "https://localhost:8443",
           "Security__DataProtectionCertificate": path("certs/api/server.pfx", "/certs/api/server.pfx"),
           "Oidc__Authority": settings["oidc"]["authority"],
           "Oidc__ClientId": settings["oidc"]["clientId"],
           "Oidc__ClientSecret": settings["oidc"]["clientSecret"]}
    if settings["oidc"].get("allowLoopbackHttp", False):
        api["Oidc__AllowLoopbackHttp"] = "true"
    worker = {**database, "Temporal__Endpoint": settings["temporal"]["endpoint"],
              "Temporal__Namespace": settings["temporal"]["namespace"]}
    if settings["temporal"].get("mtls"):
        for key, filename in (("CertPath", "tls.crt"), ("KeyPath", "tls.key"), ("CaPath", "ca.crt")):
            worker["Temporal__" + key] = path("temporal/" + filename, "/certs/temporal/" + filename)
    runner = {"RUNNER_MODE": settings["runner"]["mode"],
              "PLATFORM_GRPC": "api:8081" if docker else "localhost:8081",
              "RUNNER_CA": path("certs/runner/ca.crt", "/certs/runner/ca.crt"),
              "RUNNER_CERT": path("certs/runner/tls.crt", "/certs/runner/tls.crt"),
              "RUNNER_KEY": path("certs/runner/tls.key", "/certs/runner/tls.key"),
              "WORKSPACE_ROOT": path("workspace", "/workspace"),
              "OPENCODE_URL": "http://opencode:4096" if docker else "http://127.0.0.1:4096",
              "OPENCODE_SERVER_PASSWORD": settings["opencodePassword"],
              "OPENCODE_PROVIDER": settings["runner"]["provider"],
              "OPENCODE_MODEL": settings["runner"]["model"],
              "GIT_ALLOWED_HOSTS": settings["runner"]["allowedHosts"],
              "GIT_ASKPASS": "/app/git-askpass.py" if docker else str(ROOT / "scripts/git-askpass.py"),
              "GIT_CREDENTIAL_DIR": path("git-credentials", "/git-credentials")}
    code = {"OPENCODE_SERVER_PASSWORD": settings["opencodePassword"],
            "OPENCODE_CONFIG": path("provider/opencode.json", "/provider/opencode.json"),
            "XDG_DATA_HOME": path("opencode-data", "/data"),
            "XDG_CONFIG_HOME": path("opencode-config", "/config"),
            "XDG_CACHE_HOME": path("opencode-cache", "/cache")}
    backend = settings["runner"].get("backend", "server")
    if docker and backend == "cli":
        raise ValueError("CLI backend uses native installed OpenCode; choose local launch")
    runner["OPENCODE_BACKEND"] = backend
    if backend == "cli":
        runner.update(code)
        runner["OPENCODE_BIN"] = settings["local"]["opencode"]
        runner["OPENCODE_CLI_VERSION"] = settings["runner"].get("cliVersion", "1.2.27")
    return dict(api=api, worker=worker, runner=runner, opencode=code)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--settings", type=Path, default=LOCAL / "settings.json")
    sub = p.add_subparsers(dest="action", required=True)
    sub.add_parser("init")
    sub.add_parser("appsettings", aliases=["rider"])
    render = sub.add_parser("render"); render.add_argument("mode", choices=("local", "compose"))
    run = sub.add_parser("run"); run.add_argument("component", choices=COMPONENTS)
    args = p.parse_args()
    if args.action == "init":
        init(); return
    settings = json.loads(args.settings.read_text())
    if args.action in {"appsettings", "rider"}:
        export_appsettings(settings)
        print("Generated private appsettings.Development.json in API and Worker projects.")
        return
    native_dotnet = args.action == "run" and args.component in {"api", "worker"}
    envs = {} if native_dotnet else environments(settings, args.mode if args.action == "render" else "local")
    if args.action == "render":
        for name, env in envs.items():
            if any("\n" in str(v) or "\r" in str(v) for v in env.values()):
                raise ValueError("Multiline environment values are unsupported; use mounted files")
            write_private(LOCAL / f"{args.mode}-{name}.env", "".join(f"{k}={v}\n" for k, v in env.items()))
        if args.mode == "compose":
            image = settings["images"]["opencode"]
            if any(c.isspace() for c in image) or "$" in image:
                raise ValueError("Invalid image reference")
            write_private(LOCAL / "compose.env", f"DEV_UID={os.getuid()}\nDEV_GID={os.getgid()}\nOPENCODE_IMAGE={image}\n")
        print("Rendered private environment files in .local; values not printed.")
        return
    name = args.component
    executables = settings["local"]
    commands = {
        "api": [executables["dotnet"], "run", "--project", "src/Platform.Api", "--no-launch-profile"],
        "worker": [executables["dotnet"], "run", "--project", "src/Platform.Worker", "--no-launch-profile"],
        "runner": ["uv", "run", "--locked", "--no-dev", "agent-runner"],
        "opencode": [executables["opencode"], "serve", "--hostname", "127.0.0.1", "--port", "4096"]}
    # No shell parsing of secrets. OpenCode does not inherit platform connection strings.
    inherited = {k: v for k, v in os.environ.items() if not k.startswith(
        ("ConnectionStrings__", "Oidc__", "Runner__", "Security__", "Temporal__", "GIT_CREDENTIAL", "RUNNER_"))}
    env = {**inherited, **envs.get(name, {})}
    if name in {"api", "worker"}:
        # Use the same standard JSON configuration as Rider, without overwriting edits.
        env = {**os.environ, "DOTNET_ENVIRONMENT": "Development", "ASPNETCORE_ENVIRONMENT": "Development"}
    if name == "runner":
        env["PYTHONPATH"] = str(ROOT / "agents")
    os.chdir(ROOT)
    os.execvpe(commands[name][0], commands[name], env)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        # Do not echo configuration/command arguments containing secrets.
        print(f"Development setup failed ({type(exc).__name__}); check settings and prerequisites.", file=sys.stderr)
        sys.exit(1)
