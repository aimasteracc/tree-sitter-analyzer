# RFC-0024: Default dependency split measurement protocol

- **Status**: RFC plus descriptive post-hoc E0 baseline; no admission baseline
- **Author(s)**: Runtime Lead
- **Created**: 2026-08-08
- **Last updated**: 2026-08-10
- **Tracking**: roadmap NO1-006B

## Scope and evidence order

The measured subject is the clean, detached commit
`7e0e8f6e03270fcbf4025d717415ef69c9354145`; the collector is a later, separate
clean commit. This document makes no preregistration, blindness, or
measured-before-design claim. The first RFC draft already contained candidate
membership and gates. Later commits removed and then restored that material,
and the current collector and receipt were hardened after the design draft.
Consequently the protocol and current receipt are post-hoc hardening evidence.
They provide a descriptive E0 snapshot only and cannot be used as the NO1-011A
admission baseline.

The collector records its commit plus its script/schema SHA-256, the subject Git
tree/archive SHA-256 and `uv.lock` SHA-256. Both subject and collector reject
tracked, untracked, and ignored entries. Every subject Git/uv
build/export/install command has the subject checkout as `cwd`; the collector is
run from its own clean worktree by an absolute interpreter path located outside
that worktree. Collector tooling is exported and installed outside both
repositories.

## Offline closure protocol

`UV_OFFLINE=1` is mandatory. Collector tooling is isolated in the exact
`no1-006b-collector-tool` dependency group: `packaging==25.0`,
`hatchling==1.31.0`, `jsonschema==4.25.1`, and their lock-resolved closure. Its hashed frozen export
and the collector `uv.lock` are recorded separately from the subject closure.
The project wheel is built by the current external collector `sys.executable`
with `uv build --offline --no-build-isolation --python <collector-sys-executable>`,
so the recorded CPython implementation/version and exact Hatchling version are
the build environment rather than an implicitly resolved isolated environment.

`uv export --frozen --offline --no-dev --no-emit-project --format
requirements-txt` derives exact requirements with artifact hashes from the
**subject** `uv.lock`. A fresh environment installs that
hashed closure with `--require-hashes --no-deps`; the locally built project wheel
is then installed separately with `--no-deps`. The receipt records export/lock
hashes and every installed canonical distribution name, version, and
root/direct/transitive role. PEP 508 marker inputs are returned by
`packaging.markers.default_environment()` inside the target interpreter and are
then evaluated by the collector; extras are not silently included. This attests
the frozen resolution and installed versions. It does not attest which cached
wheel or sdist was selected, nor that selected artifact's filename or hash,
where the lock permits multiple platform-compatible artifacts.

Root wheel bytes are named `root_wheel_artifact_size_bytes`. Network-transfer
bytes remain structured `unknown`: an offline cache cannot measure transfer, and
that unknown value cannot be an improvement gate. Installed bytes reject
symlinks and out-of-venv paths and inode-deduplicate hardlinks. The source
archive, requirements export, and root-wheel size caps are checked only after
each artifact has been generated. They are post-generation artifact caps, not a
temporary-filesystem quota, and do not claim an adversarial bound on transient
disk consumption.

## Startup protocol

CLI and MCP each receive an independently created, identically installed fresh
venv. `PYTHONDONTWRITEBYTECODE=1` makes the first process bytecode-cold; the OS
page cache is explicitly uncontrolled. Later samples are fresh-process warm,
not in-process warm. No CLI probe preheats the MCP venv, but the fixed host order
is all CLI samples followed by all MCP samples, so shared OS-cache ordering is
not controlled. The receipt records that order plus CPU/logical-core/RAM fields;
filesystem, virtualization, and power state remain explicitly unknown.

The CLI clock starts before process creation and ends only after a deterministic
JSON analysis of a tiny Python fixture is validated. The MCP clock also starts
before `Popen` and ends only after successful `initialize`, the `initialized`
notification, and an exact `tools/list` surface. Binary frames use an absolute
30-second deadline and byte cap; timeout/overflow terminates the process group.

## Receipt validation and native axes

Schema v3 is property-closed and constrains commands, definitions, formats and
axis states. The collector validator additionally enforces arithmetic and
identity invariants: repeats/sample lengths, distribution counts/unique sorted
names, direct + transitive + root totals, artifact and lock aliases, payload
hash, measured axis, and chronological timezone-aware RFC 3339 timestamps.
Darwin/Linux/Windows are schema-supported; this collector currently emits only
macOS `measured_e0`, with Linux and Windows honestly `unknown`.

Output must be outside the subject repository. Parent symlinks and an output
symlink are rejected; a same-directory `O_NOFOLLOW` temporary file is fsynced,
atomically replaced, then the directory is fsynced.

## Reproduction of the descriptive receipt

The receipt binds collector commit `712dfaabda2e8f3845c94c19545902b334875828`,
which is an intermediate commit on this PR branch. Therefore PR #1250 **must be
merged with GitHub's merge-commit strategy**, preserving branch ancestry. Squash
and rebase merges are prohibited because they make the bound collector commit
unreachable in a fresh clone. The merge orchestrator must use `gh pr merge 1250
--merge` (not `--squash` or `--rebase`).

Run this from any checkout of the repository, with CPython 3.14, all locked
artifacts already available in the offline uv cache, and the operator-provided
trusted uv binary identified below. This RFC does not distribute that binary;
the operator must obtain and supply it independently. It creates separate clean,
detached collector and subject worktrees. The collector's separately locked,
exact hashed tooling closure, its virtual environment, the receipt, and every other generated file
live under an external temporary directory:

```bash
set -eu
: "${NO1_006B_UV:?set NO1_006B_UV to the operator-provided trusted uv binary}"
TRUSTED_UV=$(cd "$(dirname "$NO1_006B_UV")" && pwd -P)/$(basename "$NO1_006B_UV")
test -f "$TRUSTED_UV" && test ! -L "$TRUSTED_UV"
test "$("$TRUSTED_UV" --no-config --version)" = 'uv 0.12.3 (507230998 2026-08-07 aarch64-apple-darwin)'
test "$(shasum -a 256 "$TRUSTED_UV" | awk '{print $1}')" = '2b4ccdac26598ca8c300e5c36d24297fa1471c350c46d2f34c835bf06be303ab'
UV_CACHE_DIR_SAVED=${UV_CACHE_DIR-}
for name in $(env | sed -n 's/^\(UV_[A-Za-z0-9_]*\)=.*/\1/p'); do unset "$name"; done
export UV_NO_CONFIG=1 UV_OFFLINE=1
if test -n "$UV_CACHE_DIR_SAVED"; then export UV_CACHE_DIR=$UV_CACHE_DIR_SAVED; fi
SOURCE_REPO=$(git rev-parse --show-toplevel)
COLLECTOR_COMMIT=712dfaabda2e8f3845c94c19545902b334875828
SUBJECT_COMMIT=7e0e8f6e03270fcbf4025d717415ef69c9354145
RUN_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/no1-006b.XXXXXX")
RUN_ROOT=$(cd "$RUN_ROOT" && pwd -P)
COLLECTOR="$RUN_ROOT/collector"
SUBJECT="$RUN_ROOT/subject"
TOOL_REQUIREMENTS="$RUN_ROOT/collector-requirements.txt"
TOOL_VENV="$RUN_ROOT/collector-tool-venv"
TOOL_PYTHON="$TOOL_VENV/bin/python"
RECEIPT="$RUN_ROOT/no1-006b-macos-e0.json"
cleanup() {
  git -C "$SOURCE_REPO" worktree remove --force "$SUBJECT" 2>/dev/null || true
  git -C "$SOURCE_REPO" worktree remove --force "$COLLECTOR" 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM

git -C "$SOURCE_REPO" worktree add --detach "$COLLECTOR" "$COLLECTOR_COMMIT"
git -C "$SOURCE_REPO" worktree add --detach "$SUBJECT" "$SUBJECT_COMMIT"
test -z "$(git -C "$COLLECTOR" status --porcelain=v1 --untracked-files=all --ignored)"
test -z "$(git -C "$SUBJECT" status --porcelain=v1 --untracked-files=all --ignored)"
(
  cd "$COLLECTOR"
  "$TRUSTED_UV" export --no-config --frozen --offline \
    --only-group no1-006b-collector-tool --no-emit-project \
    --format requirements-txt >"$TOOL_REQUIREMENTS"
)
"$TRUSTED_UV" venv --no-config --offline --python 3.14 "$TOOL_VENV"
"$TRUSTED_UV" pip install --no-config --offline --python "$TOOL_PYTHON" --no-deps \
  --require-hashes -r "$TOOL_REQUIREMENTS"
test -z "$(git -C "$COLLECTOR" status --porcelain=v1 --untracked-files=all --ignored)"

PYTHONDONTWRITEBYTECODE=1 NO1_006B_PYTHON=3.14 NO1_006B_UV="$TRUSTED_UV" \
  "$TOOL_PYTHON" "$COLLECTOR/scripts/collect_no1_006b_baseline.py" \
  --repo "$SUBJECT" --repeats 5 --output "$RECEIPT"
test -z "$(git -C "$COLLECTOR" status --porcelain=v1 --untracked-files=all --ignored)"
test -z "$(git -C "$SUBJECT" status --porcelain=v1 --untracked-files=all --ignored)"
printf 'collector and subject clean-ignored gates: PASS\nreceipt: %s\n' "$RECEIPT"
printf 'remove external run directory when finished: %s\n' "$RUN_ROOT"
```

## Measured macOS E0 receipt

The post-hoc hardened collector produced
[`docs/baselines/no1-006b-macos-e0.json`](../docs/baselines/no1-006b-macos-e0.json)
from collector commit `712dfaabda2e8f3845c94c19545902b334875828` and the distinct pinned subject.
<!-- BEGIN GENERATED RECEIPT SUMMARY -->
Its canonical payload SHA-256 is `f1ff36c9ccd75a29a106227b6b448947c42b12e8c45c10910fb558b35f362973`.

| Axis | Measured value |
|---|---:|
| root wheel artifact SHA-256 / bytes | `c1cb3520542fd14dad60ddec55dfac6afbdaa424e7a4a39d875be1801d98f9e8` / 2,209,032 |
| network transfer | unknown (offline measurement) |
| installed distribution files | 89,982,491 bytes across 4,743 unique regular files |
| dependencies excluding root (direct + transitive) | 64 (33 + 31) |
| installed distributions including root | 65 |
| CLI bytecode-cold; warm samples (ms) | 1575.56; 565.793, 610.982, 609.892, 574.942, 640.368 |
| MCP protocol-ready cold; warm samples (ms) | 2170.627; 829.817, 783.43, 775.074, 791.538, 808.726 |
<!-- END GENERATED RECEIPT SUMMARY -->

This is macOS arm64 CPython 3.14.3 only. Linux and Windows remain `unknown` and
cannot pass admission. “Cold” does not claim an OS page-cache flush. The larger,
more honest startup values include real CLI analysis and MCP registry readiness;
they are not comparable to the superseded advertising/initialize-only probes.

## Candidate design sketch (not implemented or recommended)

The following is retained as a discussion sketch from the original draft. It is
not a recommendation, selection, or decision, and the descriptive E0 receipt
does not validate it:

* a default/core candidate retaining CLI/MCP protocol, shared models/security,
  formatters, tree-sitter runtime, and one documented minimal language;
* optional language groups (`popular`, `web`, `systems`, `all-languages`);
* an advanced-analysis group for graph/numeric and secret-scanning capabilities;
* a `full` compatibility extra reproducing today's default capabilities.

Membership remains a candidate, not a decision. Import tracing and native-axis
measurements decide startup requirements. Missing optional capabilities must
return deterministic installation hints, never tracebacks, silent loss, or a
false supported result. Console entry points and the locked CLI JSON/MCP TOON
defaults remain unchanged.

## Future NO1-011A chronology and possible evaluation dimensions

NO1-011A must start on an independent new branch. Before any final dependency
split is designed, that branch must commit a frozen collection protocol and
metric definitions. An independent reviewer must sign off that frozen protocol.
Only then may the team collect pre-split receipts on native macOS, Linux, and
Windows. The final split may be designed only after all three pre-split receipts
are committed. Candidate post-split wheels and receipts come afterward. The
current macOS receipt is descriptive and is expressly inadmissible as any of
those three pre-split admission receipts.

Possible dimensions for that future, independently approved protocol include
installed bytes, dependency distributions excluding root, direct/transitive
counts, and CLI/MCP cold and raw warm samples. The new protocol must decide exact
comparability, hardware/cache controls, thresholds, qualification, and rollback
before collection; this RFC does not freeze them. Network transfer remains
unknown here and cannot be compared. A future design should retain deterministic
optional-capability diagnostics, exact entry-point behavior, a compatibility
path, and metadata-only rollback, but those are discussion constraints rather
than a selected artifact or admission decision.

## Alternatives, acceptance, and deferred work

A big-bang modular rewrite and dynamic auto-download are rejected because they
make rollback unsafe and violate offline auditability. Keeping all defaults is
compatible but preserves the measured footprint. A split increases support
combinations, so the `full` path and explicit diagnostics are mandatory.

- [x] Exact lock-derived offline closure and descriptive macOS E0 receipt committed.
- [x] Subject and collector commits/hashes are distinct and bound.
- [x] Linux/Windows remain honestly unknown.
- [ ] NO1-011A freezes protocol/metrics on a new branch and obtains independent sign-off.
- [ ] NO1-011A collects three native pre-split receipts before final split design.

NO1-006B may deliver this RFC and descriptive baseline, but that delivery does
not satisfy future admission. Dependency metadata changes, lazy imports, feature
diagnostics, and admissible native evidence are deferred to NO1-011A. This E0
receipt supports no recommendation, marketing claim, or cross-platform
“faster/lighter” claim.
