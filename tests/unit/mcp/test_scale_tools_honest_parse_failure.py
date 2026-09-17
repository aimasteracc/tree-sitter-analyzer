"""规模分析工具必须传播 Java 解析失败，不能伪装成空的成功结果。"""

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
