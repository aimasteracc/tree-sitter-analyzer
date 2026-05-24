---
name: tsa-pr-review
version: 1.0.0
description: |
  AST-grounded PR / diff review. One workflow → per-file risk ranking, blast
  radius per changed symbol, the exact pytest command to gate merge, any
  architecture-constraint violations, and a final BLOCK / REVIEW / APPROVE
  verdict — in ~1–2k tokens and 4–6 MCP calls.

  Goes beyond a generic LLM diff-read because only TSA's `analyze_change_impact`
  returns a deterministic `verification_command` + `queue_ledger`, and only the
  persisted call graph can enumerate true callers/callees of changed symbols.
  (Per `docs/internal/COMPETITOR_HEAD_TO_HEAD_2026-05-23.md`: CodeGraphContext
  silently indexes 0 files, grep-ast crashes on Python 3.14, wrale miscounts
  imports. A pure-LLM diff reader has none of these guard-rails — it cannot
  reach the AST cache to enumerate callers, cannot consult
  `architectural-constraints.yml`, and invents a pytest command instead of
  reading the one TSA computed.)

  Use when:
  - Reviewing a local diff (`git diff`, staged, branch-vs-main)
  - Reviewing a GitHub PR URL
  - User asks "is this PR safe to merge?" / "what's the blast radius of this PR?"
  - Pre-merge gate in CI / agent loops
  - Right after `/ship` produced a diff and before `/land`

  Workflow: fan-out (pr_review + change_impact + check_constraints) → per-file
  fan-out (safe_to_edit) → per-symbol fan-out (callers + callees) → fold into
  a verdict-ranked report.
allowed-tools:
  - mcp__tree-sitter-analyzer__codegraph_pr_review
  - mcp__tree-sitter-analyzer__analyze_change_impact
  - mcp__tree-sitter-analyzer__safe_to_edit
  - mcp__tree-sitter-analyzer__check_constraints
  - mcp__tree-sitter-analyzer__codegraph_callers
  - mcp__tree-sitter-analyzer__codegraph_callees
  - Bash
  - Read
---

# tsa-pr-review — AST-grounded PR review with merge-gate verdict

> Replaces "LLM reads the diff and guesses" with a deterministic pipeline that
> grounds the review in (a) the AST diff, (b) the persisted call graph, and
> (c) architectural-constraints.yml. Output is a structured verdict an agent
> can act on — including the **exact** pytest command to run before merge.

## When to use

- Local diff review: unstaged, staged, or branch-vs-main
- GitHub PR review by URL (uses `gh` under the hood)
- CI / agent pre-merge gate
- Any time a generic "read the diff" review would be too shallow

**Don't use** when:
- The diff is a one-line typo in a comment or doc
- The change is in a file with no AST coverage (e.g. binary, image, .lock)
- You only need to *describe* the diff, not *judge* it → use plain `git diff`

## Why this beats a generic LLM diff-read

| Concern                          | LLM-only diff read   | tsa-pr-review                            |
|----------------------------------|----------------------|------------------------------------------|
| Classify signature vs body change| Heuristic            | `codegraph_pr_review` AST diff           |
| Exact tests to run               | Invented / hallucinated | `analyze_change_impact.verification_command` |
| Caller blast radius              | Grep guess           | `codegraph_callers` from persisted graph |
| Callee regression surface        | Read N files         | `codegraph_callees` from persisted graph |
| Architecture rule violations     | None                 | `check_constraints` vs YAML rules        |
| Per-file pre-merge verdict       | Subjective           | `safe_to_edit` SAFE/REVIEW/CAUTION/UNSAFE|
| Behaviour on Python 3.14         | n/a                  | Stable (grep-ast crashes, cgc silent-0)  |

(Source: `docs/internal/COMPETITOR_HEAD_TO_HEAD_2026-05-23.md` — the 4
fault-tolerance advantages: oracle-consistent AST, indexed-not-silent,
Python 3.14-safe, no external DB dependency.)

## Procedure

### Step 1 — Diff-level fan-out (parallel, 3 calls)

In one message, call all three:

1. `codegraph_pr_review(mode="staged")` — AST diff classification, per-symbol
   change category (signature_change / body_change / new_symbol / deletion),
   and per-file changed-symbol list.
   - For PR URL: `codegraph_pr_review(mode="pr", pr_url="<url>")`
   - For unstaged: `mode="diff"`; for branch-vs-main: `mode="branch"`
2. `analyze_change_impact(mode="staged")` — returns `verification_command`,
   `queue_ledger` (in-scope vs out-of-scope dirty files), `pytest_required`,
   and per-file impact rows.
3. `check_constraints()` — full repo audit against `architectural-constraints.yml`,
   filtered to files the diff touches if you want noise-free output:
   `check_constraints(path_filter="<glob covering changed files>")`.

### Step 2 — Per-file fan-out (parallel, N calls)

For each changed file from Step 1, call:

`safe_to_edit(file_path="<abs>", edit_type="<refactor|rename|delete|bugfix>")`

Pick `edit_type` from the dominant change category in Step 1's
`codegraph_pr_review` output. Returns per-file verdict + `risk_factors`.

### Step 3 — Per-symbol fan-out (parallel, ≤2N calls)

For each *changed signature* (not body-only) symbol from Step 1, fan out
two calls:

- `codegraph_callers(function_name="<sym>", language="<lang>", limit=20)`
  — who depends on this; the blast radius if its signature moved.
- `codegraph_callees(function_name="<sym>", language="<lang>", limit=20)`
  — what it calls; the regression surface if its body changed.

Filter callers/callees where `callee_resolution == "stdlib"` or `"unknown"` —
they're noise for blast-radius scoring (per tsa-graph guidance).

### Step 4 — Fold into verdict

```
verdict_precedence (worst wins):
  - BLOCK   ← any check_constraints violation with severity=error
              OR any safe_to_edit verdict == UNSAFE
  - REVIEW  ← any safe_to_edit verdict in {REVIEW, CAUTION}
              OR pytest_required=true with no nearby tests
              OR signature_change with ≥5 external callers
  - APPROVE ← all per-file verdicts == SAFE,
              all constraints pass,
              pytest_required=false OR verification_command is tightly scoped
```

Surface the precise `verification_command` verbatim — never paraphrase it.

## Worked example (this repo, 2-file diff)

Suppose `git diff HEAD~2 HEAD` shows changes in two files. To walk through
without committing anything new, simulate the workflow against a real diff:

```bash
git -C /Users/aisheng.yu/git-private/tree-sitter-analyzer diff HEAD~2 HEAD --name-only
# → tree_sitter_analyzer/mcp/tools/safe_to_edit_tool.py
# → tree_sitter_analyzer/mcp/tools/change_impact_tool.py
```

### Diff-level fan-out

```yaml
# Call 1
codegraph_pr_review(mode="branch", include_call_graph=true, output_format="json")
# returns:
#   changed_files:
#     - path: ".../safe_to_edit_tool.py"
#       changed_symbols:
#         - name: "SafeToEditTool.execute"
#           category: "body_change"
#         - name: "SafeToEditTool._score_risk"
#           category: "signature_change"  # ← signature changed
#     - path: ".../change_impact_tool.py"
#       changed_symbols:
#         - name: "ChangeImpactTool.execute"
#           category: "body_change"

# Call 2
analyze_change_impact(mode="branch", agent_summary_only=true)
# returns:
#   verification_command: "uv run pytest tests/unit/test_safe_to_edit_tool.py
#                          tests/unit/test_change_impact_tool.py -q"
#   pytest_required: true
#   queue_ledger:
#     in_scope: [".../safe_to_edit_tool.py", ".../change_impact_tool.py"]
#     out_of_scope_dirty: []

# Call 3
check_constraints(path_filter="tree_sitter_analyzer/mcp/**")
# returns:
#   verdict: SAFE
#   violations: []
```

### Per-file fan-out

```yaml
safe_to_edit(file_path=".../safe_to_edit_tool.py", edit_type="refactor")
# → verdict: REVIEW, risk_factors: [{factor: "high_caller_count", ...}]
safe_to_edit(file_path=".../change_impact_tool.py", edit_type="bugfix")
# → verdict: SAFE
```

### Per-symbol fan-out (only the signature-change)

```yaml
codegraph_callers(function_name="_score_risk", language="python", limit=20)
# → 7 callers; 6 in tests/, 1 in cli/commands/mcp_commands.py
codegraph_callees(function_name="_score_risk", language="python", limit=20)
# → 4 callees; all local (good — no stdlib noise)
```

### Folded verdict

```yaml
verdict: REVIEW
files:
  - path: ".../safe_to_edit_tool.py"
    verdict: REVIEW
    changed_symbols: 2
    signature_changes: 1
    blast_radius: 7         # callers of _score_risk
    health_grade: B
  - path: ".../change_impact_tool.py"
    verdict: SAFE
    changed_symbols: 1
    signature_changes: 0
    blast_radius: 0
constraint_violations: []
verification_command: "uv run pytest tests/unit/test_safe_to_edit_tool.py
                       tests/unit/test_change_impact_tool.py -q"
stop_condition: "tests exit successfully AND no NEW failures vs main"
notes:
  - "Signature change on _score_risk affects 1 non-test caller — verify mcp_commands.py still passes."
```

## CLI equivalents (1-to-1 with MCP calls)

```bash
# Step 1 — Diff fan-out
uv run tree-sitter-analyzer --pr-review --change-impact-mode staged --output-format toon
uv run tree-sitter-analyzer --change-impact --change-impact-mode staged --agent-summary-only --output-format json
uv run tree-sitter-analyzer --check-constraints --constraint-path-filter "tree_sitter_analyzer/mcp/**" --output-format toon

# Step 2 — Per-file
uv run tree-sitter-analyzer <file> --safe-to-edit --edit-type refactor --output-format json

# Step 3 — Per-symbol
uv run tree-sitter-analyzer --callers <FUNC> --output-format toon
uv run tree-sitter-analyzer --callees <FUNC> --output-format toon
```

Exit codes mirror `--change-impact` / `--check-constraints`:
- 0 → APPROVE
- 2 → REVIEW (warn-only)
- 1 → BLOCK (error severity)

## Anti-patterns

- DO NOT ask the LLM to invent the pytest command — quote
  `verification_command` verbatim. r36 / past incidents confirm hallucinated
  pytest invocations skip the regressions TSA already pinpointed.
- DO NOT skip `check_constraints` because "the LLM can spot architecture
  drift". It can't — the rules live in YAML and are evaluated against the
  persisted edge graph.
- DO NOT run callers/callees on body-only changes. Bodies don't change
  signatures; callers don't care. Reserve graph queries for signature changes,
  deletions, and new public symbols.
- DO NOT mix `mode="staged"` for pr_review with `mode="branch"` for
  change_impact — keep modes consistent so both tools see the same diff.
- DO NOT swallow `queue_ledger.out_of_scope_dirty` — it tells you the working
  tree has files outside the diff that may still break the build.
- DO NOT flip MCP `output_format` from `toon` to `json` — locked by user
  (see `CLAUDE.md` "Deliberate design decisions"). Tokens matter.

## Decision surface (output schema)

```yaml
verdict: APPROVE | REVIEW | BLOCK
files:
  - path: <abs>
    verdict: SAFE | REVIEW | CAUTION | UNSAFE
    changed_symbols: <int>
    signature_changes: <int>
    body_changes: <int>
    new_symbols: <int>
    deletions: <int>
    blast_radius: <int>            # external callers of changed signatures
    regression_surface: <int>      # non-stdlib callees touched
    health_grade: A | B | C | D | F
    risk_factors: [{factor, detail, severity}]
constraint_violations: [
  {rule_id, caller_file, caller_line, callee_file, severity, reason}
]
verification_command: <copy-paste exact pytest line from change_impact>
pytest_required: bool
queue_ledger:
  in_scope: [<path>]
  out_of_scope_dirty: [<path>]     # non-empty → warn user
stop_condition: <when to declare done>
notes: [<short string>]
```

Verdict cascade (worst wins):
- `BLOCK` → constraint error OR per-file `UNSAFE`
- `REVIEW` → per-file `REVIEW`/`CAUTION` OR ≥5-caller signature change OR
  `pytest_required` and tests aren't co-located
- `APPROVE` → all per-file `SAFE`, no constraint violations, tight verify cmd
