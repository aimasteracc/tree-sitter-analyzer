"""
Unit tests for UniversalAnalyzeTool — metric extraction and regression findings.

Tests for universal_analyze tool which provides code analysis
across multiple programming languages with automatic language detection.
"""

from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import UniversalAnalyzeTool


@pytest.fixture
def tool():
    """Create a UniversalAnalyzeTool instance for testing."""
    return UniversalAnalyzeTool()


class TestUniversalAnalyzeToolExtractBasicMetrics:
    """Tests for _extract_basic_metrics method."""

    def test_extract_basic_metrics_empty_elements(self, tool):
        """Test extracting basic metrics with empty elements."""
        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.line_count = 100
        mock_analysis_result.get_statistics = MagicMock(return_value={})

        metrics = tool._extract_basic_metrics(mock_analysis_result)
        assert "metrics" in metrics
        assert metrics["metrics"]["elements"]["classes"] == 0
        assert metrics["metrics"]["elements"]["methods"] == 0
        assert metrics["metrics"]["elements"]["fields"] == 0
        assert metrics["metrics"]["elements"]["imports"] == 0

    def test_extract_basic_metrics_with_elements(self, tool):
        """Test extracting basic metrics with elements."""
        mock_class = MagicMock()
        mock_class.element_type = "class"

        mock_method = MagicMock()
        mock_method.element_type = "function"

        mock_field = MagicMock()
        mock_field.element_type = "variable"

        mock_import = MagicMock()
        mock_import.element_type = "import"

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = [
            mock_class,
            mock_method,
            mock_field,
            mock_import,
        ]
        mock_analysis_result.line_count = 100
        mock_analysis_result.get_statistics = MagicMock(return_value={})
        mock_analysis_result.annotations = []
        mock_analysis_result.package = None

        metrics = tool._extract_basic_metrics(mock_analysis_result)
        assert metrics["metrics"]["elements"]["classes"] == 1
        assert metrics["metrics"]["elements"]["methods"] == 1
        assert metrics["metrics"]["elements"]["fields"] == 1
        assert metrics["metrics"]["elements"]["imports"] == 1


class TestUniversalAnalyzeToolExtractDetailedMetrics:
    """Tests for _extract_detailed_metrics method."""

    def test_extract_detailed_metrics_includes_complexity(self, tool):
        """Test detailed metrics include complexity information."""
        mock_method = MagicMock()
        mock_method.element_type = "function"
        mock_method.complexity_score = 10

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = [mock_method]
        mock_analysis_result.line_count = 100
        mock_analysis_result.get_statistics = MagicMock(return_value={})
        mock_analysis_result.annotations = []

        metrics = tool._extract_detailed_metrics(mock_analysis_result)
        assert "complexity" in metrics["metrics"]
        assert metrics["metrics"]["complexity"]["total"] == 10


class TestUniversalAnalyzeToolExtractStructureInfo:
    """Tests for _extract_structure_info method."""

    def test_extract_structure_info_empty(self, tool):
        """Test extracting structure info with empty elements."""
        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.package = None

        structure = tool._extract_structure_info(mock_analysis_result)
        assert structure["structure"]["classes"] == []
        assert structure["structure"]["methods"] == []
        assert structure["structure"]["fields"] == []
        assert structure["structure"]["imports"] == []

    def test_extract_structure_info_with_classes(self, tool):
        """Test extracting structure info with class elements."""
        mock_class = MagicMock()
        mock_class.element_type = "class"
        mock_class.name = "TestClass"
        mock_class.to_summary_item = MagicMock(return_value={"name": "TestClass"})

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = [mock_class]
        mock_analysis_result.package = None
        mock_analysis_result.annotations = []

        structure = tool._extract_structure_info(mock_analysis_result)
        assert len(structure["structure"]["classes"]) == 1
        assert structure["structure"]["classes"][0]["name"] == "TestClass"


class TestUniversalAnalyzeToolExtractUniversalBasicMetrics:
    """Tests for _extract_universal_basic_metrics method."""

    def test_extract_universal_basic_metrics_empty(self, tool):
        """Test extracting universal basic metrics with empty elements."""
        analysis_dict = {"elements": [], "line_count": 100}

        metrics = tool._extract_universal_basic_metrics(analysis_dict)
        assert "metrics" in metrics
        assert metrics["metrics"]["elements"]["classes"] == 0
        assert metrics["metrics"]["elements"]["methods"] == 0

    def test_extract_universal_basic_metrics_with_elements(self, tool):
        """Test extracting universal basic metrics with elements."""
        mock_class = MagicMock()
        mock_class.element_type = "class"

        mock_method = MagicMock()
        mock_method.element_type = "function"

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = [mock_class, mock_method]
        mock_analysis_result.line_count = 100
        mock_analysis_result.get_statistics = MagicMock(return_value={})

        metrics = tool._extract_basic_metrics(mock_analysis_result)
        assert metrics["metrics"]["elements"]["classes"] == 1
        assert metrics["metrics"]["elements"]["methods"] == 1


class TestUniversalAnalyzeToolExtractUniversalDetailedMetrics:
    """Tests for _extract_universal_detailed_metrics method."""

    def test_extract_universal_detailed_metrics_with_query_results(self, tool):
        """Test extracting universal detailed metrics with query results."""
        analysis_dict = {"elements": [], "line_count": 100, "query_results": {}}

        metrics = tool._extract_universal_detailed_metrics(analysis_dict)
        assert "query_results" in metrics


class TestUniversalAnalyzeToolExtractUniversalStructureInfo:
    """Tests for _extract_universal_structure_info method."""

    def test_extract_universal_structure_info(self, tool):
        """Test extracting universal structure info."""
        analysis_dict = {
            "elements": [],
            "line_count": 100,
            "structure": {},
            "queries_executed": [],
        }

        structure = tool._extract_universal_structure_info(analysis_dict)
        assert "structure" in structure
        assert "queries_executed" in structure


class TestUniversalAnalyzeToolGetAvailableQueries:
    """Tests for _get_available_queries method."""

    @pytest.mark.asyncio
    async def test_get_available_queries_java(self, tool):
        """Test getting available queries for Java."""
        result = await tool._get_available_queries("java")
        assert "language" in result
        assert result["language"] == "java"
        assert "queries" in result

    @pytest.mark.asyncio
    async def test_get_available_queries_python(self, tool):
        """Test getting available queries for Python."""
        mock_engine = MagicMock()
        mock_engine.get_supported_languages = MagicMock(
            return_value=["python", "javascript"]
        )
        tool.analysis_engine = mock_engine

        result = await tool._get_available_queries("python")
        assert "language" in result
        assert result["language"] == "python"
        assert "queries" in result
        assert "count" in result


class TestUniversalAnalyzeFindings:
    """Regression tests for round-16b dogfood findings 1 and 2."""

    @pytest.mark.asyncio
    async def test_universal_analyze_envelope_includes_success_and_summary(
        self, tmp_path
    ):
        """Finding 2: response must carry success, summary_line, agent_summary.

        Round-16b dogfood showed the response keys were limited to the
        analysis payload (classes/methods/metrics/...) with no canonical
        envelope fields. This regression guards against that shape
        regressing.
        """
        sample = tmp_path / "sample.py"
        sample.write_text(
            '''"""Sample module."""

# A single line comment
def hello(name: str) -> str:
    """Return greeting."""
    return f"Hello, {name}!"


# Another comment

class Greeter:
    pass
''',
            encoding="utf-8",
        )

        tool = UniversalAnalyzeTool(project_root=str(tmp_path))
        result = await tool.execute({"file_path": str(sample), "output_format": "json"})

        assert result["success"] is True, "Finding 2: success must be present"
        sl = result.get("summary_line")
        assert isinstance(sl, str) and sl, (
            "Finding 2: summary_line must be a non-empty string"
        )
        agent_summary = result.get("agent_summary")
        assert isinstance(agent_summary, dict), (
            "Finding 2: agent_summary must be a populated dict"
        )
        assert agent_summary.get("summary_line") == sl, (
            "Finding 2: agent_summary.summary_line must mirror top-level"
        )
        assert agent_summary.get("next_step"), (
            "Finding 2: agent_summary.next_step must be non-empty"
        )

    @pytest.mark.asyncio
    async def test_universal_analyze_counts_comments_and_blanks(self, tmp_path):
        """Finding 1: comment/blank line counts must match analyze_scale.

        Previously hardcoded ``lines_comment=0``/``lines_blank=0`` and copied
        ``lines_total`` into ``lines_code``. We now classify lines via
        :func:`compute_file_metrics` — so the universal-analyze counts
        agree with the analyze_scale counts on the same file. This test
        cross-checks them against each other rather than pinning exact
        numbers (the line classifier's treatment of trailing blank lines
        and shebangs varies).
        """
        from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import (
            AnalyzeScaleTool,
        )

        sample = tmp_path / "sample.py"
        sample.write_text(
            "# header comment\n"
            "# another comment\n"
            "\n"
            "def f():\n"
            "    return 1\n"
            "\n"
            "# trailing comment\n"
            "x = 2\n"
            "y = 3\n",
            encoding="utf-8",
        )

        u = UniversalAnalyzeTool(project_root=str(tmp_path))
        u_res = await u.execute({"file_path": str(sample), "output_format": "json"})
        u_metrics = u_res["metrics"]

        s = AnalyzeScaleTool(project_root=str(tmp_path))
        s_res = await s.execute({"file_path": str(sample), "output_format": "json"})
        s_metrics = s_res["file_metrics"]

        # Round-16b finding 1: the comment and blank counts produced by
        # universal_analyze were ``0``/``0`` even though analyze_scale
        # reported the real numbers. Now they must agree.
        assert u_metrics["lines_comment"] == s_metrics["comment_lines"], (
            f"comment count mismatch: universal={u_metrics['lines_comment']} "
            f"vs analyze_scale={s_metrics['comment_lines']}"
        )
        assert u_metrics["lines_blank"] == s_metrics["blank_lines"], (
            f"blank count mismatch: universal={u_metrics['lines_blank']} "
            f"vs analyze_scale={s_metrics['blank_lines']}"
        )
        assert u_metrics["lines_code"] == s_metrics["code_lines"], (
            f"code count mismatch: universal={u_metrics['lines_code']} "
            f"vs analyze_scale={s_metrics['code_lines']}"
        )
        # Sanity: counts are non-trivial — fix actually exercised.
        assert u_metrics["lines_comment"], (
            "Finding 1: comment count is still 0 — hardcoded bug regressed"
        )
        assert u_metrics["lines_blank"], (
            "Finding 1: blank count is still 0 — hardcoded bug regressed"
        )
        assert u_metrics["lines_code"] != u_metrics["lines_total"], (
            "Finding 1: lines_code == lines_total — fix regressed"
        )
