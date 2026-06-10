---
name: tsa-health-watch
version: 2.0.0
description: |
  Project & file health grading + dead-code detection + watch-daemon for grade
  drops. Answer "how healthy is this codebase", "what's rotting", "which files
  need attention", "alert me when something degrades" in one workflow.

  Use when:
  - Triaging a codebase: "what should we clean up first?"
  - Pre-PR check: "did this change make health worse?"
  - User asks "any dead code?" / "any rotting hot spots?"
  - Starting long-running session, want auto-alerts on degradation
  - Project-wide quality reporting

  Replaces: 5-10 grep/read calls + manual heuristics + spreadsheet (~20k
  tokens) with 2-3 MCP calls (~2k tokens).
allowed-tools:
  - mcp__tree-sitter-analyzer__health
  - mcp__tree-sitter-analyzer__project
  - Bash
  - Read
---

# tsa-health-watch — Project + file health in one pass

> Grades files A→F across 6 dimensions (complexity, structure, dependencies,
> duplication, size, git-hotspot). Daemon mode alerts on grade drops live.

## When to use

| Goal                            | Tool                                  |
|---------------------------------|---------------------------------------|
| Project portrait + worst files  | `health action=project`               |
| One-file deep dive              | `health action=file`                  |
| Top hubs + sensory neurons      | `health action=overview`              |
| Find dead functions             | `health action=dead`                  |
| Complexity hotspots (visualize) | `health action=heatmap`               |
| Watch & alert on degradation    | `--watch-health` CLI (Bash)           |

## Procedure

### One-shot triage (cold-start health audit)

Fan out in one message:

1. `health action=project` with `max_files: 20` — grade distribution + worst-20
2. `health action=dead` with `limit: 50` — pruning candidates
3. `health action=overview` — hub functions + entry points + 0-degree leaves

Read the verdict. If `D/F` files exist in worst-20, drill into each with
`health action=file` to get the per-dimension breakdown + recommendation.

### Single-file investigation

```
health action=file file_path="<path>"
```

Returns:
- `grade`: A | B | C | D | F (overall)
- `dimensions`: {complexity, structure, dependencies, duplication, size, git_hotspot}
- `weakest_dimension`: which one dragged grade down
- `signal`: healthy | moderate_depth | high_complexity | etc.
- `recommendation`: next concrete action

### Long-running watch (daemon mode, T4)

Run in a separate terminal:

```bash
uv run tree-sitter-analyzer --watch-health \
  --threshold-grade C \
  --watch-interval 60 \
  --notify-channel stdout,file \
  --notify-file .tree-sitter-cache/health-events.jsonl \
  --on-degradation 'echo "ALERT: {file} {previous_grade}→{grade} ({recommendation})"'
```

Daemon fires alerts when:
- A file's grade gets strictly worse (B→C), OR
- A file crosses below `--threshold-grade` (B→D when threshold=C)

History persists in `.ast-cache/health_scores.db` table `health_score_history`.

## Reading grades

Grade letters use **A=best, F=worst** ordering. Score ranges:
- A: 90-100 — healthy, no immediate action
- B: 80-89 — acceptable, minor smell
- C: 70-79 — review recommended
- D: 60-69 — refactor candidate
- F: <60 — high priority refactor

Weakest dimension tells you *why*:
- `complexity` → split functions
- `structure` → too many globals, missing types
- `dependencies` → too many imports / circular
- `duplication` → DRY opportunity
- `size` → split file
- `git_hotspot` → modified too often, churn risk

## CLI equivalents

```bash
uv run tree-sitter-analyzer --project-health --output-format toon
uv run tree-sitter-analyzer <file> --file-health --output-format toon
uv run tree-sitter-analyzer --overview --output-format toon
uv run tree-sitter-analyzer --dead-code --output-format toon
uv run tree-sitter-analyzer --watch-health --threshold-grade C  # daemon
```

## Anti-patterns

- Don't grade individual files when the question is "which 10 are worst" —
  use `health action=project` once instead of N file-health calls.
- Don't ignore `dimensions` and just look at the grade letter — the
  recommendation lives in the weakest dimension.
- Don't use `--watch-health` for one-shot checks — it's a long-running daemon.

## Decision surface

```yaml
project (when health action=project):
  grade_distribution: {A: n, B: n, C: n, D: n, F: n}
  worst_files: [{path, grade, score, weakest_dimension}, ...]

file (when health action=file):
  grade: A | B | C | D | F
  score: 0-100
  signal: healthy | moderate_depth | ...
  weakest_dimension: <name>
  dimensions: {complexity: 0-100, structure: 0-100, ...}
  recommendation: <next concrete action>
```
