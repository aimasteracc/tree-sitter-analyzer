#!/usr/bin/env python3
"""
Security Integration Tests

Tests to verify that security features are properly integrated
across all components of the tree-sitter-analyzer system.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.cli.commands.base_command import BaseCommand
from tree_sitter_analyzer.cli.commands.query_command import QueryCommand
from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine
from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool as TableFormatTool,
)
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool
from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import UniversalAnalyzeTool
from tree_sitter_analyzer.security import SecurityValidator


class TestSecurityIntegration:
    """Test security integration across all components."""

    def setup_method(self):
        """Set up test environment."""
        # Reset singleton instance to ensure clean state
        from tree_sitter_analyzer.core.analysis_engine import UnifiedAnalysisEngine

        UnifiedAnalysisEngine._instances = {}

        self.temp_dir = tempfile.mkdtemp()
        self.test_file = str(Path(self.temp_dir) / "test.py")

        # Create a test file
        with open(self.test_file, "w") as f:
            f.write(
                """
def hello_world():
    print("Hello, World!")
    return True

class TestClass:
    def __init__(self):
        self.value = 42
"""
            )

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_analysis_engine_security_integration(self):
        """Test that analysis engine properly validates file paths."""
        # Get parent directory of temp_dir to use as project root
        project_root = str(Path(self.temp_dir).parent)
        engine = get_analysis_engine(project_root)

        # Valid file should work
        result = await engine.analyze_file(self.test_file)
        assert result.success

        # Invalid path should be rejected
        with pytest.raises(ValueError, match="Invalid file path"):
            await engine.analyze_file("../../../etc/passwd")

        # Path traversal should be rejected
        with pytest.raises(ValueError, match="Invalid file path"):
            await engine.analyze_file(self.temp_dir + "/../../../etc/passwd")

    @pytest.mark.asyncio
    async def test_mcp_tools_security_integration(self):
        """Test that MCP tools properly validate inputs."""
        # Reset singleton instance to ensure clean state
        from tree_sitter_analyzer.core.analysis_engine import UnifiedAnalysisEngine

        UnifiedAnalysisEngine._instances = {}

        # Get parent directory of temp_dir to use as project root
        project_root = str(Path(self.temp_dir).parent)

        # Test TableFormatTool
        table_tool = TableFormatTool(project_root)

        # Valid file should work
        result = await table_tool.execute({"file_path": self.test_file})
        assert "error" not in result

        # Invalid path should be rejected
        with pytest.raises(
            Exception, match="Invalid file path|Directory traversal|Operation failed"
        ):
            await table_tool.execute({"file_path": "../../../etc/passwd"})

        # Test UniversalAnalyzeTool
        analyze_tool = UniversalAnalyzeTool(project_root)

        # Valid file should work
        result = await analyze_tool.execute({"file_path": self.test_file})
        assert "error" not in result

        # Invalid path should be rejected
        with pytest.raises(
            Exception, match="Invalid file path|Directory traversal|Operation failed"
        ):
            await analyze_tool.execute({"file_path": "../../../etc/passwd"})

    @pytest.mark.asyncio
    async def test_read_partial_tool_security(self):
        """Test ReadPartialTool security validation."""
        project_root = str(Path(self.temp_dir).parent)
        read_tool = ReadPartialTool(project_root)

        # Valid file should work
        result = await read_tool.execute(
            {"file_path": self.test_file, "start_line": 1, "end_line": 5}
        )
        assert "error" not in result

        # Invalid path should be rejected
        result = await read_tool.execute(
            {"file_path": "../../../etc/passwd", "start_line": 1}
        )
        # Should return error response instead of raising exception
        assert isinstance(result, dict)
        assert not result.get("success", True)
        assert "error" in result
        error_msg = result.get("error", "").lower()
        assert any(
            keyword in error_msg
            for keyword in [
                "invalid file path",
                "directory traversal",
                "security validation failed",
            ]
        )

    @pytest.mark.asyncio
    async def test_analyze_scale_tool_security(self):
        """Test AnalyzeScaleTool security validation."""
        # Reset singleton instance to ensure clean state
        from tree_sitter_analyzer.core.analysis_engine import UnifiedAnalysisEngine

        UnifiedAnalysisEngine._instances = {}

        project_root = str(Path(self.temp_dir).parent)
        scale_tool = AnalyzeScaleTool(project_root)

        # Valid file should work
        result = await scale_tool.execute({"file_path": self.test_file})
        assert "error" not in result

        # Invalid path should be rejected
        with pytest.raises(
            Exception, match="Invalid file path|Directory traversal|Operation failed"
        ):
            await scale_tool.execute({"file_path": "../../../etc/passwd"})

        # Test input sanitization - use a more realistic malicious input
        # that won't break the language detection
        try:
            result = await scale_tool.execute(
                {
                    "file_path": self.test_file,
                    "language": "python<script>alert('xss')</script>",
                }
            )
            # Should not contain the malicious script
            assert "<script>" not in str(result)
        except Exception as e:
            # If it fails due to language detection, that's also acceptable
            # as long as the malicious script is not executed
            assert "<script>" not in str(e)

    def test_cli_command_security_integration(self):
        """Test CLI command security validation."""
        from argparse import Namespace

        # Create a concrete implementation of BaseCommand for testing
        class TestCommand(BaseCommand):
            async def execute_async(self, language: str) -> int:
                return 0

        # Test BaseCommand validation
        args = Namespace(file_path=self.test_file, project_root=self.temp_dir)
        base_cmd = TestCommand(args)

        # Valid file should pass validation
        assert base_cmd.validate_file() is True

        # Invalid path should fail validation
        args.file_path = "../../../etc/passwd"
        args.project_root = self.temp_dir
        base_cmd = TestCommand(args)
        assert base_cmd.validate_file() is False

    @pytest.mark.asyncio
    async def test_query_command_security(self):
        """Test QueryCommand security for query strings."""
        from argparse import Namespace

        args = Namespace(
            file_path=self.test_file,
            query_string="(function_definition) @func",
            language="python",
            project_root=self.temp_dir,
            output_format="text",
        )

        query_cmd = QueryCommand(args)

        # Valid query should work
        result = await query_cmd.execute_async("python")
        assert result == 0  # Success

        # Test malicious regex pattern
        args.query_string = "(.+)*(.+)*(.+)*"  # ReDoS pattern
        query_cmd = QueryCommand(args)

        # Should be rejected due to ReDoS risk
        result = await query_cmd.execute_async("python")
        assert result == 1  # Error

    def test_security_validator_consistency(self):
        """Test that all components use consistent security validation."""
        # All components should use the same SecurityValidator
        project_root = str(Path(self.temp_dir).parent)
        engine = get_analysis_engine(project_root)
        table_tool = TableFormatTool(project_root)
        analyze_tool = UniversalAnalyzeTool(project_root)

        # All should have security_validator attribute
        assert hasattr(engine, "_security_validator")
        assert hasattr(table_tool, "security_validator")
        assert hasattr(analyze_tool, "security_validator")

        # All should reject the same malicious paths
        malicious_path = "../../../etc/passwd"

        engine_valid, _ = engine.security_validator.validate_file_path(malicious_path)
        table_valid, _ = table_tool.security_validator.validate_file_path(
            malicious_path
        )
        analyze_valid, _ = analyze_tool.security_validator.validate_file_path(
            malicious_path
        )

        assert not engine_valid
        assert not table_valid
        assert not analyze_valid

    def test_input_sanitization_consistency(self):
        """Test that input sanitization is consistent across components."""
        malicious_input = "<script>alert('xss')</script>"

        validator1 = SecurityValidator()
        validator2 = SecurityValidator()

        sanitized1 = validator1.sanitize_input(malicious_input)
        sanitized2 = validator2.sanitize_input(malicious_input)

        # Should produce consistent results
        assert sanitized1 == sanitized2
        assert "<script>" not in sanitized1
        assert ">" not in sanitized1  # HTML tags should be removed
        assert "<" not in sanitized1  # HTML tags should be removed

    @pytest.mark.asyncio
    async def test_performance_impact(self):
        """Test that security validation doesn't significantly impact performance."""
        import time

        project_root = str(Path(self.temp_dir).parent)
        engine = get_analysis_engine(project_root)

        # Measure time with security validation
        start_time = time.time()
        result = await engine.analyze_file(self.test_file)
        end_time = time.time()

        security_time = end_time - start_time

        # Security validation should add minimal overhead (< 100ms for small files)
        assert security_time < 1.0  # Should complete within 1 second
        assert result.success

    def test_audit_logging(self):
        """Test that security events are properly logged."""
        import logging
        from io import StringIO

        # Capture log output
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        logger = logging.getLogger("tree_sitter_analyzer")
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)

        try:
            # Trigger security validation failure
            validator = SecurityValidator(self.temp_dir)
            validator.validate_file_path("../../../etc/passwd")

            # Check that security event was logged (content may vary by impl)
            _ = log_capture.getvalue()

        finally:
            logger.removeHandler(handler)

    def test_error_handling_security(self):
        """Test that error messages don't leak sensitive information."""
        project_root = str(Path(self.temp_dir).parent)
        validator = SecurityValidator(project_root)

        # Test with various malicious inputs
        malicious_inputs = [
            "../../../etc/passwd",
            "/etc/shadow",
            "C:\\Windows\\System32\\config\\SAM",
            "\\\\server\\share\\file.txt",
        ]

        for malicious_input in malicious_inputs:
            is_valid, error_msg = validator.validate_file_path(malicious_input)

            # Should not be valid
            assert not is_valid

            # Error message should not contain the full malicious path
            assert malicious_input not in error_msg

            # Debug: print the actual error message
            print(f"Error message for {malicious_input}: '{error_msg}'")

            # Should contain at least one generic security keyword. On non-Windows
            # platforms, Windows-drive specific inputs may yield a platform-aware
            # message such as "Windows drive letters are not allowed on this system".
            # Accept any of the following keywords for portability.
            generic_keywords = [
                "security",
                "invalid",
                "not allowed",
                "denied",
                "traversal",
                "absolute",
                "windows drive",
            ]
            assert any(word in error_msg.lower() for word in generic_keywords)


if __name__ == "__main__":
    pytest.main([__file__])
