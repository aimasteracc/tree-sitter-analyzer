#!/usr/bin/env python3
"""
Unit Tests for Trace Impact Tool

Tests the trace_impact MCP tool using mocks (no real ripgrep execution).
"""

from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.tools.trace_impact_tool import TraceImpactTool


class TestTraceImpactToolBasic:
    """Basic functionality tests for trace_impact tool"""

    def setup_method(self):
        """Set up test fixtures"""
        self.tool = TraceImpactTool(project_root="/test/project")

    def test_init(self):
        """Test tool initialization"""
        assert self.tool.project_root == "/test/project"
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
    """Test trace_impact execution with mocked ripgrep"""

    def setup_method(self):
        """Set up test fixtures"""
        self.tool = TraceImpactTool(project_root="/test/project")

    @pytest.mark.asyncio
    async def test_execute_no_matches(self):
        """Test execution when no matches are found"""
        # Mock ripgrep returning no matches (rc=1)
        with patch(
            "tree_sitter_analyzer.mcp.tools.trace_impact_tool.run_command_capture"
        ) as mock_run:
            mock_run.return_value = (1, b"", b"")

            result = await self.tool.execute({"symbol": "nonexistent"})

            assert result["success"] is True
            assert result["symbol"] == "nonexistent"
            assert result["call_count"] == 0
            assert len(result["usages"]) == 0
            assert "No usages" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_with_matches(self):
        """Test execution with successful matches"""
        # Mock ripgrep JSON output with matches
        json_output = b"""{"type":"match","data":{"path":{"text":"src/Service.java"},"line_number":23,"lines":{"text":"  processPayment(order);"},"submatches":[{"start":2,"end":16}]}}
{"type":"match","data":{"path":{"text":"src/Controller.java"},"line_number":45,"lines":{"text":"    result = processPayment(req);"},"submatches":[{"start":13,"end":27}]}}
"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.trace_impact_tool.run_command_capture"
        ) as mock_run:
            mock_run.return_value = (0, json_output, b"")

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
                "tree_sitter_analyzer.mcp.tools.trace_impact_tool.run_command_capture"
            ) as mock_run:
                json_output = b"""{"type":"match","data":{"path":{"text":"Service.java"},"line_number":10,"lines":{"text":"test"},"submatches":[]}}"""
                mock_run.return_value = (0, json_output, b"")

                result = await self.tool.execute({
                    "symbol": "test",
                    "file_path": "src/Service.java"
                })

                assert result["success"] is True
                assert result["language"] == "java"
                assert result["filtered_by_language"] is True
                assert result["source_file"] == "src/Service.java"

    @pytest.mark.asyncio
    async def test_execute_with_max_results_truncation(self):
        """Test execution with max_results truncation"""
        # Mock ripgrep with many matches
        json_lines = []
        for i in range(150):
            json_lines.append(
                f'{{"type":"match","data":{{"path":{{"text":"File{i}.java"}},"line_number":{i},"lines":{{"text":"test"}},"submatches":[]}}}}'
            )
        json_output = "\n".join(json_lines).encode()

        with patch(
            "tree_sitter_analyzer.mcp.tools.trace_impact_tool.run_command_capture"
        ) as mock_run:
            mock_run.return_value = (0, json_output, b"")

            result = await self.tool.execute({
                "symbol": "test",
                "max_results": 50
            })

            assert result["success"] is True
            # call_count must reflect the TRUE total (150), not the display cap.
            # max_results=50 only limits the usages list, not the count.
            assert result["call_count"] == 150
            assert len(result["usages"]) == 50
            assert result["truncated"] is True

    @pytest.mark.asyncio
    async def test_execute_ripgrep_not_installed(self):
        """Test execution when ripgrep is not installed"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.trace_impact_tool.run_command_capture"
        ) as mock_run:
            mock_run.return_value = (127, b"", b"Command not found")

            result = await self.tool.execute({"symbol": "test"})

            assert result["success"] is False
            assert "not installed" in result["error"]
            assert result["call_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        """Test execution timeout"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.trace_impact_tool.run_command_capture"
        ) as mock_run:
            mock_run.return_value = (124, b"", b"Timeout")

            result = await self.tool.execute({"symbol": "test"})

            assert result["success"] is False
            assert "timed out" in result["error"]
            assert result["call_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_with_multiple_roots(self):
        """Test execution with multiple project roots"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.trace_impact_tool.run_command_capture"
        ) as mock_run:
            mock_run.return_value = (1, b"", b"")

            result = await self.tool.execute({
                "symbol": "test",
                "project_root": "/root1,/root2,/root3"
            })

            assert result["success"] is True
            # Verify command was called (roots are passed to ripgrep)
            assert mock_run.called


class TestTraceImpactToolLanguageDetection:
    """Test language detection and extension filtering"""

    def setup_method(self):
        """Set up test fixtures"""
        self.tool = TraceImpactTool(project_root="/test/project")

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


class TestImpactLevelBoundaries:
    """Test impact level classification at exact boundaries."""

    def test_impact_none_at_zero(self) -> None:
        """0 callers → level 'none'."""
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import _get_impact_level

        result = _get_impact_level(0)
        assert result["level"] == "none"
        assert "NO CALLERS" in result["badge"]

    def test_impact_low_at_1(self) -> None:
        """1 caller → level 'low'."""
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import _get_impact_level

        result = _get_impact_level(1)
        assert result["level"] == "low"

    def test_impact_low_at_5(self) -> None:
        """5 callers → still 'low' (boundary)."""
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import _get_impact_level

        result = _get_impact_level(5)
        assert result["level"] == "low"

    def test_impact_medium_at_6(self) -> None:
        """6 callers → 'medium' (just above low boundary)."""
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import _get_impact_level

        result = _get_impact_level(6)
        assert result["level"] == "medium"

    def test_impact_medium_at_20(self) -> None:
        """20 callers → still 'medium' (boundary)."""
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import _get_impact_level

        result = _get_impact_level(20)
        assert result["level"] == "medium"

    def test_impact_high_at_21(self) -> None:
        """21 callers → 'high' (just above medium boundary)."""
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import _get_impact_level

        result = _get_impact_level(21)
        assert result["level"] == "high"
        assert "21" in result["badge"]

    def test_impact_high_at_1000(self) -> None:
        """1000 callers → 'high'."""
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import _get_impact_level

        result = _get_impact_level(1000)
        assert result["level"] == "high"
        assert "1000" in result["badge"]

    def test_guidance_includes_caller_count(self) -> None:
        """Guidance text should mention the caller count."""
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import _get_impact_level

        result = _get_impact_level(42)
        assert "42" in result["guidance"]
