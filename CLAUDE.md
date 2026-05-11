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
