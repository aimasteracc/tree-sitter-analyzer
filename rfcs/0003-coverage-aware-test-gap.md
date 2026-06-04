# RFC-0003: Coverage-aware test-gap analysis

- **Status**: draft
- **Author(s)**: @aimasteracc
- **Created**: 2026-06-04
- **Last updated**: 2026-06-04
- **Tracking issue**: TBD
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/test_gap_analyzer.py`
  - `tree_sitter_analyzer/mcp/tools/test_gap_tool.py`
  - `tree_sitter_analyzer/mcp/tools/health_facade.py` (wire the orphaned tool in)
  - `tree_sitter_analyzer/cli/` (add the parity flag)
  - `tests/unit/test_test_gap_analyzer.py`, `tests/unit/test_test_gap_tool.py`

## Summary

TSA's test-gap analysis currently decides "is this symbol tested?" by **naming
convention** (`test_foo` ⇒ assume `foo` is tested). This is imprecise in both
directions. This RFC makes test-gap analysis **consume `coverage.json`** (the
artifact `coverage.py` already produces, and that TSA already reads in
`scripts/check_patch_coverage.py`) as the ground-truth data source when
available, falling back to the naming heuristic when it is not — and layers
TSA's unique static-graph value on top (who-should-test-this, change impact,
complexity-ranked priority, why-it's-missing). It does **not** reimplement
runtime tracing; TSA stays a static tool that *consumes* dynamic data.

As a prerequisite, it also wires `CodeGraphTestGapTool` into the `health`
facade + a CLI flag — today the tool exists and is tested but is reachable from
no facade and no CLI flag (an orphan left by the Wave-C facade cutover).

## Motivation

`test_gap_analyzer.py:8` states its method: *"Match test symbols to production
symbols by naming convention."* `_extract_test_targets` strips prefixes
(`test_`, `should_`, `it_`, `given_`) and matches by name. This produces
**two-way errors**:

- **False negatives (real gaps reported)**: `foo` exercised only by
  `test_workflow` (not named `test_foo`) reads as untested.
- **False positives (gaps hidden)**: a `test_foo` that asserts nothing (the
  pass-stub / swallow-exception fakes removed in PRs #281–#283) makes `foo`
  read as tested when it is not.

We have now spent **three dogfood rounds** manually applying the workaround:
*static finds candidates → `pytest-cov` confirms which are real*. A concrete
example from this work: `_markdown_formatter_rendering.py` was flagged with 20
"untested" functions by the static view yet has **100% line coverage** (covered
indirectly via dispatch the static view can't see). The manual pipeline should
be **built into the tool**.

`coverage.py` is precise because it does **runtime tracing** (`sys.monitoring`
/ `settrace` records every executed line). A purely static tool *cannot* match
that — indirect dispatch, reflection, and dynamic calls are only knowable at
run time. That is a paradigm boundary, not a TSA implementation gap. The
correct move is therefore to **stand on `coverage.py`'s shoulders** (consume
its JSON) and add what it cannot give: the call/ownership graph around each gap.

## Detailed design

### Data structures

`CoverageGapResult` gains a provenance field so callers (and agents) know how
trustworthy the verdict is:

```python
@dataclass
class CoverageGapResult:
    # ... existing fields ...
    coverage_pct: float
    source: str  # "coverage" (line-precise, from coverage.json) | "naming" (heuristic fallback)
    coverage_json_path: str | None  # which file was consumed, for transparency
```

Each reported gap gains, when `source == "coverage"`, the line-level truth:

```python
@dataclass
class ProductionSymbol:
    # ... existing fields ...
    covered_lines: int | None      # executed lines in the symbol's range (coverage source only)
    total_lines: int | None
    is_tested: bool                # coverage: any executed line in range; naming: prefix match
```

### Algorithms

Resolution order for "is symbol S tested?":

1. **coverage source** (preferred): if a `coverage.json` is found (explicit
   arg → `coverage.json` in project root → `.coverage` via `coverage.py` API),
   a symbol is *tested* iff ≥1 **body** line in its range is marked executed —
   **excluding the declaration lines** (the `def`/`class` line and any decorator
   lines).

   > **Why exclude declaration lines (Codex P1 on #284):** coverage.py records
   > the `def`/`class` *statement* line as executed on mere **import**. If we
   > counted any executed line in `[start_line, end_line]`, a function that is
   > imported but whose body is never called would read as *tested* — hiding
   > exactly the fake / missing tests this RFC exists to expose. So a symbol is
   > covered only when an executed line lies strictly inside its body. For
   > Python, body lines = the symbol's range minus the signature/decorator span
   > (derivable from the AST node already extracted by the parser). A symbol
   > with **only** its `def` line executed is a GAP, not covered.

   This is line-precise and immune to both fake-test and indirect-dispatch
   errors.
2. **naming fallback** (current behavior): when no coverage data is present,
   keep the prefix-matching heuristic, but stamp `source="naming"` so the
   result is clearly labeled lower-confidence.

The static graph then **enriches** every gap regardless of source — this is
TSA's differentiator over raw `coverage.py`:

- **who-should-test-it**: existing test files that already import the symbol's
  module (from the call/import graph).
- **change impact**: `blast_radius` of the untested symbol (files affected if
  it changes untested).
- **priority**: cyclomatic complexity × impact (already partly present).
- **why-missing**: nearest tested caller in the call chain.

### MCP surface (facade + action)

`health` facade gains action `test_gap` routing to `CodeGraphTestGapTool`:

```
health(action="test_gap", mode="gaps"|"summary"|"file",
       file_path=?, coverage_json=?, language_filter=?, max_gaps=?)
```

`coverage_json` is an optional explicit path; default is auto-discovery.

### Error handling

- Malformed / stale `coverage.json` → log a warning, fall back to naming with
  `source="naming"` (never hard-fail the analysis).
- `coverage.json` referencing files that no longer exist → skip those entries.

### Concurrency / async

No new concurrency. Reading `coverage.json` is a one-shot synchronous load
before the existing analysis loop.

## Three-Surface impact (CLI ↔ MCP parity)

TSA holds a hard CLI↔MCP parity rule. This RFC ADDS a surface that is currently
missing on both sides (the tool is an orphan):

- **MCP**: `health` facade, `action="test_gap"`.
- **CLI**: `--test-gap [gaps|summary|file]` with `--test-gap-file`,
  `--coverage-json`.

They stay 1:1. Output defaults follow the locked decision: MCP → TOON, CLI →
JSON (CLAUDE.md "MCP defaults to TOON; CLI defaults to JSON"). The new
`source` / coverage fields appear identically in both surfaces.

## Drawbacks

- **Requires the user to have run `pytest-cov` first** for the precise path.
  Mitigated by graceful fallback to naming (clearly labeled).
- Coverage data can be **stale** (generated before a refactor). Mitigated by
  the `source` + `coverage_json_path` transparency fields; callers can re-run.
- Adds a dependency direction: test-gap now optionally reads a coverage
  artifact. It does **not** add `coverage` as an import-time dependency — the
  JSON is read with stdlib `json`.

## Alternatives

- **Reimplement runtime tracing inside TSA** — Pros: self-contained. Cons:
  duplicates `coverage.py`, requires running the target's test suite (abandons
  TSA's "never run the code" static identity), huge maintenance surface.
  **Rejected**: wrong layer; we'd become a worse second coverage.py.
- **Only improve the static heuristic** (resolve more indirect calls) — Pros:
  stays purely static. Cons: indirect dispatch / reflection are provably not
  statically decidable; there is a hard ceiling (~the false positives this RFC
  exists to fix). **Rejected as a complete fix**, but kept as the fallback.
- **Leave it naming-only, document the caveat** — Cons: ships a "find untested
  code" feature that is wrong often enough to mislead agents. **Rejected.**

## Prior art

- **coverage.py** (7.x): `sys.monitoring` (3.12+) / C-tracer line tracing →
  `coverage.json`. We *consume* its output, not its mechanism.
- **codegraph / Sourcegraph**: no test-coverage notion — TSA's graph-enriched
  gap view is novel relative to them (and to coverage.py, which has no graph).
- **TSA `scripts/check_patch_coverage.py`**: already parses `coverage.json` for
  patch-coverage gating — proves the consumption pattern works in-repo; this
  RFC reuses that parsing approach for the analysis tool.

## Test plan (RED-first)

The failing tests this RFC will be implemented against:

- **unit (coverage source)**: given a fixture `coverage.json` marking `foo`'s
  lines executed and `bar`'s not, `analyze_coverage_gaps(..., coverage_json=...)`
  returns `bar` as a gap, `foo` as covered, `source=="coverage"`.
- **unit (fake-test immunity)**: a `test_foo` that asserts nothing + no
  coverage for `foo` ⇒ `foo` reported as a gap under coverage source (proving
  the fix over naming, which would hide it).
- **unit (indirect-dispatch immunity)**: a symbol covered only indirectly (no
  `test_<name>`) but executed in coverage ⇒ NOT a gap under coverage source.
- **unit (declaration-line immunity, Codex P1)**: a symbol whose ONLY executed
  line is its `def`/`class` declaration (imported, body never run) ⇒ reported
  as a GAP, not covered. Guards against import-time def-line execution masking
  untested bodies.
- **unit (fallback)**: no coverage.json ⇒ `source=="naming"`, current behavior
  preserved.
- **unit (graceful degradation)**: malformed coverage.json ⇒ warning +
  `source=="naming"`, no exception.
- **parity**: `tests/unit/test_agent_contracts.py` — `health` action
  `test_gap` ↔ `--test-gap` flag present and 1:1.
- **dogfood**: run on TSA itself with a real `coverage.json`; confirm the
  `_markdown_formatter_rendering.py` false-positive (20 fake gaps) disappears.

## Acceptance criteria

- [ ] `analyze_coverage_gaps` accepts `coverage_json` and prefers it as ground truth
- [ ] Coverage verdict requires an executed **body** line (declaration/decorator lines excluded) — Codex P1
- [ ] `CoverageGapResult.source` distinguishes `"coverage"` vs `"naming"`
- [ ] Auto-discovery of `coverage.json` (project root) + explicit override
- [ ] Graceful fallback to naming on missing/malformed coverage data
- [ ] Static-graph enrichment (who-tests / impact / priority) attached to gaps
- [ ] `CodeGraphTestGapTool` wired into the `health` facade (`action="test_gap"`)
- [ ] CLI `--test-gap` flag added
- [ ] CLI↔MCP parity test green
- [ ] dogfood: false-positive `_markdown_formatter_rendering` gaps gone with coverage source
- [ ] Docs/CODEMAPS updated

## What this RFC does NOT do (deferred)

- **Does not** implement runtime tracing / run the user's test suite.
- **Does not** change `coverage.py` config or how coverage is generated.
- **Does not** add branch-coverage gap analysis (line coverage only for v1).
- **Does not** auto-run `pytest-cov` — the user/CI produces `coverage.json`.

## Open questions

1. Auto-discovery precedence: explicit arg → `coverage.json` → `.coverage`
   (binary, via `coverage` API) — do we want the binary `.coverage` path in v1,
   or JSON-only to avoid an import-time `coverage` dependency? (Leaning
   JSON-only.)
2. Staleness policy: should we warn when `coverage.json` mtime predates the
   newest source file, or stay silent and just expose `coverage_json_path`?
3. Should `source` surface as a verdict badge in the agent summary line so
   agents weight the result appropriately?
