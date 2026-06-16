---
name: tsa-landing
version: 2.0.0
description: |
  Land in a new (or familiar) codebase using the tree-sitter-analyzer MCP server.
  One workflow → 6 decision surfaces (project_card / entry_points / recent_signals /
  health / top_files / agent_next_step) → ≤2k tokens, ≤3 MCP calls.

  Use when:
  - First time entering an unfamiliar repository
  - Returning to a repo after >1 week
  - User asks "what is this project?" / "where do I start?"

  Workflow: parallel-fan-out 3-4 MCP tools, fold output, return decision_surface.
  Replaces the typical 15k-token bootstrap (read README + ls -R + git log + AGENTS).
allowed-tools:
  - mcp__tree-sitter-analyzer__project
  - mcp__tree-sitter-analyzer__health
  - mcp__tree-sitter-analyzer__edit
  - Bash
  - Read
---

# tsa-landing — Land in any repo in <3s

> **First action on entering a new repo.** Replaces 6 separate bootstrap calls (~15k tokens) with 3-4 parallel calls (~2k tokens). 92% token saved.

## When to use

- You just entered an unfamiliar project (no Claude.md / no skim yet)
- You return after long gap and need "what's the state?"
- User asks any of: "what is this project / where do I start / what's the entry / recent changes / health"

**Don't use** when:
- You already have full context (just continue working)
- User wants to read source — use `structure action=read` directly

## Procedure

### Step 1 — Verify tools available

```bash
uv run python -m tree_sitter_analyzer --check-tools --format json | head -5
```

If `fd` or `rg` missing, stop and tell user how to install.

### Step 2 — Fan-out 4 MCP calls (in single message, parallel)

Call these 4 tools in ONE message (parallel tool use):

1. `project action=overview` (no args) — project_card + entry_points
2. `health action=project` with `max_files: 5` — grade distribution + weakest dimension
3. `edit action=impact` with `mode: "branch"` — recent_signals (last commit, ahead-of-main)
4. `project action=workflow` (no args) — current_phase + recommended_commands

### Step 3 — Fold and emit decision_surface

Combine into single Decision Surface:

```jsonc
{
  "project_card": {
    "name": <from project action=overview project_root basename>,
    "primary_language": <key with the highest count in project action=overview summary.by_language — it is a {language: file_count} dict sorted descending, so the first key>,
    "language_mix": <from project action=overview summary.by_language — first 3 keys of the {language: file_count} dict>,
    "size": {
      "files": <from project action=overview summary.total_files>,
      "loc": <from project action=overview summary.total_lines>
    }
  },
  "entry_points": <from project action=overview entry_points>,
  "recent_signals": {
    "last_commit": <git log -1 --oneline via Bash>,
    "ahead_of_origin": <git rev-list --count via Bash>,
    "uncommitted_files": <git status --short | wc -l via Bash>,
    "branch": <git branch --show-current via Bash>
  },
  "health": {
    "verdict": <from health action=project verdict>,
    "risk": <from health action=project agent_summary.risk>,
    "grade_distribution": <from health action=project grade_distribution>,
    "weakest_dimension": <from health action=project weakest_dimension>
  },
  "top_files_to_know": [
    "AGENTS.md",
    "CLAUDE.md",
    <from project action=overview entry_points>,
    <top 3 from health action=project top_refactoring_targets>
  ],
  "agent_next_step": {
    "if_asked_what_is_this":
      "Read AGENTS.md (canonical contracts) + docs/CODEMAPS/architecture.md (topology). Stop after 2k tokens.",
    "if_asked_to_add_feature":
      "Call project action=workflow → follow phase_order. Use TDD (write test first).",
    "if_asked_to_fix_bug":
      "Call health action=patterns file_path=<file> → edit action=refactor file_path=<file>. Cross-ref nav action=lineage if symbol-level.",
    "if_asked_about_test_status":
      "Run: uv run pytest -q (5-min cap). Project enforces xdist parallel, ~5min for 15k tests."
  },
  "summary_line": "<project> files=<N> py=<X%> grade=<G> recent=<commit_subj>",
  "verdict": "INFO"
}
```

### Step 4 — Stop after landing

Do NOT proceed to action until user gives next instruction. The landing is the deliverable.

## Token accounting

| Approach | Tool calls | Token cost |
|---|---|---|
| Naive (read README + ls -R + git log + AGENTS) | 6 | ~15k |
| **tsa-landing** | **3-4** | **~2k** |
| Savings | -50% | **-87%** |

## Why this is a Skill, not an MCP tool

- MCP tool definition costs ~400 tokens **always-loaded**
- Skill description costs ~30 tokens (loads on trigger)
- 13-15× cheaper — frees context budget for actual work
- Workflow logic (parallel fan-out + folding) doesn't need MCP semantics

## See also

- `~/.claude/memory/tsa_research_gold.md` — Why this design (3 金矿洞察)
- `~/.claude/memory/tsa_playbook_24x7.md` — full project state map
- `docs/internal/AGENT_LANDING_KIT_DESIGN.md` — earlier MCP-tool variant of this (deprecated in favor of Skill form)

## Anti-bias note (per Anthropic verification-specialist pattern)

When in doubt about the health verdict, **err toward higher-severity**:
- `INFO` vs `REVIEW` — pick `REVIEW`
- `REVIEW` vs `CAUTION` — pick `CAUTION`

False positives at landing time are recoverable (user says "false alarm"); false negatives ship bugs into agent workflow.
