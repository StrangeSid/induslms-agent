#!/usr/bin/env bash
# Install the induslms-academics skill into pi + opencode + Claude skill dirs.
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../skills/induslms-academics" && pwd)"
PI_DIR="${PI_SKILL_DIR:-$HOME/.pi/agent/skills}"
OCODE_DIR="${OCODE_SKILL_DIR:-$HOME/.config/opencode/skills}"
CLAUDE_USER_DIR="${CLAUDE_SKILL_DIR:-$HOME/.claude/skills}"
CLAUDE_PROJ_DIR="$PWD/.claude/skills"
mkdir -p "$PI_DIR" "$OCODE_DIR" "$CLAUDE_USER_DIR"
rm -rf "$PI_DIR/induslms-academics" "$OCODE_DIR/induslms-academics" "$CLAUDE_USER_DIR/induslms-academics"
cp -R "$SRC" "$PI_DIR/induslms-academics"
cp -R "$SRC" "$OCODE_DIR/induslms-academics"
cp -R "$SRC" "$CLAUDE_USER_DIR/induslms-academics"
echo "installed skill from $SRC"
echo "  pi:       $PI_DIR/induslms-academics"
echo "  opencode: $OCODE_DIR/induslms-academics"
echo "  claude:   $CLAUDE_USER_DIR/induslms-academics"
if [ "${INSTALL_PROJECT_SKILL:-0}" = "1" ]; then
  mkdir -p "$CLAUDE_PROJ_DIR"
  rm -rf "$CLAUDE_PROJ_DIR/induslms-academics"
  cp -R "$SRC" "$CLAUDE_PROJ_DIR/induslms-academics"
  echo "  project:  $CLAUDE_PROJ_DIR/induslms-academics"
fi
