#!/usr/bin/env bash
# PostToolUse hook: Edit|Write 後に TSA knowledge graph を incremental update する
# exit 0 でノンブロッキング実行
set -euo pipefail

# stdin をドレイン (使用しない)
cat > /dev/null

# uv が利用可能か確認
if ! command -v uv &>/dev/null; then exit 0; fi

# TSA が利用可能か確認
if ! uv run python -m tree_sitter_analyzer --version &>/dev/null 2>&1; then exit 0; fi

# バックグラウンドで incremental update を実行
PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
nohup uv run python -m tree_sitter_analyzer \
  --knowledge-graph-index \
  --knowledge-graph-index-mode update \
  --project-root "$PROJECT_ROOT" \
  > /tmp/tsa-kg-update.log 2>&1 &

exit 0
