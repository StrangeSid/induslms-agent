#!/usr/bin/env bash
# Install the induslms-academics skill into pi + opencode skill dirs.
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../skills/induslms-academics" && pwd)"
PI_DIR="${PI_SKILL_DIR:-$HOME/.pi/agent/skills}"
OCODE_DIR="${OCODE_SKILL_DIR:-$HOME/.config/opencode/skills}"
mkdir -p "$PI_DIR" "$OCODE_DIR"
rm -rf "$PI_DIR/induslms-academics" "$OCODE_DIR/induslms-academics"
cp -R "$SRC" "$PI_DIR/induslms-academics"
cp -R "$SRC" "$OCODE_DIR/induslms-academics"
echo "installed skill from $SRC"
echo "  pi:       $PI_DIR/induslms-academics"
echo "  opencode: $OCODE_DIR/induslms-academics"
