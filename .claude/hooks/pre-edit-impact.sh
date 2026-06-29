#!/usr/bin/env bash
# PreToolUse hook: Edit|Write 前に change-impact を Claude context に注入する
# stdout に {"systemMessage": "..."} を出力する
set -euo pipefail

INPUT=$(cat)

# tool_input.file_path を JSON から取得
FILE_PATH=$(printf '%s' "$INPUT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    inp = d.get('tool_input', {})
    print(inp.get('file_path', '') or inp.get('path', ''))
except Exception:
    print('')
" 2>/dev/null || echo "")

if [ -z "$FILE_PATH" ]; then
  printf '{"systemMessage": ""}\n'
  exit 0
fi

# uv が利用可能か確認
if ! command -v uv &>/dev/null; then
  printf '{"systemMessage": ""}\n'
  exit 0
fi

# change-impact を 30 秒 timeout で実行
IMPACT=$(timeout 30 uv run python -m tree_sitter_analyzer \
  --change-impact \
  --format json \
  "$FILE_PATH" 2>/dev/null || echo "")

if [ -z "$IMPACT" ]; then
  printf '{"systemMessage": ""}\n'
  exit 0
fi

# systemMessage として JSON 出力
python3 -c "
import json, sys
msg = '[TSA Impact Preview]\nFile: ' + sys.argv[1] + '\n' + sys.argv[2]
print(json.dumps({'systemMessage': msg}))
" "$FILE_PATH" "$IMPACT"

exit 0
