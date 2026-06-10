"""Scale/universal analyze tools must honor the engine's parse-failure flag
on their Java code-paths instead of masking it as an empty-success result.

Follow-up to PR #414 (Theme-D). The structure facade was fixed there; this
covers the same masking class in the Java branches of:
  - ``analyze_scale_tool.AnalyzeScaleTool._run_structural_analysis``
  - ``universal_analyze_tool.UniversalAnalyzeTool._analyze_advanced``

Both only checked ``result is None`` and then proceeded, so a
``AnalysisResult(success=False, ...)`` from the engine was stamped
``success: True`` with zero counts. The Java grammar is installed, so this is
only reachable by a real engine failure (read error, etc.) — exercised here by
mocking the engine to return ``success=False``.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.models.result import AnalysisResult


def _failed_result() -> AnalysisResult:
    return AnalysisResult(
        file_path="examples/Sample.java",
        language="java",
        success=False,
        error_message="Failed to parse file: examples/Sample.java",
        elements=[],
    )


@pytest.mark.asyncio
async def test_scale_tool_java_path_honors_parse_failure() -> None:
    from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool

    tool = AnalyzeScaleTool(project_root=".")

    async def _fake_analyze(_request):  # noqa: ANN001
        return _failed_result()

    tool.analysis_engine.analyze = _fake_analyze  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        await tool._run_structural_analysis(
            "examples/Sample.java", "java", include_details=True
        )


@pytest.mark.asyncio
async def test_universal_tool_advanced_path_honors_parse_failure() -> None:
    from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import (
        UniversalAnalyzeTool,
    )

    tool = UniversalAnalyzeTool(project_root=".")

    async def _fake_analyze(_request):  # noqa: ANN001
        return _failed_result()

    tool.analysis_engine.analyze = _fake_analyze  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        await tool._analyze_advanced("examples/Sample.java", "java", "structure", {})
