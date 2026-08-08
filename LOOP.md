# Loop Configuration — Trusted Agent Change Intelligence No.1

## Mission

**Become the most trusted local code-change intelligence layer for AI coding agents.**

- Trust evidence: conservative resolution, provenance, freshness, reproducible outcomes
- Task UX: understand → plan_change → assess_change over existing primitives
- Runtime reliability: low-friction install, fast index/query/refresh, multi-agent safety
- Independent adoption: E2/E3/E4 evidence, integrations, external maintainers, real cases

North star: **Verified Change Success Rate (VCSR)**. Public leadership wording is
bounded by the RFC-0021 evidence ladder. Active plan:
[`rfcs/ROADMAP-no1-agent-trust.md`](rfcs/ROADMAP-no1-agent-trust.md).

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
- One worktree per fix; rerun TSA change-impact and follow its exact verification command
- For broad verification, use the AGENTS.md quick/comprehensive xdist commands; never invent a serial suite
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
