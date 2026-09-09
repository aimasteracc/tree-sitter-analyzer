#!/usr/bin/env python3
"""
Unit Tests for Trace Impact Tool

用模拟原生扫描结果验证 trace_impact MCP 工具。
"""

from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.tools.trace_impact_tool import TraceImpactTool


class TestTraceImpactToolBasic:
    """Basic functionality tests for trace_impact tool"""

    @pytest.fixture(autouse=True)
    def setup_tool(self, tmp_path):
        """为扫描边界提供真实且隔离的项目目录。"""
        self.tool = TraceImpactTool(project_root=str(tmp_path))
        self.project_dir = tmp_path

    def test_init(self):
        """Test tool initialization"""
        assert self.tool.project_root == str(self.project_dir)
        assert self.tool.language_detector is not None

    def test_get_tool_definition(self):
        """Test tool definition structure"""
        definition = self.tool.get_tool_definition()
        assert definition["name"] == "trace_impact"
        assert "description" in definition
        assert "inputSchema" in definition
        assert "symbol" in definition["inputSchema"]["properties"]
        assert definition["inputSchema"]["required"] == ["symbol"]

    def test_validate_arguments_valid(self):
        """Test argument validation with valid inputs"""
        valid_args = {
            "symbol": "processPayment",
            "file_path": "Service.java",
            "case_sensitive": False,
            "word_match": True,
            "max_results": 500,
            "exclude_patterns": ["**/test/**"],
        }
        # Should not raise
        result = self.tool.validate_arguments(valid_args)
        assert result is True

    def test_validate_arguments_missing_symbol(self):
        """Test argument validation with missing symbol"""
        invalid_args = {}
        with pytest.raises(ValueError, match="symbol parameter is required"):
            self.tool.validate_arguments(invalid_args)

    def test_validate_arguments_empty_symbol(self):
        """Test argument validation with empty symbol"""
        invalid_args = {"symbol": "   "}
        with pytest.raises(ValueError, match="symbol parameter is required"):
            self.tool.validate_arguments(invalid_args)

    def test_validate_arguments_invalid_file_path_type(self):
        """Test argument validation with invalid file_path type"""
        invalid_args = {"symbol": "test", "file_path": 123}
        with pytest.raises(ValueError, match="file_path must be a string"):
            self.tool.validate_arguments(invalid_args)

    def test_validate_arguments_invalid_case_sensitive_type(self):
        """Test argument validation with invalid case_sensitive type"""
        invalid_args = {"symbol": "test", "case_sensitive": "true"}
        with pytest.raises(ValueError, match="case_sensitive must be a boolean"):
            self.tool.validate_arguments(invalid_args)

    def test_validate_arguments_invalid_max_results(self):
        """Test argument validation with invalid max_results"""
        invalid_args = {"symbol": "test", "max_results": -1}
        with pytest.raises(ValueError, match="max_results must be a positive integer"):
            self.tool.validate_arguments(invalid_args)

    def test_validate_arguments_invalid_exclude_patterns_type(self):
        """Test argument validation with invalid exclude_patterns type"""
        invalid_args = {"symbol": "test", "exclude_patterns": "not a list"}
        with pytest.raises(ValueError, match="exclude_patterns must be an array"):
            self.tool.validate_arguments(invalid_args)


class TestTraceImpactToolExecution:
    """用模拟原生扫描结果验证执行逻辑"""

    @pytest.fixture(autouse=True)
    def setup_tool(self, tmp_path):
        """为扫描边界提供真实且隔离的项目目录。"""
        self.tool = TraceImpactTool(project_root=str(tmp_path))
        self.project_dir = tmp_path

    @pytest.mark.asyncio
    async def test_execute_no_matches(self):
        """Test execution when no matches are found"""
        # 模拟原生扫描没有命中
        with patch(
            "tree_sitter_analyzer.mcp.tools.trace_impact_tool.scan_symbol_lines"
        ) as mock_run:
            mock_run.return_value = []

            result = await self.tool.execute({"symbol": "nonexistent"})

            assert result["success"] is True
            assert result["symbol"] == "nonexistent"
            assert result["call_count"] == 0
            assert len(result["usages"]) == 0
            assert "No usages" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_with_matches(self):
        """Test execution with successful matches"""
        # 将原有命中样本转换为原生扫描结果
        json_output = b"""{"type":"match","data":{"path":{"text":"src/Service.java"},"line_number":23,"lines":{"text":"  processPayment(order);"},"submatches":[{"start":2,"end":16}]}}
{"type":"match","data":{"path":{"text":"src/Controller.java"},"line_number":45,"lines":{"text":"    result = processPayment(req);"},"submatches":[{"start":13,"end":27}]}}
"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.trace_impact_tool.scan_symbol_lines"
        ) as mock_run:
            mock_run.return_value = [
                {
                    "file": data["path"]["text"],
                    "line": data["line_number"],
                    "text": " ".join(data["lines"]["text"].split()),
                }
                for raw in json_output.splitlines()
                for data in [__import__("json").loads(raw)["data"]]
            ]

            result = await self.tool.execute({"symbol": "processPayment"})

            assert result["success"] is True
            assert result["symbol"] == "processPayment"
            assert result["call_count"] == 2
            assert len(result["usages"]) == 2
            assert result["usages"][0]["file"] == "src/Service.java"
            assert result["usages"][0]["line"] == 23
            assert "processPayment" in result["usages"][0]["context"]
            assert result["usages"][1]["file"] == "src/Controller.java"
            assert result["usages"][1]["line"] == 45

    @pytest.mark.asyncio
    async def test_execute_with_language_filtering(self):
        """Test execution with language filtering"""
        # Mock language detection
        with patch(
            "tree_sitter_analyzer.mcp.tools.trace_impact_tool.detect_language_from_file"
        ) as mock_detect:
            mock_detect.return_value = "java"

            with patch(
                "tree_sitter_analyzer.mcp.tools.trace_impact_tool.scan_symbol_lines"
            ) as mock_run:
                json_output = b"""{"type":"match","data":{"path":{"text":"Service.java"},"line_number":10,"lines":{"text":"test"},"submatches":[]}}"""
                mock_run.return_value = [
                    {
                        "file": data["path"]["text"],
                        "line": data["line_number"],
                        "text": " ".join(data["lines"]["text"].split()),
                    }
                    for raw in json_output.splitlines()
                    for data in [__import__("json").loads(raw)["data"]]
                ]

                result = await self.tool.execute(
                    {"symbol": "test", "file_path": "src/Service.java"}
                )

                assert result["success"] is True
                assert result["language"] == "java"
                assert result["filtered_by_language"] is True
                assert result["source_file"] == "src/Service.java"

    @pytest.mark.asyncio
    async def test_execute_with_max_results_truncation(self):
        """Test execution with max_results truncation"""
        # 模拟大量源码命中
        json_lines = []
        for i in range(150):
            json_lines.append(
                f'{{"type":"match","data":{{"path":{{"text":"File{i}.java"}},"line_number":{i},"lines":{{"text":"test"}},"submatches":[]}}}}'
            )
        json_output = "\n".join(json_lines).encode()

        with patch(
            "tree_sitter_analyzer.mcp.tools.trace_impact_tool.scan_symbol_lines"
        ) as mock_run:
            mock_run.return_value = [
                {
                    "file": data["path"]["text"],
                    "line": data["line_number"],
                    "text": " ".join(data["lines"]["text"].split()),
                }
                for raw in json_output.splitlines()
                for data in [__import__("json").loads(raw)["data"]]
            ]

            result = await self.tool.execute({"symbol": "test", "max_results": 50})

            assert result["success"] is True
            # call_count must reflect the TRUE total (150), not the display cap.
            # max_results=50 only limits the usages list, not the count.
            assert result["call_count"] == 150
            assert len(result["usages"]) == 50
            assert result["truncated"] is True

    @pytest.mark.asyncio
    async def test_execute_unavailable_root(self):
        """扫描根目录不可用时返回失败"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.trace_impact_tool.scan_symbol_lines"
        ) as mock_run:
            mock_run.side_effect = OSError("SOURCE_ROOT_UNAVAILABLE")

            result = await self.tool.execute({"symbol": "test"})

            assert result["success"] is False
            assert result["error"] == "SOURCE_ROOT_UNAVAILABLE"
            assert result["call_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        """Test execution timeout"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.trace_impact_tool.scan_symbol_lines"
        ) as mock_run:
            mock_run.side_effect = TimeoutError("SOURCE_SCAN_BUDGET_EXCEEDED")

            result = await self.tool.execute({"symbol": "test"})

            assert result["success"] is False
            assert result["error"] == "SOURCE_SCAN_BUDGET_EXCEEDED"
            assert result["call_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_with_multiple_roots(self):
        """只允许在已配置项目边界内选择多个扫描目录。"""
        roots = [self.project_dir / name for name in ("one", "two", "three")]
        for root in roots:
            root.mkdir()
        with patch(
            "tree_sitter_analyzer.mcp.tools.trace_impact_tool.scan_symbol_lines"
        ) as mock_run:
            mock_run.return_value = []

            result = await self.tool.execute(
                {
                    "symbol": "test",
                    "project_root": ",".join(str(root) for root in roots),
                }
            )

            assert result["success"] is True
            # 确认扫描器收到项目根目录
            assert mock_run.called


class TestTraceImpactToolLanguageDetection:
    """Test language detection and extension filtering"""

    @pytest.fixture(autouse=True)
    def setup_tool(self, tmp_path):
        """为扫描边界提供真实且隔离的项目目录。"""
        self.tool = TraceImpactTool(project_root=str(tmp_path))
        self.project_dir = tmp_path

    def test_get_extensions_for_language_java(self):
        """Test getting extensions for Java"""
        extensions = self.tool._get_extensions_for_language("java")
        assert ".java" in extensions
        # Note: .jsp maps to "jsp", not "java" in EXTENSION_MAPPING

    def test_get_extensions_for_language_python(self):
        """Test getting extensions for Python"""
        extensions = self.tool._get_extensions_for_language("python")
        assert ".py" in extensions
        assert ".pyw" in extensions

    def test_get_extensions_for_language_javascript(self):
        """Test getting extensions for JavaScript"""
        extensions = self.tool._get_extensions_for_language("javascript")
        assert ".js" in extensions
        assert ".mjs" in extensions
        assert ".cjs" in extensions
        # Note: .jsx maps to "jsx", not "javascript" in EXTENSION_MAPPING

    def test_get_extensions_for_language_unknown(self):
        """Test getting extensions for unknown language"""
        extensions = self.tool._get_extensions_for_language("unknown")
        assert len(extensions) == 0


class TestR37sImpactGuidanceGrammar:
    """r37s dogfood: ``_get_impact_level`` emitted ``"3 caller(s) found"`` —
    the ``(s)`` placeholder is for ambiguous plurality, but we KNOW the
    count here. Renders proper English singular/plural.
    """

    def test_low_impact_single_caller_uses_singular(self):
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import (
            _get_impact_level,
        )

        info = _get_impact_level(1)
        assert info["level"] == "low"
        assert "1 caller found" in info["guidance"]
        assert "caller(s)" not in info["guidance"]

    def test_low_impact_multiple_callers_uses_plural(self):
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import (
            _get_impact_level,
        )

        info = _get_impact_level(3)
        assert info["level"] == "low"
        assert "3 callers found" in info["guidance"]
        assert "caller(s)" not in info["guidance"]

    def test_low_impact_five_callers_uses_plural(self):
        """5 is still ``low`` per the existing bucket (count <= 5)."""
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import (
            _get_impact_level,
        )

        info = _get_impact_level(5)
        assert info["level"] == "low"
        assert "5 callers found" in info["guidance"]


def test_trace_rejects_outside_project_root(tmp_path):
    # 2026-09-09：调用参数不得覆盖已配置的项目边界。
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ValueError):
        TraceImpactTool(str(project))._resolve_search_roots(str(outside))


def test_trace_rejects_empty_root_component(tmp_path):
    with pytest.raises(ValueError, match="SOURCE_ROOT_EMPTY"):
        TraceImpactTool(str(tmp_path))._resolve_search_roots(str(tmp_path) + ",")


def test_display_hard_cap_keeps_complete_count():
    from tree_sitter_analyzer.mcp.tools.trace_impact_tool import _truncate_for_display

    matches = list(range(10001))
    displayed, truncated = _truncate_for_display(matches, 1000000)
    assert displayed == list(range(10000))
    assert truncated is True
    assert len(matches) == 10001
