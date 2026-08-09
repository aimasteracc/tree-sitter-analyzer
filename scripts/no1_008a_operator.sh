#!/usr/bin/env bash
# Linux-only, fail-all NO1-008A detached-receipt operator. No claim is produced.
set -Eeuo pipefail
umask 077

readonly REPOS=(vscode excalidraw django tokio okhttp gin alamofire)
readonly ARMS=(tsa-warm codegraph-warm)
readonly CLAIM='{"dominance_allowed":false,"evaluation_stage":"E0","publishable":false,"status":"NOT_EVALUATED","unlock_allowed":false,"winner":null}'

usage() {
  echo "usage: $0 contract|dry-run|preflight|run|verify [options]" >&2
  exit 64
}

contract() {
  printf '%s\n' '{"schema_version":1,"cells":14,"attempts_per_cell":1,"max_concurrency":1,"network_mode":"none","snapshot":"dm-verity-v1","receipt_schema":3,"roles":["producer","executor-signer","approver-signer","fresh-verifier"],"evaluation_stage":"E0","status":"NOT_EVALUATED","publishable":false,"winner":null,"dominance_allowed":false,"unlock_allowed":false}'
}

linux_root() {
  [[ $(uname -s) == Linux ]] || { echo "Linux is required" >&2; exit 69; }
  [[ ${EUID} -eq 0 ]] || { echo "root is required" >&2; exit 77; }
}

fresh_directory() {
  local path=$1
  [[ ! -e $path ]] || { echo "path must be fresh: $path" >&2; return 1; }
  install -d -m 0700 -- "$path"
}

# Uses Linux openat2 rather than pathname pre-checks. RESOLVE_BENEATH (0x08) and
# RESOLVE_NO_SYMLINKS (0x04) close rename/symlink races; O_NOFOLLOW is retained.
validate_role_key() {
  local path=$1
  python3 - "$path" <<'PY'
import ctypes, os, stat, sys
path=os.path.abspath(sys.argv[1]); parent,name=os.path.split(path)
root=os.open(parent, os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
class How(ctypes.Structure): _fields_=[("flags",ctypes.c_ulonglong),("mode",ctypes.c_ulonglong),("resolve",ctypes.c_ulonglong)]
number=437 if os.uname().machine in {"x86_64","aarch64"} else -1
if number < 0: raise SystemExit("unsupported openat2 architecture")
how=How(os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,0,0x08|0x04)
fd=ctypes.CDLL(None,use_errno=True).syscall(number,root,name.encode(),ctypes.byref(how),ctypes.sizeof(how))
if fd < 0: raise OSError(ctypes.get_errno(),"openat2 role key")
st=os.fstat(fd)
if not stat.S_ISREG(st.st_mode) or stat.S_IMODE(st.st_mode)!=0o400 or st.st_uid!=0 or st.st_size!=32:
    raise SystemExit("role key must be a root-owned 0400 regular 32-byte file")
os.close(fd); os.close(root)
PY
}

require_digest_image() {
  local image=$1
  [[ $image == *@sha256:* ]] || { echo "image must use immutable repo@sha256 digest" >&2; return 1; }
  docker image inspect "$image" >/dev/null
}

COMMON=()
set_common() {
  local seccomp=$1 pids=$2 memory=$3
  COMMON=(--network none --read-only --cap-drop ALL
    --security-opt no-new-privileges --security-opt "seccomp=$seccomp"
    --user 65532:65532 --pids-limit "$pids" --memory "$memory" --cpus 1
    --tmpfs "/tmp:rw,noexec,nosuid,nodev,size=64m"
    --env HOME=/nonexistent --env LANG=C.UTF-8 --env LC_ALL=C.UTF-8)
}

emit_cells() {
  local command=$1
  local count=0 repo arm
  for repo in "${REPOS[@]}"; do
    for arm in "${ARMS[@]}"; do
      count=$((count+1))
      printf '{"ordinal":%d,"repo_id":"%s","arm_id":"%s","attempt":1,"command":"%s","evaluation_stage":"E0","status":"NOT_EVALUATED"}\n' "$count" "$repo" "$arm" "$command"
    done
  done
  [[ $count -eq 14 ]]
}

COMMAND=${1:-}; [[ $# -gt 0 ]] || usage; shift
if [[ $COMMAND == contract ]]; then [[ $# -eq 0 ]] || usage; contract; exit 0; fi

declare PLAN='' INVENTORY='' SOURCES='' EXECUTOR_KEY='' APPROVER_KEY='' PUBLIC_CONFIG=''
declare SECCOMP='' EXPERIMENT_ROOT='' OUTPUT_ROOT=''
declare PRODUCER_IMAGE='' EXECUTOR_IMAGE='' APPROVER_IMAGE='' VERIFIER_IMAGE=''
while [[ $# -gt 0 ]]; do
  case $1 in
    --plan) PLAN=${2:?}; shift 2;; --inventory) INVENTORY=${2:?}; shift 2;;
    --sources) SOURCES=${2:?}; shift 2;; --executor-key) EXECUTOR_KEY=${2:?}; shift 2;;
    --approver-key) APPROVER_KEY=${2:?}; shift 2;; --public-config) PUBLIC_CONFIG=${2:?}; shift 2;;
    --seccomp) SECCOMP=${2:?}; shift 2;; --experiment-root) EXPERIMENT_ROOT=${2:?}; shift 2;;
    --output-root) OUTPUT_ROOT=${2:?}; shift 2;; --producer-image) PRODUCER_IMAGE=${2:?}; shift 2;;
    --executor-signer-image) EXECUTOR_IMAGE=${2:?}; shift 2;; --approver-signer-image) APPROVER_IMAGE=${2:?}; shift 2;;
    --verifier-image) VERIFIER_IMAGE=${2:?}; shift 2;; *) usage;;
  esac
done

if [[ $COMMAND == dry-run ]]; then
  # Contract inspection never invokes Docker, veritysetup, mounts, or key reads.
  emit_cells dry-run
  printf '%s\n' "$CLAIM"
  exit 0
fi
[[ $COMMAND == preflight || $COMMAND == run || $COMMAND == verify ]] || usage
linux_root
command -v docker >/dev/null; command -v veritysetup >/dev/null
[[ -f $PUBLIC_CONFIG ]] || { echo "public config missing" >&2; exit 66; }
if [[ $COMMAND != verify ]]; then
  [[ -f $PLAN && -f $INVENTORY && -d $SOURCES ]] || { echo "trusted inputs missing" >&2; exit 66; }
  validate_role_key "$EXECUTOR_KEY"; validate_role_key "$APPROVER_KEY"
  [[ $(sha256sum "$EXECUTOR_KEY"|cut -d' ' -f1) != $(sha256sum "$APPROVER_KEY"|cut -d' ' -f1) ]] || { echo "role private keys must differ" >&2; exit 65; }
fi
for image in "$PRODUCER_IMAGE" "$EXECUTOR_IMAGE" "$APPROVER_IMAGE" "$VERIFIER_IMAGE"; do
  [[ -z $image ]] || require_digest_image "$image"
done
[[ $COMMAND != preflight ]] || { emit_cells preflight >/dev/null; contract; exit 0; }

[[ -n $SECCOMP && -f $SECCOMP ]] || { echo "pinned seccomp profile missing" >&2; exit 66; }
set_common "$SECCOMP" 64 4g

if [[ $COMMAND == verify ]]; then
  fresh_directory "$OUTPUT_ROOT"
  # Verifier sees only public identities, source/snapshot ro, and a fresh verdict out.
  docker run --rm "${COMMON[@]}" \
    --mount "type=bind,src=$EXPERIMENT_ROOT,dst=/evidence,readonly" \
    --mount "type=bind,src=$PUBLIC_CONFIG,dst=/public/config.json,readonly" \
    --mount "type=bind,src=$OUTPUT_ROOT,dst=/verdict-out" \
    "$VERIFIER_IMAGE" aggregate --experiment /evidence --public-config /public/config.json --output /verdict-out/verdict.json
  exit $?
fi

fresh_directory "$EXPERIMENT_ROOT"
failures=0
ordinal=0
for repo in "${REPOS[@]}"; do
  for arm in "${ARMS[@]}"; do
    ordinal=$((ordinal+1)); cell="$EXPERIMENT_ROOT/cells/$repo/$arm"
    install -d -m 0700 "$cell"; out="$cell/producer-out"
    [[ ! -e $out && ! -e $cell/index && ! -e $cell/raw ]] || { failures=$((failures+1)); continue; }
    # Producer is keyless. Source and frozen inputs are read-only; only fresh /out is rw.
    mkdir -m 0700 "$out"
    if ! docker run --name "no1-008a-p-${ordinal}" "${COMMON[@]}" \
      --mount "type=bind,src=$SOURCES/$repo,dst=/source,readonly,bind-propagation=rprivate" \
      --mount "type=bind,src=$PLAN,dst=/plan/cell-plan.json,readonly" \
      --mount "type=bind,src=$SECCOMP,dst=/operator/no-network-seccomp.json,readonly" \
      --mount "type=bind,src=$out,dst=/out" "$PRODUCER_IMAGE" \
      --plan /plan/cell-plan.json --out /out; then failures=$((failures+1)); fi
    docker wait "no1-008a-p-${ordinal}" >/dev/null || true
    docker rm "no1-008a-p-${ordinal}" >/dev/null || true

    # No retry and no overwrite: whatever terminal evidence exists is sealed once.
    truncate -s 1G "$cell/data.img"; mkfs.ext4 -q -d "$out/core" "$cell/data.img"
    truncate -s 256M "$cell/hash.img"
    salt=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
    format=$(veritysetup format "$cell/data.img" "$cell/hash.img" --hash sha256 --salt "$salt")
    root_hash=$(awk '/Root hash:/{print $3}' <<<"$format")
    mapping="no1-008a-${ordinal}-$$"; mountpoint="$cell/verity"
    veritysetup open "$cell/data.img" "$mapping" "$cell/hash.img" "$root_hash" --salt "$salt"
    mkdir "$mountpoint"; mount -o ro,nosuid,nodev,noexec "/dev/mapper/$mapping" "$mountpoint"

    # Each signer receives exactly one private key. Receipt remains detached.
    docker run --rm "${COMMON[@]}" --mount "type=bind,src=$mountpoint,dst=/snapshot,readonly" \
      --mount "type=bind,src=$EXECUTOR_KEY,dst=/role-key/private.ed25519,readonly" \
      --mount "type=bind,src=$cell,dst=/receipt-out" "$EXECUTOR_IMAGE" sign-executor || failures=$((failures+1))
    docker run --rm "${COMMON[@]}" --mount "type=bind,src=$mountpoint,dst=/snapshot,readonly" \
      --mount "type=bind,src=$APPROVER_KEY,dst=/role-key/private.ed25519,readonly" \
      --mount "type=bind,src=$cell,dst=/receipt-out" "$APPROVER_IMAGE" sign-approver || failures=$((failures+1))
    # Fresh verifier has public bytes only.
    docker run --rm "${COMMON[@]}" --mount "type=bind,src=$mountpoint,dst=/snapshot,readonly" \
      --mount "type=bind,src=$SOURCES/$repo,dst=/source,readonly" \
      --mount "type=bind,src=$PUBLIC_CONFIG,dst=/public/config.json,readonly" \
      --mount "type=bind,src=$cell,dst=/verdict-out" "$VERIFIER_IMAGE" cell || failures=$((failures+1))
    umount "$mountpoint"; veritysetup close "$mapping"
  done
done
[[ $ordinal -eq 14 ]]
printf '%s\n' "$CLAIM" >"$EXPERIMENT_ROOT/verdict.json"
# Fail-all: the matrix is attempted exactly once, but any failure remains terminal E0.
(( failures == 0 )) || exit 1
exit 1 # A real reviewer, never this operator, may later issue SETUP_QUALIFIED.
