## 任务拆解 (Work Breakdown Structure)

### T1: Add quality-compliant docstrings to public test methods
- Objective: Satisfy scripts/check_code_quality.py requirements.
- Acceptance Criteria:
  - Each public test method docstring includes Args/Returns/Note sections.
  - Quality score >= 90.
- Status: in_progress
- Files to Modify: tests/unit/test_analysis_engine.py

### T2: Reduce diagnostics (Any/private usage)
- Objective: Reduce LSP diagnostics to zero for test file.
- Acceptance Criteria:
  - Replace MagicMock/AsyncMock with CallSpy/AsyncCallSpy where feasible.
  - Avoid direct private attribute access when possible.
  - Replace analysis_engine.os monkeypatching with os/pathlib patches.
- Status: pending
- Files to Modify: tests/unit/test_analysis_engine.py

### T3: Verification
- Objective: Ensure tests pass and diagnostics are clean.
- Acceptance Criteria:
  - lsp_diagnostics reports clean for tests/unit/test_analysis_engine.py.
  - uv run pytest tests/unit/test_analysis_engine.py -v passes.
  - python scripts/check_code_quality.py tests/unit/test_analysis_engine.py >= 90.
- Status: pending
- Files to Modify: none
