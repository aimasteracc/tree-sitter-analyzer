# CodeGraph Comparison Benchmark

## NO1-001A Gin Smoke qualification

The model-free qualification adapter proves that the fixed native,
tree-sitter-analyzer, and CodeGraph cells can be isolated and replayed. It
does not run an index, backend, or model and can only emit E0 evidence:

```bash
RECEIPT=$(python -m benchmarks.codegraph_compare.gin_smoke create /tmp/gin-smoke \
  --benchmark-git-sha "$(git rev-parse HEAD)" \
  --repository-path /fixture/gin \
  --repository-commit 0123456789abcdef0123456789abcdef01234567 \
  --repository-fingerprint 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef \
  --question "Where is the Gin router assembled?" \
  --model fixture-model --timeout-seconds 60)
DIGEST=$(printf '%s' "$RECEIPT" | jq -r .bundle_digest)
python -m benchmarks.codegraph_compare.gin_smoke validate /tmp/gin-smoke \
  --expected-git-sha "$(git rev-parse HEAD)" --expected-bundle-digest "$DIGEST"
python -m benchmarks.codegraph_compare.gin_smoke replay \
  /tmp/gin-smoke /tmp/gin-smoke-replay \
  --expected-git-sha "$(git rev-parse HEAD)" --expected-bundle-digest "$DIGEST"
```

Validation requires a trusted Git SHA supplied outside the bundle. Any
checksum change, missing or mixed cell, namespace collision, tool leakage,
oracle material, selective retry, or claim above E0 invalidates the bundle.

Measures answer quality, token cost, and latency across three code-intelligence approaches on real open-source repositories:

| Arm | Tool(s) | Index |
|-----|---------|-------|
| `native-only` | grep + file reads | none |
| `codegraph-warm` | CodeGraph MCP | pre-built |
| `codegraph-cold` | CodeGraph MCP | built at query time |
| `tsa-warm` | tree-sitter-analyzer | pre-built |
| `tsa-cold` | tree-sitter-analyzer | built at query time |

---

## Directory Structure

```
benchmarks/codegraph_compare/
├── README.md           — this file
├── schemas.py          — Pydantic v2 dataclasses (RunRecord, EvalRecord, …)
├── repos.yaml          — 7 pinned repositories
├── arms.yaml           — 5 treatment arms
├── adapters/           — one adapter module per tool
├── prompts/            — question bank (QuestionSpec YAML files per repo)
├── repo_prep.py        — clone + pin + index build script
└── results/            — run records, eval records, transcripts
```

---

## Quick Start

```bash
# 1. Prepare repos (clone at pinned SHA, optionally pre-build indexes)
uv run python benchmarks/codegraph_compare/run.py prepare --all

# 2. Run a Codex-backed smoke without spending model quota
uv run python benchmarks/codegraph_compare/run.py phase smoke \
    --agent-backend codex \
    --dry-run

# 3. Run a real Codex-backed smoke
uv run python benchmarks/codegraph_compare/run.py run-matrix \
    --repos gin \
    --arms native-only,tsa-warm,codegraph-warm \
    --question-limit 1 \
    --repeats 1 \
    --agent-backend codex \
    --model <exact-model-id> \
    --timeout-seconds 1200 \
    --manifest <frozen-manifest.json> \
    --index-evidence <validated-index-evidence.json>

# 4. Evaluate answers (LLM judge, writes EvalRecord JSONL)
uv run python benchmarks/codegraph_compare/evaluate.py \
    --runs results/runs.jsonl --out results/evals.jsonl

# 5. Print summary table
uv run python benchmarks/codegraph_compare/analyze.py \
    --runs results/runs.jsonl --evals results/evals.jsonl \
    --fail-on-gate
```

Use `--agent-backend claude` to reproduce the original Claude Code arm, or
`--agent-backend codex` to spend Codex quota through `codex exec --json`.
Run IDs include the backend name so Claude and Codex results never overwrite
each other.

Manifest-backed execution first consumes the strict setup evidence without a
model call, then follows `expected_cells` in manifest order. Each terminal
attempt is written under `results/experiments/<manifest-hash>/runs.jsonl` as a
V1 record and receives a mechanical transcript-policy audit. The older
unmanifested `phase smoke` path remains available only for historical harness
compatibility and cannot establish RFC-0021 evidence.

Codex records include `cached_input_tokens` and `reasoning_output_tokens` when
the CLI reports them. These are stored separately because Codex reports them as
detail counters already covered by the top-level input/output totals, while
Claude reports cache counters outside `input_tokens`.

---

## Fairness Rules

These rules are enforced by the harness. Violating any of them invalidates a run.

1. **Pinned commits** — all repos use a fixed SHA from `repos.yaml`; no `HEAD`-tracking.
2. **Same model for all arms** — the selected model ID is applied uniformly within an agent backend.
3. **Identical question text** — each arm receives the exact same `prompt` string from `QuestionSpec`.
4. **Minimum 4 repeats** — the pilot and full phases require `--repeats 4` or higher; the summary drops any arm with fewer.
5. **Report median, not best** — `overall`, `elapsed_seconds`, and `total_tokens` are summarized as median across repeats.
6. **Cold and warm reported separately** — arms with `index_mode: cold` are never averaged with `index_mode: warm`; they form separate columns in the summary table.
7. **Index build time excluded from warm query time** — `elapsed_seconds` in a warm run begins after the index is confirmed ready.
8. **Flag low-quality answers** — any run with `EvalRecord.overall < 2.5` is marked `LOW_QUALITY` in the report even if it was token-efficient.
9. **Auto-penalize phantom citations** — citations to files that do not exist in the pinned repo reduce `citation_quality` automatically before human/LLM review.
10. **No silent drops** — timeouts and exceptions are recorded as `RunRecord` entries with `error` set; they appear in the report as `FAILED` rather than being omitted.

Claude runs use hard CLI tool allowlists. Codex runs ignore the user's global
configuration and inject exactly one required MCP server for each indexed arm,
with an explicit MCP tool allowlist; native-only injects no MCP server. Codex
native-only runs use a read-only sandbox. Codex indexed arms use a
workspace-write sandbox because CodeGraph and TSA query paths may update SQLite
WAL/cache metadata during otherwise read-only queries. CodeGraph's Codex MCP
server is pinned to `@colbymchenry/codegraph@1.5.0`.

---

## Warm vs Cold Index

| | Warm | Cold |
|-|------|------|
| Index state at query time | Already built and on disk | Built from scratch during the timed run |
| What is measured | Query latency and quality only | Full end-to-end cost including index construction |
| Indexed build time in report | Separate `IndexStats` record | Included in `elapsed_seconds` |
| Realistic scenario | Persistent dev environment | Fresh CI checkout or first-run |

---

## Phase Execution Order

Run phases in order. Each phase gates the next.

```
smoke    →  1 repo, 1 question, 1 repeat, all arms
             Goal: verify adapters run without errors

pilot    →  1 repo, all questions, 4 repeats, all arms
             Goal: catch quality regressions before full compute spend

full-warm →  all 7 repos, all questions, 4 repeats, warm arms only
             Goal: primary quality + token comparison

cold     →  all 7 repos, all questions, 4 repeats, cold arms only
             Goal: measure index-build overhead
```

Stop and investigate if any arm has a `FAILED` rate above 5 % in smoke or pilot.
The `phase` subcommand applies these defaults directly:

```bash
uv run python benchmarks/codegraph_compare/run.py phase smoke --agent-backend codex
uv run python benchmarks/codegraph_compare/run.py phase pilot --agent-backend codex
uv run python benchmarks/codegraph_compare/run.py phase full-warm --agent-backend codex
uv run python benchmarks/codegraph_compare/run.py phase cold --agent-backend codex
```

---

## Reading the Summary Table

```
repo         question_id          arm              med_overall  med_tokens  med_elapsed_s  fail_rate
----------   ------------------   --------------   -----------  ----------  -------------  ---------
django       call-chain-orm-001   native-only            3.2      14 200          18.4       0 %
django       call-chain-orm-001   codegraph-warm         4.1       6 100           4.2       0 %
django       call-chain-orm-001   tsa-warm               3.9       7 800           5.1       0 %
```

Column meanings:

- `med_overall` — median `EvalRecord.overall` (1–5 scale, 5 = best)
- `med_tokens` — median `RunRecord.total_tokens`
- `med_elapsed_s` — median wall-clock seconds (index build excluded for warm arms)
- `fail_rate` — percentage of repeats with `error` set or `overall < 2.5`

A result is considered **dominant** if it scores higher on `med_overall` AND lower on `med_tokens` than the next-best arm. Neither dimension alone is sufficient.
