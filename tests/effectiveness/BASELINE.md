# RFC-0017 Phase 1 — Mutation Baseline

**Date**: 2026-06-14
**Tool**: mutmut 3.6.0
**Runner**: macOS (arm64, Python 3.14.3)
**Config**: `[tool.mutmut]` in `pyproject.toml`; per-mutant test selection narrows to module-specific tests
**Run command (per module)**: see `scripts/run_mutation_baseline.py`

> This file records the **curated baseline** from the first phase-1 run.
> Per-run cache files (`.mutmut-cache`, `mutants/`) are NOT committed — see `.gitignore`.
> Refresh this file deliberately (not on every CI run) when the baseline improves.

---

## Results: all 5 RFC-0017 core modules measured

| Module | Total mutants | Killed | Survived | No-test | Score | Surviving = bugs suite misses |
|---|---|---|---|---|---|---|
| `ast_diff.py` | 580 | 342 | **238** | 0 | **59.0%** | 238 deliberate bugs the suite does not catch |
| `semantic_change_classifier.py` | 314 | 243 | **71** | 0 | **77.4%** | 71 deliberate bugs the suite does not catch |
| `mcp/tools/facade_tool.py` | 269 | 189 | **65** | 15 | **70.3%** | 65 deliberate bugs the suite does not catch |
| `mcp/tools/query_symbol_search.py` | 767 | 285 | **360** | 122 | **37.2%** | 360 deliberate bugs the suite does not catch |
| `formatters/toon_encoder.py` | 464 | 141 | **140** | 183 | **30.4%** | 140 deliberate bugs the suite does not catch |
| **TOTAL (5 modules)** | **2 394** | **1 200** | **874** | 320 | **50.1%** | **874 surviving mutants = 874 deliberate bugs the current suite cannot catch** |

**Headline (RFC-0017 deliverable):** 874 surviving mutants across 5 core modules.
The suite is ~2× the size of the source, yet 874 deliberate bugs escape it.
This is the quantified answer to "why does 2× test volume not catch bugs?":
the suite tests *conformance* (does code match spec?), not *value* (is the spec correct/good?).

---

## Interpretation per module

### `ast_diff.py` — 238 surviving / 59.0%

The highest absolute surviving count. The `_diff_matched_nodes`, `_sig_diff`, and
`diff_strings`/`diff_files` method bodies have the most survivors. Tests check that
hunks are produced and classify correctly; they do not assert on fine-grained field
values within hunks (which fields changed, by exactly how much, etc.). This module
produced the real defect that triggered the RFC: 155 KB output for a small diff —
the output-size invariant was missing.

### `semantic_change_classifier.py` — 71 surviving / 77.4%

Best score of the five. The classifier has property-based test coverage (Hypothesis)
which kills mutants that purely structural tests would not. Still 71 surviving; most
are in edge-case branches and the scoring arithmetic.

### `mcp/tools/facade_tool.py` — 65 surviving / 70.3%

15 mutants had no test associations (untouched code paths in targeted test set).
65 survive: the routing logic, the action-dispatch switch, and optional-parameter
handling are under-asserted. Tests confirm the facade routes and returns something;
they do not pin the dispatch invariants.

### `mcp/tools/query_symbol_search.py` — 360 surviving / 37.2%

Worst score. 122 mutants had no test associations — large uncovered surface in the
targeted test set. The 360 survivors concentrate in SQL-building helpers and result
post-processing. Tests assert on result shape (keys present), not on values or SQL
correctness.

### `formatters/toon_encoder.py` — 140 surviving / 30.4%

183 "no-test" mutants: the targeted test set (`test_output_cost_invariants.py`,
`test_toon_compact_only.py`, `test_toon_losslessness_637.py`) does not exercise
many encoder branches. The 140 survivors are in low-level formatting helpers.
The cost-invariant test is the only value test here; it kills the most mutants
per test line in the targeted set.

---

## Mutation score emoji legend (from mutmut progress output)

- 🎉 = killed (test caught the bug)
- 🫥 = survived (test missed the bug) — THE NUMBER
- ⏰ = timeout
- 🙁 = killed by another exit code (still killed)
- 🔇 = no tests
- 🧙 = caught by type checker

---

## Notes on "no-test" mutants

Exit code 33 from mutmut means the targeted test set has no association with
that mutant's function. This is a real signal: it means those code paths have
**zero targeted test coverage**. For `toon_encoder.py` (183 no-test / 40%) and
`query_symbol_search.py` (122 no-test / 16%), expanding the targeted test set
would likely reveal additional survivors.

---

## How to re-run

```bash
# Per-module run (see scripts/run_mutation_baseline.py):
uv run python scripts/run_mutation_baseline.py ast_diff
uv run python scripts/run_mutation_baseline.py semantic_change_classifier
uv run python scripts/run_mutation_baseline.py facade_tool
uv run python scripts/run_mutation_baseline.py query_symbol_search
uv run python scripts/run_mutation_baseline.py toon_encoder

# Or use the CI workflow (ubuntu-latest only; mutmut needs os.fork):
# .github/workflows/mutation-baseline.yml (manual trigger / on-label)
```

---

## Phase-2 plan (separate PR)

Once the ratchet is configured, a PR may not lower any module's mutation score.
Surviving mutants are triaged: kill (add the missing assertion) or annotate
(equivalent mutant, document why behavior-preserving). The `query_symbol_search.py`
score (37.2%) and `toon_encoder.py` score (30.4%) are the highest-priority targets.
