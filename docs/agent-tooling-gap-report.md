# Agent Tooling Gap Report

Last updated: 2026-05-23 JST

## Ingested Local Sources

- `CONTEXT.md`: domain language for the Analysis Engine, Language Plugin, Element Extractor, Formatter, Output Manager, and SMART Workflow.
- `docs/features.md`: Deep AI Integration, MCP support, SMART Workflow, token reduction, fd/ripgrep search, and security boundaries.
- `docs/smart-workflow.md`: Set-Map-Analyze-Retrieve-Trace workflow and CLI/MCP mapping.
- `docs/api/mcp_tools_specification.md`: project-level tools, tool routing, `pytest_command` change-impact output, SMART prompts, and recovery hints.
- `AGENTS.md` and `CLAUDE.md`: durable local agent contracts for test runtime, MCP/CLI parity, self-hosted safe-edit/change-impact workflow, and handoff verification.
- `docs/toon-format-guide.md`: TOON response format and token reduction results.
- `docs/ja/project-management/00_プロジェクト憲章.md`: project purpose: enterprise-grade code analysis optimized for the AI era.
- `docs/ja/test-management/04_品質メトリクス.md`: local competitor comparison: MCP integration, language coverage, cache, speed, and security.
- `.agents/skills/triage/AGENT-BRIEF.md`: durable agent handoff style: behavioral contracts, key interfaces, acceptance criteria, and explicit scope.

No local Claude Code source-analysis artifact was found with `rg` during this pass. When that artifact is available, ingest it here and compare its control loop, memory model, skill loading, and permission model against our own MCP/CLI workflow.

## External Wiki Inspiration

- Tree-sitter's parser wiki is a useful model for language-roadmap intelligence because it tracks parser ABI, recent maintenance, whether `grammar.json` is pre-generated, and whether an external scanner is required. This suggests a higher-value future feature than a flat language checklist: a parser-readiness advisor that ranks new language plugins by parser maturity, install friction, generated grammar availability, scanner risk, and expected test-fixture cost.

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

- MCP integration: strong, and now guarded by both registry-level CLI parity contracts and handler-level CLI smoke tests. The next step is richer examples and recovery guidance for each tool.
- SMART Workflow: useful, but should become an executable workflow pack or prompt/tool router rather than only prose.
- Health scoring: valuable, and `file-health` now lifts the weakest dimension plus the first actionable smell's line, symbol, and detail into `agent_summary`; project health still shows coverage as the weakest dimension, so the top F/D files should drive the next refactoring queue.
- TOON/token optimization: differentiated, but needs side-by-side examples in docs and demos so users feel the context savings immediately.
- Change impact: high leverage because it returns `verification_command`, generic `test_required`/`test_runner`/`test_command`, pytest compatibility fields, and a scoped `queue_ledger` that separates current-queue files from out-of-scope dirty files; future agents should follow that command for fast feedback, then run the full default suite before release when risk remains.

## Hard Requirements For Future Updates

- Every MCP tool change must include CLI parity in the same change.
- `tests/unit/test_agent_contracts.py` must pass before handoff; it guards pytest runtime, dependencies, MCP/CLI parity, and known Python warning-prone API patterns.
- `tests/unit/cli/test_mcp_commands.py` must pass after MCP-equivalent CLI changes; it guards delegated tool arguments, required file-path checks, and TOON output.
- `uv run pytest -q` is the default full-suite command and must remain under 5 minutes.
- Benchmark runs must stay explicit: `--benchmark-enable --benchmark-only -n 0 --session-timeout=0`.
- Every feature update must run the self-hosted workflow: `safe_to_edit` before risky edits, `file_health` on changed files, `change_impact` after edits, its reported `verification_command`, then the full default suite when risk remains.

## Next High-Value Work

1. Add richer routing examples for the first-class agent workflow pack. The workflow pack now exists in both CLI (`agent-workflow`) and MCP (`get_agent_workflow`) forms, exposes `current_phase`, `current_step`, `recommended_commands`, and `phase_order`, and routes agents from setup (`set`) to targeted file analysis (`analyze`) when a queue head already exists.
2. Turn the repeatable demo script into recorded evidence. `examples/agent_workflow_comparison_demo.py` now compares full-file reading with SMART workflow focused context on `examples/BigService.java`, can emit asciinema v2 JSONL with `--format cast`, and has a checked-in sample at `docs/assets/agent-workflow-comparison.cast`; next convert or host the cast as richer README media.
3. Turn `.agents/skills` into an inspectable project asset: `agent-skills` CLI plus `list_agent_skills` MCP inventory now list skills, read order, support files, scripts, context needs, side effects, completion guidance, and validation status with blocking/caution/optional gap counts. Current validation is ready; next add optional `AGENT-BRIEF.md` handoffs for the highest-value skills.
4. Harden the parser-readiness advisor. `parser-readiness` CLI plus `advise_parser_readiness` MCP now compare declared parser dependencies, plugin entry points, loader mappings, tests, golden masters, and wiki-inspired parser-risk signals. For installed parsers, the advisor now reports package version, project and maintenance URLs, local binding ABI, semantic version, packaged `grammar.json`, and scanner-file signals before leaving online maintenance as a follow-up. The first closed-loop use of that advisor promoted Swift from a declared parser candidate into a local language plugin with loader, entry point, detector, tests, and full-format golden-master coverage.
5. ~~Use `check_project_health` output to open focused refactoring slices for the current F-grade files, starting with low-coverage Language Plugin extractors and `api.py`.~~ **DONE 2026-05-23** via `tsa-refactor-queue` skill: intersects `check_project_health` × `tsa-temporal` churn × `codegraph_dead_code` × `codegraph_callers` blast radius into a deterministic top-N queue (ranking: `(1 - health/100) × log(1 + churn) × (dead_ratio + 0.1)`). See `.claude/skills/tsa-refactor-queue/SKILL.md`.
6. Decide a warning-as-error policy that is fast enough for daily agent work, then add it as a separate contract target.
