#!/usr/bin/env bash
# Unprivileged NO1-008A operator: submits root-signed contracts, never host facts.
set -Eeuo pipefail
umask 077
readonly REPOS=(vscode excalidraw django tokio okhttp gin alamofire)
readonly ARMS=(tsa-warm codegraph-warm)
readonly CLAIM='{"dominance_allowed":false,"evaluation_stage":"E0","publishable":false,"status":"NOT_EVALUATED","unlock_allowed":false,"winner":null}'
usage(){ echo "usage: $0 contract|dry-run|preflight|run [--contracts-dir DIR --audit-authority-socket SOCKET --public-config FILE --experiment-root DIR]" >&2; exit 64; }
contract(){ printf '%s
' '{"schema_version":1,"cells":14,"attempts_per_cell":1,"max_concurrency":1,"network_mode":"none","snapshot":"dm-verity-v1","receipt_schema":3,"roles":["producer","executor-signer","approver-signer","external-authority-service","fresh-verifier"],"evaluation_stage":"E0","status":"NOT_EVALUATED","publishable":false,"winner":null,"dominance_allowed":false,"unlock_allowed":false}'; }
emit_cells(){ local command=$1 count=0 repo arm; for repo in "${REPOS[@]}"; do for arm in "${ARMS[@]}"; do count=$((count+1)); printf '{"ordinal":%d,"repo_id":"%s","arm_id":"%s","attempt":1,"command":"%s","evaluation_stage":"E0","status":"NOT_EVALUATED"}
' "$count" "$repo" "$arm" "$command"; done; done; [[ $count -eq 14 ]]; }
canonical_existing(){ [[ -n $1 && $1 != *','* && $(realpath -e -- "$1") == "$1" ]] || { echo "canonical existing path required" >&2; return 1; }; }
COMMAND=${1:-}; [[ $# -gt 0 ]] || usage; shift
if [[ $COMMAND == contract ]]; then [[ $# -eq 0 ]] || usage; contract; exit 0; fi
if [[ $COMMAND == dry-run ]]; then [[ $# -eq 0 ]] || usage; emit_cells dry-run; printf '%s
' "$CLAIM"; exit 0; fi
declare CONTRACTS_DIR='' AUDIT_AUTHORITY_SOCKET='' PUBLIC_CONFIG='' EXPERIMENT_ROOT=''
while [[ $# -gt 0 ]]; do case $1 in
 --contracts-dir) CONTRACTS_DIR=${2:?}; shift 2;;
 --audit-authority-socket) AUDIT_AUTHORITY_SOCKET=${2:?}; shift 2;;
 --public-config) PUBLIC_CONFIG=${2:?}; shift 2;;
 --experiment-root) EXPERIMENT_ROOT=${2:?}; shift 2;;
 *) usage;; esac; done
[[ $COMMAND == preflight || $COMMAND == run ]] || usage
# Deliberately no root check, Docker socket, authority key, cgroup, mkfs, or output mount.
for path in "$CONTRACTS_DIR" "$PUBLIC_CONFIG" "$AUDIT_AUTHORITY_SOCKET"; do canonical_existing "$path"; done
python3 - "$PUBLIC_CONFIG" "$CONTRACTS_DIR" <<'PY'
import json,sys
from pathlib import Path
from benchmarks.codegraph_compare.verifier import parse_public_config
config=parse_public_config(Path(sys.argv[1]).read_bytes())
for contract in sorted(Path(sys.argv[2]).glob('*.json')):
 value=json.loads(contract.read_bytes())
 if set(value)!={'schema_version','job_id','cell','nonce','root_signature'}: raise SystemExit('contract is not closed')
print(config['auditor']['key_id'])
PY
[[ $COMMAND == preflight ]] && { contract; exit 0; }
[[ -n $EXPERIMENT_ROOT && ! -e $EXPERIMENT_ROOT ]] || { echo "fresh response directory required" >&2; exit 65; }
mkdir -m 0700 -- "$EXPERIMENT_ROOT"
count=0
for contract_path in "$CONTRACTS_DIR"/*.json; do
 count=$((count+1)); python3 - "$contract_path" "$AUDIT_AUTHORITY_SOCKET" "$PUBLIC_CONFIG" "$EXPERIMENT_ROOT/response-$count.json" <<'PY'
import json,sys
from pathlib import Path
from benchmarks.codegraph_compare.audit_authority_client import run_cell
from benchmarks.codegraph_compare.verifier import parse_public_config
contract=json.loads(Path(sys.argv[1]).read_bytes()); authority=parse_public_config(Path(sys.argv[3]).read_bytes())['auditor']
result=run_cell(contract,Path(sys.argv[2]),authority)
Path(sys.argv[4]).write_text(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n')
PY
done
[[ $count -eq 14 ]] || { printf '%s
' "$CLAIM" >"$EXPERIMENT_ROOT/verdict.json"; exit 1; }
printf '%s
' "$CLAIM" >"$EXPERIMENT_ROOT/verdict.json"
