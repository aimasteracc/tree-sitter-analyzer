## 现状分析 (Current State Analysis)
- tests/unit/test_analysis_engine.py is the only target file for changes.
- Unit tests rely heavily on MagicMock/AsyncMock and private attribute access.
- BasedPyright diagnostics are noisy; current file uses pyright ignore headers.
- Quality checker (scripts/check_code_quality.py) reports 0/100 due to missing docstring sections on public test methods.

## 问题识别 (Problem Identification)
- Public test methods lack required docstring sections (Args/Returns/Note).
- Excessive Any/private usage in tests creates diagnostics.
- Some monkeypatching targets analysis_engine.os instead of os.

## 目标定义 (Goals & Objectives)
- Bring scripts/check_code_quality.py score to >= 90 for the test file.
- Reduce lsp_diagnostics to clean for tests/unit/test_analysis_engine.py.
- Keep tests unit-only with mocks; avoid real filesystem I/O.
- Avoid source code changes; modify tests only.

## 非功能性要求 (Non-functional Requirements)
- Maintain existing test behavior (81 tests passing).
- Preserve readable, consistent documentation format.
- Windows path compatibility.

## 用例场景 (Use Cases)
- Running `uv run pytest tests/unit/test_analysis_engine.py -v` succeeds.
- Running `python scripts/check_code_quality.py tests/unit/test_analysis_engine.py` returns >= 90.
- LSP diagnostics report no errors/warnings for the test file.

## 术语表 (Glossary)
- LSP Diagnostics: Static analysis warnings/errors from language server.
- Quality Checker: scripts/check_code_quality.py enforcement tool.
- Call Spy: Lightweight object recording calls without MagicMock.
