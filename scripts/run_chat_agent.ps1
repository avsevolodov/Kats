# Launch Chat Agent with the same mTLS env as OpenCode runner (via dev.py).
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not $env:CHAT_AGENT_MODE) { $env:CHAT_AGENT_MODE = "fake" }
& uv run --locked scripts/dev.py run chat-agent @args
