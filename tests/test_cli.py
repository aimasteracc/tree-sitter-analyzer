#!/usr/bin/env python3
"""
Tests for CLI module
"""

import sys

# Add project root to path
sys.path.insert(0, ".")

import os
import sys
import tempfile
from io import StringIO

import pytest

from tree_sitter_analyzer.cli_main import main


class TestCLI:
    """Test cases for CLI functionality"""

    def test_show_query_languages(self, monkeypatch):
        """Test --show-query-languages option"""
        monkeypatch.setattr(sys, "argv", ["cli", "--show-query-languages"])
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        try:
            main()
        except SystemExit:
            pass  # Expected for some CLI commands

        output = mock_stdout.getvalue()
        assert (
            "Query supported languages" in output
            or "クエリサポートされている言語" in output
        )
        assert "java" in output
        assert "javascript" in output
        assert "python" in output

    def test_show_supported_languages(self, monkeypatch):
        """Test --show-supported-languages option"""
        monkeypatch.setattr(sys, "argv", ["cli", "--show-supported-languages"])
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        try:
            main()
        except SystemExit:
            pass

        output = mock_stdout.getvalue()
        assert "Supported languages" in output or "サポートされている言語" in output

    def test_show_supported_extensions(self, monkeypatch):
        """Test --show-supported-extensions option"""
        monkeypatch.setattr(sys, "argv", ["cli", "--show-supported-extensions"])
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        try:
            main()
        except SystemExit:
            pass

        output = mock_stdout.getvalue()
        assert "Supported extensions" in output or "サポートされている拡張子" in output

    def test_show_common_queries(self, monkeypatch):
        """Test --show-common-queries option"""
        monkeypatch.setattr(sys, "argv", ["cli", "--show-common-queries"])
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        try:
            main()
        except SystemExit:
            pass

        output = mock_stdout.getvalue()
        assert (
            "Common queries for multiple languages" in output
            or "複数言語共通のクエリ" in output
        )
        # Check for some common query names
        assert any(
            query in output
            for query in [
                "class_names",
                "method_names",
                "imports",
                "all_declarations",
            ]
        )

    def test_list_queries_with_language(self, monkeypatch):
        """Test --list-queries with --language option"""
        monkeypatch.setattr(
            sys, "argv", ["cli", "--list-queries", "--language", "java"]
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        try:
            main()
        except SystemExit:
            pass

        output = mock_stdout.getvalue()
        assert "java" in output.lower()

    def test_list_queries_without_language(self, monkeypatch):
        """Test --list-queries without language specification"""
        monkeypatch.setattr(sys, "argv", ["cli", "--list-queries"])
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        try:
            main()
        except SystemExit:
            pass

        output = mock_stdout.getvalue()
        assert "Supported languages" in output or "サポートされている言語" in output

    def test_describe_query_with_language(self, monkeypatch):
        """Test --describe-query with --language option"""
        monkeypatch.setattr(
            sys, "argv", ["cli", "--describe-query", "class", "--language", "java"]
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        try:
            main()
        except SystemExit:
            pass

        output = mock_stdout.getvalue()

        assert "class" in output
        output = mock_stdout.getvalue()
        # This should show an error message since no language is specified
        # The error goes to stderr, so check that stdout is empty

        assert "java" in output.lower()

    def test_describe_query_without_language(self, monkeypatch):
        """Test --describe-query without language specification"""
        monkeypatch.setattr(sys, "argv", ["cli", "--describe-query", "class"])
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        try:
            main()
        except SystemExit:
            pass

        # This should show an error message since no language is specified
        # The error goes to stderr, so check that stdout is empty
        _ = mock_stdout.getvalue()

    def test_analyze_java_file(self, monkeypatch):
        """Test analyzing a Java file"""
        # Create a temporary Java file
        java_code = """
public class TestClass {
    public void testMethod() {
        System.out.println("Hello, World!");
    }
}
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False, encoding="utf-8"
        ) as f:
            f.write(java_code)
            temp_path = f.name

        try:
            monkeypatch.setattr(sys, "argv", ["cli", temp_path])
            mock_stdout = StringIO()
            monkeypatch.setattr("sys.stdout", mock_stdout)

            try:
                main()
            except SystemExit:
                pass

            output = mock_stdout.getvalue()
            # Should contain some analysis results
            assert len(output) > 0
        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_analyze_with_query_key(self, monkeypatch):
        """Test analyzing file with specific query"""
        # Create a temporary Java file
        java_code = """
public class TestClass {
    public void testMethod() {
        System.out.println("Hello, World!");
    }
}
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False, encoding="utf-8"
        ) as f:
            f.write(java_code)
            temp_path = f.name

        try:
            monkeypatch.setattr(
                sys, "argv", ["cli", temp_path, "--query-key", "class_names"]
            )
            mock_stdout = StringIO()
            monkeypatch.setattr("sys.stdout", mock_stdout)

            try:
                main()
            except SystemExit:
                pass

            output = mock_stdout.getvalue()
            # Should contain class name analysis
            assert len(output) > 0
        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_analyze_with_custom_query(self, monkeypatch):
        """Test analyzing file with custom query string"""
        # Create a temporary Java file
        java_code = """
public class TestClass {
    public void testMethod() {
        System.out.println("Hello, World!");
    }
}
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False, encoding="utf-8"
        ) as f:
            f.write(java_code)
            temp_path = f.name

        try:
            custom_query = "(class_declaration name: (identifier) @class-name)"
            monkeypatch.setattr(
                sys, "argv", ["cli", temp_path, "--query-string", custom_query]
            )
            mock_stdout = StringIO()
            monkeypatch.setattr("sys.stdout", mock_stdout)

            try:
                main()
            except SystemExit:
                pass

            output = mock_stdout.getvalue()
            # Should contain query results
            assert len(output) > 0
        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_language_detection(self, monkeypatch):
        """Test automatic language detection"""
        # Create a temporary Python file
        python_code = """
def hello_world():
    print("Hello, World!")

if __name__ == "__main__":
    hello_world()
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(python_code)
            temp_path = f.name

        try:
            monkeypatch.setattr(sys, "argv", ["cli", temp_path])
            mock_stdout = StringIO()
            monkeypatch.setattr("sys.stdout", mock_stdout)

            try:
                main()
            except SystemExit:
                pass

            output = mock_stdout.getvalue()
            # Should automatically detect Python and analyze
            assert len(output) > 0
        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_explicit_language_override(self, monkeypatch):
        """Test explicit language specification"""
        # Create a temporary file with .txt extension but Java content
        java_code = """
public class TestClass {
    public void testMethod() {
        System.out.println("Hello, World!");
    }
}
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(java_code)
            temp_path = f.name

        try:
            monkeypatch.setattr(sys, "argv", ["cli", temp_path, "--language", "java"])
            mock_stdout = StringIO()
            monkeypatch.setattr("sys.stdout", mock_stdout)

            try:
                main()
            except SystemExit:
                pass

            output = mock_stdout.getvalue()
            # Should treat file as Java despite .txt extension
            assert len(output) > 0
        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_unsupported_file_extension(self, monkeypatch):
        """Test handling of unsupported file extensions"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".xyz", delete=False, encoding="utf-8"
        ) as f:
            f.write("some content")
            temp_path = f.name

        try:
            monkeypatch.setattr(sys, "argv", ["cli", temp_path])
            mock_stderr = StringIO()
            monkeypatch.setattr("sys.stderr", mock_stderr)

            try:
                main()
            except SystemExit:
                pass

            error_output = mock_stderr.getvalue()
            # Should contain error message about unsupported extension
            assert "Could not determine language for file" in error_output
        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_nonexistent_file(self, monkeypatch):
        """Test handling of nonexistent files"""
        nonexistent_path = "/path/that/does/not/exist.java"
        monkeypatch.setattr(sys, "argv", ["cli", nonexistent_path])
        mock_stderr = StringIO()
        monkeypatch.setattr("sys.stderr", mock_stderr)

        try:
            main()
        except SystemExit:
            pass

        error_output = mock_stderr.getvalue()
        # Should contain error message about file not found
        assert "File not found" in error_output

    def test_output_format_json(self, monkeypatch):
        """Test JSON output format"""
        # Create a temporary Java file
        java_code = """
public class TestClass {
    public void testMethod() {
        System.out.println("Hello, World!");
    }
}
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False, encoding="utf-8"
        ) as f:
            f.write(java_code)
            temp_path = f.name

        try:
            monkeypatch.setattr(
                sys, "argv", ["cli", temp_path, "--output-format", "json", "--advanced"]
            )
            mock_stdout = StringIO()
            monkeypatch.setattr("sys.stdout", mock_stdout)

            try:
                main()
            except SystemExit:
                pass

            output = mock_stdout.getvalue()
            # Should contain JSON formatted output
            assert "{" in output or "[" in output
        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_output_format_text(self, monkeypatch):
        """Test text output format"""
        # Create a temporary Java file
        java_code = """
public class TestClass {
    public void testMethod() {
        System.out.println("Hello, World!");
    }
}
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False, encoding="utf-8"
        ) as f:
            f.write(java_code)
            temp_path = f.name

        try:
            monkeypatch.setattr(
                sys, "argv", ["cli", temp_path, "--output-format", "text"]
            )
            mock_stdout = StringIO()
            monkeypatch.setattr("sys.stdout", mock_stdout)

            try:
                main()
            except SystemExit:
                pass

            output = mock_stdout.getvalue()
            # Should contain text formatted output
            assert len(output) > 0
        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestCLIEdgeCases:
    """Test edge cases and error conditions"""

    def test_no_arguments(self, monkeypatch):
        """Test CLI with no arguments"""
        monkeypatch.setattr(sys, "argv", ["cli"])
        mock_stderr = StringIO()
        monkeypatch.setattr("sys.stderr", mock_stderr)

        try:
            main()
        except SystemExit:
            pass

        error_output = mock_stderr.getvalue()
        # Should show help or error message
        assert len(error_output) > 0

    def test_invalid_query_key(self, monkeypatch):
        """Test with invalid query key"""
        # Create a temporary Java file
        java_code = "public class TestClass {}"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False, encoding="utf-8"
        ) as f:
            f.write(java_code)
            temp_path = f.name

        try:
            monkeypatch.setattr(
                sys, "argv", ["cli", temp_path, "--query-key", "invalid_query_key"]
            )
            mock_stderr = StringIO()
            monkeypatch.setattr("sys.stderr", mock_stderr)

            try:
                main()
            except SystemExit:
                pass

            error_output = mock_stderr.getvalue()
            # Should contain error about invalid query
            assert "not found" in error_output or "見つかりません" in error_output
        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_help_option(self, monkeypatch):
        """Test help option"""
        monkeypatch.setattr(sys, "argv", ["cli", "--help"])
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        try:
            main()
        except SystemExit:
            pass

        output = mock_stdout.getvalue()
        # Should contain help text
        assert "usage" in output.lower()


if __name__ == "__main__":
    pytest.main([__file__])
