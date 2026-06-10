---
name: tsa-landing
version: 1.0.0
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
- User wants to read source — use `extract_code_section` directly

## Procedure

### Step 1 — Verify tools available

```bash
uv run python -m tree_sitter_analyzer --check-tools --format json | head -5
```

If `fd` or `rg` missing, stop and tell user how to install.

### Step 2 — Fan-out 4 MCP calls (in single message, parallel)

Call these 4 tools in ONE message (parallel tool use):

1. `get_project_summary` (no args) — project_card + entry_points
2. `check_project_health` with `max_files: 5` — grade distribution + weakest dimension
3. `analyze_change_impact` with `mode: "branch"` — recent_signals (last commit, ahead-of-main)
4. `get_agent_workflow` (no args) — current_phase + recommended_commands

### Step 3 — Fold and emit decision_surface

Combine into single Decision Surface:

```jsonc
{
  "project_card": {
    "name": <from get_project_summary.project_root basename>,
    "purpose": <from get_project_summary.summary.purpose if present>,
    "primary_language": <from get_project_summary.summary.by_language[0].name>,
    "language_mix": <from get_project_summary.summary.by_language top 3>,
    "size": {
      "files": <from get_project_summary.summary.total_files>,
      "loc": <from get_project_summary.summary.total_lines>
    }
  },
  "entry_points": <from get_project_summary.entry_points>,
  "recent_signals": {
    "last_commit": <git log -1 --oneline via Bash>,
    "ahead_of_origin": <git rev-list --count via Bash>,
    "uncommitted_files": <git status --short | wc -l via Bash>,
    "branch": <git branch --show-current via Bash>
  },
  "health": {
    "verdict": <from check_project_health.verdict>,
    "risk": <from check_project_health.agent_summary.risk>,
    "grade_distribution": <from check_project_health.grade_distribution>,
    "weakest_dimension": <from check_project_health.weakest_dimension>
  },
  "top_files_to_know": [
    "AGENTS.md",
    "CLAUDE.md",
    <from get_project_summary.entry_points>,
    <top 3 from check_project_health.top_refactoring_targets>
  ],
  "agent_next_step": {
    "if_asked_what_is_this":
      "Read AGENTS.md (canonical contracts) + docs/CODEMAPS/architecture.md (topology). Stop after 2k tokens.",
    "if_asked_to_add_feature":
      "Call get_agent_workflow → follow phase_order. Use TDD (write test first).",
    "if_asked_to_fix_bug":
      "Call code_patterns(file_path) → refactoring_suggestions(file_path). Cross-ref symbol_lineage if symbol-level.",
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
