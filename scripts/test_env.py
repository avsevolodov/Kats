#!/usr/bin/env python3
"""Developer infrastructure in Docker, application processes on the WSL/Linux host."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import urllib.request
import dev

ROOT = dev.ROOT
LOCAL = dev.LOCAL
INFRA = LOCAL / "test-infra"
SETTINGS = LOCAL / "test-settings.json"
REPOSITORY_ID = "11111111-1111-4111-8111-111111111111"


def save(path, value, container_readable=False):
    dev.write_private(path, json.dumps(value, indent=2) + "\n")
    if container_readable:
        path.chmod(0o644)  # Bind-mounted file; host parent .local is private.


def configure():
    dev.init()
    credentials = INFRA / "credentials.json"
    if credentials.exists():
        c = json.loads(credentials.read_text())
    else:
        c = {name: "Kats1!" + secrets.token_hex(16) for name in
             ("sa", "database", "admin", "developer", "other", "client")}
        save(credentials, c)
    dev.write_private(INFRA / "mssql.env", f"MSSQL_SA_PASSWORD={c['sa']}\nSQLCMDPASSWORD={c['sa']}\n")
    dev.write_private(INFRA / "keycloak.env", f"KC_BOOTSTRAP_ADMIN_USERNAME=admin\nKC_BOOTSTRAP_ADMIN_PASSWORD={c['admin']}\n")
    realm = {
        "realm": "kats-dev", "enabled": True, "sslRequired": "none",
        "registrationAllowed": False, "resetPasswordAllowed": False,
        "roles": {"realm": [{"name": "admin", "description": "Repository allowlist admin"}]},
        "clients": [{"clientId": "kats-local", "enabled": True,
            "protocol": "openid-connect", "publicClient": False, "secret": c["client"],
            "standardFlowEnabled": True, "directAccessGrantsEnabled": False,
            "redirectUris": ["https://localhost:8443/signin-oidc"],
            "webOrigins": ["https://localhost:8443"],
            "attributes": {
                "pkce.code.challenge.method": "S256",
                "post.logout.redirect.uris": "https://localhost:8443/*##https://localhost:8443/"
            },
            "protocolMappers": [{
                "name": "realm-roles", "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-realm-role-mapper", "consentRequired": False,
                "config": {"multivalued": "true", "claim.name": "roles", "jsonType.label": "String",
                           "id.token.claim": "true", "access.token.claim": "true", "userinfo.token.claim": "true"}}]}],
        "users": [
            {"username": "admin", "enabled": True, "emailVerified": True,
             "email": "admin@kats.invalid", "firstName": "admin", "lastName": "Test",
             "credentials": [{"type": "password", "value": c["admin"], "temporary": False}],
             "realmRoles": ["admin"]},
            *[{"username": user, "enabled": True, "emailVerified": True,
               "email": user + "@kats.invalid", "firstName": user, "lastName": "Test",
               "credentials": [{"type": "password", "value": c[user], "temporary": False}]}
              for user in ("developer", "other")]]}
    save(INFRA / "realm/kats-dev-realm.json", realm, True)
    # Only locally generated hex-based secrets are interpolated; no untrusted SQL inputs.
    password = c["database"].replace("'", "''")
    sql = """SET NOCOUNT ON;
IF DB_ID(N'KatsDev') IS NULL CREATE DATABASE KatsDev;
GO
USE KatsDev;
GO
""" + (ROOT / "sql/001-initial.sql").read_text() + "\nGO\n" + (ROOT / "sql/002-repository-credentials.sql").read_text() + "\nGO\n" + (ROOT / "sql/003-runner-sessions.sql").read_text() + f"""
GO
IF SUSER_ID(N'kats_dev') IS NULL CREATE LOGIN kats_dev WITH PASSWORD=N'{password}', CHECK_POLICY=OFF;
IF USER_ID(N'kats_dev') IS NULL CREATE USER kats_dev FOR LOGIN kats_dev;
IF IS_ROLEMEMBER('db_datareader','kats_dev') <> 1 ALTER ROLE db_datareader ADD MEMBER kats_dev;
IF IS_ROLEMEMBER('db_datawriter','kats_dev') <> 1 ALTER ROLE db_datawriter ADD MEMBER kats_dev;
IF NOT EXISTS(SELECT 1 FROM dbo.Repositories WHERE Id='{REPOSITORY_ID}')
 INSERT INTO dbo.Repositories(Id,DisplayName,CloneUrl,CredentialRef,AuthKind,ProviderHint,Enabled)
 VALUES('{REPOSITORY_ID}',N'Fake smoke fixture',N'https://example.invalid/kats-fixture.git',N'',N'Anonymous',N'Generic',1);
GO
"""
    dev.write_private(INFRA / "bootstrap/init.sql", sql)
    (INFRA / "bootstrap/init.sql").chmod(0o644)
    if not SETTINGS.exists():
        s = json.loads((ROOT / "deploy/local/settings.example.json").read_text())
        s["database"] = f"Server=localhost,14333;Database=KatsDev;User Id=kats_dev;Password={c['database']};Encrypt=True;TrustServerCertificate=True"
        s["temporal"] = {"endpoint": "localhost:7233", "namespace": "default", "mtls": False}
        s["oidc"] = {"authority": "http://localhost:8180/realms/kats-dev",
                     "clientId": "kats-local", "clientSecret": c["client"], "allowLoopbackHttp": True}
        s["runner"].update(mode="fake", backend="cli")
        s["opencodePassword"] = secrets.token_urlsafe(32)
        save(SETTINGS, s)
    dev.export_appsettings(json.loads(SETTINGS.read_text()))
    print("Test settings prepared; appsettings.Development.json regenerated in API and Worker projects.")


def compose(*args, **kwargs):
    return subprocess.run(["docker", "compose", "-f", str(ROOT / "compose.infra.yaml"),
                           "--project-directory", str(ROOT), *args], cwd=ROOT, check=True, **kwargs)


def check():
    compose("ps")
    compose("exec", "-T", "mssql", "/opt/mssql-tools18/bin/sqlcmd", "-S", "localhost", "-U", "sa",
            "-C", "-b", "-d", "KatsDev", "-Q",
            "IF OBJECT_ID('dbo.Operations') IS NULL THROW 51001,'Schema missing',1; SELECT COUNT(*) AS Repositories FROM dbo.Repositories;")
    compose("exec", "-T", "temporal", "temporal", "operator", "cluster", "health")
    with urllib.request.urlopen("http://localhost:8180/realms/kats-dev/.well-known/openid-configuration", timeout=10) as r:
        discovery = json.load(r)
    if discovery["issuer"] != "http://localhost:8180/realms/kats-dev":
        raise ValueError("Unexpected local OIDC issuer")
    print("SQL schema, Temporal and OIDC discovery checks passed.")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    for action in ("configure", "up", "down", "check"):
        sub.add_parser(action)
    run = sub.add_parser("run")
    run.add_argument("component", choices=dev.COMPONENTS)
    args = p.parse_args()
    if args.action == "configure":
        configure()
    elif args.action == "up":
        configure()
        compose("config", "--quiet")
        compose("up", "-d", "--wait", "--wait-timeout", "240")
        compose("exec", "-T", "mssql", "/opt/mssql-tools18/bin/sqlcmd", "-S", "localhost", "-U", "sa",
                "-C", "-b", "-i", "/bootstrap/init.sql", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        check()
        print("Ready: run api, worker and runner in separate terminals. Credentials: .local/test-infra/credentials.json")
    elif args.action == "down":
        compose("down")  # No volume deletion; no automatic destructive reset.
    elif args.action == "check":
        check()
    else:
        os.execv(sys.executable, [sys.executable, str(ROOT / "scripts/dev.py"), "--settings", str(SETTINGS), "run", args.component])


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError):
        print("Test environment command failed. Check Docker/ports, local settings and container health; no secrets printed.", file=sys.stderr)
        sys.exit(1)
