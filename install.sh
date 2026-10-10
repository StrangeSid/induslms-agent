#!/usr/bin/env bash
# One-command installer for induslms-agent (idempotent).
# - Creates .venv, installs package (editable) + deps
# - Prompts for login (or uses INDUSLMS_EMAIL/PASS) -> token outside repo
# - Merges MCP configs for pi + opencode (never overwrites other servers)
# - Installs skill, runs doctor
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_BIN="$REPO/.venv/bin/python"
PIP_BIN="$REPO/.venv/bin/pip"

echo "==> induslms-agent installer ($REPO)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 not found (need >=3.10)" >&2
  exit 1
fi

if [ ! -x "$PY_BIN" ]; then
  python3 -m venv "$REPO/.venv"
fi
"$PIP_BIN" install -q -e "$REPO"

# Login (skip if token already works)
if "$PY_BIN" lms.py doctor 2>/dev/null | grep -q "lms_token: ok"; then
  echo "==> LMS token already OK, skipping login"
else
  EMAIL="${INDUSLMS_EMAIL:-}"
  if [ -z "$EMAIL" ]; then
    printf "School email: "
    read -r EMAIL
  fi
  "$PY_BIN" lms.py login "$EMAIL"
fi

# Merge MCP configs via stdlib json (idempotent)
"$PY_BIN" - "$REPO" <<'PY'
import json, os, sys
repo = sys.argv[1]
py = os.path.join(repo, ".venv", "bin", "python")
srv = os.path.join(repo, "server.py")

def merge_pi(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {}
    if os.path.exists(path):
        try:
            data = json.load(open(path))
        except Exception:
            data = {}
    data.setdefault("mcpServers", {})
    data["mcpServers"]["induslms-academics"] = {
        "command": py, "args": [srv], "cwd": repo,
        "env": {"INDUSLMS_TENANT": "${INDUSLMS_TENANT}"},
        "description": "Indus LMS academics (reads + confirmed writes) + school inbox",
    }
    json.dump(data, open(path, "w"), indent=2)
    print(f"  pi: {path}")

def merge_opencode(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {}
    if os.path.exists(path):
        try:
            text = open(path).read()
            data = json.loads(text) if text.strip() else {}
        except Exception:
            print(f"  warn: could not parse {path}, skipping")
            return
    data.setdefault("mcp", {})
    data["mcp"]["induslms-academics"] = {
        "type": "local",
        "command": [py, srv],
        "cwd": repo,
        "environment": {"INDUSLMS_TENANT": "{env:INDUSLMS_TENANT}"},
        "enabled": True,
        "timeout": 15000,
    }
    json.dump(data, open(path, "w"), indent=2)
    print(f"  opencode: {path}")

merge_pi(os.path.expanduser("~/.pi/agent/mcp.json"))
for p in (os.path.expanduser("~/.config/opencode/opencode.json"),
          os.path.expanduser("~/.config/opencode/opencode.jsonc")):
    # only write jsonc if json doesn't exist, to avoid duplicates
    if p.endswith(".jsonc") and os.path.exists(os.path.expanduser("~/.config/opencode/opencode.json")):
        continue
    try:
        merge_opencode(p)
        break
    except Exception as e:
        print(f"  warn opencode: {e}")
PY

bash "$REPO/scripts/install-skill.sh"

echo "==> doctor"
"$PY_BIN" lms.py doctor || true

cat <<EOF

Next:
  1. Restart pi / opencode / Claude Code
  2. Ask: "list my courses using induslms-academics"
  3. Claude Code: claude mcp add induslms-academics -- $PY_BIN $REPO/server.py
     Desktop: copy examples/claude_desktop_config.json.example entry
EOF
