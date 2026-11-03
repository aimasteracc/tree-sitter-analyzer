# Callers gate (`benchmarks/callers_gate`)

A permanent, local verification gate for every PR that can change
`nav action=callers` verdicts. It replays the r15 callers corpus (7 pinned OSS
repos, 2,457 targets, full + compact form) on the base and the head code, on
**one shared index**, and judges the difference automatically. A human reads
only the residual list at the top of `report.md`.

The worst TSA bug is a wrong `complete`. The gate exists to catch it, so every
cache in it fails closed: anything unreadable, stale or mismatched is rebuilt
or recomputed, never used.

## Workflow per PR

```powershell
cd <your PR worktree>
py -3 -m benchmarks.callers_gate precheck --head .                       # ruff, format, mypy, related tests, patch coverage
py -3 -m benchmarks.callers_gate run --base origin/develop --head .      # replay + judge, writes runs/<stamp>/report.md
```

After the PR is squash-merged and `origin/develop` is fetched:

```powershell
py -3 -m benchmarks.callers_gate promote --ref origin/develop
```

`promote` copies the head answers of the merged tree into `baseline/`. It
works only when the merged `tree_sitter_analyzer/` tree hash equals a tree the
gate ran as a head (a squash merge with nothing in between); otherwise it
exits 2 and the next run recomputes the base side once. `run` also promotes
automatically: when `baseline/` misses but `results/` holds the base tree's
answers for the same index key, they are used (and copied).

One-time setup (already done on the owner's machine; idempotent):

```powershell
py -3 -m benchmarks.callers_gate setup [--python <venv python>]
```

`setup` bare-clones the 7 repos at their pinned commits (from the local r10 /
ts1 clones, hard-linked, else from GitHub), copies the r15 target lists, GT2
and the hono / zod hand labels into `corpus/`, and records the gate
interpreter (default: the main checkout's `.venv`).

### Exit status of `run`

| code | meaning |
|---|---|
| 0 | PASS: no failure, nothing to review |
| 3 | REVIEW: no failure, but residual grep hits need a human |
| 1 | FAIL: a forbidden change, a GT2 / label miss, or an oracle failure |
| 2 | ERROR: the gate could not run (corpus drift, index build failure, server crash, ...). Never a pass. |

### Brief template for a subagent

> Run the callers gate for this PR. From the PR worktree, run
> `py -3 -m benchmarks.callers_gate precheck --head .` and fix every failure.
> Then run `py -3 -m benchmarks.callers_gate run --base origin/develop --head .`
> (add `--policy <file>` only for transitions the PR is meant to make, and say
> which). Report the exit code, the Transitions table and the Failures section
> of `report.md` verbatim. If the exit code is 3, read every row of
> "Residual items for human review": open the hit, decide whether it can reach
> the target, and report each as "not a caller because ..." or "MISSED CALLER".
> One missed caller means the new `complete` is wrong: stop and report it. Do
> not edit the gate, its caches or its policy defaults to make a run pass.

## What `run` does

For each repo, concurrently (`--jobs`, default `min(cpus/2, (free GiB - 2) / 0.5, 8)`):

1. **Index.** Compute the index key from the head code (below). Reuse
   `index/<repo>/<key>/` if its manifest is valid; else build it with the head
   code in a subprocess that audits `sys.modules` afterwards.
2. **Base answers.** Look up `baseline/<base tree>/<index key>/<repo>.json`.
   On a miss, start long-lived MCP servers with the base code on that index
   and ask every target (full form, then compact form).
3. **Head answers.** Same, with the head code, always computed. Saved under
   `results/<head tree>/<index key>/<repo>.json`.
4. **Judge** (below) and write `report.md` / `report.json`.

Base and head always read the same index (the determinism of the manual
gates). A side may be split over several servers on the same index
(`--shards repo=N`, default `zod=5 pydantic=2 fastapi=2 hono=2`). The base side
uses contiguous slices; the head side balances slices by the base side's
measured per-target cost. Rows are merged back in corpus order. Every server gets its own environment: no inherited `TSA_*`,
`TREE_SITTER_*` or `PYTHON*` variables, `PYTHONHASHSEED=0`, and private
`TEMP` / `HOME` / `APPDATA` / `LOCALAPPDATA` directories under the run
directory. A server refuses to start unless `tree_sitter_analyzer` resolves to
the directory under test (an editable install cannot answer for it).

The head may be a worktree (uncommitted edits count: its tree hash is computed
with a throwaway index) or a git ref. The base is usually a ref; its package
is extracted once with `git archive` into `src/<tree>/`.

## Cache layout

Root: `C:\git-private\tsa-gate` (`--root` or `TSA_GATE_ROOT`).

```
config.json                              gate interpreter, pinned SHAs
repos/<repo>/                            bare clone; never deleted per PR
corpus/{targets,gt2,labels}/<repo>.json  inputs; corpus/manifest.json holds their sha256
src/<tree>/tree_sitter_analyzer/         base package snapshots (git archive of the tree)
index/<repo>/<index-key>/tree/           detached worktree at the pin = project root, .ast-cache inside
index/<repo>/<index-key>/manifest.json   written last; its absence marks a partial build
baseline/<tree>/<index-key>/<repo>.json  base answers
results/<tree>/<index-key>/<repo>.json   head answers (promote -> baseline)
runs/<stamp>/                            report.md, report.json, server logs, oracle I/O
locks/<repo>.lock                        one index builder per repo across concurrent runs
```

Disk (measured): repos ~50 MB (hard links), indexes ~0.3-0.6 GB per key for all 7
repos, answers ~2-4 MB per repo per tree. `run` keeps no more than the
current index key per repo plus the previous ones you have used; delete old
`index/<repo>/<key>` directories with `git -C repos/<repo> worktree remove`
or simply delete them and run `git -C repos/<repo> worktree prune`.

## Invalidation rules

**Index key** (`keys.index_key`) = hash of

- the gate format version and the index build arguments (`mode=full`);
- the repo name and pinned commit, and the checkout setting (`core.autocrlf=true`, as the r15 clones);
- the interpreter version, every installed distribution `name==version`
  (except the analyzer itself), and the fixed server environment variables;
- the blob of `pyproject.toml`;
- the **git blob hash of every file** under `tree_sitter_analyzer/` (code,
  `.scm` queries, data files) **except** the query-only modules
  `tree_sitter_analyzer/mcp/tools/callers_*.py` (`keys.QUERY_ONLY`).

Why not TSA's `source_fingerprint` (used by `.ast-cache/graph-memo`): it hashes
path + size + **mtime**, so two checkouts of one commit never agree. Git blobs
are content-addressed and line-ending normalized.

Why the exclusion is safe: the index builder runs in its own process and, after
the build, lists every loaded `tree_sitter_analyzer` module. If any
`QUERY_ONLY` module was imported, the gate refuses the index (exit 2) and
`QUERY_ONLY` must be narrowed. For a callers module to start influencing the
index, some non-excluded file must start importing it; that edit changes the
key, so the audit always runs on the code that would be cached. When in
doubt, the rule is: a file belongs in `QUERY_ONLY` only if no index build can
load it. Everything else rebuilds.

**Answer files** (baseline and results) are used only when all of these match
the request: format, tree hash, index key, repo, pinned commit, query key
(sha256 of the target list + query arguments + forms), and the sha256 of the
rows (timings excluded). A file that fails any check is moved to
`*.corrupt` and the side is recomputed.

**Corpus**: every run re-hashes `corpus/` against `corpus/manifest.json`; any
drift is exit 2. A missing GT2 or label file is exit 2.

## Judging

### Transitions (per repo)

Each target row is compared base vs head and gets change kinds: `verdict`,
`reasons`, `caller_count`, `callers` (same count, different callers),
`sites` (site lists / `open_sites` / site totals), `compact` (compact verdict
disagrees with full on head but not on base), `error` (a query error), `other`
(any other field). Caller order is ignored: TSA does not fix it.

### Policy

Default (no `--policy`):

- verdict transitions: only `X->complete`; every other transition, and any
  loss of `complete`, is a violation;
- reason changes: allowed;
- site changes: allowed on a row whose verdict transition is allowed or whose
  reasons changed (the sites are the evidence of the reason); a site change
  with the same verdict and reasons is a violation;
- caller-count and caller-list changes: violations;
- `error` and `compact`: always violations, cannot be allowed.

A PR that is meant to change something else passes a policy file or flags
(`--allow-transition unknown->incomplete`, `--allow-caller-changes`,
`--allow-site-changes`); see `benchmarks/callers_gate/policy.py` for the file
format, including per-target `allow_items`.

### Oracles

- **Python** (rich, pydantic, fastapi): every head `complete` must list every
  GT2 caller; a target GT2 does not define is `gt2_untracked`. A miss on a new
  or changed row fails; on a row identical to base it is reported as
  pre-existing.
- **`open_sites` enumerated answers** (the PR-4 soundness check): each GT2
  caller (Python) or labelled call (hono, zod) must be a listed caller or an
  open site. Labelled calls are also checked on hono / zod completes.
- **TS / JS / Java new completes**: every `git grep -w` occurrence of the bare
  name in a tracked file is classified with tree-sitter
  (`oracle_grep.py`): `caller` (inside a listed caller's span),
  `own_declaration`, `declaration` (another declaration's name token),
  `import_export`, `comment`, `string` (a literal whose text is not exactly the
  name; a literal equal to the name is residual, it may be a dynamic key),
  `non_code` (docs / data files), `other_symbol` (provably different: an
  unqualified Java call, `this.name` or `Cls.name` in a project class with no
  inheritance relation to the target's class, when the target's whole
  ancestry resolves; or a bare name bound by an import from an external
  module), and `residual` with the reason. Only residual hits reach a human.

## `precheck`

`precheck --head <worktree> [--base origin/develop] [--tests ...] [--patch-target N]`
runs, under the gate interpreter with `PYTHONPATH=<worktree>`:

1. `ruff check .` (as CI) and `ruff format --check` on the changed files;
2. `mypy` on the changed `tree_sitter_analyzer/` files;
3. the related tests: changed test files, `tests/**/test_*<stem>*.py` for every
   changed package module, plus `--tests`, under branch coverage;
4. patch coverage of the changed package lines against the merge base,
   counted like Codecov (a partially covered branch line is not a hit). The
   repo has no `codecov.yml`, so Codecov's patch target is `auto`: the base
   commit's project coverage, read from the Codecov API (e.g. 90.51% at
   1b453d6a). `--patch-target` overrides it; without network the check fails
   rather than guess.

The related tests are a subset of CI's suite, so local patch coverage can only
be lower than CI's; a pass is a strong proxy, not a guarantee.

## CI: two E2E passes in parallel

`ci.yml`'s `e2e` job ("E2E Tests (MCP black-box)") is a matrix of two
attempts on the same head with `fail-fast: false`, so the two required passes
run concurrently instead of by manual rerun. Check names become
`E2E Tests (MCP black-box) (attempt 1)` and `(attempt 2)`. Branch protection
on `develop` requires only `Quality Gate`, `Claim Invariant Suite (unit
subset)` and `Validate head→base per GITFLOW.md`; `Quality Gate` reads
`needs.e2e.result`, which is `success` only when both attempts pass. No
protection setting changes.
