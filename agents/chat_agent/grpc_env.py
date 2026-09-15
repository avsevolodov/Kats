"""Resolve PLATFORM_GRPC / mTLS like OpenCode runner (WSL NAT + no HTTP proxy)."""

from __future__ import annotations

import json
import os
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SETTINGS = _REPO / ".local" / "settings.json"
_PROXY_KEYS = (
    "http_proxy",
    "https_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "all_proxy",
    "grpc_proxy",
    "GRPC_PROXY",
)


def scrub_proxy_env(grpc_target: str) -> None:
    """Corporate HTTP_PROXY sends gRPC to 127.0.0.1:3128 → 502; strip and allowlist target host."""
    for key in _PROXY_KEYS:
        os.environ.pop(key, None)
    host = grpc_target.rsplit(":", 1)[0]
    existing = os.environ.get("no_proxy") or os.environ.get("NO_PROXY") or ""
    entries = {item.strip() for item in existing.split(",") if item.strip()}
    entries.update({host, "localhost", "127.0.0.1", "api", "::1"})
    joined = ",".join(sorted(entries))
    os.environ["no_proxy"] = os.environ["NO_PROXY"] = joined


def resolve_platform_grpc() -> tuple[str, str | None]:
    """Return (authority, ssl_name_override). Prefer env, then settings.local.platformGrpc."""
    env_target = (os.environ.get("PLATFORM_GRPC") or "").strip()
    if env_target:
        host = env_target.rsplit(":", 1)[0]
        ssl = os.environ.get("PLATFORM_GRPC_SSL_NAME")
        if not ssl and host not in {"localhost", "127.0.0.1", "api"}:
            ssl = "localhost"
        return env_target, ssl or None
    if _SETTINGS.is_file():
        settings = json.loads(_SETTINGS.read_text(encoding="utf-8"))
        override = ((settings.get("local") or {}).get("platformGrpc") or "").strip()
        if override:
            host = override.rsplit(":", 1)[0]
            ssl = None if host in {"localhost", "127.0.0.1", "api"} else "localhost"
            return override, ssl
    return "localhost:8081", None
