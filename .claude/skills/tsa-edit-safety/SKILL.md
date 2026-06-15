---
name: tsa-edit-safety
version: 2.0.0
description: |
  Pre-edit safety check using tree-sitter-analyzer. One workflow → verdict
  (SAFE/REVIEW/CAUTION/UNSAFE) + verification command + risk factors → ≤2k
  tokens, ≤3 MCP calls. Replaces ~10k tokens of grep/read/git-diff exploration
  before touching a file.

  Use when:
  - About to edit a file you haven't touched in this session
  - Refactoring across multiple files
  - Asked "is it safe to change X?" or "what breaks if I touch Y?"
  - Before approving a code review

  Workflow: 2-3 parallel MCP calls (edit action=safe + edit action=impact +
  health action=file), fold the verdicts, surface the exact
  `verification_command` and stop_condition.
allowed-tools:
  - mcp__tree-sitter-analyzer__edit
  - mcp__tree-sitter-analyzer__health
  - mcp__tree-sitter-analyzer__project
  - mcp__tree-sitter-analyzer__nav
  - Bash
  - Read
---

# tsa-edit-safety — Decide before you edit

> Replaces grep/read/git-diff/blame exploration with 2-3 MCP calls returning
> verdict + exact command to verify. **80% token reduction** vs. manual recon.

## When to use

- Pre-edit gate for any non-trivial change (more than 5 lines or crossing files)
- User asks any of: "is X safe to change", "what depends on Y", "what tests cover Z"
- Right after `git diff` shows pending changes you want to evaluate

**Don't use** when:
- One-line typo fix in a doc / comment
- File you're literally creating from scratch (no callers)

## Procedure

### Step 1 — Single fan-out (parallel)

Call these 3 tools in ONE message:

1. `edit action=safe` with `file_path: "<the file>"` and `edit_type: "<refactor|add_feature|fix_bug|rename>"`
2. `edit action=impact` with `mode: "staged"` (or `"branch"` if pre-stage), scope to the file
3. `health action=file` with `file_path: "<the file>"`

### Step 2 — Read the verdict cascade

Verdict precedence (worst wins):
- `UNSAFE` (from constraints or impact) → STOP, explain why, do not edit
- `CAUTION` (high impact / dependencies / hot zone) → narrow scope, write tests first
- `REVIEW` (moderate, often "no tests nearby") → write tests before edit
- `SAFE` → proceed; still run the returned `verification_command`

### Step 3 — Always quote the exact `verification_command`

The tools return a `verification_command` and `stop_condition`. Surface them
verbatim to the user before editing. Example:

> verdict: REVIEW
> verification_command: `uv run pytest tests/unit/test_health_scorer.py -q`
> stop_condition: tests exit successfully
> next_step: write a failing test for the new behaviour first

## Common shapes

**No tests nearby** → escalate to REVIEW + recommend tdd workflow
**`__init__.py` edit** → REVIEW automatically (re-exports)
**`mod_count_30d >= 5`** → CAUTION (hot zone — extra review attention)
**Constraint violation** → UNSAFE (architectural rule — forbidden edge)

## CLI equivalents (if MCP unavailable)

```bash
uv run tree-sitter-analyzer <file> --safe-to-edit --edit-type refactor --output-format json
uv run tree-sitter-analyzer --change-impact --change-impact-mode staged --agent-summary-only --output-format json
uv run tree-sitter-analyzer <file> --file-health --output-format json
```

## Anti-patterns

- DO NOT read the file before this check — the tool's verdict is informed by
  the AST + DB, not text scan. Reading first wastes tokens.
- DO NOT run pytest -q (whole suite) when the tool returned a focused command.
- DO NOT skip the gate just because the file is "small" — small files often
  have outsized blast radius (e.g. `__init__.py`, `conftest.py`).

## Decision surface returned

```yaml
verdict: SAFE | REVIEW | CAUTION | UNSAFE
file_path: <abs>
risk_level: safe | caution | high
edit_strategy: focused_edit_with_tests | narrow_then_widen | freeze_and_redesign
verification_command: <copy-paste exact pytest line>
stop_condition: <when to declare done>
risk_factors: [{factor, detail, severity}, ...]
health_grade: A | B | C | D | F
constraint_violations: []   # non-empty triggers UNSAFE
hot_zone: bool              # mod_count_30d >= 5 → true
```
