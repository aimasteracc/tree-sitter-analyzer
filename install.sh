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
  echo "ℹ️  WSL detected. Agent auto-detection may not work in all cases."
fi

# ─── uv check & auto-install ──────────────────────────────────────────────────
MINIMUM_UV_VERSION="0.11.0"

uv_version_is_supported() {
  # Match doctor's contract: exactly one "uv X.Y.Z" line, with optional metadata.
  UV_VERSION_TEXT=$1
  UV_VERSION=$(printf '%s\n' "$UV_VERSION_TEXT" | awk '
    NR == 1 && /^uv [0-9]+\.[0-9]+\.[0-9]+([[:blank:]].*)?$/ { version = $2 }
    END { if (NR != 1 || version == "") exit 1; print version }
  ') || return 1
  UV_MAJOR=$(printf '%s\n' "$UV_VERSION" | awk -F. '{print $1}')
  UV_MINOR=$(printf '%s\n' "$UV_VERSION" | awk -F. '{print $2}')

  # Compare digit strings rather than shell integers.  Version output is an
  # external boundary and components may exceed the native integer range.
  while [ "${UV_MAJOR#0}" != "$UV_MAJOR" ]; do UV_MAJOR=${UV_MAJOR#0}; done
  while [ "${UV_MINOR#0}" != "$UV_MINOR" ]; do UV_MINOR=${UV_MINOR#0}; done
  [ -n "$UV_MAJOR" ] || UV_MAJOR=0
  [ -n "$UV_MINOR" ] || UV_MINOR=0
  if [ "${#UV_MAJOR}" -gt 1 ] || { [ "${#UV_MAJOR}" -eq 1 ] && [ "$UV_MAJOR" \> 0 ]; }; then
    return 0
  fi
  [ "$UV_MAJOR" = 0 ] || return 1
  [ "${#UV_MINOR}" -gt 2 ] || {
    [ "${#UV_MINOR}" -eq 2 ] && { [ "$UV_MINOR" = 11 ] || [ "$UV_MINOR" \> 11 ]; }
  }
}

terminate_uv_version_probe_on_signal() {
  UV_VERSION_PROBE_SIGNAL_STATUS=$1
  # Ignore a second termination request while the isolated probe group is
  # being torn down; otherwise it could interrupt cleanup and leak the temp.
  trap '' HUP INT TERM
  kill -TERM -"$UV_VERSION_PROBE_PID" 2>/dev/null || :
  sleep 1
  kill -KILL -"$UV_VERSION_PROBE_PID" 2>/dev/null || :
  wait "$UV_VERSION_PROBE_PID" 2>/dev/null || :
  rm -f "$UV_VERSION_PROBE_OUTPUT"
  exit "$UV_VERSION_PROBE_SIGNAL_STATUS"
}

probe_uv_version() {
  # Portable bounded probe: macOS has no coreutils `timeout`, and bash 3.x has
  # no `wait -n`. Capture to a file so a killed shim cannot hold a command
  # substitution pipe open through one of its children.
  UV_VERSION_PROBE_ERROR="failed"
  UV_VERSION_PROBE_OUTPUT=$(mktemp "${TMPDIR:-/tmp}/tsa-uv-version.XXXXXX") || return 1

  # Monitor mode gives the background probe its own process group on both
  # bash 3 (macOS) and current bash (Linux), so timeout cleanup reaches shims'
  # descendants instead of killing only the immediate uv process.
  set -m
  uv --version >"$UV_VERSION_PROBE_OUTPUT" 2>/dev/null &
  UV_VERSION_PROBE_PID=$!
  set +m
  trap 'terminate_uv_version_probe_on_signal 129' HUP
  trap 'terminate_uv_version_probe_on_signal 130' INT
  trap 'terminate_uv_version_probe_on_signal 143' TERM
  UV_VERSION_WAIT_COUNT=0
  while kill -0 "$UV_VERSION_PROBE_PID" 2>/dev/null; do
    if [ "$UV_VERSION_WAIT_COUNT" -eq 50 ]; then
      UV_VERSION_PROBE_ERROR="timeout"
      kill -TERM -"$UV_VERSION_PROBE_PID" 2>/dev/null || :
      sleep 1
      kill -KILL -"$UV_VERSION_PROBE_PID" 2>/dev/null || :
      break
    fi
    sleep 0.1
    UV_VERSION_WAIT_COUNT=$((UV_VERSION_WAIT_COUNT + 1))
  done

  if wait "$UV_VERSION_PROBE_PID"; then
    UV_VERSION_PROBE_STATUS=0
  else
    UV_VERSION_PROBE_STATUS=$?
  fi
  UV_VERSION_OUTPUT=$(cat "$UV_VERSION_PROBE_OUTPUT")
  rm -f "$UV_VERSION_PROBE_OUTPUT"
  trap - HUP INT TERM
  if [ "$UV_VERSION_PROBE_ERROR" = "timeout" ]; then
    return 1
  fi
  [ "$UV_VERSION_PROBE_STATUS" -eq 0 ]
}

uv_is_ready() {
  UV_VERSION_PROBE_ERROR="missing"
  command -v uv >/dev/null 2>&1 || return 1
  probe_uv_version || return 1
  uv_version_is_supported "$UV_VERSION_OUTPUT"
}

UV_INSTALL_NEEDED=0
UV_INSTALL_ACTION="install"
if ! command -v uv >/dev/null 2>&1; then
  echo "📦 uv not found. Automatic installation is required."
  UV_INSTALL_NEEDED=1
elif ! probe_uv_version; then
  if [ "$UV_VERSION_PROBE_ERROR" = "timeout" ]; then
    echo "❌ Timed out after 5 seconds running $(command -v uv) --version."
  else
    echo "❌ Existing uv at $(command -v uv) could not report its version."
  fi
  echo "   Required: uv >= $MINIMUM_UV_VERSION"
  echo "   Replace or repair uv, then re-run the original Tree-sitter Analyzer install command."
  exit 1
elif ! uv_version_is_supported "$UV_VERSION_OUTPUT"; then
  echo "📦 $UV_VERSION_OUTPUT does not satisfy required uv >= $MINIMUM_UV_VERSION. Automatic update is required."
  UV_INSTALL_ACTION="update"
  UV_INSTALL_NEEDED=1
fi

if [ "$UV_INSTALL_NEEDED" = "1" ]; then
  if [ "${TSA_DISABLE_UNVERIFIED_UV_BOOTSTRAP:-0}" = "1" ]; then
    echo "❌ Automatic uv bootstrap disabled by TSA_DISABLE_UNVERIFIED_UV_BOOTSTRAP=1."
    echo "   Install uv >= $MINIMUM_UV_VERSION manually: https://docs.astral.sh/uv/"
    echo "   Then re-run the original Tree-sitter Analyzer install command."
    exit 1
  fi
  if ! command -v curl >/dev/null 2>&1; then
    echo "❌ curl not found — cannot download the uv installer over TLS."
    echo "   Install curl and re-run, or install uv >= $MINIMUM_UV_VERSION manually."
    exit 1
  fi
  echo "⚠️  WARNING: the official uv bootstrap is UNVERIFIED and mutable (not content-bound)."
  echo "   It will be downloaded over TLS to a temporary file and checked after execution."
  if [ "$UV_INSTALL_ACTION" = "update" ]; then
    echo "📦 Updating uv automatically..."
  else
    echo "📦 Installing uv automatically..."
  fi
  UV_INSTALLER_FILE=$(mktemp "${TMPDIR:-/tmp}/tsa-uv-installer.XXXXXX")
  trap 'rm -f "$UV_INSTALLER_FILE"' EXIT
  trap 'exit 129' HUP
  trap 'exit 130' INT
  trap 'exit 143' TERM
  if ! curl --proto '=https' --tlsv1.2 -LsSf \
    https://astral.sh/uv/install.sh -o "$UV_INSTALLER_FILE"; then
    echo "❌ Automatic uv bootstrap failed."
    echo "   Recovery: install uv >= $MINIMUM_UV_VERSION from https://docs.astral.sh/uv/"
    echo "   Then re-run the original Tree-sitter Analyzer install command."
    exit 1
  fi
  if ! sh "$UV_INSTALLER_FILE"; then
    echo "❌ Automatic uv bootstrap failed."
    echo "   Recovery: install uv >= $MINIMUM_UV_VERSION from https://docs.astral.sh/uv/"
    echo "   Then re-run the original Tree-sitter Analyzer install command."
    exit 1
  fi
  rm -f "$UV_INSTALLER_FILE"
  trap - EXIT HUP INT TERM
  # Re-source common profile locations
  if [ -f "$HOME/.cargo/env" ]; then
    # shellcheck disable=SC1091
    . "$HOME/.cargo/env"
  fi
  export PATH="$HOME/.local/bin:$PATH"
  hash -r
  if ! uv_is_ready; then
    if [ "$UV_VERSION_PROBE_ERROR" = "timeout" ]; then
      echo "❌ Timed out after 5 seconds running $(command -v uv) --version after bootstrap."
    fi
    echo "❌ uv installation did not provide required uv >= $MINIMUM_UV_VERSION."
    echo "   Install uv manually: https://docs.astral.sh/uv/getting-started/installation/"
    echo "   Then re-run the original Tree-sitter Analyzer install command."
    exit 1
  fi
  echo "✅ uv ready: $UV_VERSION_OUTPUT ($(command -v uv))"
else
  echo "✅ $UV_VERSION_OUTPUT: $(command -v uv)"
fi


# ─── Resolve absolute project root ────────────────────────────────────────────
if command -v realpath >/dev/null 2>&1; then
  PROJECT_ROOT=$(realpath .)
else
  PROJECT_ROOT=$(pwd)
fi
echo ""
echo "📁 Project root: $PROJECT_ROOT"

# ─── Agent config paths ───────────────────────────────────────────────────────
OS_TYPE="$(uname -s)"

# One line per client: label|config path|servers key|create policy (bash 3.x compatible).
CLAUDE_CREATE=existing
CURSOR_CREATE=existing
VSCODE_CREATE=existing
if command -v claude >/dev/null 2>&1 || [ -d "$HOME/.claude" ]; then CLAUDE_CREATE=create; fi
if command -v cursor >/dev/null 2>&1 || [ -d "$HOME/.cursor" ]; then CURSOR_CREATE=create; fi
if [ "$OS_TYPE" = "Darwin" ]; then
  DESKTOP_PATH="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
  CODE_USER_DIR="$HOME/Library/Application Support/Code/User"
else
  DESKTOP_PATH="$HOME/.config/Claude/claude_desktop_config.json"
  if [ ! -f "$DESKTOP_PATH" ] && [ -f "$HOME/.config/claude/claude_desktop_config.json" ]; then
    DESKTOP_PATH="$HOME/.config/claude/claude_desktop_config.json"
  fi
  CODE_USER_DIR="$HOME/.config/Code/User"
fi
if command -v code >/dev/null 2>&1 || [ -d "$CODE_USER_DIR" ]; then VSCODE_CREATE=create; fi
AGENT_CONFIG_ENTRIES="Claude Desktop (global)|$DESKTOP_PATH|mcpServers|existing
Claude Code (project)|$PROJECT_ROOT/.mcp.json|mcpServers|$CLAUDE_CREATE
Cursor (project)|$PROJECT_ROOT/.cursor/mcp.json|mcpServers|$CURSOR_CREATE
VS Code (project)|$PROJECT_ROOT/.vscode/mcp.json|servers|$VSCODE_CREATE"

if [ -f "$HOME/.cursor/mcp.json" ] && command -v python3 >/dev/null 2>&1; then
  if python3 - "$HOME/.cursor/mcp.json" <<'PYWARN'
import json
import sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    sys.exit(0 if isinstance(data, dict) and isinstance(data.get("mcpServers"), dict) and "tree-sitter-analyzer" in data["mcpServers"] else 1)
except (OSError, ValueError, RecursionError):
    sys.exit(1)
PYWARN
  then
    echo "⚠️  Global Cursor tree-sitter-analyzer entry pins every project to one root."
  fi
fi
if command -v codex >/dev/null 2>&1 || [ -d "$HOME/.codex" ]; then
  echo "Add this block to $HOME/.codex/config.toml:"
  cat <<EOF
[mcp_servers.tree-sitter-analyzer]
command = "uvx"
args = ["--from", "tree-sitter-analyzer[mcp]", "tree-sitter-analyzer-mcp"]
env = { TREE_SITTER_PROJECT_ROOT = "$PROJECT_ROOT" }
EOF
fi

# ─── Process each agent config ────────────────────────────────────────────────
CONFIGURED_AGENTS=""
SKIPPED_AGENTS=""
FAILED_AGENTS=""
CONFIGURATION_FAILURE=0

echo ""
echo "🔍 Scanning for agent config files..."

# Read the table line by line; never use a path as a printf format string.
while IFS='|' read -r AGENT_LABEL CONFIG_PATH SERVERS_KEY CREATE_POLICY; do
  # Skip empty lines
  if [ -z "$AGENT_LABEL" ]; then
    continue
  fi

  if [ ! -e "$CONFIG_PATH" ] && [ ! -L "$CONFIG_PATH" ] && [ "$CREATE_POLICY" != create ]; then
    echo "   ⏭️  $AGENT_LABEL: config file not found ($CONFIG_PATH)"
    SKIPPED_AGENTS="${SKIPPED_AGENTS}${AGENT_LABEL}\n"
    continue
  fi

  echo "   🔧 $AGENT_LABEL: configuring..."
  if [ "$AGENT_LABEL" = "Claude Desktop (global)" ]; then
    echo "   Note: a global entry pins one project root."
  fi

  # Merge MCP entry using python3. Keep the assignment in an explicit
  # failure list: under set -e a bare failing command substitution exits before
  # its status can be classified below.
  if ! command -v python3 >/dev/null 2>&1; then
    echo "   ❌ $AGENT_LABEL: python3 not found — skipping ($CONFIG_PATH)"
    FAILED_AGENTS="${FAILED_AGENTS}${AGENT_LABEL} (python3 not found)\n"
    CONFIGURATION_FAILURE=1
    continue
  fi

  MERGE_EXIT=0
  MERGE_RESULT=$(python3 - "$CONFIG_PATH" "$PROJECT_ROOT" "$SERVERS_KEY" <<'PYEOF'
import datetime
import json
import os
import shutil
import stat
import sys
import tempfile

config_path = sys.argv[1]
project_root = sys.argv[2]
servers_key = sys.argv[3]
exists = os.path.lexists(config_path)

try:
    if exists:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}
except json.JSONDecodeError as exc:
    print(f"PARSE_ERROR:{exc}", file=sys.stderr)
    sys.exit(2)

if not isinstance(data, dict):
    print("TYPE_ERROR:config root must be a JSON object", file=sys.stderr)
    sys.exit(3)

if servers_key not in data:
    mcp_servers = {}
    data[servers_key] = mcp_servers
else:
    mcp_servers = data[servers_key]
if not isinstance(mcp_servers, dict):
    print(f"TYPE_ERROR:{servers_key} must be a JSON object", file=sys.stderr)
    sys.exit(3)

existing_entry = mcp_servers.get("tree-sitter-analyzer")
if existing_entry is not None and not isinstance(existing_entry, dict):
    print("TYPE_ERROR:tree-sitter-analyzer entry must be a JSON object", file=sys.stderr)
    sys.exit(3)
if isinstance(existing_entry, dict):
    existing_env = existing_entry.get("env")
    if existing_env is not None and not isinstance(existing_env, dict):
        print("TYPE_ERROR:tree-sitter-analyzer env must be a JSON object", file=sys.stderr)
        sys.exit(3)

# Preserve dotfile-managed symlinks: atomically replace the resolved target,
# never the link path itself.
write_path = os.path.realpath(config_path)
config_dir = os.path.dirname(write_path) or "."
if not exists:
    os.makedirs(config_dir, exist_ok=True)
target_mode = stat.S_IMODE(os.stat(write_path).st_mode) if exists else 0o644
if target_mode & 0o222 == 0:
    raise PermissionError(f"config file is not writable: {write_path}")
if stat.S_IMODE(os.stat(config_dir).st_mode) & 0o222 == 0:
    raise PermissionError(f"config directory is not writable: {config_dir}")

mcp_servers["tree-sitter-analyzer"] = {
    "command": "uvx",
    "args": ["--from", "tree-sitter-analyzer[mcp]", "tree-sitter-analyzer-mcp"],
    "env": {"TREE_SITTER_PROJECT_ROOT": project_root},
}

if servers_key == "servers":
    mcp_servers["tree-sitter-analyzer"]["type"] = "stdio"
    mcp_servers["tree-sitter-analyzer"]["env"]["TREE_SITTER_PROJECT_ROOT"] = "${workspaceFolder}"

timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
backup_path = config_path + ".bak." + timestamp
if exists:
    shutil.copy2(config_path, backup_path)
else:
    backup_path = "none (new file)"

fd, temporary_path = tempfile.mkstemp(prefix=".tsa-mcp-", dir=config_dir, text=True)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.chmod(temporary_path, target_mode)
    os.replace(temporary_path, write_path)
except BaseException:
    try:
        os.unlink(temporary_path)
    except FileNotFoundError:
        pass
    raise

print(f"OK:{backup_path}")
PYEOF
  ) || MERGE_EXIT=$?

  if [ "$MERGE_EXIT" = "2" ]; then
    echo "   ❌ $AGENT_LABEL: JSON parse error — skipping ($CONFIG_PATH)"
    FAILED_AGENTS="${FAILED_AGENTS}${AGENT_LABEL} (JSON parse error)\n"
    CONFIGURATION_FAILURE=1
  elif [ "$MERGE_EXIT" = "0" ]; then
    BACKUP_PATH="${MERGE_RESULT#OK:}"
    echo "   ✅ $AGENT_LABEL: configured (backup: $BACKUP_PATH)"
    CONFIGURED_AGENTS="${CONFIGURED_AGENTS}${AGENT_LABEL}\n"
  else
    echo "   ❌ $AGENT_LABEL: unexpected error (exit $MERGE_EXIT) — skipping"
    FAILED_AGENTS="${FAILED_AGENTS}${AGENT_LABEL} (error)\n"
    CONFIGURATION_FAILURE=1
  fi

done <<EOF
$(printf '%s\n' "$AGENT_CONFIG_ENTRIES")
EOF

# ─── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "🎉 Tree-sitter Analyzer installation complete"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "📌 Project root: $PROJECT_ROOT"
echo ""

if [ -n "$CONFIGURED_AGENTS" ]; then
  echo "✅ Configured agents:"
  printf '%b' "$CONFIGURED_AGENTS" | while IFS= read -r agent; do
    [ -n "$agent" ] && echo "   • $agent"
  done
  echo ""
fi

if [ -n "$SKIPPED_AGENTS" ]; then
  echo "⏭️  Skipped agents (client not detected / config file not found):"
  printf '%b' "$SKIPPED_AGENTS" | while IFS= read -r agent; do
    [ -n "$agent" ] && echo "   • $agent"
  done
  echo ""
fi

if [ -n "$FAILED_AGENTS" ]; then
  echo "❌ Failed agents:"
  printf '%b' "$FAILED_AGENTS"
fi

echo "📋 Next steps:"
echo "   1. Restart your agent"
echo "   2. Build the index once: uvx --from \"tree-sitter-analyzer[mcp]\" tree-sitter-analyzer --project-root \"$PROJECT_ROOT\" --full-index"
echo "   3. Verify: TREE_SITTER_PROJECT_ROOT=\"$PROJECT_ROOT\" uvx --from tree-sitter-analyzer tree-sitter-analyzer --doctor"
echo "Note: .mcp.json and .cursor/mcp.json contain an absolute path; do not commit them, or edit the path."
echo ""

if [ "$WSL_ENV" = "1" ]; then
  echo "⚠️  WSL environment: if agent config is not picked up, check the"
  echo "   Windows-side config file manually."
fi

if [ "$CONFIGURATION_FAILURE" = "1" ]; then
  echo "❌ One or more existing agent configs could not be updated."
  exit 1
fi
