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

This project provides its own MCP server with 15 tools for deep code analysis.
These tools provide capabilities that Claude Code built-in tools (Read, Grep, Glob) cannot:
AST structural analysis, code health scoring, dependency graphs, git-aware impact analysis.

### Edit workflow (use EVERY time you modify code)

```
BEFORE editing:  safe_to_edit → risk_level + blast_radius + checklist
AFTER editing:   analyze_change_impact → affected files + tests to run
IF health issue: check_file_health → D/F grade files get extraction_plan
```

### Discovery workflow (when approaching unfamiliar code)

```
1. get_project_overview  → project portrait: languages, structure, health
2. check_code_scale      → file metrics + complexity
3. analyze_code_structure → AST elements: classes, methods, fields, line positions
4. extract_code_section  → read specific line ranges (batch supported)
5. query_code(symbol=)   → cross-file symbol search across project
```

### Search tools (prefer over built-in Grep for efficiency)

```
search_content  → ripgrep with total_only/count_only/summary modes
find_and_grep   → fd + ripgrep combined
list_files      → fd-based file discovery
```

### Efficiency tips
- Always use `output_format: toon` (default) for ~60% token reduction
- Use `total_only: true` on `search_content` for existence checks (~10 tokens)
