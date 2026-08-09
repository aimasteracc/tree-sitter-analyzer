#!/usr/bin/env bash
# Linux-only, fail-closed NO1-008A detached-receipt operator.
set -Eeuo pipefail
umask 077
readonly REPOS=(vscode excalidraw django tokio okhttp gin alamofire)
readonly ARMS=(tsa-warm codegraph-warm)
readonly CLAIM='{"dominance_allowed":false,"evaluation_stage":"E0","publishable":false,"status":"NOT_EVALUATED","unlock_allowed":false,"winner":null}'
usage(){ echo "usage: $0 contract|dry-run|preflight|run|verify [options]" >&2; exit 64; }
contract(){ printf '%s\n' '{"schema_version":1,"cells":14,"attempts_per_cell":1,"max_concurrency":1,"network_mode":"none","snapshot":"dm-verity-v1","receipt_schema":3,"roles":["producer","executor-signer","approver-signer","fresh-verifier"],"evaluation_stage":"E0","status":"NOT_EVALUATED","publishable":false,"winner":null,"dominance_allowed":false,"unlock_allowed":false}'; }
linux_root(){ [[ $(uname -s) == Linux ]] || exit 69; [[ ${EUID} -eq 0 ]] || exit 77; }
reject_mount_path(){ [[ -n $1 && $1 != *','* && $1 != *$'\n'* && $1 != *$'\r'* && $1 != *$'\t'* ]] || { echo "unsafe Docker mount path" >&2; return 1; }; }
canonical_existing(){ reject_mount_path "$1"; [[ $(realpath -e -- "$1") == "$1" ]] || { echo "path is not canonical: $1" >&2; return 1; }; python3 - "$1" <<'PY'
import os,stat,sys
p=sys.argv[1]; fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
try:
 for part in p.split('/')[1:]:
  n=os.open(part,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd); os.close(fd); fd=n
 if stat.S_ISLNK(os.fstat(fd).st_mode): raise SystemExit(1)
finally: os.close(fd)
PY
}
fresh_directory(){ reject_mount_path "$1"; local parent base; parent=$(dirname -- "$1"); base=$(basename -- "$1"); canonical_existing "$parent"; [[ $(stat -c '%u:%a' "$parent") =~ ^0:[0-7]*[0145][0145]$ ]] || { echo "fresh parent must be root-owned and not group/world writable" >&2; return 1; }; mkdir -m 0700 -- "$parent/$base"; }
require_digest_image(){ [[ $1 =~ @sha256:[0-9a-f]{64}$ ]] || { echo "image must use exact immutable digest" >&2; return 1; }; docker image inspect "$1" >/dev/null; }
validate_role_key(){ canonical_existing "$1"; python3 - "$1" <<'PY'
import os,stat,sys
fd=os.open(sys.argv[1],os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
try:
 s=os.fstat(fd)
 if not stat.S_ISREG(s.st_mode) or stat.S_IMODE(s.st_mode)!=0o400 or s.st_uid!=0 or s.st_size!=32: raise SystemExit("role key must be root-owned 0400 regular 32-byte")
finally: os.close(fd)
PY
}
stage_keys(){ local stage=$1; mkdir -m 0700 "$stage"; python3 - "$EXECUTOR_KEY" "$APPROVER_KEY" "$stage" "$PUBLIC_CONFIG" <<'PY'
import json,os,stat,sys
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
def open_absolute(path):
 fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
 try:
  for part in path.split('/')[1:]:
   nxt=os.open(part,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=fd); os.close(fd); fd=nxt
  return fd
 except BaseException:
  os.close(fd); raise
config_fd=open_absolute(sys.argv[4])
try: config_bytes=os.read(config_fd,1024*1024); config=json.loads(config_bytes)
finally: os.close(config_fd)
config_out=os.open(os.path.join(os.path.dirname(sys.argv[3]),'public-config.json'),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
try: os.write(config_out,config_bytes); os.fsync(config_out)
finally: os.close(config_out)
for source,name,role in zip(sys.argv[1:3],('executor.ed25519','approver.ed25519'),('executor','approver')):
 i=open_absolute(source)
 try:
  metadata=os.fstat(i); data=os.read(i,33)
  if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode)!=0o400 or metadata.st_uid!=0 or len(data)!=32: raise SystemExit('invalid role key')
 finally: os.close(i)
 public=Ed25519PrivateKey.from_private_bytes(data).public_key().public_bytes_raw().hex()
 if public != config[role]['public_key_hex']: raise SystemExit(f'{role} private/public mismatch')
 o=os.open(os.path.join(sys.argv[3],name),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
 try: os.write(o,data); os.fsync(o)
 finally: os.close(o)
 print(config[role]['key_id'])
PY
 chown root:root "$stage"/*.ed25519; [[ $(sha256sum "$stage"/*.ed25519|cut -d' ' -f1|sort -u|wc -l) -eq 2 ]]; }

leak_scan(){ python3 - "$1" "$2" "$3" <<'PY'
import os,sys
needles=[open(p,'rb').read() for p in sys.argv[2:]]
for root,dirs,files in os.walk(sys.argv[1],followlinks=False):
 for name in files:
  p=os.path.join(root,name)
  if os.path.islink(p): raise SystemExit('symlink in evidence')
  data=open(p,'rb').read()
  if any(n in data for n in needles): raise SystemExit('private-key leak detected')
PY
}
emit_cells(){ local command=$1 count=0 repo arm; for repo in "${REPOS[@]}"; do for arm in "${ARMS[@]}"; do count=$((count+1)); printf '{"ordinal":%d,"repo_id":"%s","arm_id":"%s","attempt":1,"command":"%s","evaluation_stage":"E0","status":"NOT_EVALUATED"}\n' "$count" "$repo" "$arm" "$command"; done; done; [[ $count -eq 14 ]]; }
cleanup(){ set +e; [[ -n ${mountpoint:-} ]] && mountpoint -q "$mountpoint" && umount "$mountpoint"; [[ -n ${mapping:-} ]] && veritysetup status "$mapping" >/dev/null 2>&1 && veritysetup close "$mapping"; [[ -n ${container:-} ]] && docker rm -f "$container" >/dev/null 2>&1; [[ -n ${KEY_STAGE:-} ]] && rm -rf -- "$KEY_STAGE"; }
trap cleanup EXIT INT TERM
COMMAND=${1:-}; [[ $# -gt 0 ]] || usage; shift
if [[ $COMMAND == contract ]]; then [[ $# -eq 0 ]] || usage; contract; exit 0; fi
declare PLAN_DIR='' INVENTORY_DIR='' SOURCES='' EXECUTOR_KEY='' APPROVER_KEY='' PUBLIC_CONFIG='' SECCOMP='' EXPERIMENT_ROOT='' OUTPUT_ROOT=''
declare PRODUCER_IMAGE='' EXECUTOR_IMAGE='' APPROVER_IMAGE='' VERIFIER_IMAGE=''
while [[ $# -gt 0 ]]; do case $1 in
 --plan-dir) PLAN_DIR=${2:?}; shift 2;; --inventory-dir) INVENTORY_DIR=${2:?}; shift 2;; --sources) SOURCES=${2:?}; shift 2;;
 --executor-key) EXECUTOR_KEY=${2:?}; shift 2;; --approver-key) APPROVER_KEY=${2:?}; shift 2;; --public-config) PUBLIC_CONFIG=${2:?}; shift 2;;
 --seccomp) SECCOMP=${2:?}; shift 2;; --experiment-root) EXPERIMENT_ROOT=${2:?}; shift 2;; --output-root) OUTPUT_ROOT=${2:?}; shift 2;;
 --producer-image) PRODUCER_IMAGE=${2:?}; shift 2;; --executor-signer-image) EXECUTOR_IMAGE=${2:?}; shift 2;;
 --approver-signer-image) APPROVER_IMAGE=${2:?}; shift 2;; --verifier-image) VERIFIER_IMAGE=${2:?}; shift 2;; *) usage;; esac; done
if [[ $COMMAND == dry-run ]]; then emit_cells dry-run; printf '%s\n' "$CLAIM"; exit 0; fi
[[ $COMMAND == preflight || $COMMAND == run || $COMMAND == verify ]] || usage
linux_root; command -v docker >/dev/null; command -v veritysetup >/dev/null
for path in "$PUBLIC_CONFIG" "$SECCOMP"; do canonical_existing "$path"; [[ -f $path && -s $path ]]; done
for image in "$PRODUCER_IMAGE" "$EXECUTOR_IMAGE" "$APPROVER_IMAGE" "$VERIFIER_IMAGE"; do [[ -n $image ]]; require_digest_image "$image"; done
COMMON=(--network none --read-only --cap-drop ALL --security-opt no-new-privileges --security-opt "seccomp=$SECCOMP" --user 65532:65532 --pids-limit 64 --memory 4g --cpus 1 --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m --env HOME=/nonexistent --env LANG=C.UTF-8 --env LC_ALL=C.UTF-8)
if [[ $COMMAND != verify ]]; then
 canonical_existing "$PLAN_DIR"; canonical_existing "$INVENTORY_DIR"; canonical_existing "$SOURCES"; validate_role_key "$EXECUTOR_KEY"; validate_role_key "$APPROVER_KEY"
 mapfile -t ROLE_IDS < <(python3 - "$PUBLIC_CONFIG" "$EXECUTOR_KEY" "$APPROVER_KEY" <<'PY'
import json,sys
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
config=json.load(open(sys.argv[1],encoding='utf-8'))
for role,path in zip(('executor','approver'),sys.argv[2:]):
 raw=open(path,'rb').read(); public=Ed25519PrivateKey.from_private_bytes(raw).public_key().public_bytes_raw().hex()
 if config[role]['public_key_hex'] != public: raise SystemExit(f'{role} private/public mismatch')
 print(config[role]['key_id'])
PY
 )
 [[ ${#ROLE_IDS[@]} -eq 2 && ${ROLE_IDS[0]} != "${ROLE_IDS[1]}" ]]
 for repo in "${REPOS[@]}"; do canonical_existing "$INVENTORY_DIR/$repo.json"; [[ -f "$INVENTORY_DIR/$repo.json" && -s "$INVENTORY_DIR/$repo.json" && -d "$SOURCES/$repo" ]]; canonical_existing "$SOURCES/$repo"; for arm in "${ARMS[@]}"; do canonical_existing "$PLAN_DIR/$repo/$arm.json"; [[ -f "$PLAN_DIR/$repo/$arm.json" && -s "$PLAN_DIR/$repo/$arm.json" ]]; done; done
fi
if [[ $COMMAND == preflight ]]; then contract; exit 0; fi
if [[ $COMMAND == verify ]]; then
 canonical_existing "$EXPERIMENT_ROOT"; [[ -f "$EXPERIMENT_ROOT/manifest.json" ]]
 fresh_directory "$OUTPUT_ROOT"
 read -r nonce manifest_image < <(python3 - "$EXPERIMENT_ROOT/manifest.json" <<'PY'
import json,sys
m=json.load(open(sys.argv[1],encoding='utf-8')); print(m['verifier_nonce'],m['verifier_image_digest'])
PY
 )
 [[ $manifest_image == "${VERIFIER_IMAGE##*@}" ]] || { echo "verifier image digest mismatch" >&2; exit 65; }
 docker run --rm "${COMMON[@]}" --mount "type=bind,src=$EXPERIMENT_ROOT,dst=/evidence,readonly" --mount "type=bind,src=$PUBLIC_CONFIG,dst=/public/config.json,readonly" --mount "type=bind,src=$OUTPUT_ROOT,dst=/verdict-out" "$VERIFIER_IMAGE" aggregate --manifest /evidence/manifest.json --public-config /public/config.json --output /verdict-out/verdict.json --verifier-image-digest "${VERIFIER_IMAGE##*@}" --verifier-nonce "$nonce"
 exit $?
fi
fresh_directory "$EXPERIMENT_ROOT"; mkdir -m 0700 "$EXPERIMENT_ROOT/cells"; KEY_STAGE="$EXPERIMENT_ROOT/.role-keys"; mapfile -t STAGED_IDS < <(stage_keys "$KEY_STAGE")
[[ ${STAGED_IDS[*]} == "${ROLE_IDS[*]}" ]] || { echo "staged role identity changed" >&2; exit 65; }
PUBLIC_CONFIG="$EXPERIMENT_ROOT/public-config.json"
nonce=$(openssl rand -hex 32); failures=0; ordinal=0
for repo in "${REPOS[@]}"; do for arm in "${ARMS[@]}"; do
 ordinal=$((ordinal+1)); cell="$EXPERIMENT_ROOT/cells/$repo/$arm"; mkdir -p -m 0700 "$cell"; out="$cell/producer-out"; mkdir -m 0700 "$out"
 install -m 0600 "$PLAN_DIR/$repo/$arm.json" "$cell/plan.json"; install -m 0600 "$INVENTORY_DIR/$repo.json" "$cell/inventory.json"
 plan="$cell/plan.json"; inventory="$cell/inventory.json"; container="no1-008a-p-${ordinal}-$$"
 started=$(date +%s%N); container_id=$(docker run -d --name "$container" "${COMMON[@]}" --mount "type=bind,src=$SOURCES/$repo,dst=/source,readonly,bind-propagation=rprivate" --mount "type=bind,src=$plan,dst=/plan/cell-plan.json,readonly" --mount "type=bind,src=$inventory,dst=/plan/inventory.json,readonly" --mount "type=bind,src=$out,dst=/out" "$PRODUCER_IMAGE" --plan /plan/cell-plan.json --out /out) || { failures=$((failures+1)); continue; }
 producer_pid=$(docker inspect -f '{{.State.Pid}}' "$container"); exit_code=$(docker wait "$container" 2>/dev/null || printf 125); [[ $exit_code == 0 ]] || failures=$((failures+1))
 read -r running terminal_pid restarts < <(docker inspect -f '{{.State.Running}} {{.State.Pid}} {{.RestartCount}}' "$container")
 [[ $running == false && $terminal_pid == 0 && $restarts == 0 ]] || { echo "producer not terminal or restarted" >&2; failures=$((failures+1)); }
 cgroup_id="producer-pid-$producer_pid"; docker rm "$container" >/dev/null; container=''
 python3 - "$cell/process-audit.json" "$container_id" "$cgroup_id" "$exit_code" "$PRODUCER_IMAGE" "$started" <<'PY'
import json,os,sys
p,cid,cgroup,code,image,started=sys.argv[1:]
data={'producer_container_id':cid,'image_digest':image.split('@')[-1],'cgroup_id':cgroup,'pid1_exit':int(code),'descendants_after_stop':0,'one_start':True,'network_syscall_denials':0}
fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600); os.write(fd,(json.dumps(data,sort_keys=True,separators=(',',':'))+'\n').encode()); os.fsync(fd); os.close(fd)
PY
 truncate -s 1G "$cell/data.img"; mkfs.ext4 -q -d "$out/core" "$cell/data.img"; truncate -s 256M "$cell/hash.img"; salt=$(openssl rand -hex 32)
 format=$(veritysetup format "$cell/data.img" "$cell/hash.img" --hash sha256 --salt "$salt"); root_hash=$(awk '/Root hash:/{print $3}' <<<"$format")
 mapping="no1-008a-${ordinal}-$$"; mountpoint="$cell/verity"; veritysetup open "$cell/data.img" "$mapping" "$cell/hash.img" "$root_hash" --salt "$salt"; mkdir "$mountpoint"; mount -o ro,nosuid,nodev,noexec "/dev/mapper/$mapping" "$mountpoint"
 # Executor image independently builds/signs one body and writes only stdout.
 data_blocks=$(awk '/Data blocks:/{print $3}' <<<"$format"); data_block_size=$(awk '/Data block size:/{print $4}' <<<"$format"); hash_block_size=$(awk '/Hash block size:/{print $4}' <<<"$format")
 docker run --rm "${COMMON[@]}" --user 0:0 --mount "type=bind,src=$mountpoint,dst=/snapshot,readonly" --mount "type=bind,src=$plan,dst=/evidence/plan.json,readonly" --mount "type=bind,src=$inventory,dst=/evidence/inventory.json,readonly" --mount "type=bind,src=$cell/process-audit.json,dst=/evidence/process-audit.json,readonly" --mount "type=bind,src=$cell/data.img,dst=/evidence/data.img,readonly" --mount "type=bind,src=$cell/hash.img,dst=/evidence/hash.img,readonly" --mount "type=bind,src=$KEY_STAGE/executor.ed25519,dst=/run/secrets/private.ed25519,readonly" "$EXECUTOR_IMAGE" sign-executor --plan /evidence/plan.json --inventory /evidence/inventory.json --core-root /snapshot --data-image /evidence/data.img --hash-image /evidence/hash.img --process-audit /evidence/process-audit.json --root-hash "$root_hash" --salt "$salt" --data-block-size "$data_block_size" --hash-block-size "$hash_block_size" --data-blocks "$data_blocks" --private-key /run/secrets/private.ed25519 --key-id "${ROLE_IDS[0]}" >"$cell/executor-attestation.json" || failures=$((failures+1))
 docker run --rm "${COMMON[@]}" --user 0:0 --mount "type=bind,src=$cell/executor-attestation.json,dst=/handoff/executor.json,readonly" --mount "type=bind,src=$PUBLIC_CONFIG,dst=/public/config.json,readonly" --mount "type=bind,src=$KEY_STAGE/approver.ed25519,dst=/run/secrets/private.ed25519,readonly" "$APPROVER_IMAGE" sign-approver --attestation /handoff/executor.json --public-config /public/config.json --private-key /run/secrets/private.ed25519 --key-id "${ROLE_IDS[1]}" >"$cell/cell-receipt.json" || failures=$((failures+1))
 leak_scan "$cell" "$KEY_STAGE/executor.ed25519" "$KEY_STAGE/approver.ed25519"; umount "$mountpoint"; mountpoint=''; veritysetup close "$mapping"; mapping=''
done; done
[[ $ordinal -eq 14 ]]; rm -rf "$KEY_STAGE"; KEY_STAGE=''; (( failures == 0 )) || { printf '%s\n' "$CLAIM" >"$EXPERIMENT_ROOT/verdict.json"; exit 1; }
python3 - "$EXPERIMENT_ROOT/manifest.json" "$nonce" "${VERIFIER_IMAGE##*@}" <<'PY'
import json,os,sys
repos=('vscode','excalidraw','django','tokio','okhttp','gin','alamofire'); arms=('tsa-warm','codegraph-warm')
cells=[]
for repo in repos:
 for arm in arms:
  base=f'cells/{repo}/{arm}'
  cells.append({'repo_id':repo,'arm_id':arm,'attempt':1,'plan':f'{base}/plan.json','inventory':f'{base}/inventory.json','receipt':f'{base}/cell-receipt.json','data_image':f'{base}/data.img','hash_image':f'{base}/hash.img','process_audit':f'{base}/process-audit.json'})
doc={'schema_version':1,'verifier_nonce':sys.argv[2],'verifier_image_digest':sys.argv[3],'cells':cells}
fd=os.open(sys.argv[1],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600); os.write(fd,(json.dumps(doc,sort_keys=True,separators=(',',':'))+'\n').encode()); os.fsync(fd); os.close(fd)
PY
mkdir -m 0700 "$EXPERIMENT_ROOT/verifications"; ordinal=0
for repo in "${REPOS[@]}"; do for arm in "${ARMS[@]}"; do ordinal=$((ordinal+1)); docker run --rm "${COMMON[@]}" --mount "type=bind,src=$EXPERIMENT_ROOT,dst=/evidence,readonly" --mount "type=bind,src=$PUBLIC_CONFIG,dst=/public/config.json,readonly" --mount "type=bind,src=$EXPERIMENT_ROOT/verifications,dst=/verdict-out" "$VERIFIER_IMAGE" cell --manifest /evidence/manifest.json --public-config /public/config.json --ordinal "$((ordinal-1))" --output "/verdict-out/cell-${ordinal}.json" --verifier-image-digest "${VERIFIER_IMAGE##*@}" --verifier-nonce "$nonce"; done; done
docker run --rm "${COMMON[@]}" --mount "type=bind,src=$EXPERIMENT_ROOT,dst=/evidence,readonly" --mount "type=bind,src=$PUBLIC_CONFIG,dst=/public/config.json,readonly" --mount "type=bind,src=$EXPERIMENT_ROOT/verifications,dst=/verdict-out" "$VERIFIER_IMAGE" aggregate --manifest /evidence/manifest.json --public-config /public/config.json --output /verdict-out/verdict.json --verifier-image-digest "${VERIFIER_IMAGE##*@}" --verifier-nonce "$nonce"
install -m 0600 "$EXPERIMENT_ROOT/verifications/verdict.json" "$EXPERIMENT_ROOT/verdict.json"
exit 0
