#!/usr/bin/env bash
# Install the induslms skill into pi + opencode skill dirs.
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../skills/induslms" && pwd)"
PI_DIR="${PI_SKILL_DIR:-$HOME/.pi/skills}"
OCODE_DIR="${OCODE_SKILL_DIR:-$HOME/.config/opencode/skills}"
mkdir -p "$PI_DIR" "$OCODE_DIR"
cp -R "$SRC" "$PI_DIR/induslms" 2>/dev/null || true
cp -R "$SRC" "$OCODE_DIR/induslms" 2>/dev/null || true
echo "installed skill from $SRC"
echo "  pi:       $PI_DIR/induslms"
echo "  opencode: $OCODE_DIR/induslms"
