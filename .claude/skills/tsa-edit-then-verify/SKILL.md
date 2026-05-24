---
name: tsa-edit-then-verify
version: 1.0.0
description: |
  The full edit-and-verify loop mandated by CLAUDE.md and docs/agent-tooling-gap-report.md:58.
  Pre-edit gate (safe_to_edit + baseline file_health) → LLM edits → post-edit verify
  (file_health diff + analyze_change_impact + scoped verification_command).
  Replaces "edit then run the whole pytest suite" (~5 min) with a scoped
  verification (~30-60s) that only escalates to full suite when risk remains.

  Use when:
  - About to make any non-trivial edit to a code file in tree-sitter-analyzer
  - User asks "implement X" / "fix this bug" / "refactor Y" / "add this feature"
  - You just finished editing and need to verify before committing
  - Any change touching tree_sitter_analyzer/** or tests/**

  Don't use when:
  - One-line typo in docs/comments (no behavior change → no verify needed)
  - Pure README/markdown edits
  - You're still in plan mode and haven't decided on the edit yet
  - File you're literally creating from scratch (no callers, no baseline)

  Workflow: 1 parallel batch pre-edit → edit → 1 parallel batch post-edit →
  run scoped verification_command → only run full pytest if risk remains.
allowed-tools:
  - mcp__tree-sitter-analyzer__safe_to_edit
  - mcp__tree-sitter-analyzer__check_file_health
  - mcp__tree-sitter-analyzer__smart_context
  - mcp__tree-sitter-analyzer__analyze_change_impact
  - Bash
  - Read
---

# tsa-edit-then-verify — The full edit loop, scoped not full-suite

> **Source of authority.** From `docs/agent-tooling-gap-report.md` line 58:
>
> > Every feature update must run the self-hosted workflow: `safe_to_edit`
> > before risky edits, `file_health` on changed files, `change_impact` after
> > edits, its reported `verification_command`, then the full default suite
> > when risk remains.
>
> This skill is the **executable form** of that rule. `tsa-edit-safety` only
> covers Phase A (the pre-edit gate). This skill covers A + B + C end-to-end
> and is the canonical replacement for the global `verify` skill (which runs
> the full ~5-minute suite every time).

## When to use vs. not

**Use** when you're about to edit (or just edited) a real code file in this
repo and the change is more than a 1-line cosmetic fix. The smaller the diff,
the bigger the win — full pytest is ~5 min, scoped verification is typically
30-60s.

**Don't use** for:
- One-line typo in a doc/comment (no Python AST impact)
- Pure markdown / README edits (no symbol-level risk)
- File you're creating from scratch with no callers yet
- Read-only exploration

## Why this exists (vs. `verify` skill)

| Skill                       | What it runs                          | Time    | When right |
|-----------------------------|---------------------------------------|---------|------------|
| `verify` (global)           | `uv run pytest -q` (15k tests)        | ~5 min  | Pre-commit gate, large refactor |
| **`tsa-edit-then-verify`**  | scoped `verification_command` from `analyze_change_impact` | **30-60s** | **Every feature update (the mandate)** |
| `tsa-edit-safety`           | Pre-edit verdict only                 | ~3s     | "Is this safe to touch?" — no edit yet |

The scoped command targets only the tests reachable from the changed symbols,
via the AST call-graph. That's the whole point — `analyze_change_impact`
returns a `verification_command` that's narrower than `pytest -q` but still
covers the blast radius the AST sees.

## Procedure

### Phase A — Pre-edit (1 parallel MCP batch)

Call these in ONE message (parallel tool use):

1. `safe_to_edit` with `file_path: "<file>"` and `edit_type: "<refactor|rename|delete|bugfix|feature>"`
2. `check_file_health` with `file_path: "<file>"` — **record the grade. This is your baseline.**
3. (Optional, only if file is unfamiliar to you in this session)
   `smart_context` with `file_path: "<file>"` and `query: "<what you intend to change>"`

**Gate the verdict.** From `safe_to_edit.verdict`:
- `UNSAFE` → STOP. Surface the `risk_factors`, ask the user how to proceed.
  Do not edit.
- `CAUTION` → narrow your scope. Write a failing test first if there isn't
  one for the behavior you're changing.
- `REVIEW` → write a test before the edit if `risk_factors` mentions
  "no tests nearby".
- `SAFE` → proceed to Phase B.

**Persist the baseline grade.** Note `check_file_health.grade` and
`check_file_health.score` in your scratch — you will diff against these in
Phase C.

### Phase B — Edit (out of skill scope)

This is where the LLM actually does the work — Edit / Write / MultiEdit tool
calls. The skill's only job here is to remind you: keep the diff focused.
Large diffs make Phase C's scoped command less reliable (and may bump you
into "full suite" territory at step 7).

If you find yourself making >100 lines of changes across >3 files, pause
and reconsider whether this is really one task or three.

### Phase C — Post-edit verify (1 parallel MCP batch, then Bash)

After your last edit, call these in ONE message (parallel tool use):

4. `check_file_health` with `file_path: "<file>"` again
   → **diff against Phase A baseline. Grade MUST NOT regress.** (B→C is a
   regression. A→A is fine. F→D is improvement.)
5. `analyze_change_impact` with `mode: "staged"` (or `mode: "branch"` if you
   haven't staged) — returns `verification_command`, `pytest_command`,
   `queue_ledger`, `risk_remains` flag.

**Then sequentially via Bash:**

6. Run the **exact** `verification_command` returned by step 5. This is the
   scoped command. Example shape:
   ```bash
   uv run pytest tests/unit/test_health_scorer.py tests/unit/test_file_health_smells.py -q
   ```
   Expect 30-60s. If it fails, fix and re-run from step 4.

7. **Only if** `analyze_change_impact.risk_remains == true` (or grade
   regressed in step 4, or impact reports cross-module reach), run the full
   suite:
   ```bash
   uv run pytest -q
   ```
   This is the ~5-minute fallback. Use it sparingly — the whole point of
   step 6 is to avoid this when the AST says we don't need it.

If step 7 also passes, you're done. Report verdict, grade delta, and the
command you ran.

## Worked example: editing `tree_sitter_analyzer/health_scorer.py`

This file is 891 lines, complex, and has many callers — a realistic
"feature update" target. Suppose you're adding a new dimension to the
health-grading rubric.

### Phase A trace

```
PARALLEL BATCH (one message):
  → safe_to_edit(file_path="tree_sitter_analyzer/health_scorer.py", edit_type="feature")
  → check_file_health(file_path="tree_sitter_analyzer/health_scorer.py")
  → smart_context(file_path="tree_sitter_analyzer/health_scorer.py",
                  query="add new dimension to grading rubric")

Returned:
  safe_to_edit:  verdict=REVIEW
                 risk_factors=[{factor: "hot_zone", detail: "mod_count_30d=7"}]
                 verification_command="uv run pytest tests/unit/test_health_scorer.py -q"
  check_file_health: grade=B, score=84, weakest=complexity   ← BASELINE
  smart_context: top 3 callers = [check_project_health, check_file_health, cli/__main__]
```

Verdict is REVIEW + hot_zone — write a test for the new dimension first.

### Phase B (out of scope)

You write the failing test, then edit `health_scorer.py` to add the new
dimension. Diff is ~40 lines.

### Phase C trace

```
PARALLEL BATCH (one message):
  → check_file_health(file_path="tree_sitter_analyzer/health_scorer.py")
  → analyze_change_impact(mode="staged")

Returned:
  check_file_health: grade=B, score=82, weakest=complexity   ← B→B, no regression ✓
  analyze_change_impact:
    verification_command="uv run pytest tests/unit/test_health_scorer.py
                          tests/unit/test_file_health_blocks.py
                          tests/unit/test_file_health_smells.py -q"
    pytest_required=true
    risk_remains=false   ← scoped command is sufficient
    queue_ledger=[{file: health_scorer.py, symbols: [grade_file, _compute_dim]}]

THEN Bash (sequential):
  $ uv run pytest tests/unit/test_health_scorer.py \
                  tests/unit/test_file_health_blocks.py \
                  tests/unit/test_file_health_smells.py -q
  ... 42 passed in 38.1s ✓                                    ← ~38s, scoped

  (risk_remains=false → skip full suite)
```

Done. **Total verify time: ~38s** vs. ~5 min for `uv run pytest -q`.
That's an **~8× reduction** on the verify step alone, and you still ran
the tests the AST said were reachable from your edit.

## Phase D — Doc Sync (gate before commit)

If your edits touched any of these surfaces, the corresponding codemap MUST be updated in the SAME commit:

| Surface touched (in `tree_sitter_analyzer/`) | Codemap to refresh |
|---|---|
| `mcp/_tool_registry.py` (tool added/removed) | `docs/CODEMAPS/mcp-tools.md` |
| `cli/argument_parser_builder.py` (new flag/command) | `docs/CODEMAPS/cli.md` |
| `languages/<lang>_plugin/` (new plugin) | `docs/CODEMAPS/languages.md` |
| `formatters/` (new formatter) | `docs/CODEMAPS/formatters.md` |

### Step D1 — Detect surface change

```bash
git diff --cached --name-only
git diff --cached -- tree_sitter_analyzer/mcp/_tool_registry.py | grep -E '^\+.*\("(codegraph_|[a-z_]+",)'
```

### Step D2 — If a surface changed, run the codemap skill

Invoke `/update-codemaps` — it scans the registries and regenerates the codemap section. Alternatively dispatch the global `doc-updater` agent for deeper sync (also touches README/AGENTS.md).

### Step D3 — Verify with the hard gate

`scripts/codemap-sync-check.sh` runs automatically as a pre-commit hook and BLOCKs the commit if a surface change is staged but its codemap isn't. To dry-run locally:

```bash
bash scripts/codemap-sync-check.sh
echo "exit=$?"  # 0 = pass, 1 = block
```

Escape hatch (intentional rename without semantic change): `SKIP_CODEMAP_SYNC=1 git commit ...`. The pytest `test_registered_mcp_tools_have_codemap_parity` is the safety net that catches abuse in CI.

### Why Phase D exists

The hook (Phase D's hard gate) only catches what's staged at commit time. Phase D in this skill catches drift earlier — at edit-time the agent already knows which codemap to update, so the user never sees the commit-time block. The hook is the fallback for forgotten cases / non-AI commits.

## CLI equivalents (when MCP is unavailable)

Run pre-edit (Phase A) in parallel:

```bash
uv run tree-sitter-analyzer tree_sitter_analyzer/health_scorer.py \
  --safe-to-edit --edit-type feature --output-format json
uv run tree-sitter-analyzer tree_sitter_analyzer/health_scorer.py \
  --file-health --output-format json
uv run tree-sitter-analyzer tree_sitter_analyzer/health_scorer.py \
  --smart-context --query "add new dimension" --output-format json
```

Run post-edit (Phase C):

```bash
uv run tree-sitter-analyzer tree_sitter_analyzer/health_scorer.py \
  --file-health --output-format json                          # grade diff
uv run python -m tree_sitter_analyzer --change-impact \
  --change-impact-mode staged --output-format json            # gets verification_command
# then copy-paste the verification_command from the JSON output and run it
```

## Verdict cascade (Phase A gate)

| `safe_to_edit.verdict` | Action |
|------------------------|--------|
| `UNSAFE`               | STOP. Surface risk_factors. Ask user. Do not edit. |
| `CAUTION`              | Narrow scope. Write test first. Then edit. |
| `REVIEW`               | Edit OK; write a test first if "no tests nearby". |
| `SAFE`                 | Proceed to Phase B. |

## Grade-regression rule (Phase C step 4)

Compare `check_file_health.grade` before vs. after:

| Before → After | Verdict | Action |
|----------------|---------|--------|
| A → A, B → B, etc. | No regression | Continue to step 5 |
| F → D, D → C, etc. | Improvement | Continue to step 5 |
| A → B, B → C, C → D, D → F | **REGRESSION** | Investigate `weakest_dimension`; consider revert or refactor before commit |

A grade regression is a soft fail — surface it to the user, don't auto-abort.
Some edits legitimately worsen one dimension while improving overall behavior.
Let the user decide.

## When to escalate to full pytest (Phase C step 7)

Run `uv run pytest -q` (full suite, ~5 min) only when ANY of these is true:

- `analyze_change_impact.risk_remains == true`
- Grade regressed in step 4 (A→B or worse)
- Edit touched any of: `BaseMCPTool.__init__`, `PathResolver`, `SecurityValidator`, `plugin registry`, `cli/__main__.py`, `mcp/server.py`
- Edit crossed >3 files
- `analyze_change_impact.queue_ledger` shows cross-module reach (impact crossing top-level packages)

Otherwise the scoped `verification_command` from step 6 is the official
verify gate — no need to burn 5 minutes.

## Anti-patterns

- **Skipping Phase A** because "it's just a small change" — Phase A is ~3s
  and catches `UNSAFE` constraint violations that would waste your Phase B
  effort.
- **Running `pytest -q` immediately in Phase C** without first calling
  `analyze_change_impact` — defeats the whole purpose of this skill. The
  scoped command is the point.
- **Ignoring grade regression** in Phase C step 4 — a B→C regression on a
  hot-zone file is a real signal even if tests pass.
- **Running each phase in serial MCP calls** — Phase A is one parallel
  batch, Phase C is one parallel batch. Don't make 6 sequential calls.
- **Treating `verification_command` as advisory** — it's the literal
  command to run. Don't paraphrase it or "improve" it.

## Decision surface returned

```yaml
phase_a:
  verdict: SAFE | REVIEW | CAUTION | UNSAFE
  baseline_grade: A | B | C | D | F
  baseline_score: 0-100
  risk_factors: [...]
phase_c:
  current_grade: A | B | C | D | F
  current_score: 0-100
  grade_regression: bool
  verification_command: <exact bash line>
  verification_result: PASS | FAIL
  risk_remains: bool
  ran_full_suite: bool
  total_verify_seconds: <int>
verdict: PASS | FAIL | NEEDS_REVIEW
```

## See also

- `tsa-edit-safety` — Phase A alone, when you only want the gate verdict
- `tsa-health-watch` — grade tracking over time (daemon)
- `verify` (global) — full-suite fallback for pre-commit
- `CLAUDE.md` § Build & Test — the project rule this skill implements
- `docs/agent-tooling-gap-report.md` line 58 — the source-of-authority mandate
