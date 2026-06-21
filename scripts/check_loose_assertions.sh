#!/bin/bash
# Layer-1 CI ratchet: block new weak assertions.
#
# Usage:
#   ./scripts/check_loose_assertions.sh [<base-ref>]
#
# Defaults to origin/develop if base-ref not provided.
#
# Thin wrapper - actual logic lives in scripts/check_loose_assertions.py.
# AST analysis catches multi-line loose bounds, placeholder existence checks,
# and None-check tautologies.
#
# Exemption marker (anywhere within the assert's source lines):
#   assert x >= 1  # ratchet: nondeterministic <reason>
#
# Whitelist (filenames):
#   *property* or *propert* in the filename skips the entire file

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec python3 "${SCRIPT_DIR}/check_loose_assertions.py" "$@"
