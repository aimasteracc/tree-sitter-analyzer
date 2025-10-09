#!/usr/bin/env python3
"""
CLI Regression Tests

Tests to ensure CLI commands produce consistent output for unchanged files.
These tests help detect regressions in CLI functionality during development.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest


class TestCLIRegression:
    """Regression tests for CLI commands"""

    @pytest.fixture
    def bigservice_path(self):
        """Path to the BigService.java test file"""
        return "examples/BigService.java"

    @pytest.fixture
    def sample_py_path(self):
        """Path to the sample.py test file"""
        return "examples/sample.py"

    @pytest.fixture
    def test_markdown_path(self):
        """Path to the test_markdown.md test file"""
        return "examples/test_markdown.md"

    def run_cli_command(self, args):
        """Helper to run CLI commands and return output"""
        cmd = [sys.executable, "-m", "tree_sitter_analyzer"] + args
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=Path.cwd(), encoding='utf-8', errors='replace'
        )
        return result.returncode, result.stdout, result.stderr

    def test_summary_command_consistency(self, bigservice_path):
        """Test --summary command produces consistent output"""
        returncode, stdout, stderr = self.run_cli_command([bigservice_path, "--summary"])
        
        assert returncode == 0, f"Command failed with stderr: {stderr}"
        assert "Summary Results" in stdout
        
        # Parse JSON output
        json_start = stdout.find("{")
        json_output = stdout[json_start:]
        data = json.loads(json_output)
        
        # Verify expected structure
        assert data["file_path"] == bigservice_path
        assert data["language"] == "java"
        assert "summary" in data
        assert "classes" in data["summary"]
        assert "methods" in data["summary"]
        
        # Verify expected counts (these should remain stable)
        assert len(data["summary"]["classes"]) == 1
        assert data["summary"]["classes"][0]["name"] == "BigService"
        assert len(data["summary"]["methods"]) == 66  # Total methods including constructor

    def test_table_full_command_consistency(self, bigservice_path):
        """Test --table=full command produces consistent output"""
        returncode, stdout, stderr = self.run_cli_command([bigservice_path, "--table=full"])
        
        assert returncode == 0, f"Command failed with stderr: {stderr}"
        
        # Verify key sections are present
        assert "# com.example.service.BigService" in stdout
        assert "## Package" in stdout
        assert "## Imports" in stdout
        assert "## Class Info" in stdout
        assert "### Fields" in stdout
        assert "### Constructors" in stdout
        assert "### Public Methods" in stdout
        assert "### Private Methods" in stdout
        
        # Verify specific counts in the output
        assert "Total Methods | 66" in stdout
        assert "Total Fields | 9" in stdout

    def test_advanced_json_command_consistency(self, bigservice_path):
        """Test --advanced --output-format=json command produces consistent output"""
        returncode, stdout, stderr = self.run_cli_command([
            bigservice_path, "--advanced", "--output-format=json"
        ])
        
        assert returncode == 0, f"Command failed with stderr: {stderr}"
        assert "Advanced Analysis Results" in stdout
        
        # Parse JSON output
        json_start = stdout.find("{")
        json_output = stdout[json_start:]
        data = json.loads(json_output)
        
        # Verify expected structure and counts
        assert data["file_path"] == bigservice_path
        assert data["language"] == "java"
        assert data["line_count"] == 1419
        assert data["element_count"] == 85  # Total elements (methods, classes, fields, imports, package)
        assert data["success"] is True
        
        # Verify elements structure
        assert "elements" in data
        elements = data["elements"]
        
        # Count different element types
        functions = [e for e in elements if e["type"] == "function"]
        classes = [e for e in elements if e["type"] == "class"]
        variables = [e for e in elements if e["type"] == "variable"]
        imports = [e for e in elements if e["type"] == "import"]
        packages = [e for e in elements if e["type"] == "package"]
        
        assert len(functions) == 66  # All methods including constructor
        assert len(classes) == 1     # BigService class
        assert len(variables) == 9   # Class fields
        assert len(imports) == 8     # Import statements
        assert len(packages) == 1    # Package declaration

    def test_advanced_text_command_consistency(self, bigservice_path):
        """Test --advanced --output-format=text command produces consistent output"""
        returncode, stdout, stderr = self.run_cli_command([
            bigservice_path, "--advanced", "--output-format=text"
        ])
        
        assert returncode == 0, f"Command failed with stderr: {stderr}"
        
        # Verify text format output structure
        assert "Advanced Analysis Results" in stdout
        assert "File: examples/BigService.java" in stdout
        assert "Lines: 1419" in stdout
        assert "Classes: 1" in stdout
        assert "Methods: 66" in stdout
        assert "Fields: 9" in stdout

    def test_partial_read_command_consistency(self, bigservice_path):
        """Test --partial-read command produces consistent output"""
        returncode, stdout, stderr = self.run_cli_command([
            bigservice_path, "--partial-read", "--start-line", "93", "--end-line", "106"
        ])
        
        assert returncode == 0, f"Command failed with stderr: {stderr}"
        
        # Parse JSON output
        data = json.loads(stdout)
        
        # Verify expected structure
        assert data["file_path"] == bigservice_path
        assert data["range"]["start_line"] == 93
        assert data["range"]["end_line"] == 106
        assert "content" in data
        assert "content_length" in data
        
        # Verify specific content (this should be stable)
        content = data["content"]
        assert "private void checkMemoryUsage()" in content
        assert "Runtime runtime = Runtime.getRuntime();" in content
        assert "WARNING: High memory usage detected!" in content

    def test_structure_command_consistency(self, bigservice_path):
        """Test --structure command produces consistent output"""
        returncode, stdout, stderr = self.run_cli_command([bigservice_path, "--structure"])
        
        assert returncode == 0, f"Command failed with stderr: {stderr}"
        
        # Verify structure output contains expected sections
        assert "Structure Analysis Results" in stdout
        
        # Parse JSON output
        json_start = stdout.find("{")
        json_output = stdout[json_start:]
        data = json.loads(json_output)
        
        # Verify expected structure
        assert data["file_path"] == bigservice_path
        assert data["language"] == "java"
        assert "classes" in data
        assert "methods" in data
        assert "fields" in data
        assert "imports" in data
        assert "statistics" in data
        
        # Verify expected counts
        assert len(data["classes"]) == 1
        assert len(data["methods"]) == 66
        assert len(data["fields"]) == 9
        assert len(data["imports"]) == 8
        assert data["statistics"]["class_count"] == 1
        assert data["statistics"]["method_count"] == 66
        assert data["statistics"]["field_count"] == 9
        assert data["statistics"]["total_lines"] == 1419

    def test_python_language_command_consistency(self, sample_py_path):
        """Test --language python --table=full command produces consistent output"""
        returncode, stdout, stderr = self.run_cli_command([
            sample_py_path, "--language", "python", "--table=full"
        ])
        
        assert returncode == 0, f"Command failed with stderr: {stderr}"
        
        # Verify Python-specific output
        assert "# sample" in stdout
        assert "## Classes Overview" in stdout
        assert "Animal" in stdout
        assert "Dog" in stdout
        assert "Cat" in stdout

    def test_all_commands_exit_successfully(self, bigservice_path, sample_py_path):
        """Test that all documented CLI commands exit with code 0"""
        commands = [
            # BigService.java commands
            [bigservice_path, "--summary"],
            [bigservice_path, "--structure"],
            [bigservice_path, "--advanced"],
            [bigservice_path, "--table=full"],
            [bigservice_path, "--advanced", "--output-format=json"],
            [bigservice_path, "--advanced", "--output-format=text"],
            [bigservice_path, "--partial-read", "--start-line", "93", "--end-line", "106"],
            # Python file command
            [sample_py_path, "--language", "python", "--table=full"],
        ]
        
        for cmd_args in commands:
            returncode, stdout, stderr = self.run_cli_command(cmd_args)
            assert returncode == 0, f"Command {' '.join(cmd_args)} failed with stderr: {stderr}"
            assert len(stdout) > 0, f"Command {' '.join(cmd_args)} produced no output"

    def test_error_handling_consistency(self):
        """Test that error conditions are handled consistently"""
        # Test non-existent file
        returncode, stdout, stderr = self.run_cli_command([
            "nonexistent.java", "--summary"
        ])
        assert returncode != 0
        
        # Test invalid arguments
        returncode, stdout, stderr = self.run_cli_command([
            "examples/BigService.java", "--invalid-option"
        ])
        assert returncode != 0

    def test_output_format_consistency(self, bigservice_path):
        """Test that different output formats are consistent in structure"""
        # Test JSON format
        returncode_json, stdout_json, _ = self.run_cli_command([
            bigservice_path, "--advanced", "--output-format=json"
        ])
        
        # Test text format
        returncode_text, stdout_text, _ = self.run_cli_command([
            bigservice_path, "--advanced", "--output-format=text"
        ])
        
        assert returncode_json == 0
        assert returncode_text == 0
        
        # Both should contain the same basic information
        assert "examples/BigService.java" in stdout_json
        assert "examples/BigService.java" in stdout_text
        assert "java" in stdout_json
        assert "java" in stdout_text

    def test_query_methods_consistency(self, bigservice_path):
        """Test --query-key methods command produces consistent output"""
        returncode, stdout, stderr = self.run_cli_command([
            bigservice_path, "--query-key", "methods"
        ])
        
        assert returncode == 0, f"Command failed with stderr: {stderr}"
        
        # Parse JSON output (it's an array format)
        data = json.loads(stdout)
        
        # Verify it's an array
        assert isinstance(data, list)
        
        # Verify expected method count
        assert len(data) == 65  # Total methods (constructor not included in method_declaration query)
        
        # Verify structure of first method
        assert "capture_name" in data[0]
        assert "node_type" in data[0]
        assert "start_line" in data[0]
        assert "end_line" in data[0]
        assert "content" in data[0]

    def test_query_classes_consistency(self, bigservice_path):
        """Test --query-key classes command produces consistent output"""
        returncode, stdout, stderr = self.run_cli_command([
            bigservice_path, "--query-key", "classes"
        ])
        
        assert returncode == 0, f"Command failed with stderr: {stderr}"
        
        # Parse JSON output (it's an array format)
        data = json.loads(stdout)
        
        # Verify it's an array
        assert isinstance(data, list)
        
        # Verify expected class count
        assert len(data) == 1  # BigService class
        
        # Verify structure of class
        assert "capture_name" in data[0]
        assert "node_type" in data[0]
        assert "start_line" in data[0]
        assert "end_line" in data[0]
        assert "content" in data[0]

    def test_filter_main_method_consistency(self, bigservice_path):
        """Test --query-key methods --filter name=main command produces consistent output"""
        returncode, stdout, stderr = self.run_cli_command([
            bigservice_path, "--query-key", "methods", "--filter", "name=main"
        ])
        
        assert returncode == 0, f"Command failed with stderr: {stderr}"
        
        # Parse JSON output (it's an array format)
        data = json.loads(stdout)
        
        # Verify it's an array
        assert isinstance(data, list)
        
        # Verify main method found
        assert len(data) == 1
        
        # Verify it contains main method
        assert "main" in data[0]["content"]

    def test_filter_auth_pattern_consistency(self, bigservice_path):
        """Test --query-key methods --filter name=~auth* command produces consistent output"""
        returncode, stdout, stderr = self.run_cli_command([
            bigservice_path, "--query-key", "methods", "--filter", "name=~auth*"
        ])
        
        assert returncode == 0, f"Command failed with stderr: {stderr}"
        
        # Parse JSON output (it's an array format)
        data = json.loads(stdout)
        
        # Verify it's an array
        assert isinstance(data, list)
        
        # Verify auth-related method found
        assert len(data) == 1
        
        # Verify it contains authenticateUser method
        assert "authenticateUser" in data[0]["content"]

    def test_filter_public_no_params_consistency(self, bigservice_path):
        """Test --query-key methods --filter params=0,public=true command produces consistent output"""
        returncode, stdout, stderr = self.run_cli_command([
            bigservice_path, "--query-key", "methods", "--filter", "params=0,public=true"
        ])
        
        assert returncode == 0, f"Command failed with stderr: {stderr}"
        
        # Parse JSON output (it's an array format)
        data = json.loads(stdout)
        
        # Verify it's an array
        assert isinstance(data, list)
        
        # Verify public methods with no parameters found
        assert len(data) >= 2  # Should find multiple public no-param methods
        
        # Verify all results contain public methods
        for result in data:
            assert "public" in result["content"]
            assert "(" in result["content"] and ")" in result["content"]

    def test_filter_static_methods_consistency(self, bigservice_path):
        """Test --query-key methods --filter static=true command produces consistent output"""
        returncode, stdout, stderr = self.run_cli_command([
            bigservice_path, "--query-key", "methods", "--filter", "static=true"
        ])
        
        assert returncode == 0, f"Command failed with stderr: {stderr}"
        
        # Parse JSON output (it's an array format)
        data = json.loads(stdout)
        
        # Verify it's an array
        assert isinstance(data, list)
        
        # Verify static method found (main method should be static)
        assert len(data) == 1
        
        # Verify it contains static main method
        assert "static" in data[0]["content"]
        assert "main" in data[0]["content"]

    def test_filter_help_consistency(self):
        """Test --filter-help command produces consistent output"""
        returncode, stdout, stderr = self.run_cli_command(["--filter-help"])
        
        assert returncode == 0, f"Command failed with stderr: {stderr}"
        
        # Verify help content
        assert "Filter Syntax Help" in stdout
        assert "Basic Syntax" in stdout
        assert "Supported filter keys" in stdout
        assert "Examples" in stdout
        assert "name=" in stdout
        assert "params=" in stdout
        assert "static=" in stdout
        assert "public=" in stdout
        assert "private=" in stdout

    def test_all_query_commands_exit_successfully(self, bigservice_path):
        """Test that all documented query CLI commands exit with code 0"""
        commands = [
            # Query commands
            [bigservice_path, "--query-key", "methods"],
            [bigservice_path, "--query-key", "classes"],
            # Filter commands
            [bigservice_path, "--query-key", "methods", "--filter", "name=main"],
            [bigservice_path, "--query-key", "methods", "--filter", "name=~auth*"],
            [bigservice_path, "--query-key", "methods", "--filter", "params=0,public=true"],
            [bigservice_path, "--query-key", "methods", "--filter", "static=true"],
            # Help command
            ["--filter-help"],
        ]
        
        for cmd_args in commands:
            returncode, stdout, stderr = self.run_cli_command(cmd_args)
            assert returncode == 0, f"Command {' '.join(cmd_args)} failed with stderr: {stderr}"
            assert len(stdout) > 0, f"Command {' '.join(cmd_args)} produced no output"

    # Markdown-specific tests
    def test_markdown_summary_consistency(self, test_markdown_path):
        """Test --summary command for Markdown files produces consistent output"""
        returncode, stdout, stderr = self.run_cli_command([test_markdown_path, "--summary"])
        
        assert returncode == 0, f"Command failed with stderr: {stderr}"
        
        # Parse JSON output
        json_start = stdout.find("{")
        json_output = stdout[json_start:]
        data = json.loads(json_output)
        
        # Verify expected structure
        assert data["file_path"] == test_markdown_path
        assert data["language"] == "markdown"
        assert "summary" in data
        
        # Verify Markdown-specific elements
        summary = data["summary"]
        assert "headers" in summary
        assert "code_blocks" in summary
        assert "lists" in summary
        
        # Verify expected counts
        assert len(summary["headers"]) == 28  # Comprehensive test file has many headers
        assert len(summary["links"]) >= 3  # Links in test file (3-6 depending on parser and format)
        assert len(summary["images"]) >= 2  # Images in test file (2-3 depending on reference parsing)
        assert len(summary["code_blocks"]) == 3  # Three code blocks
        assert len(summary["lists"]) == 6  # Six lists (including task lists)

    def test_markdown_structure_consistency(self, test_markdown_path):
        """Test --structure command for Markdown files produces consistent output"""
        returncode, stdout, stderr = self.run_cli_command([test_markdown_path, "--structure"])
        
        assert returncode == 0, f"Command failed with stderr: {stderr}"
        
        # Parse JSON output
        json_start = stdout.find("{")
        json_output = stdout[json_start:]
        data = json.loads(json_output)
        
        # Verify expected structure
        assert data["file_path"] == test_markdown_path
        assert data["language"] == "markdown"
        assert "headers" in data
        assert "code_blocks" in data
        assert "statistics" in data
        
        # Verify statistics
        stats = data["statistics"]
        assert stats["header_count"] == 28
        assert stats["link_count"] >= 3  # Link count varies by parsing method (3-5)
        assert stats["image_count"] == 3
        assert stats["code_block_count"] == 3
        assert stats["list_count"] == 6
        assert stats["table_count"] == 1
        assert stats["total_lines"] == 160

    def test_markdown_advanced_consistency(self, test_markdown_path):
        """Test --advanced command for Markdown files produces consistent output"""
        returncode, stdout, stderr = self.run_cli_command([test_markdown_path, "--advanced"])
        
        assert returncode == 0, f"Command failed with stderr: {stderr}"
        
        # Parse JSON output
        json_start = stdout.find("{")
        json_output = stdout[json_start:]
        data = json.loads(json_output)
        
        # Verify expected structure
        assert data["file_path"] == test_markdown_path
        assert data["language"] == "markdown"
        assert data["line_count"] == 160
        assert data["element_count"] >= 40  # Many elements in comprehensive test file
        assert data["success"] is True
        
        # Verify document metrics
        metrics = data["document_metrics"]
        assert metrics["header_count"] == 28
        assert metrics["max_header_level"] == 6
        assert metrics["link_count"] >= 3  # Link count varies (3-5 depending on parsing)
        assert metrics["image_count"] == 3  # Three unique images
        assert metrics["code_block_count"] == 3
        assert metrics["list_count"] == 6
        assert metrics["table_count"] == 1

    def test_markdown_table_consistency(self, test_markdown_path):
        """Test --table=full command for Markdown files produces consistent output"""
        returncode, stdout, stderr = self.run_cli_command([test_markdown_path, "--table=full"])
        
        assert returncode == 0, f"Command failed with stderr: {stderr}"
        
        # Verify Markdown table format output
        assert "# Comprehensive Markdown Test Document" in stdout
        assert "## Document Overview" in stdout
        assert "## Document Structure" in stdout
        assert "## Links" in stdout
        assert "## Images" in stdout
        assert "## Code Blocks" in stdout
        assert "## Lists" in stdout
        assert "| Language | markdown |" in stdout
        assert "| Total Lines | 160 |" in stdout

    def test_markdown_advanced_text_format_consistency(self, test_markdown_path):
        """Test --advanced --output-format=text command for Markdown files"""
        returncode, stdout, stderr = self.run_cli_command([
            test_markdown_path, "--advanced", "--output-format=text"
        ])
        
        assert returncode == 0, f"Command failed with stderr: {stderr}"
        
        # Verify text format output
        assert "Advanced Analysis Results" in stdout
        assert "File: examples/test_markdown.md" in stdout
        assert "Language: markdown" in stdout
        assert "Lines: 160" in stdout
        # Element count can vary slightly (67-70) based on parsing details
        assert any(f"Elements: {i}" in stdout for i in range(67, 71))
        assert "Headers: 28" in stdout
        assert "Document Complexity: Complex" in stdout

    def test_all_markdown_commands_exit_successfully(self, test_markdown_path):
        """Test that all Markdown CLI commands exit with code 0"""
        commands = [
            [test_markdown_path, "--summary"],
            [test_markdown_path, "--structure"],
            [test_markdown_path, "--advanced"],
            [test_markdown_path, "--table=full"],
            [test_markdown_path, "--advanced", "--output-format=json"],
            [test_markdown_path, "--advanced", "--output-format=text"],
        ]
        
        for cmd_args in commands:
            returncode, stdout, stderr = self.run_cli_command(cmd_args)
            assert returncode == 0, f"Command {' '.join(cmd_args)} failed with stderr: {stderr}"
            assert len(stdout) > 0, f"Command {' '.join(cmd_args)} produced no output"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])