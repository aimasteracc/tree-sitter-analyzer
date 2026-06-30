#!/usr/bin/env bash
# Install TSA Claude Code hooks into the project's .claude/settings.json.
# Run once after cloning: bash scripts/install_hooks.sh
#
# The hook scripts and base settings.json are committed to the repo under
# .claude/hooks/ and .claude/settings.json. This script ensures they are
# executable and that settings.json contains the hooks stanza.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
SETTINGS="$REPO_ROOT/.claude/settings.json"
HOOKS_DIR="$REPO_ROOT/.claude/hooks"

echo "[tsa-hooks] Installing hooks from: $HOOKS_DIR"

if [ ! -d "$HOOKS_DIR" ]; then
    echo "[tsa-hooks] ERROR: .claude/hooks/ directory not found in repo."
    echo "[tsa-hooks] This directory should be committed to git."
    exit 1
fi

if [ ! -f "$HOOKS_DIR/on-file-edit.sh" ] || [ ! -f "$HOOKS_DIR/pre-edit-impact.sh" ]; then
    echo "[tsa-hooks] ERROR: hook scripts missing from $HOOKS_DIR"
    exit 1
fi

chmod +x "$HOOKS_DIR/on-file-edit.sh" "$HOOKS_DIR/pre-edit-impact.sh"
echo "[tsa-hooks] Hook scripts are executable."

# Create or validate settings.json
if [ ! -f "$SETTINGS" ]; then
    echo "[tsa-hooks] Creating .claude/settings.json with hooks stanza..."
    mkdir -p "$(dirname "$SETTINGS")"
    cat > "$SETTINGS" << 'EOF'
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/on-file-edit.sh"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/pre-edit-impact.sh"
          }
        ]
      }
    ]
  }
}
EOF
    echo "[tsa-hooks] Created settings.json with hooks stanza."
else
    # Validate that hooks stanza exists; add it if missing
    python3 - "$SETTINGS" << 'PY'
import json
import sys

settings_path = sys.argv[1]
with open(settings_path) as f:
    cfg = json.load(f)

if "hooks" not in cfg:
    print("[tsa-hooks] hooks stanza missing — adding it...")
    cfg["hooks"] = {
        "PostToolUse": [
            {
                "matcher": "Edit|Write|MultiEdit",
                "hooks": [{"type": "command", "command": "bash .claude/hooks/on-file-edit.sh"}],
            }
        ],
        "PreToolUse": [
            {
                "matcher": "Edit|Write|MultiEdit",
                "hooks": [{"type": "command", "command": "bash .claude/hooks/pre-edit-impact.sh"}],
            }
        ],
    }
    with open(settings_path, "w") as f:
        json.dump(cfg, f, indent=2)
    print("[tsa-hooks] Added hooks stanza to existing settings.json")
else:
    print("[tsa-hooks] settings.json already has hooks stanza - OK.")
PY
fi

echo "[tsa-hooks] Hooks registered:"
echo "  PostToolUse (Edit|Write|MultiEdit) -> on-file-edit.sh (incremental KG update)"
echo "  PreToolUse  (Edit|Write|MultiEdit) -> pre-edit-impact.sh (change-impact injection)"
echo ""
echo "[tsa-hooks] To verify hooks are active, open Claude Code in this repo and edit a file."
echo "[tsa-hooks] Knowledge graph update log: /tmp/tsa-kg-update.log"
echo "[tsa-hooks] Done."
