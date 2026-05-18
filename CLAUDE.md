# Project Guidelines

## gstack

Use /browse from gstack for all web browsing. Never use mcp__claude-in-chrome__* tools.

Available skills:
- /office-hours - YC Office Hours: reframe your product before you write code
- /plan-ceo-review - CEO/Founder: rethink the problem, find the 10-star product
- /plan-eng-review - Eng Manager: lock in architecture, data flow, diagrams
- /plan-design-review - Senior Designer: rate design dimensions, detect AI slop
- /design-consultation - Design Partner: build a complete design system
- /review - Staff Engineer: find bugs that pass CI but blow up in production
- /ship - Release Engineer: sync main, run tests, push, open PR
- /land-and-deploy - Release Engineer: merge PR, wait for CI/deploy, verify
- /canary - SRE: post-deploy monitoring loop
- /benchmark - Performance Engineer: baseline page load, Core Web Vitals
- /browse - QA Engineer: real Chromium browser with eyes
- /qa - QA Lead: test your app, find bugs, fix with atomic commits
- /qa-only - QA Reporter: pure bug report without code changes
- /design-review - Designer Who Codes: audit and fix design issues
- /setup-browser-cookies - Session Manager: import cookies for authenticated pages
- /setup-deploy - Deploy Configurator: one-time setup for /land-and-deploy
- /retro - Eng Manager: weekly retro with per-person breakdowns
- /investigate - Debugger: systematic root-cause debugging
- /document-release - Technical Writer: update docs to match what you shipped
- /codex - Second Opinion: independent code review from OpenAI Codex CLI
- /careful - Safety Guardrails: warns before destructive commands
- /freeze - Edit Lock: restrict file edits to one directory
- /guard - Full Safety: /careful + /freeze in one command
- /unfreeze - Unlock: remove the /freeze boundary
- /gstack-upgrade - Self-Updater: upgrade gstack to latest

If gstack skills aren't working, run `cd .claude/skills/gstack && ./setup` to build the binary and register skills.

## Agent skills

### Issue tracker

GitHub Issues for `aimasteracc/tree-sitter-analyzer` via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical roles use the default label names: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Development workflow

### Pre-work alignment
Before any non-trivial change, use `/grill-with-docs` to sharpen terminology and surface contradictions with the CONTEXT.md glossary. Use `/grill-me` for quick one-on-one interrogation without docs update.

### Architecture stewardship  
Run `/improve-codebase-architecture` when you notice repeated changes in the same module, or when adding the Nth language plugin. Use `/zoom-out` when unfamiliar with a code area to get a high-level map first.

### Feature pipeline
New features follow: `/grill-with-docs` → `/to-prd` (synthesize PRD) → `/to-issues` (split into vertical slices) → `/tdd` (implement one slice at a time). Each Issue gets a behavioral Agent Brief for AFK execution.

### Branch and review
- `/caveman` for ultra-compact communication (~75% token savings) in long sessions
- `/review` for independent code review before merge
- `/codex` for second opinion from OpenAI Codex
- `/prototype` for throwaway logic/UI experiments

### Quality and diagnosis
- `/diagnose` with 10-step feedback loop when a bug passes existing tests
- `/benchmark` for performance baseline before/after optimization
- `/qa` for comprehensive testing with atomic fix commits
- `/qa-only` for bug reports without code changes

### Issue triage (via `/triage`)
State machine: `needs-triage` → `needs-info` → `ready-for-agent` / `ready-for-human` / `wontfix`.
Agent Briefs are behavioral (not procedural) — no file paths, just what must be true.

### Release flow
- `/ship` — sync main, run tests, push, open PR
- `/land-and-deploy` — merge PR, wait for CI/deploy, verify
- `/canary` — post-deploy monitoring loop
- `/retro` — weekly retrospective

### Safety
- `/careful` — warn before destructive commands
- `/freeze` — restrict edits to one directory
- `/guard` — both combined

### Meta
- `/write-a-skill` — create new skills from patterns you discover
- `/document-release` — update docs after shipping
- `/gstack-upgrade` — keep gstack current

## DeepSeek TUI — native skills

DS TUI has its own skill system at `~/.deepseek/skills/`. Use `/skill-creator` to create new DS-native skills from reusable patterns discovered during development.

### Automation integration
- `/automation-list` — see all registered automations
- `/automation-run ts-analyzer-autonomous-loop` — trigger autonomous dev loop manually
- Read `.autonomous-runtime/ds-automation.yaml` for the full 8-step loop specification
## MCP tool usage (self-hosted)

This project provides its own MCP server with 14 tools for deep code analysis.
These tools provide capabilities that Claude Code built-in tools (Read, Grep, Glob) CANNOT:
AST structural analysis, health scoring with security scan, dependency graphs,
git-aware impact analysis, refactoring extraction plans, edit risk assessment.

### Complete workflow (tools call each other)

```
get_project_overview     → Start here: languages, files, tool routing guide
        ↓
check_project_health     → Grade ALL files, top targets with fix actions
        ↓
check_file_health        → Single file: A-F grade + smells + security scan
        ↓ (D/F files auto-suggest ↓)
refactoring_suggestions  → Precise plans: helper names, line ranges, params, skeletons
        ↓
safe_to_edit             → MUST call before editing: risk + deps + test files
        ↓
  ... edit code ...
        ↓
analyze_change_impact    → git diff + dep graph → affected files, tests, risk, verification_command
        ↓
check_file_health        → Verify improvement
```

### Edit workflow (use EVERY time you modify code)

```
BEFORE editing:  safe_to_edit → risk_level + blast_radius + checklist
AFTER editing:   analyze_change_impact → affected files + tests to run + verification_command
IF health issue: check_file_health → D/F grade files get next_action
```

Run `uv run python -m tree_sitter_analyzer --change-impact --format json`
after edits and follow its `verification_command` first. For code changes this
is usually the targeted `test_command`; for docs-only changes `test_required`
is false and the command may be `git diff --check`. `pytest_command` remains
available when the detected runner is pytest, with `pytest_required` kept as a
compatibility signal for older agent prompts.
Use the full suite before release/PR when risk remains high. `uv run pytest -q`
runs with pytest-xdist by default (`--numprocesses=auto --dist=loadfile`); the
latest measured full-suite wall time is about 26 seconds on this workstation.
Default pytest also enforces a 300-second session timeout, a 180-second per-test
timeout, and disables benchmark hooks during normal test runs. Run
benchmark-only jobs with `--benchmark-enable -n 0 --session-timeout=0` so
pytest-benchmark is active, xdist is disabled, and long benchmark runs are
allowed.

### Discovery workflow (when approaching unfamiliar code)

```
1. get_project_overview  → project portrait: languages, structure, health
2. check_code_scale      → file metrics + complexity
3. analyze_code_structure → AST elements: classes, methods, fields, line positions
4. extract_code_section  → read specific line ranges (batch supported)
5. query_code(symbol=)   → AST symbol search (NOT text grep), wildcards: *Service, fuzzy: ~analyz
```

### Search tools (prefer over built-in Grep for efficiency)

```
search_content  → ripgrep with total_only (~10 tok) / count_only / summary modes
find_and_grep   → fd + ripgrep combined
list_files      → fd-based file discovery
query_code      → AST symbol search with wildcards and type filtering
```

### Efficiency tips
- Always use `output_format: toon` (default) for ~60% token reduction
- Use `total_only: true` on `search_content` for existence checks (~10 tokens)
- Use `include_skeleton: true` on `refactoring_suggestions` only when you need code skeletons (default: off, saves ~50%)
- Use `symbol_type: class/function` on `query_code` to filter by element type

## Development guardrails

### Edit discipline
- Edit <50 lines at a time; use `uv run python -m tree_sitter_analyzer --change-impact --format json` to choose focused verification, then run the reported `verification_command`
- For "move to module-level" refactors: add new function → update call site → delete old method, testing between each step
- Never replace 200+ lines in a single edit without immediate verification

### CLI-MCP parity (hard requirement)
- Every MCP tool MUST have a CLI equivalent entry in `cli_main.py`
- When adding/updating an MCP tool: add `--flag` to `create_argument_parser()`, handler in `handle_special_commands()` or `tree_sitter_analyzer/cli/commands/mcp_commands.py`, and example in epilog
- Test: `uv run python -m tree_sitter_analyzer <file> --flag --format json`
- Guardrails: `tests/unit/test_agent_contracts.py` fails if a registered MCP tool loses its CLI access path; `tests/unit/cli/test_mcp_commands.py` fails if MCP-equivalent CLI handlers pass the wrong arguments, require the wrong file path, or drop TOON output.

### Test runtime contract (do not weaken)
- Keep `uv run pytest -q` parallel, benchmark-disabled, and bounded by `--session-timeout=300`.
- Do not remove `pytest-xdist`, `pytest-timeout`, `--dist=loadfile`, or the 300s/180s timeout defaults without updating `tests/unit/test_agent_contracts.py` and proving the full suite remains under 5 minutes.
- Reason: this prevents recurring agent failures from serial test runs, accidental benchmark execution, and hidden hangs.

### Self-hosting verification
- Before committing: run `--file-health` on changed files and verify grade did not drop
- Before committing: run `--safe-to-edit` to confirm blast radius is acceptable
- After committing: run `--change-impact` to verify no unexpected regressions
