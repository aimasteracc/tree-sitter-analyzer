#!/usr/bin/env bash
# install.sh — Tree-sitter Analyzer one-command installer
# Supports: macOS / Linux. Windows PowerShell: use install.ps1 (coming soon).
# bash 3.x compatible (no declare -A, no ${var,,}, no mapfile)
set -euo pipefail

# ─── Windows MSYS2/MINGW guard ────────────────────────────────────────────────
case "$(uname -s)" in
  MINGW* | MSYS*)
    echo "Windows PowerShell: use install.ps1 (coming soon)"
    exit 0
    ;;
esac

# ─── WSL detection ────────────────────────────────────────────────────────────
WSL_ENV=0
if [ -f /proc/version ] && grep -qi microsoft /proc/version 2>/dev/null; then
  WSL_ENV=1
  echo "ℹ️  WSL 環境が検出されました。エージェント自動検出は動作しない場合があります。"
fi

# ─── uv check & auto-install ──────────────────────────────────────────────────
if ! command -v uv >/dev/null 2>&1; then
  echo "📦 uv が見つかりません。自動インストールします..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # Re-source common profile locations
  if [ -f "$HOME/.cargo/env" ]; then
    # shellcheck disable=SC1091
    . "$HOME/.cargo/env"
  fi
  export PATH="$HOME/.local/bin:$PATH"
  if ! command -v uv >/dev/null 2>&1; then
    echo "❌ uv のインストールに失敗しました。手動でインストールしてから再実行してください:"
    echo "   https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
  fi
  echo "✅ uv がインストールされました: $(command -v uv)"
else
  echo "✅ uv: $(command -v uv)"
fi

# ─── fd / ripgrep check (optional, warning only) ──────────────────────────────
if ! command -v fd >/dev/null 2>&1; then
  echo "⚠️  fd が見つかりません (text search に必要)。後でインストールしてください:"
  if [ "$(uname -s)" = "Darwin" ]; then
    echo "   brew install fd"
  else
    echo "   apt install fd-find  # または sudo snap install fd"
  fi
fi

if ! command -v rg >/dev/null 2>&1; then
  echo "⚠️  ripgrep (rg) が見つかりません (text search に必要)。後でインストールしてください:"
  if [ "$(uname -s)" = "Darwin" ]; then
    echo "   brew install ripgrep"
  else
    echo "   apt install ripgrep"
  fi
fi

# ─── Resolve absolute project root ────────────────────────────────────────────
if command -v realpath >/dev/null 2>&1; then
  PROJECT_ROOT=$(realpath .)
else
  PROJECT_ROOT=$(pwd)
fi
echo ""
echo "📁 プロジェクトルート: $PROJECT_ROOT"

# ─── Agent config paths ───────────────────────────────────────────────────────
OS_TYPE="$(uname -s)"

# Build list of (label, path) pairs using positional variables (bash 3.x compatible)
# Format: "label|path" — process with IFS='|'

AGENT_CONFIG_ENTRIES=""

if [ "$OS_TYPE" = "Darwin" ]; then
  AGENT_CONFIG_ENTRIES="${AGENT_CONFIG_ENTRIES}Claude Desktop (macOS)|$HOME/Library/Application Support/Claude/claude_desktop_config.json\n"
else
  AGENT_CONFIG_ENTRIES="${AGENT_CONFIG_ENTRIES}Claude Desktop (Linux)|$HOME/.config/claude/claude_desktop_config.json\n"
fi

AGENT_CONFIG_ENTRIES="${AGENT_CONFIG_ENTRIES}Claude Code (global)|$HOME/.claude/.mcp.json\n"
AGENT_CONFIG_ENTRIES="${AGENT_CONFIG_ENTRIES}Claude Code (project-local)|$(pwd)/.claude/.mcp.json\n"
AGENT_CONFIG_ENTRIES="${AGENT_CONFIG_ENTRIES}Cursor|$HOME/.cursor/mcp.json\n"

if [ "$OS_TYPE" = "Darwin" ]; then
  AGENT_CONFIG_ENTRIES="${AGENT_CONFIG_ENTRIES}VS Code (macOS)|$HOME/Library/Application Support/Code/User/mcp.json\n"
else
  AGENT_CONFIG_ENTRIES="${AGENT_CONFIG_ENTRIES}VS Code (Linux)|$HOME/.config/Code/User/mcp.json\n"
fi

# ─── Process each agent config ────────────────────────────────────────────────
CONFIGURED_AGENTS=""
SKIPPED_AGENTS=""

echo ""
echo "🔍 エージェント設定ファイルを検索中..."

# Use printf to interpret \n, then process line by line
while IFS='|' read -r AGENT_LABEL CONFIG_PATH; do
  # Skip empty lines
  if [ -z "$AGENT_LABEL" ]; then
    continue
  fi

  if [ ! -f "$CONFIG_PATH" ]; then
    echo "   ⏭️  $AGENT_LABEL: 設定ファイルが見つかりません ($CONFIG_PATH)"
    SKIPPED_AGENTS="${SKIPPED_AGENTS}${AGENT_LABEL}\n"
    continue
  fi

  echo "   🔧 $AGENT_LABEL: 設定中..."

  # Merge MCP entry using python3
  MERGE_RESULT=$(python3 - "$CONFIG_PATH" "$PROJECT_ROOT" <<'PYEOF'
import sys, json, shutil, os

config_path = sys.argv[1]
project_root = sys.argv[2]

# Create backup with timestamp
import datetime
timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
backup_path = config_path + ".bak." + timestamp
shutil.copy2(config_path, backup_path)

# Parse existing JSON
try:
    with open(config_path, encoding="utf-8") as f:
        data = json.load(f)
except json.JSONDecodeError as e:
    print(f"PARSE_ERROR:{e}", file=sys.stderr)
    sys.exit(2)

# Ensure mcpServers key exists
if "mcpServers" not in data:
    data["mcpServers"] = {}

# Merge TSA entry (preserves existing entries)
data["mcpServers"]["tree-sitter-analyzer"] = {
    "command": "uvx",
    "args": ["--from", "tree-sitter-analyzer[mcp]", "tree-sitter-analyzer-mcp"],
    "env": {"TREE_SITTER_PROJECT_ROOT": project_root},
}

with open(config_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")

print(f"OK:{backup_path}")
PYEOF
  )
  MERGE_EXIT=$?

  if [ "$MERGE_EXIT" = "2" ]; then
    echo "   ❌ $AGENT_LABEL: JSON 解析エラー — スキップします ($CONFIG_PATH)"
    SKIPPED_AGENTS="${SKIPPED_AGENTS}${AGENT_LABEL} (JSON parse error)\n"
  elif [ "$MERGE_EXIT" = "0" ]; then
    BACKUP_PATH="${MERGE_RESULT#OK:}"
    echo "   ✅ $AGENT_LABEL: 設定完了 (バックアップ: $BACKUP_PATH)"
    CONFIGURED_AGENTS="${CONFIGURED_AGENTS}${AGENT_LABEL}\n"
  else
    echo "   ❌ $AGENT_LABEL: 予期しないエラー (exit $MERGE_EXIT) — スキップします"
    SKIPPED_AGENTS="${SKIPPED_AGENTS}${AGENT_LABEL} (error)\n"
  fi

done <<EOF
$(printf "$AGENT_CONFIG_ENTRIES")
EOF

# ─── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "🎉 Tree-sitter Analyzer インストール完了"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "📌 プロジェクトルート: $PROJECT_ROOT"
echo ""

if [ -n "$CONFIGURED_AGENTS" ]; then
  echo "✅ 設定済みエージェント:"
  printf "$CONFIGURED_AGENTS" | while IFS= read -r agent; do
    [ -n "$agent" ] && echo "   • $agent"
  done
  echo ""
fi

if [ -n "$SKIPPED_AGENTS" ]; then
  echo "⏭️  スキップされたエージェント (設定ファイルなし):"
  printf "$SKIPPED_AGENTS" | while IFS= read -r agent; do
    [ -n "$agent" ] && echo "   • $agent"
  done
  echo ""
fi

echo "📋 次のステップ:"
echo "   1. エージェント (Claude Code / Claude Desktop / Cursor / VS Code) を再起動してください"
echo "   2. エージェントに「Run the index tool with action=status」と入力してください"
echo "   3. 問題が発生した場合: tree-sitter-analyzer --doctor"
echo ""

if [ "$WSL_ENV" = "1" ]; then
  echo "⚠️  WSL 環境: エージェント設定が正しく反映されない場合は、"
  echo "   Windows 側の設定ファイルを手動で確認してください。"
fi
