#!/usr/bin/env bash
# Keyless NO1-008A operator: authority -> executor service -> approver service -> fresh verifier.
set -Eeuo pipefail
umask 077
readonly REPOS=(vscode excalidraw django tokio okhttp gin alamofire)
readonly ARMS=(tsa-warm codegraph-warm)
usage(){ echo "usage: $0 contract|dry-run|preflight|run [closed pipeline options]" >&2; exit 64; }
contract(){ printf '%s\n' '{"schema_version":1,"cells":14,"attempts_per_cell":1,"max_concurrency":1,"roles":["producer","auditor","executor","approver","verifier","decision-consumer"],"qualification":"production-verifier-exact-14-only"}'; }
emit_cells(){ local count=0 repo arm; for repo in "${REPOS[@]}"; do for arm in "${ARMS[@]}"; do count=$((count+1)); printf '{"ordinal":%d,"repo_id":"%s","arm_id":"%s","attempt":1}\n' "$count" "$repo" "$arm"; done; done; [[ $count -eq 14 ]]; }
COMMAND=${1:-}; [[ $# -gt 0 ]] || usage; shift
[[ $COMMAND != contract ]] || { [[ $# -eq 0 ]] || usage; contract; exit 0; }
[[ $COMMAND != dry-run ]] || { [[ $# -eq 0 ]] || usage; emit_cells; exit 0; }
[[ $COMMAND == preflight || $COMMAND == run ]] || usage
readonly ANCHOR_RESOURCE="$(python3 - <<'PY'
from benchmarks.codegraph_compare.trust_anchor import ROOT_RESOURCE
print(ROOT_RESOURCE.resolve(strict=True))
PY
)"
if [[ ${NO1_008A_OPERATOR_IMAGE:-0} != 1 ]]; then
 [[ $ANCHOR_RESOURCE != "$PWD"/* && ! -w $ANCHOR_RESOURCE ]] || { echo "host execution requires an externally pinned read-only root anchor outside the checkout; use the operator image" >&2; exit 65; }
fi
declare CONTRACTS_DIR='' AUTHORITY_SOCKET='' EXECUTOR_SOCKET='' APPROVER_SOCKET='' VERIFIER_SOCKET='' DECISION_CONSUMER_SOCKET='' DECISION_CONTRACT='' PUBLIC_CONFIG='' STAGED_ROOT='' EXPERIMENT_ROOT=''
while [[ $# -gt 0 ]]; do case $1 in
 --contracts-dir) CONTRACTS_DIR=${2:?}; shift 2;;
 --authority-socket|--audit-authority-socket) AUTHORITY_SOCKET=${2:?}; shift 2;;
 --executor-socket) EXECUTOR_SOCKET=${2:?}; shift 2;;
 --approver-socket) APPROVER_SOCKET=${2:?}; shift 2;;
 --verifier-socket) VERIFIER_SOCKET=${2:?}; shift 2;;
 --decision-consumer-socket) DECISION_CONSUMER_SOCKET=${2:?}; shift 2;;
 --decision-contract) DECISION_CONTRACT=${2:?}; shift 2;;
 --public-config) PUBLIC_CONFIG=${2:?}; shift 2;;
 --staged-root) STAGED_ROOT=${2:?}; shift 2;;
 --experiment-root) EXPERIMENT_ROOT=${2:?}; shift 2;;
 *) usage;; esac; done
for value in "$CONTRACTS_DIR" "$AUTHORITY_SOCKET" "$EXECUTOR_SOCKET" "$APPROVER_SOCKET" "$VERIFIER_SOCKET" "$DECISION_CONSUMER_SOCKET" "$DECISION_CONTRACT" "$PUBLIC_CONFIG" "$STAGED_ROOT"; do
 [[ -n $value && $value != *,* && $(realpath -e -- "$value") == "$value" ]] || { echo "canonical existing pipeline path required" >&2; exit 65; }
done
python3 - "$PUBLIC_CONFIG" "$CONTRACTS_DIR" <<'PY'
import sys
from pathlib import Path
from benchmarks.codegraph_compare.audit_authority_service import verify_contract
from benchmarks.codegraph_compare.receipt_v3 import strict_json_loads
from benchmarks.codegraph_compare.setup_qualification_plan import EXPECTED_CELLS
from benchmarks.codegraph_compare.verifier import parse_public_config
parse_public_config(Path(sys.argv[1]).read_bytes())
cells=[]
for path in Path(sys.argv[2]).glob('*.json'):
 contract=verify_contract({'operation':'run-cell','contract':strict_json_loads(path.read_bytes())})
 cells.append((contract['cell']['repo_id'],contract['cell']['arm_id']))
if set(cells)!=set(EXPECTED_CELLS) or len(cells)!=14: raise SystemExit('contracts are not exact-14')
PY
[[ $COMMAND == preflight ]] && { contract; exit 0; }
[[ -n $EXPERIMENT_ROOT && ! -e $EXPERIMENT_ROOT ]] || { echo "fresh experiment root required" >&2; exit 65; }
exec python3 -m benchmarks.codegraph_compare.qualification_operator \
 --contracts-dir "$CONTRACTS_DIR" --authority-socket "$AUTHORITY_SOCKET" \
 --executor-socket "$EXECUTOR_SOCKET" --approver-socket "$APPROVER_SOCKET" \
 --verifier-socket "$VERIFIER_SOCKET" \
 --decision-consumer-socket "$DECISION_CONSUMER_SOCKET" \
 --decision-contract "$DECISION_CONTRACT" \
 --public-config "$PUBLIC_CONFIG" --staged-root "$STAGED_ROOT" --experiment-root "$EXPERIMENT_ROOT"
