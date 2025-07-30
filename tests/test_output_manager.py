#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Output Manager

This module tests the output management functionality including
various output formats, quiet mode, and structured data output.
"""

import json
import sys
import pytest
import pytest_asyncio
from io import StringIO

# Import the module under test
from tree_sitter_analyzer.output_manager import (
    OutputManager,
    output_data,
    output_error,
    output_extensions,
    output_info,
    output_json,
    output_languages,
    output_list,
    output_queries,
    output_query_results,
    output_section,
    output_statistics,
    output_success,
    output_warning,
)


@pytest.fixture
def output_manager():
    """Fixture for OutputManager instance"""
    return OutputManager()


class TestOutputManager:
    """Test cases for OutputManager class"""

    def test_output_manager_initialization(self):
        """Test OutputManager initializes correctly"""
        manager = OutputManager()
        assert not manager.quiet
        assert not manager.json_output

        manager_quiet = OutputManager(quiet=True)
        assert manager_quiet.quiet

        manager_json = OutputManager(json_output=True)
        assert manager_json.json_output

    def test_output_info(self, monkeypatch, output_manager):
        """Test info output"""
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        output_manager.output_info("Test info message")
        output = mock_stdout.getvalue()
        assert "Test info message" in output

    def test_output_warning(self, monkeypatch, output_manager):
        """Test warning output"""
        mock_stderr = StringIO()
        monkeypatch.setattr("sys.stderr", mock_stderr)
        output_manager.output_warning("Test warning message")
        output = mock_stderr.getvalue()
        assert "WARNING: Test warning message" in output

    def test_output_error(self, monkeypatch, output_manager):
        """Test error output"""
        mock_stderr = StringIO()
        monkeypatch.setattr("sys.stderr", mock_stderr)
        output_manager.output_error("Test error message")
        output = mock_stderr.getvalue()
        assert "ERROR: Test error message" in output

    def test_output_success(self, monkeypatch, output_manager):
        """Test success output"""
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        output_manager.output_success("Test success message")
        output = mock_stdout.getvalue()
        assert "✓ Test success message" in output

    def test_output_json(self, monkeypatch, output_manager):
        """Test JSON output"""
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        test_data = {"key": "value", "number": 42}
        output_manager.output_json(test_data)
        output = mock_stdout.getvalue()

        # Verify it's valid JSON
        parsed = json.loads(output.strip())
        assert parsed["key"] == "value"
        assert parsed["number"] == 42

    def test_output_data_dict(self, monkeypatch, output_manager):
        """Test data output with dictionary"""
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        test_data = {"name": "test", "value": 123}
        output_manager.output_data(test_data)
        output = mock_stdout.getvalue()
        # JSON形式での出力を期待
        parsed = json.loads(output.strip())
        assert parsed["name"] == "test"
        assert parsed["value"] == 123

    def test_output_data_list(self, monkeypatch, output_manager):
        """Test data output with list"""
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        test_data = ["item1", "item2", "item3"]
        output_manager.output_data(test_data)
        output = mock_stdout.getvalue()
        # JSON形式での出力を期待
        parsed = json.loads(output.strip())
        assert parsed == ["item1", "item2", "item3"]

    def test_output_data_string(self, monkeypatch, output_manager):
        """Test data output with string"""
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        output_manager.output_data("Simple string output")
        output = mock_stdout.getvalue()
        assert "Simple string output" in output

    def test_output_section(self, monkeypatch, output_manager):
        """Test section output"""
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        output_manager.output_section("Test Section")
        output = mock_stdout.getvalue()
        assert "--- Test Section ---" in output

    def test_output_query_results(self, monkeypatch, output_manager):
        """Test query results output"""
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        results = [
            {
                "capture_name": "class_declaration",
                "node_type": "class",
                "start_line": 1,
                "end_line": 10,
                "content": "public class Test {}",
            },
            {
                "capture_name": "method_declaration",
                "node_type": "method",
                "start_line": 5,
                "end_line": 8,
                "content": "public void test() {}",
            },
        ]
        output_manager.output_query_results(results)
        output = mock_stdout.getvalue()
        assert "class_declaration" in output
        assert "method_declaration" in output
        assert "public class Test" in output

    def test_quiet_mode(self, monkeypatch):
        """Test quiet mode suppresses output"""
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        manager = OutputManager(quiet=True)
        manager.output_info("This should not appear")
        manager.output_warning("This warning should not appear")
        manager.output_success("This success should not appear")
        output = mock_stdout.getvalue()
        assert output == ""

    def test_json_output_mode(self, monkeypatch):
        """Test JSON output mode"""
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        manager = OutputManager(json_output=True)
        test_data = {"test": True}
        manager.output_data(test_data, format_type="json")
        output = mock_stdout.getvalue()
        parsed = json.loads(output.strip())
        assert parsed["test"] is True


class TestModuleLevelFunctions:
    """Test module-level convenience functions"""

    def test_output_info_function(self, monkeypatch):
        """Test module-level output_info function"""
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        output_info("Test module info")
        output = mock_stdout.getvalue()
        assert "Test module info" in output

    def test_output_warning_function(self, monkeypatch):
        """Test module-level output_warning function"""
        mock_stderr = StringIO()
        monkeypatch.setattr("sys.stderr", mock_stderr)
        output_warning("Test module warning")
        output = mock_stderr.getvalue()
        assert "WARNING: Test module warning" in output

    def test_output_error_function(self, monkeypatch):
        """Test module-level output_error function"""
        mock_stderr = StringIO()
        monkeypatch.setattr("sys.stderr", mock_stderr)
        output_error("Test module error")
        output = mock_stderr.getvalue()
        assert "ERROR: Test module error" in output

    def test_output_success_function(self, monkeypatch):
        """Test module-level output_success function"""
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        output_success("Test module success")
        output = mock_stdout.getvalue()
        assert "✓ Test module success" in output

    def test_output_json_function(self, monkeypatch):
        """Test module-level output_json function"""
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        test_data = {"module": "test", "working": True}
        output_json(test_data)
        output = mock_stdout.getvalue()
        parsed = json.loads(output.strip())
        assert parsed["module"] == "test"
        assert parsed["working"] is True

    def test_output_data_function(self, monkeypatch):
        """Test module-level output_data function"""
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        output_data("Module data test")
        output = mock_stdout.getvalue()
        assert "Module data test" in output

    def test_output_list_function(self, monkeypatch):
        """Test module-level output_list function"""
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        output_list("Module list item")
        output = mock_stdout.getvalue()
        assert "Module list item" in output

    def test_output_section_function(self, monkeypatch):
        """Test module-level output_section function"""
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        output_section("Module Section")
        output = mock_stdout.getvalue()
        assert "--- Module Section ---" in output


class TestSpecializedOutputFunctions:
    """Test specialized output functions"""

    def test_output_statistics(self, monkeypatch):
        """Test statistics output"""
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        stats = {"classes": 5, "methods": 20, "fields": 15, "lines": 500}
        output_statistics(stats)
        output = mock_stdout.getvalue()
        assert "classes: 5" in output
        assert "methods: 20" in output
        assert "fields: 15" in output
        assert "lines: 500" in output

    def test_output_languages(self, monkeypatch):
        """Test languages output"""
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        languages = ["java", "python", "javascript", "typescript"]
        output_languages(languages, "Supported Languages")
        output = mock_stdout.getvalue()
        assert "Supported Languages:" in output
        for lang in languages:
            assert lang in output

    def test_output_queries(self, monkeypatch):
        """Test queries output"""
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        queries = {
            "class_declaration": "Find class declarations",
            "method_declaration": "Find method declarations",
            "field_declaration": "Find field declarations",
        }
        output_queries(queries, "java")
        output = mock_stdout.getvalue()
        assert "利用可能なクエリキー (java):" in output
        assert "class_declaration" in output
        assert "method_declaration" in output
        assert "field_declaration" in output

    def test_output_extensions(self, monkeypatch):
        """Test extensions output"""
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        extensions = [".java", ".js", ".py", ".ts", ".cpp", ".c", ".go", ".rs"]
        output_extensions(extensions)
        output = mock_stdout.getvalue()
        assert "サポートされている拡張子:" in output
        # 拡張子の数をカウントして確認
        extension_count = len(extensions)
        assert f"合計 {extension_count} 個の拡張子をサポート" in output
        for ext in extensions:
            assert ext in output


class TestOutputManagerEdgeCases:
    """Test edge cases and error conditions"""

    def test_output_manager_with_none_data(self, output_manager):
        """Test output manager handles None data gracefully"""
        # These should not raise exceptions
        output_manager.output_data(None)
        output_manager.output_json(None)

    def test_output_empty_collections(self, monkeypatch, output_manager):
        """Test output with empty collections"""
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        output_manager.output_data([])  # Empty list
        output_manager.output_data({})  # Empty dict
        output_manager.output_query_results([])  # Empty results

        # Should handle gracefully without errors
        output = mock_stdout.getvalue()
        assert isinstance(output, str)

    def test_output_complex_nested_data(self, monkeypatch, output_manager):
        """Test output with complex nested data structures"""
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        complex_data = {
            "project": {
                "name": "test-project",
                "languages": ["java", "python"],
                "statistics": {"classes": 10, "methods": 50},
            },
            "metadata": {"version": "1.0.0", "created": "2024-01-01"},
        }

        output_manager.output_json(complex_data)
        output = mock_stdout.getvalue()

        # Verify it's valid JSON and contains expected data
        parsed = json.loads(output.strip())
        assert parsed["project"]["name"] == "test-project"
        assert "java" in parsed["project"]["languages"]
        assert parsed["project"]["statistics"]["classes"] == 10
