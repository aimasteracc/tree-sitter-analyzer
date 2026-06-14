#!/usr/bin/env bash
set -euo pipefail

APP_NAME=${APP_NAME:-tree-sitter-analyzer}
TARGET_DIR=${1:-dist}

log() {
  printf '[%s] %s\n' "$APP_NAME" "$1"
}

prepare() {
  mkdir -p "$TARGET_DIR"
  for file in README.md pyproject.toml; do
    if [[ -f "$file" ]]; then
      cp "$file" "$TARGET_DIR/"
    fi
  done
}

main() {
  log "preparing artifacts"
  prepare

  case "${MODE:-local}" in
    local)
      log "local mode"
      ;;
    ci)
      log "ci mode"
      ;;
    *)
      log "unknown mode"
      return 2
      ;;
  esac
}

main "$@"
