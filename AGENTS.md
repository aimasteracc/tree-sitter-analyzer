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
- The full suite must finish in under 5 minutes. The config enforces `--session-timeout=300` and `--timeout=180`.
- After edits, run `uv run python -m tree_sitter_analyzer --change-impact --format json` and follow its `verification_command`.
- If `test_required` is `false`, do not run tests just to look busy; run the reported non-test verification such as `git diff --check`.
- For targeted code feedback, prefer `verification_command`/`test_command`; `pytest_required` and `pytest_command` are retained for pytest-specific compatibility.
- Benchmark-only runs are the exception: use `uv run pytest tests/benchmarks/ --benchmark-enable --benchmark-only -n 0 --session-timeout=0`.
- Do not remove or weaken these pytest defaults. They prevent repeated agent mistakes: serial full-suite runs, accidental benchmark execution, hidden hangs, and >5 minute feedback loops.
- If a test-runtime setting must change, update `tests/unit/test_agent_contracts.py`, explain why the new setting is faster or safer, and prove `uv run pytest -q` still finishes under 5 minutes.

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
