# Agent Tooling Gap Report

Last updated: 2026-05-17 JST

## Ingested Local Sources

- `CONTEXT.md`: domain language for the Analysis Engine, Language Plugin, Element Extractor, Formatter, Output Manager, and SMART Workflow.
- `docs/features.md`: Deep AI Integration, MCP support, SMART Workflow, token reduction, fd/ripgrep search, and security boundaries.
- `docs/smart-workflow.md`: Set-Map-Analyze-Retrieve-Trace workflow and CLI/MCP mapping.
- `docs/api/mcp_tools_specification.md`: project-level tools, tool routing, `pytest_command` change-impact output, SMART prompts, and recovery hints.
- `docs/toon-format-guide.md`: TOON response format and token reduction results.
- `docs/ja/project-management/00_プロジェクト憲章.md`: project purpose: enterprise-grade code analysis optimized for the AI era.
- `docs/ja/test-management/04_品質メトリクス.md`: local competitor comparison: MCP integration, language coverage, cache, speed, and security.
- `.agents/skills/triage/AGENT-BRIEF.md`: durable agent handoff style: behavioral contracts, key interfaces, acceptance criteria, and explicit scope.

No local Claude Code source-analysis artifact was found with `rg` during this pass. When that artifact is available, ingest it here and compare its control loop, memory model, skill loading, and permission model against our own MCP/CLI workflow.

## Product Thesis

Tree-sitter Analyzer should be the structural workbench for coding agents: local, bounded, reproducible code intelligence that every agent can call through MCP and every human or CI job can call through CLI.

The distinctive value is not "another chat coding tool." It is agent-grade code context with hard contracts:

- Structure before reading: tree-sitter elements, scale checks, and targeted extraction before full-file context.
- Bounded autonomy: project-root security, safe-to-edit risk checks, and change-impact test selection.
- Reproducible tool use: every MCP capability has a CLI access path, smoke test, and docs.
- Token leverage: TOON, summary-only, total-only, grouped output, and file-output modes.
- Self-improvement loop: health scoring, refactoring suggestions, `pytest_command`, and a default full suite under 5 minutes.

## What Competitors Have That We Still Need

- Productized agent workflows: competitors make planning, editing, testing, and review feel like one flow; our pieces exist, but the workflow is still mostly documented rather than first-class.
- First-class skills: this repo has `.agents/skills`, but users cannot yet discover, validate, install, or run project skills through the same MCP/CLI contract as code-analysis tools.
- Stronger demo surface: docs mention a demo GIF, but the "with this project vs without this project" contrast is not yet captured as an automated, repeatable benchmark/video scenario.
- Memory and policy model: AGENTS/CLAUDE guidance exists, but there is no structured policy registry that tools can inspect and enforce beyond current contract tests.
- Zero-warning quality gate: default pytest is now fast and bounded; the next step is deciding which warning-as-error subset should be promoted into CI without slowing the main loop.

## What We Have But Need To Make More Special

- MCP integration: strong, but it becomes exceptional only when every MCP tool has CLI parity, examples, smoke tests, and recovery guidance.
- SMART Workflow: useful, but should become an executable workflow pack or prompt/tool router rather than only prose.
- Health scoring: valuable, but project health currently shows coverage as the weakest dimension; the top F/D files should drive the next refactoring queue.
- TOON/token optimization: differentiated, but needs side-by-side examples in docs and demos so users feel the context savings immediately.
- Change impact: high leverage because it returns `pytest_command`; future agents should prefer it for fast feedback, then run full default suite before release.

## Hard Requirements For Future Updates

- Every MCP tool change must include CLI parity in the same change.
- `tests/unit/test_agent_contracts.py` must pass before handoff; it guards pytest runtime, dependencies, MCP/CLI parity, and known Python warning-prone API patterns.
- `uv run pytest -q` is the default full-suite command and must remain under 5 minutes.
- Benchmark runs must stay explicit: `--benchmark-enable --benchmark-only -n 0 --session-timeout=0`.
- Every feature update must run the self-hosted workflow: `safe_to_edit` before risky edits, `file_health` on changed files, `change_impact` after edits, targeted tests, then the full default suite when risk remains.

## Next High-Value Work

1. Add a first-class "agent workflow pack" interface that exposes SMART, safe edit, change impact, and test commands as a single guided MCP/CLI workflow.
2. Create a repeatable demo script that compares agent behavior with and without Tree-sitter Analyzer on a large-file/debugging task.
3. Turn `.agents/skills` into an inspectable project asset: list skills, validate metadata, map each skill to a CLI/MCP invocation, and report missing acceptance criteria.
4. Use `check_project_health` output to open focused refactoring slices for the current F-grade files, starting with low-coverage Language Plugin extractors and `api.py`.
5. Decide a warning-as-error policy that is fast enough for daily agent work, then add it as a separate contract target.
