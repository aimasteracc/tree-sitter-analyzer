#!/usr/bin/env bash
# Install TSA Claude Code hooks into the project's .claude/settings.json.
# Run once after cloning: bash scripts/install_hooks.sh
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
SETTINGS="$REPO_ROOT/.claude/settings.json"
HOOKS_DIR="$REPO_ROOT/.claude/hooks"

echo "[tsa-hooks] Checking hooks directory: $HOOKS_DIR"

if [ ! -d "$HOOKS_DIR" ]; then
    echo "[tsa-hooks] ERROR: .claude/hooks/ directory not found. Run from repo root."
    exit 1
fi

chmod +x "$HOOKS_DIR/on-file-edit.sh" "$HOOKS_DIR/pre-edit-impact.sh"
echo "[tsa-hooks] Hook scripts are executable."

if [ ! -f "$SETTINGS" ]; then
    echo "[tsa-hooks] ERROR: .claude/settings.json not found."
    exit 1
fi

echo "[tsa-hooks] Settings already configured at: $SETTINGS"
echo "[tsa-hooks] Hooks registered:"
echo "  PostToolUse (Edit|Write|MultiEdit) → on-file-edit.sh (incremental KG update)"
echo "  PreToolUse  (Edit|Write|MultiEdit) → pre-edit-impact.sh (change-impact injection)"
echo ""
echo "[tsa-hooks] To verify hooks are active, open Claude Code in this repo and edit a file."
echo "[tsa-hooks] Knowledge graph update log: /tmp/tsa-kg-update.log"
echo "[tsa-hooks] Done."
