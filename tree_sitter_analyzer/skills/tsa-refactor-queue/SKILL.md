---
name: tsa-refactor-queue
version: 2.0.0
description: |
  Build a top-N prioritized refactoring queue by intersecting three signals:
  health grade (which files are F/D), temporal churn (which files change
  most often), and dead-code density (which files carry the most unreachable
  symbols). For each candidate the queue surfaces (a) the dimension that
  dragged the grade down, (b) the target symbol, (c) blast radius from
  `nav action=callers`, and (d) a concrete action — `split`, `delete dead`,
  or `extract`.

  Motivated by `docs/agent-tooling-gap-report.md` "Next High-Value Work" §5:
  use `health action=project` output to open focused refactoring slices for
  the current F-grade files, starting with low-coverage Language Plugin
  extractors and `api.py`.

  Use when:
  - "Where should I refactor next?" / "Build me a refactor queue"
  - Post-feature cleanup pass
  - Engineering planning: "what would 2 weeks of cleanup buy us?"
  - Re-grading after a sprint: "did the queue shrink?"

  Replaces: per-file `health action=file` loops + spreadsheet ranking
  (~25k tokens) with 3 parallel MCP calls + a deterministic rank
  (~3k tokens).
allowed-tools:
  - mcp__tree-sitter-analyzer__health
  - mcp__tree-sitter-analyzer__nav
  - mcp__tree-sitter-analyzer__structure
  - mcp__tree-sitter-analyzer__edit
  - Bash
  - Read
---

# tsa-refactor-queue — Top-N prioritized refactor slices

> Three signals, one ranked list. Health × churn × dead-code → the five files
> you'd refactor first if you had a week. Each row carries a target symbol, a
> blast radius, and a concrete action.

## When to use

- "What should we refactor next?" — daily/weekly engineering triage
- Post-feature cleanup pass — find rot that accumulated while shipping
- Pre-sprint planning — turn "we should clean up" into 5 concrete tickets
- After a CI grade-drop alert from `tsa-health-watch` — re-rank with churn

**Don't use** when:
- You already know the file (one-file deep dive → `health action=file` or `tsa-edit-safety`)
- The codebase is brand-new (<2 weeks of git history) — churn signal is noise
- You want to optimize one hot function — use `tsa-graph` + `edit action=refactor` directly
- Shallow clone in CI — `git_state=shallow` makes mod_count_30d unreliable

## Procedure

### Step 1 — Single fan-out (parallel, 3 MCP calls)

Call these in ONE message:

1. `health action=project` with `min_grade: "D"` and `max_files: 20` — F/D files + per-file `weakest_dimension`
2. `health action=dead` with `limit: 200` — symbol-level dead candidates, grouped by file
3. `health action=heatmap` with `top_n: 20` — complexity-weighted file list (covers structural smell)

The three responses overlap on file path. Joining on `file_path` gives a
3-signal table per candidate.

### Step 2 — Score and rank (deterministic, no LLM needed)

For each file that appears in `health action=project worst_files`, compute:

```
priority = (1 - health_score/100)            # how bad is the grade
         * log(1 + mod_count_30d_for_file)   # how hot is the file
         * (dead_symbol_count / total_symbols + 0.1)
```

Where:
- `health_score` ∈ [0,100] from `health action=project` (lower → worse → bigger weight)
- `mod_count_30d_for_file` = sum of `mod_count_30d` across the file's symbols
  (read from `ast_symbol_activation` — see tsa-temporal). `log(1+x)` damps
  pathological churn so a single 50× file doesn't dominate.
- `dead_symbol_count / total_symbols` = fraction of symbols `health action=dead`
  flagged. The `+ 0.1` floor ensures non-dead files can still rank if churn+grade
  alone justify it.

Sort descending, keep top 5.

### Step 3 — Enrich top 5 with target symbol + blast radius

For each of the top 5 files, fan out one more parallel batch:

```yaml
# For each candidate file:
structure action=analyze file_path=<f> format_type="compact"
  → list of symbols + complexity + line ranges → pick worst symbol
nav action=callers function_name=<worst_symbol> include_activation=true limit=50
  → blast_radius = len(callers) where callee_resolution in {local, project}
edit action=refactor file_path=<f>
  → action_hint: split | extract | delete | rename
```

### Step 4 — Emit the queue

For each row in the top 5, produce:

```yaml
- file: tree_sitter_analyzer/api.py
  rank: 1
  health_grade: F
  health_score: 42
  weakest_dimension: complexity        # from health action=project
  mod_count_30d: 18                     # summed from activation
  dead_symbols: 4 / 67                  # 6.0%
  target_symbol: api.analyze            # worst from structure action=analyze
  blast_radius: 23                      # local+project callers
  action: split                         # split → extract helpers; delete → prune dead; extract → DRY
  estimated_token_savings: ~8k          # rough: 0.5 * (dead_symbols * 200)
  verification_command: uv run pytest tests/unit/test_api.py -q
```

## Worked example — this very repo

Run on `/Users/aisheng.yu/git-private/tree-sitter-analyzer`:

```bash
# Parallel CLI batch (humans):
uv run tree-sitter-analyzer --project-health --max-files 20 --output-format json > /tmp/health.json
uv run tree-sitter-analyzer --dead-code --output-format json > /tmp/dead.json
sqlite3 .ast-cache/index.db "
  SELECT s.file_path, SUM(a.mod_count_30d) AS churn
  FROM ast_symbol_activation a
  JOIN ast_symbol_rows s ON s.id = a.symbol_id
  GROUP BY s.file_path ORDER BY churn DESC LIMIT 50" > /tmp/churn.tsv
```

Expected shape after joining (truncated, illustrative — actual numbers vary
with the working tree state — last fixture run on `feat/consolidated` produced
something like this for the top three rows):

```yaml
top_5_refactor_queue:
  - rank: 1
    file: tree_sitter_analyzer/api.py
    health_grade: F
    weakest_dimension: complexity
    mod_count_30d: 18
    dead_symbols: 3
    target_symbol: api.analyze
    blast_radius: 23
    action: split
    note: "called from CLI + MCP + tests — split into api_facade + api_core first"

  - rank: 2
    file: tree_sitter_analyzer/languages/python_plugin.py
    health_grade: F
    weakest_dimension: size
    mod_count_30d: 11
    dead_symbols: 7
    target_symbol: PythonElementExtractor.extract
    blast_radius: 6
    action: extract
    note: "650+ lines — gap report calls out Language Plugin extractors specifically"

  - rank: 3
    file: tree_sitter_analyzer/mcp/server.py
    health_grade: D
    weakest_dimension: dependencies
    mod_count_30d: 14
    dead_symbols: 1
    target_symbol: TreeSitterAnalyzerMCPServer._handle_call_tool
    blast_radius: 55  # every MCP tool routes through it
    action: split
    note: "hot zone (mod_count_30d ≥ 5) + high blast radius → solo PR, no bundling"
```

**Read the queue right:**
- Row 1 (api.py) matches the gap-report §5 callout — handle first.
- Row 2 (python_plugin.py) is a known "negative fixture" file (see CLAUDE.md
  "Test Fixture Files") — extracting helpers is OK but renaming risks breaking
  `test_python_detects_deep_nesting`. Run that test before/after.
- Row 3 (server.py) touches `BaseMCPTool` adjacency — solo commit, macOS gate
  check (see CLAUDE.md design-decision §2).

## Choosing the action per row

The `action` column should drive how you ticket the refactor:

| action  | when to pick                                | typical PR shape          |
|---------|---------------------------------------------|---------------------------|
| split   | `weakest_dimension ∈ {size, complexity}` and `blast_radius >= 5` | extract helpers, no public-API change |
| extract | `weakest_dimension = duplication` or repeated patterns across files | new shared util module |
| delete  | `dead_symbols / total_symbols > 15%` and `weakest_dimension != git_hotspot` | pure prune PR |
| rename  | only if `edit action=refactor` returns `rename_advised: true` AND blast_radius < 10 | tiny solo PR |

If two actions tie, prefer `delete` first — it's the cheapest, lowest-risk PR
and shrinks the next queue automatically.

## Anti-patterns

- DON'T act on the queue without re-checking each row with `tsa-edit-safety`
  before editing — the queue is *prioritization*, not a green light.
- DON'T bundle row 1 + row 3 in one PR if either touches `BaseMCPTool`,
  `PathResolver`, or `SecurityValidator` (CLAUDE.md "Foundational changes")
  — solo commits only.
- DON'T re-rank every turn — cache the queue in memory and only refresh
  after a commit that touches a file already in the queue, or weekly.
- DON'T trust the `mod_count_30d` column when `git_state=shallow` (CI). The
  CLI returns `git_state` per symbol — bail out of churn ranking and fall
  back to health-only ranking if any row in the top 20 is shallow.
- DON'T re-add `.md` files to the source set hoping for markdown smells — see
  CLAUDE.md design-decision §4. Build a separate `markdown_health` tool instead.

## CLI equivalents (if MCP unavailable)

```bash
# 1. Health portrait (defaults to D-and-worse)
uv run tree-sitter-analyzer --project-health --max-files 20 --output-format json

# 2. Dead-code candidates
uv run tree-sitter-analyzer --dead-code --output-format json

# 3. Complexity heatmap (covers the structural smell axis)
uv run tree-sitter-analyzer --overview --output-format json

# 4. Per-file churn (no dedicated --temporal flag yet — query DB directly)
sqlite3 .ast-cache/index.db "
  SELECT s.file_path, SUM(a.mod_count_30d) AS churn_30d
  FROM ast_symbol_activation a
  JOIN ast_symbol_rows s ON s.id = a.symbol_id
  WHERE a.git_state = 'tracked'
  GROUP BY s.file_path
  ORDER BY churn_30d DESC LIMIT 50"

# 5. Per-row enrichment (loop top 5)
uv run tree-sitter-analyzer <file> --outline --output-format json
uv run tree-sitter-analyzer --callers <SYMBOL> --output-format json
uv run tree-sitter-analyzer <file> --refactor --output-format json
```

The MCP-side ranking script (PRIORITY × log(churn+1) × dead_ratio) is
deterministic — implement it as a small Python helper if you run the CLI
flow repeatedly. Don't ask an LLM to do arithmetic over 20 rows.

## Decision surface returned

```yaml
verdict: INFO   # this skill is observational + prioritization, not a gate
queue_at: <iso-8601 timestamp>
queue_size: 5
top_5:
  - rank: 1..5
    file: <abs path>
    health_grade: A | B | C | D | F
    health_score: 0-100
    weakest_dimension: complexity | structure | dependencies | duplication | size | git_hotspot
    mod_count_30d: <int>           # 0 if git_state != tracked
    dead_symbols: <int>
    total_symbols: <int>
    target_symbol: <name>
    blast_radius: <int>            # local+project callers
    action: split | extract | delete | rename
    verification_command: <copy-paste exact pytest line>
    note: <one-line caveat>
provenance:
  health_call: health action=project{min_grade=D, max_files=20}
  dead_call: health action=dead{limit=200}
  churn_source: ast_symbol_activation  # see tsa-temporal
  git_state_seen: [tracked, ...]  # warn if "shallow" appears
```
