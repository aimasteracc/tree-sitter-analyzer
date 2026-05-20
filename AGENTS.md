# Agent Instructions

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
