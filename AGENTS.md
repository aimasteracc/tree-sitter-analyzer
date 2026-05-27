# Agent Instructions

> **Discovery path**: read this file → skim [`CLAUDE.md`](CLAUDE.md) for the locked design decisions → load only the [`docs/CODEMAPS/`](docs/CODEMAPS/) map matching the area you're touching. Do **not** load the full source tree blindly — the codemaps exist to keep agent context lean.

## Codemap Index

| Area | Codemap |
|---|---|
| High-level topology | [`docs/CODEMAPS/architecture.md`](docs/CODEMAPS/architecture.md) |
| MCP tools (count in codemap) | [`docs/CODEMAPS/mcp-tools.md`](docs/CODEMAPS/mcp-tools.md) |
| CLI flags / commands | [`docs/CODEMAPS/cli.md`](docs/CODEMAPS/cli.md) |
| Language plugins (count in codemap) | [`docs/CODEMAPS/languages.md`](docs/CODEMAPS/languages.md) |
| Output formatters | [`docs/CODEMAPS/formatters.md`](docs/CODEMAPS/formatters.md) |
| Security boundary | [`docs/CODEMAPS/security.md`](docs/CODEMAPS/security.md) |

## Test Runtime Contract

- The default full-suite command is `uv run pytest -q`.
- Do not run the full suite serially. Project pytest config enables xdist with `--numprocesses=auto --dist=loadfile`.
- The full suite must finish in under 5 minutes. The config enforces `--session-timeout=600` and `--timeout=180`. (Bumped from 300 in v1.13.1 — see `docs/POSTMORTEM_v1.13.md` § 9.)
- After edits, run `uv run python -m tree_sitter_analyzer --change-impact --format json` and follow its `verification_command`.
- If `test_required` is `false`, do not run tests just to look busy; run the reported non-test verification such as `git diff --check`.
- For targeted code feedback, prefer `verification_command`/`test_command`; `pytest_required` and `pytest_command` are retained for pytest-specific compatibility.
- For PRs that change Python source, run focused tests with `--cov=tree_sitter_analyzer --cov-report=json`, then run `uv run python scripts/check_patch_coverage.py --base origin/develop --coverage-json coverage.json` before pushing. The local patch gate must report no added executable misses; add effective tests instead of waiting for CI Codecov to block the PR.
- Benchmark-only runs are the exception: use `uv run pytest tests/benchmarks/ --benchmark-enable --benchmark-only -n 0 --session-timeout=0`.
- Do not remove or weaken these pytest defaults. They prevent repeated agent mistakes: serial full-suite runs, accidental benchmark execution, hidden hangs, and >5 minute feedback loops.
- If a test-runtime setting must change, update `tests/unit/test_agent_contracts.py`, explain why the new setting is faster or safer, and prove `uv run pytest -q` still finishes under 5 minutes.

## CI Test Tier Contract

- CI must not run exhaustive all-language golden/regression tests on every OS/Python axis. Mark that class with `@pytest.mark.full_language`.
- `.github/workflows/reusable-test.yml` runs `full_language` tests only on the single Linux coverage axis; every no-coverage matrix job must exclude `not full_language`.
- PR feedback uses `matrix-profile: pr` to run a small representative matrix (Linux coverage/full-language, Linux latest Python, Windows, macOS). Release/hotfix/push validation must keep `matrix-profile: full`.
- `.github/workflows/test-coverage.yml` is manual-only because reusable-test already uploads coverage on the Linux coverage axis. Do not re-enable PR/push triggers unless reusable-test coverage is removed in the same change.
- `.github/workflows/ci.yml` owns ordinary PR routing through `scripts/ci_route.py` and `config/ci-routing.yml`. Expensive optional checks such as regression, SQL platform compatibility, benchmarks, and broad E2E must be path-routed or manual/scheduled instead of running unconditionally on every PR.
- For language-plugin changes, rely on `--change-impact --change-impact-scope ...` during development, run the focused command it reports, then let CI's single full-language axis provide the final cross-language golden gate.

## Agent Dogfood Feedback Loop

For non-trivial work, expert agents must use this project as their primary feedback instrument while they work, then preserve the learning in memory:

1. **Before edits:** run `uv run python -m tree_sitter_analyzer --change-impact --format json` to get the affected surface and verification command.
2. **During exploration:** prefer TSA queries over blind file scans. Use focused codegraph/query/health commands for the area being changed, and keep the raw command outputs small enough to compare before/after.
3. **After edits:** rerun change-impact and the reported verification command. For Python source changes, also run the local patch coverage gate from the Test Runtime Contract.
4. **Memory capture:** store a concise JSON record in project memory with `branch`, `task`, `tools_used`, `signals`, `decision`, `verification`, and `followups`. Use the available `memory_store` MCP when present; otherwise use the Claude Flow memory CLI (`npx @claude-flow/cli@latest memory store --namespace tsa/agent-feedback ...`). If neither memory backend is available, include the JSON in the final response so the lead can store it.

Memory records should capture reusable lessons, not logs: benchmark surprises, Codecov/CI failure patterns, query misses, performance bottlenecks, and successful verification recipes.

## MCP/CLI Parity Contract

- Every registered MCP tool must have a CLI access path.
- Main CLI flags and standalone scripts are guarded by `tests/unit/test_agent_contracts.py`.
- MCP-equivalent CLI handler arguments, required file-path checks, and TOON output are guarded by `tests/unit/cli/test_mcp_commands.py`.
- When adding or changing an MCP tool, update the CLI path in the same change and run a real CLI smoke test, for example `uv run python -m tree_sitter_analyzer <file> --smart-context --format json`.
- This keeps MCP-only features from becoming invisible to users, CI, and future agents.

## Codemap-sync mandate

Any change touching one of these registries MUST update the corresponding `docs/CODEMAPS/*.md` in the **same commit**:

| Registry file | Codemap |
|---|---|
| `tree_sitter_analyzer/mcp/_tool_registry.py` | `docs/CODEMAPS/mcp-tools.md` |
| `tree_sitter_analyzer/cli/argument_parser_builder.py` | `docs/CODEMAPS/cli.md` |
| `tree_sitter_analyzer/languages/<lang>_plugin/*` | `docs/CODEMAPS/languages.md` |
| `tree_sitter_analyzer/formatters/*` | `docs/CODEMAPS/formatters.md` |

Enforced by:
- `scripts/codemap-sync-check.sh` (pre-commit hook + Claude PreToolUse soft-nag)
- `test_registered_mcp_tools_have_codemap_parity` in `tests/unit/test_agent_contracts.py`

Escape hatch for intentional rename/rebase: `SKIP_CODEMAP_SYNC=1 git commit ...`. The pytest test still runs in CI as the final safety net — bypass is local-only.

Why: previously the codemap drifted from 23 → 27 → 30 → 55 tools across 4 months with manual catch-up commits in between. The agent contract is now self-enforcing.

## GitFlow Branching Mandate

**Hard requirement.** Every branch operation MUST follow [`GITFLOW.md`](GITFLOW.md) ([中文](GITFLOW_zh.md) / [日本語](GITFLOW_ja.md)). The matrix below is the full surface — anything else is a violation.

| Operation | Branch name | Cut from | Target (via PR) |
|---|---|---|---|
| Feature | `feature/<name>` | `develop` | `develop` |
| Release prep | `release/v<X.Y.Z>` | `develop` | `main` **and back into** `develop` |
| Production hotfix | `hotfix/<name>` | `main` | `main` **and back into** `develop` |
| Chore / docs / test (non-release) | `chore/<name>` · `docs/<name>` · `test/<name>` · `fix/<name>` | `develop` | `develop` |

**Agents MUST NEVER:**
- Push directly to `main` or `develop` — open a PR from a properly-named branch instead
- Open a PR targeting `main` from anything other than `release/v*` or `hotfix/*`
- Cut a `feature/*` from `main` — it must come from `develop`
- Force-push or delete `main`, `develop`, or any released tag (`v*`)
- Skip the `develop` merge-back after a release or hotfix is published
- **Use `hotfix/*` for non-release fixes.** Pushing to `hotfix/*` auto-triggers `hotfix-automation.yml` → PyPI publish with a version bump. Reserve `hotfix/*` for "production is broken, needs a same-day patch release". For a generic bug fix, CI YAML repair, workflow tweak, etc., use `fix/*` · `ci/*` · `chore/*` against `develop`.

**Release flow (every detail in [`GITFLOW.md`](GITFLOW.md)):**
1. `release/v<X.Y.Z>` cut from `develop`
2. Push triggers `.github/workflows/release-automation.yml` → test → build → publish to PyPI
3. After PyPI is live: PR `release/v*` → `main`, tag `v<X.Y.Z>` on main, GitHub Release
4. Merge `release/v*` → `develop` to bring back release-prep commits (version bumps, CHANGELOG)
5. Delete `release/v<X.Y.Z>` from origin

**Enforcement layers:**
- `.github/workflows/gitflow-guard.yml` — CI fails on a PR whose head→base pair violates the matrix
- GitHub branch protection on `main` (PR + status checks required, no force-push)
- `test_gitflow_documentation_is_present` in `tests/unit/test_agent_contracts.py` — guards against `GITFLOW.md` being deleted or `AGENTS.md` losing the link

Escape hatch: none. If GITFLOW.md itself needs to change, that's a PR like any other — argue the case in the description and update the matrix + tests in the same commit.

## Anti-Patterns (from v1.13 postmortem)

These are failure modes the project has *already paid for* during the v1.13.0 / v1.13.1 release lifecycle. The full incident catalogue is in [`docs/POSTMORTEM_v1.13.md`](docs/POSTMORTEM_v1.13.md). The rules below are the standing defense — break them and you reintroduce a documented bug.

**Each rule cites a postmortem section so you can read the original incident.**

1. **No skip-and-paper-over.** Every new `pytest.skip*` MUST include a tracking reference in its `reason=` text — issue number (`#123` / `GH-123`), `POSTMORTEM`, or `tracked: ...`. The `test_skips_have_tracking_references` contract enforces a soft budget; new untracked skips push you over it. (Postmortem § 1.)

2. **YAML/Actions changes go through `actionlint`.** Edits to `.github/workflows/*.yml` or `.github/actions/**/action.yml` are validated by the `actionlint` pre-commit hook. Don't bypass it with `--no-verify`; fix the actual lint. (Postmortem § 3, § 4.)

3. **`shell: powershell` blocks are ASCII-only.** The `scripts/check_ps_ascii.py` pre-commit hook fails commits that put emoji/Unicode inside an inline Windows PowerShell `run:` block. If you really need Unicode, switch the step to `shell: pwsh` (PowerShell Core, UTF-8 by default). (Postmortem § 5.)

4. **tree-sitter grammar snapshots regen on Linux only.** The `tree-sitter-c-sharp 0.23.1` wheel ships different compiled grammars per OS (macOS: 229 csharp nodes; Linux: 234, including C# 12 collection-expression nodes). Always commit snapshots produced on Linux CI / a Linux container — never from a local mac. (Postmortem § 6.)

5. **Before using a 3.11+ stdlib symbol, check the floor.** `requires-python = ">=3.10"` is the contract. `tomllib`, `from datetime import UTC`, `typing.Self`, structural-pattern-match exhaustiveness checks, etc. are 3.11+ and break the Py3.10 matrix silently. The `test_python_version_floor_is_consistent` contract guards the ruff/mypy/pyproject alignment. (Postmortem § 7.)

6. **`develop` must not rot behind `main`.** Before merging `release/v*` back into develop, run `git log --oneline develop..main` and verify nothing on main is being orphaned. If develop has fallen far behind, fast-forward / rebuild it from main before the merge-back. (Postmortem § 8.)

7. **Release-prep PRs >30 commits: prefer rebase-merge over squash.** Squashing a large consolidation PR makes `git bisect` useless on main for every bug it introduced. Use squash only for short feature PRs. (Postmortem § 10.)

8. **Never lower `--maxfail` or `--session-timeout` in pytest config.** v1.13 release CI repeatedly capped failures at 10 while the actual count was ~85, forcing multi-hour debug cycles. `--maxfail=200` + `--session-timeout=600` are the locked floors; `test_default_pytest_runtime_contract_is_locked` enforces them. (Postmortem § 9.)

These rules are guarded by tests in `tests/unit/test_agent_contracts.py`:

- `test_postmortem_v1_13_doc_exists`
- `test_agents_md_documents_v1_13_anti_patterns`
- `test_check_ps_ascii_script_is_present_and_pre_commit_wired`
- `test_actionlint_is_wired_into_pre_commit`
- `test_no_powershell_blocks_contain_non_ascii`
- `test_skips_have_tracking_references`
- `test_python_version_floor_is_consistent`
- `test_default_pytest_runtime_contract_is_locked` (also guards rule 8)
- `test_readme_mcp_tool_count_matches_registry`

Why these are at the bottom of AGENTS.md: they're the rules an agent is most likely to *forget* on a fast cycle, and the cost of forgetting each was measured in CI hours during v1.13. Keep them visible.
