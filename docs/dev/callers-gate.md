# Callers gate (`benchmarks/callers_gate`)

A permanent, local verification gate for every PR that can change
`nav action=callers` verdicts. It replays the r15 callers corpus (7 pinned OSS
repos, 2,457 targets, full + compact form) on the base and the head code and
judges the difference automatically. Base and head first answer on **one
shared index** (the head build); when the PR changes code the index build
uses, the base code also answers on **its own index**, so an indexer
regression is visible too. A human reads only the residual list at the top of
`report.md`. What the gate does and does not prove is in
[Trust model](#trust-model).

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

`promote` copies the head answers of the merged tree into `baseline/`. Head
answers are kept per run (`results/<tree>/<key>/<run-id>/`), so a later run on
the same tree never overwrites an earlier one; when several runs of the tree
disagree, pass `--run <run-id>` to pick one (without it, only agreeing runs
are promoted). It
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
| 3 | REVIEW: no failure, but residual items need a human, or the run was PARTIAL (`--repos` subset without `--allow-partial`) |
| 1 | FAIL: a forbidden change, a GT2 / label / compact miss, or an oracle failure |
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

For each repo, concurrently (`--jobs`, default `min(cpus/2, (free GiB - 2) / 0.5, 8)`;
`--jobs 1` is strictly sequential: one repo at a time and one server per side).
`--fresh-base` recomputes every base side instead of using cached answers, so
base and head latencies are measured in the same run, on the same load:

1. **Index.** Compute the index key from the head code (below). Reuse
   `index/<repo>/<key>/` if its manifest is valid; else build it with the head
   code in one audited subprocess (`TSA_INDEX_WORKERS=1`; a child interpreter
   fails the build) that lists `sys.modules` afterwards. The index's
   `.ast-cache/graph-memo` is replaced by a regular file (see Trust model).
2. **Base answers.** Look up `baseline/<base tree>/<index key>/<repo>.json`.
   On a miss, start long-lived MCP servers with the base code on that index
   and ask every target (full form, then compact form).
3. **Base answers on the base's own index** (only when the base index key
   differs from the head key, i.e. the PR changes a file the index key
   covers). Look up `baseline/<base tree>/<base index key>/`, else promote
   `results/<base tree>/<base index key>/` (the base tree's own head run),
   else build the base index with the base code and ask every target on it.
   After a merge this is the promoted baseline, so it is normally a cache hit.
4. **Head answers.** Same as 2, with the head code, always computed. Saved
   under `results/<head tree>/<index key>/<repo>.json`.
4. **Budget retry.** TSA bounds some checks by wall-clock budgets and answers
   `*_UNCHECKED` (or a compact verdict that disagrees with the full one) when
   a check ran out of time, or leaves a check result missing / `null` on one
   side only (`non_call_references: null`). Under load that changes answers without any code
   change (seen on the shared machine: `Context.#newResponse` went
   `complete -> incomplete (NON_CALL_REFERENCES_UNCHECKED)`). After all repos
   finish, every *changed* row that is budget-limited on either side is
   re-asked on one quiet server per side, up to 2 times; a conclusive answer
   replaces the cached one. A change that stays budget-limited is still
   judged and stays a violation (the note says to re-run on a quiet machine);
   it is never silently dropped. Both comparisons are retried.
6. **Judge** (below) and write `report.md` / `report.json`.

`report --rejudge [--run <dir>] [--policy ...]` judges a finished run again
from its cached answer files, for example with a policy that allows what a
reviewer accepted.

The same-index comparison is the determinism of the manual gates: only the
query code differs. A side may be split over several servers on the same index
(`--shards repo=N`, default `zod=5 pydantic=2 fastapi=2 hono=2`). The base side
uses contiguous slices; the head side balances slices by the base side's
measured per-target cost. Rows are merged back in corpus order.

Every server gets its own environment: no inherited `TSA_*`,
`TREE_SITTER_*` or `PYTHON*` variables, `PYTHONHASHSEED=0`,
`TSA_EVIDENCE_STORE=off`, and private `TEMP` / `HOME` / `APPDATA` /
`LOCALAPPDATA` directories under the run directory. A server refuses to start unless `tree_sitter_analyzer` resolves to
the directory under test (an editable install cannot answer for it).

The head may be a worktree (uncommitted edits count: its tree hash is computed
with a throwaway index) or a git ref. The base is usually a ref; its package
is extracted once with `git archive` into `src/<tree>/`, and every file gets an
mtime derived from the tree hash (`gitutil.tree_stamp_ns`).

`run --repos <subset>` is a PARTIAL run: it is printed, recorded in
`report.json` (`meta.partial`, `meta.skipped_repos`) and in the report title,
and exits at least 3 unless `--allow-partial` is passed.

## Cache layout

Root: `C:\git-private\tsa-gate` (`--root` or `TSA_GATE_ROOT`). Every cache
of one gate format lives under `v<format>/` (`layout.GATE_FORMAT`, now 2), so a
gate of another format can run on the same root; format 1 used the root
itself.

```
config.json                                 gate interpreter, pinned SHAs
repos/<repo>/                               bare clone; never deleted per PR
corpus/{targets,gt2,labels}/<repo>.json     inputs; corpus/manifest.json holds their sha256
v2/src/<tree>/tree_sitter_analyzer/         base package snapshots (git archive, tree-derived mtimes)
v2/index/<repo>/<index-key>/tree/           detached worktree at the pin = project root, .ast-cache inside
v2/index/<repo>/<index-key>/manifest.json   written last; its absence marks a partial build
v2/baseline/<tree>/<index-key>/<repo>.json  answers of <tree> on that index (base sides)
v2/results/<tree>/<index-key>/<repo>.json   head answers (promote -> baseline)
v2/runs/<stamp>/                            report.md, report.json, server logs, oracle I/O
v2/locks/<repo>.lock                        one index builder per repo across concurrent runs
```

`run` keeps the current index keys per repo (head and base) plus the 2 most
recently used others (`--keep-indexes`); older keys are removed with `git
worktree remove`.
Snapshots under `src/` and answer files are small and are not pruned.

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

Why the exclusion is safe: the index builder runs in its own process, with
`TSA_INDEX_WORKERS=1` and every child interpreter refused (a spawn worker's
imports would be invisible), and, after the build, lists every loaded
`tree_sitter_analyzer` module. If any
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

### Transitions (per repo, per comparison)

Each target row is compared base vs head and gets change kinds: `verdict`,
`reasons`, `caller_count`, `callers` (same count, different callers; every
kept caller field counts, `confidence_tier` included), `sites` (site lists /
`open_sites` / site totals), `compact` (compact verdict disagrees with full on
head but not on base), `error` (a query error), `other` (any other kept field,
including the compact answer text). Caller order is ignored: TSA does not fix
it.

There are one or two comparisons per repo:

- `same_index`: base code vs head code, both on the head-built index. It
  isolates the query path.
- `own_index`: base code on the base's own index vs head code on the head
  index. It exists only when the index keys differ, and is then the
  reference: "pre-existing" means "identical to the base on its own index".

The report shows a Transitions table per comparison.

### Policy

Default (no `--policy`), applied to every comparison:

- verdict transitions: only `X->complete`; every other transition, and any
  loss of `complete`, is a violation;
- reason changes: allowed;
- site changes: allowed on a row whose verdict transition is allowed or whose
  reasons changed (the sites are the evidence of the reason); a site change
  with the same verdict and reasons is a violation;
- caller-count and caller-list changes: violations;
- `other` changes: violations;
- `error` and `compact`: always violations, cannot be allowed.

A PR that is meant to change something else passes a policy file or flags
(`--allow-transition unknown->incomplete`, `--allow-caller-changes`,
`--allow-site-changes`, `--allow-other-changes`); see
`benchmarks/callers_gate/policy.py` for the file format. An `allow_items`
entry must name `repo`, `mode`, `file`, `qual` and `kinds`: it allows exactly
one row. Allowing a change never skips an oracle.

The report lists, for every changed row, the head's finding (verdict,
reasons, caller count, delta) and its `next_step`. A budget-limited violation (the row was still `*_UNCHECKED` or form-disagreeing
after the retries) carries a note that load may explain it; it is still a
violation.

### Oracles

Every head `complete` that differs from any base answer set (new completes and
changed `complete -> complete` rows alike) is checked:

- **Python** (rich, pydantic, fastapi): every head `complete` must list every
  GT2 caller; an open site is not coverage on a `complete`. A target GT2 does
  not define is `gt2_untracked`. A miss on a new or changed row fails; on a
  row identical to the reference base it is reported as pre-existing. On a new
  or changed complete, every GT2 `open_sites[name]` entry (a call GT2 itself
  could not resolve) that is not inside the listed caller of that name is a
  residual item.
- **`open_sites` enumerated answers** (the PR-4 soundness check): each GT2
  caller (Python) or labelled call (hono, zod) must be a listed caller or an
  open site.
- **Hand labels** (hono, zod): every labelled call of a `complete` must be
  inside a listed caller; the oracle decides that by innermost definition
  (below), never by the answer's `end_line`.
- **Compact form** (every head row, regardless of the base): a compact
  `complete` must be confirmed by the full answer (`compact_unconfirmed_complete`)
  and list exactly the full answer's callers, with the same count
  (`compact_callers_mismatch`). Both always fail.
- **TS / JS / Java**: every `git grep -w` occurrence of the bare name in a
  tracked file is classified with tree-sitter (`oracle_grep.py`):
  - `residual` first if the occurrence is inside a parse error;
  - `caller`: its innermost enclosing definition (by byte range; see
    `oracle_scope.py`) is a listed caller with exactly that name and start
    line. Definitions mirror TSA's attribution: named functions, methods,
    named arrows / function expressions (own name or the `const` they
    initialize), Java methods and constructors including those of an
    anonymous class body. Anonymous callbacks and lambdas belong to the
    enclosing definition, top-level code to `<module>` at the hit's line;
  - `own_declaration`, `declaration` (another declaration's name token),
    `comment`, `string` (a literal whose text is not exactly the name; a
    literal equal to the name is residual, it may be a dynamic key),
    `non_code` (docs / data files);
  - `import_export`: an un-aliased import or export specifier, or an aliased
    import (`import { f as g }`) whose every use of `g` in that file is
    proven. An aliased re-export (`export { f as g }`), `export default f`
    and a default-exported declaration are residual: importers can bind them
    under a name grep never sees;
  - `other_symbol`: `X.name` / `this.name` / an unqualified Java call on a
    project class that is provably unrelated to the target's class, or a bare
    name bound only by imports of external modules. A receiver `X` counts as
    the class `X` only when that file binds `X` to it: a class declaration or
    an un-aliased import that resolves to a module exporting class `X` (Java:
    the declaration or an exact single-type import), and nothing else in the
    file binds `X`. A module is external only when it is a `node:` builtin or
    a declared dependency (or under `node_modules`), not one of the project's
    packages, and no tsconfig `paths` / `baseUrl` or import map can map it
    into the project; an unreadable config makes nothing external. Two classes
    are provably unrelated only if neither is an interface, both ancestries
    resolve, neither is an ancestor of the other, and no project class has
    both in its ancestry (nor touches either through an unresolved one). A
    supertype resolves only when the file binds its name to that class (as
    above); an aliased import or re-export, `extends ns.Base`, a mixin call or
    an unknown name leave the ancestry unresolved;
  - `residual` with the reason, for everything else. Only residual items reach
    a human.
- **Classifier limits (by design conservative).** A target's class comes from
  its qual, which drops anonymous classes; a target declared inside an
  anonymous class body or object literal has no provable class, so member and
  `this` uses of it stay residual. Classes are matched by simple name (all
  same-named classes are unioned). A Java class used without an import (same
  package) is not a provable receiver.

## `run --scip`: measuring the opt-in SCIP evidence layer

`run --scip DIR` runs the head side with `TSA_SCIP_INDEX=DIR/<repo>.scip`; each
repo needs `<repo>.scip` and `<repo>.scip.manifest.json` (written by
`python -m tree_sitter_analyzer.mcp.tools.callers_scip_manifest` in a checkout
of the pinned commit, right after the indexer). Use it with the TS / JS repos
(`--repos hono zod axios --allow-partial`). Without `--scip`, nothing changes:
the same keys, rows and policy as before the option existed.

- The head query key includes a digest of the index and its manifest, and the
  head answers go to `results-scip/<tree>/<index-key>/<digest>/<run-id>/`, so
  `promote` never sees them. The base side is the ordinary cached baseline.
- Head rows keep the answer's `scip` report; it is never compared.
- The policy gains the additive SCIP rules (`policy.py`): callers may only be
  *added*, each with `confidence_tier: "scip"`, and the count grows by exactly
  those; site lists may only shrink (a non-call reference list may appear where
  the base never ran that gate); `excluded_by_reason` may only gain
  `SCIP_RESOLVED_OTHER`; `unknown->incomplete` is allowed when SCIP added a
  caller. Losing `complete` stays a violation. Every oracle runs unchanged on
  every new or changed `complete`.
- A repo on which any head row reports `scip.status` other than `used` is an
  ERROR: a run in which the index was ignored proves nothing.
- `report.md` gains a "SCIP evidence" table (status, target mapping, site
  outcomes, added callers, rows with unlisted references or disagreements) and
  lists every new `complete`.

Building the indexes (TS: the project's `node_modules`; JS: an `allowJs`
tsconfig kept outside the checkout, passed as the project with `--cwd`):

```powershell
npx -y @sourcegraph/scip-typescript@0.6.1 index --output <dir>\hono.scip . adapters/aws-lambda ...
npx -y @sourcegraph/scip-typescript@0.6.1 index --cwd <axios checkout> --output <dir>\axios.scip <outside>\tsconfig.json
py -3 -m tree_sitter_analyzer.mcp.tools.callers_scip_manifest --project <checkout> --index <dir>\hono.scip
```

## Trust model

**What a PASS (exit 0) guarantees**, for the 2,457 corpus targets of the 7
pinned repos, under the gate interpreter:

- every head answer was computed by exactly the head code (the server refuses
  any other package) on an index built by exactly the head code, and every
  cached answer it was compared with matches its tree, index key, repo, pin,
  query and row digest;
- no answer changed in a way the policy forbids, against the base code on the
  head index and, when the PR touches indexed code, against the base code on
  its own index;
- every head `complete` that differs from a base answer: lists every GT2
  caller (Python) and labelled call (hono, zod), and every grep occurrence of
  its bare name in the repo is provably not an unlisted caller (TS/JS/Java),
  under the classifier rules above;
- every head compact `complete` is confirmed by the full answer, caller for
  caller.

**What it does not guarantee:**

- correctness outside the corpus, or of a head `complete` identical to the
  reference base (those are the baseline's own state; GT2 / label findings on
  them are listed as pre-existing);
- Python callers GT2 itself does not know (GT2 is a static approximation;
  its open sites are surfaced as residual items, not proven);
- calls the grep oracle cannot see: dynamic dispatch by computed name
  (`obj[name]()`), `eval`, reflection, or a binding through code generation;
  a string literal equal to the name is residual, but a name built at run
  time is not visible;
- anything the classifier rules prove wrongly: they are deliberately
  conservative (an unresolved case is residual), but they are code, and the
  unit tests in `tests/unit/callers_gate/` are their specification;
- behaviour under other interpreters, other dependency versions, or with the
  query-time disk memos enabled (gate servers run with `TSA_EVIDENCE_STORE=off`
  and `graph-memo` blocked, see below), or with a parallel index build;
- a REVIEW (exit 3) is not a pass: one residual item judged "MISSED CALLER"
  means the new `complete` is wrong.

**Isolation assumptions the guarantees rest on**, each enforced:

- *Base and head do not share query-time state.* TSA keys its disk memos by
  `source_fingerprint` (path + size + mtime of the package's `.py` files).
  `git archive` stamps every file with the current second, so two trees of
  equal file sizes extracted in one second used to collide. Now snapshots get
  mtimes derived from their tree hash, servers run with
  `TSA_EVIDENCE_STORE=off`, and the index's `.ast-cache/graph-memo` is a
  regular file, which TSA treats as "no memo" (`index_store.block_query_memos`).
- *The index key covers everything that shapes the index.* The query-only
  exclusion (`mcp/tools/callers_*.py`) is audited after every build; the build
  runs in one process (`TSA_INDEX_WORKERS=1`) so the audit sees every import,
  and a child interpreter started during the build fails it.
- *Every cache fails closed* (Invalidation rules above).

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
