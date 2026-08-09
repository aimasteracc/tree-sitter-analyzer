# RFC-0024: Default dependency split measurement protocol

- **Status**: measurement protocol registered; design deferred
- **Author(s)**: Runtime Lead
- **Created**: 2026-08-08
- **Last updated**: 2026-08-10
- **Tracking**: roadmap NO1-006B

## Scope and evidence order

This revision registers the E0 protocol only. The measured subject is the clean,
detached commit `7e0e8f6e03270fcbf4025d717415ef69c9354145`; the collector is a later,
separate clean commit. Candidate dependency membership and admission thresholds
are intentionally deferred until a receipt is committed, so the history proves
that the probe was registered before recommendations.

The collector records its commit plus its script/schema SHA-256, the subject Git
tree/archive SHA-256 and `uv.lock` SHA-256. The subject rejects tracked,
untracked, and ignored entries. Every subject Git/uv build/export/install command
has the subject checkout as `cwd`; the collector is run from its own clean
worktree using `.venv/bin/python` (or `uv run --offline --frozen --no-sync`).

## Offline closure protocol

`UV_OFFLINE=1` is mandatory. `uv export --frozen --offline --no-dev
--no-emit-project --format requirements-txt` derives exact requirements with
artifact hashes from the subject `uv.lock`. A fresh environment installs that
hashed closure with `--require-hashes --no-deps`; the locally built project wheel
is then installed separately with `--no-deps`. The receipt records export/lock
hashes and every installed canonical distribution name, version, and
root/direct/transitive role. PEP 508 markers are evaluated with `packaging`'s
target-environment semantics; extras are not silently included.

Root wheel bytes are named `root_wheel_artifact_size_bytes`. Network-transfer
bytes remain structured `unknown`: an offline cache cannot measure transfer, and
that unknown value cannot be an improvement gate. Installed bytes reject
symlinks and out-of-venv paths and inode-deduplicate hardlinks.

## Startup protocol

CLI and MCP each receive an independently created, identically installed fresh
venv. `PYTHONDONTWRITEBYTECODE=1` makes the first process bytecode-cold; the OS
page cache is explicitly uncontrolled. Later samples are fresh-process warm,
not in-process warm. No CLI probe preheats the MCP venv.

The CLI clock starts before process creation and ends only after a deterministic
JSON analysis of a tiny Python fixture is validated. The MCP clock also starts
before `Popen` and ends only after successful `initialize`, the `initialized`
notification, and an exact `tools/list` surface. Binary frames use an absolute
30-second deadline and byte cap; timeout/overflow terminates the process group.

## Receipt validation and native axes

Schema v2 is property-closed and constrains commands, definitions, formats and
axis states. The collector validator additionally enforces arithmetic and
identity invariants: repeats/sample lengths, distribution counts/unique sorted
names, direct + transitive + root totals, artifact and lock aliases, payload
hash, measured axis, and chronological timezone-aware RFC 3339 timestamps.
Darwin/Linux/Windows are schema-supported; this collector currently emits only
macOS `measured_e0`, with Linux and Windows honestly `unknown`.

Output must be outside the subject repository. Parent symlinks and an output
symlink are rejected; a same-directory `O_NOFOLLOW` temporary file is fsynced,
atomically replaced, then the directory is fsynced.

## Reproduction (after this protocol commit)

Create a clean detached subject worktree, with required locked artifacts already
in the offline uv cache:

```bash
git worktree add --detach /tmp/no1-006b-subject 7e0e8f6e03270fcbf4025d717415ef69c9354145
UV_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 NO1_006B_PYTHON=3.14 \
  .venv/bin/python scripts/collect_no1_006b_baseline.py \
  --repo /tmp/no1-006b-subject --repeats 5 \
  --output /tmp/no1-006b-macos-e0.json
git worktree remove /tmp/no1-006b-subject
```

The receipt, measured values, candidate design, gates, and rollback policy are
added only after this protocol commit.
