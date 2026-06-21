# High-Risk Diff Review

Measured on 2026-06-20 from the current working branch.

## Highest-Risk Items

1. Full-suite verification currently times out on Windows.
   - Command: `uv run pytest -q`
   - Observed result: process-level timeout after 10 minutes.
   - Follow-up signal: timed-out runs left `pytest`, `fd.exe`, and MCP server
     child processes behind. The named force-refresh tests passed when run
     directly, so the remaining risk is full-suite orchestration or cleanup
     under xdist rather than a single deterministic failing assertion.

2. The diff is very large.
   - Current change-impact result: `changed=212`, `risk=high`.
   - Most touched files are tests whose assertions were strengthened, but the
     blast radius still requires careful review because review tools and humans
     must inspect many small assertion edits.

3. The weak-assertion gate is now a shared CI/pre-commit control.
   - Changed files: `scripts/check_loose_assertions.py`,
     `scripts/check_loose_assertions.sh`, `.pre-commit-config.yaml`, and
     `.github/workflows/reusable-quality.yml`.
   - A Windows locale bug was found and fixed by decoding git diff output as
     UTF-8 with replacement.

4. Baseline docs changed substantially.
   - Authoritative current baseline: 171 weak assertions.
   - Category split: 130 placeholder, 30 loose-bound, 10 tautology, 1 optional
     dependency.
   - This is a ratchet baseline, not permission to add new weak assertions.

5. One production file changed only for punctuation style.
   - File: `tree_sitter_analyzer/cli/argument_groups/_analysis_graph_nav.py`
   - Risk: low functional risk, but it is still production code and should be
     explicitly reviewed because the task is otherwise test-architecture work.

## Verified

- `uv run python scripts/check_loose_assertions.py origin/develop`
- `uv run python scripts/check_loose_assertions.py --baseline`
- `uv run pytest -q tests/unit/test_check_loose_assertions.py -q`
- `uv run pytest -q tests/unit/test_check_loose_assertions.py tests/contracts/test_pytest_runtime_contract.py tests/governance/test_postmortem_guards.py -q`
- `git diff --check`

## Not Yet Green

- `uv run pytest -q` did not finish within the 10-minute local command window.
