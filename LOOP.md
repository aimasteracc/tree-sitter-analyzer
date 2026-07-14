# Loop Configuration — Codegraph #1 (Claude Code)

## Mission

**Become the #1 project in the codegraph industry.**

- High-performance initial indexing (parallel pool, SQLite WAL + mmap tuning)
- Graph database with centrality metrics and auto-build after every index
- Visualization on par with Sourcegraph and CodeGraph (force-directed layout, DOT, GraphML)
- Agent neural interface: 16-language moat, Synapse resolver, full MCP tool suite

**Dogfood protocol:** TSA uses its own MCP tools and skills to audit and repair its own
codebase before writing a single line of code. Fixing TSA makes TSA a more trustworthy
agent tool, which makes the next fix faster.

## Active Loops

| Pattern | Cadence | Status | Command |
|---------|---------|--------|---------|
| Daily Triage (dogfood) | 1d weekdays | L1 report-only | `/loop 1d $loop-triage` |
| Architecture Fix | on-demand | L2 worktree | Invoke `$tsa-self-repair` skill |

## Dogfood Protocol — Required MCP Calls Per Triage Run

Every triage run MUST call TSA's own MCP tools before writing its report:

1. `mcp__tree-sitter-analyzer__health action=overview` — project health snapshot
2. `mcp__tree-sitter-analyzer__structure action=sitemap mode=module` — language module landscape
3. `mcp__tree-sitter-analyzer__nav action=xref symbol=register_language` — moat coverage check
4. `mcp__tree-sitter-analyzer__health action=dead` — find orphaned code in language modules
5. `mcp__tree-sitter-analyzer__edit action=constraints` — check architectural constraints

These calls are ground truth. Do not substitute grep or file reads when a TSA MCP call
can answer the question.

## Human Gates

- No auto-merge to develop or main — all PRs require human review
- Moat changes (`synapse_resolver/`): human review before merge
- RFC implementations: design review required before any code

## Worktrees

- Use `isolation: worktree` for all architecture changes (L2+)
- One worktree per fix; run `pytest tests/ -x --timeout=60` before proposing PR
- Discard worktree after verifier REJECT or after 3 failed attempts

## Budget

- Max sub-agent spawns per run: 2 (L2)
- Token cap: see `loop-budget.md`
- Kill switch: add `loop-pause-all` to STATE.md High Priority section

## Links

- Pattern: `patterns/daily-triage.md` (in loop-engineering repo)
- Checklist: `docs/loop-design-checklist.md` (in loop-engineering repo)
- Self-repair skill: `.claude/skills/tsa-self-repair/SKILL.md`
- Triage skill: `.claude/skills/loop-triage/SKILL.md`
