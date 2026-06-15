#!/usr/bin/env python3
"""Robustness tests for JavaScriptTableFormatter — empty/None/malformed data, performance, unicode, concurrency."""

from unittest.mock import patch

import pytest

from tree_sitter_analyzer.formatters.javascript_formatter import (
    JavaScriptTableFormatter,
)


class TestJavaScriptFormatterRobustness:
    """Robustness and resilience tests for JavaScriptTableFormatter"""

    @pytest.fixture
    def formatter(self) -> JavaScriptTableFormatter:
        """Create a JavaScriptTableFormatter instance for testing"""
        return JavaScriptTableFormatter()

    def test_format_with_missing_statistics(self, formatter):
        """Test formatting with missing statistics"""
        data = {
            "file_path": "test.js",
            "imports": [],
            "exports": [],
            "classes": [],
            "variables": [],
            "functions": [],
            # Missing statistics
        }

        result = formatter._format_full_table(data)

        # Should handle missing statistics gracefully and return valid output
        assert isinstance(result, str)
        assert "test" in result

    def test_format_with_empty_data(self, formatter):
        """Test formatting with completely empty data"""
        data = {}

        result = formatter._format_full_table(data)

        # Should handle empty data gracefully
        assert isinstance(result, str)
        assert result == "# Unknown"

    def test_format_compact_with_empty_data(self, formatter):
        """Test compact formatting with completely empty data"""
        data = {}

        result = formatter._format_compact_table(data)

        # Should handle empty data gracefully
        assert isinstance(result, str)
        assert result == (
            "# Unknown\n"
            "\n"
            "## Info\n"
            "| Property | Value |\n"
            "|----------|-------|\n"
            "| Package |  |\n"
            "| Methods | 0 |\n"
            "| Fields | 0 |"
        )

    def test_format_csv_with_empty_data(self, formatter):
        """Test CSV formatting with completely empty data"""
        data = {}

        result = formatter._format_csv(data)

        # Should handle empty data gracefully
        assert isinstance(result, str)
        assert result == "Type,Name,Signature,Visibility,Lines,Complexity,Doc"

    def test_format_json_with_empty_data(self, formatter):
        """Test JSON formatting with completely empty data"""
        data = {}

        result = formatter._format_json(data)

        # Should handle empty data gracefully
        assert isinstance(result, str)
        assert result == "{}"

    def test_format_with_none_values(self, formatter):
        """Test formatting with None values in data"""
        data = {
            "file_path": None,
            "imports": None,
            "exports": None,
            "classes": None,
            "variables": None,
            "functions": None,
            "statistics": None,
        }

        result = formatter._format_full_table(data)

        # Should handle None values gracefully (same fallback as empty data)
        assert isinstance(result, str)
        assert result == "# Unknown"

    def test_format_with_malformed_data(self, formatter):
        """Test formatting with malformed data structures"""
        data = {
            "file_path": "test.js",
            "imports": "not_a_list",  # Should be list
            "exports": {"not": "a_list"},  # Should be list
            "classes": None,
            "variables": [],
            "functions": [],
            "statistics": "not_a_dict",  # Should be dict
        }

        # Should not raise exception
        result = formatter._format_full_table(data)
        assert isinstance(result, str)

    def test_get_function_signature_edge_cases(self, formatter):
        """Test function signature generation with edge cases"""
        # Function with no parameters
        func_data = {"name": "noParams", "parameters": []}
        result = formatter._get_function_signature(func_data)
        assert result == "noParams()"

        # Function with None parameters
        func_data = {"name": "noneParams", "parameters": None}
        result = formatter._get_function_signature(func_data)
        assert result == "noneParams()"

        # Function with malformed parameters
        func_data = {"name": "malformedParams", "parameters": "not_a_list"}
        result = formatter._get_function_signature(func_data)
        assert result == "malformedParams()"

    def test_get_class_info_edge_cases(self, formatter):
        """Test class info generation with edge cases"""
        # Class with no methods
        class_data = {"name": "EmptyClass", "methods": []}
        result = formatter._get_class_info(class_data)
        assert result == "EmptyClass (0 methods)"

        # Class with None methods
        class_data = {"name": "NoneMethodsClass", "methods": None}
        result = formatter._get_class_info(class_data)
        assert result == "NoneMethodsClass (0 methods)"

        # Class with malformed methods
        class_data = {"name": "MalformedClass", "methods": "not_a_list"}
        result = formatter._get_class_info(class_data)
        assert result == "MalformedClass (0 methods)"

    def test_infer_js_type_edge_cases(self, formatter):
        """Test JavaScript type inference with edge cases"""
        edge_cases = [
            ("", "unknown"),
            ("   ", "unknown"),
            ("undefined", "undefined"),
            ("NaN", "number"),
            ("Infinity", "number"),
            ("-Infinity", "number"),
            ("Symbol('test')", "unknown"),
            ("BigInt(123)", "unknown"),
            ("new Date()", "unknown"),
            ("new RegExp()", "unknown"),
            ("/pattern/g", "unknown"),
            ("async function() {}", "function"),
            ("function*() {}", "function"),
            ("async () => {}", "function"),
            ("new Function()", "function"),
        ]

        for value, expected in edge_cases:
            result = formatter._infer_js_type(value)
            assert result == expected, f"Failed for value: '{value}'"

    def test_determine_scope_edge_cases(self, formatter):
        """Test variable scope determination with edge cases"""
        edge_cases = [
            ({}, "unknown"),  # Empty dict
            ({"raw_text": ""}, "unknown"),  # Empty text
            ({"raw_text": "   "}, "unknown"),  # Whitespace only
            ({"raw_text": "const"}, "block"),  # Just keyword
            ({"raw_text": "let"}, "block"),  # Just keyword
            ({"raw_text": "var"}, "function"),  # Just keyword
            ({"raw_text": "CONST x = 1"}, "unknown"),  # Wrong case
            ({"raw_text": "LET x = 1"}, "unknown"),  # Wrong case
            ({"raw_text": "VAR x = 1"}, "unknown"),  # Wrong case
        ]

        for var_data, expected in edge_cases:
            with patch.object(formatter, "_get_variable_kind") as mock_get_kind:
                if var_data.get("is_constant") or var_data.get(
                    "raw_text", ""
                ).strip().startswith("const"):
                    mock_get_kind.return_value = "const"
                elif var_data.get("raw_text", "").strip().startswith("let"):
                    mock_get_kind.return_value = "let"
                elif var_data.get("raw_text", "").strip().startswith("var"):
                    mock_get_kind.return_value = "var"
                else:
                    mock_get_kind.return_value = "unknown"

                result = formatter._determine_scope(var_data)
                assert result == expected, f"Failed for var_data: {var_data}"

    def test_get_variable_kind_edge_cases(self, formatter):
        """Test variable kind detection with edge cases"""
        edge_cases = [
            ({}, "unknown"),  # Empty dict
            ({"raw_text": None}, "unknown"),  # None text
            ({"raw_text": ""}, "unknown"),  # Empty text
            ({"raw_text": "   "}, "unknown"),  # Whitespace only
            ({"is_constant": False}, "unknown"),  # False constant
            ({"is_constant": None}, "unknown"),  # None constant
            ({"raw_text": "const x = 1; let y = 2"}, "const"),  # Multiple keywords
            ({"raw_text": "// const x = 1"}, "unknown"),  # Commented out
            ({"raw_text": "string_const = 'const'"}, "unknown"),  # In string
        ]

        for var_data, expected in edge_cases:
            result = formatter._get_variable_kind(var_data)
            assert result == expected, f"Failed for var_data: {var_data}"

    def test_get_export_type_edge_cases(self, formatter):
        """Test export type detection with edge cases"""
        edge_cases = [
            ({}, "unknown"),  # Empty dict
            ({"is_default": False}, "unknown"),  # False flags
            ({"is_named": False}, "unknown"),
            ({"is_all": False}, "unknown"),
            ({"is_default": None}, "unknown"),  # None flags
            ({"is_named": None}, "unknown"),
            ({"is_all": None}, "unknown"),
            (
                {"is_default": True, "is_named": True},
                "default",
            ),  # Multiple flags (default wins)
            (
                {"is_named": True, "is_all": True},
                "named",
            ),  # Multiple flags (named wins)
            ({"unknown_flag": True}, "unknown"),  # Unknown flag
        ]

        for export_data, expected in edge_cases:
            result = formatter._get_export_type(export_data)
            assert result == expected, f"Failed for export_data: {export_data}"

    def test_format_performance_with_large_data(self, formatter):
        """Test formatting performance with large datasets"""
        import time

        # Create large dataset
        large_data = {
            "file_path": "large_test.js",
            "imports": [
                {"name": f"import{i}", "source": f"module{i}"} for i in range(100)
            ],
            "exports": [{"name": f"export{i}", "is_named": True} for i in range(100)],
            "classes": [{"name": f"Class{i}", "methods": []} for i in range(50)],
            "variables": [{"name": f"var{i}", "type": "string"} for i in range(200)],
            "functions": [{"name": f"func{i}", "parameters": []} for i in range(150)],
            "statistics": {"function_count": 150, "variable_count": 200},
        }

        # Test full table formatting
        start_time = time.time()
        result = formatter._format_full_table(large_data)
        end_time = time.time()

        # Should complete within reasonable time (5 seconds)
        assert end_time - start_time < 5.0
        assert isinstance(result, str)
        assert len(result) == 3124  # exact output size for this fixed dataset

        # Test compact table formatting
        start_time = time.time()
        result = formatter._format_compact_table(large_data)
        end_time = time.time()

        # Should complete within reasonable time (5 seconds)
        assert end_time - start_time < 5.0
        assert isinstance(result, str)
        assert len(result) == 105  # exact output size for this fixed dataset

    def test_unicode_handling(self, formatter):
        """Test handling of Unicode characters in data"""
        unicode_data = {
            "file_path": "unicode_test.js",
            "imports": [{"name": "モジュール", "source": "ライブラリ"}],
            "exports": [{"name": "エクスポート", "is_named": True}],
            "classes": [{"name": "クラス", "methods": []}],
            "variables": [{"name": "変数", "type": "文字列"}],
            "functions": [{"name": "関数", "parameters": []}],
            "statistics": {"function_count": 1, "variable_count": 1},
        }

        # Should handle Unicode without errors
        result = formatter._format_full_table(unicode_data)
        assert isinstance(result, str)
        # Check that the class name (which is used in the header) is present
        assert "クラス" in result

    def test_special_characters_handling(self, formatter):
        """Test handling of special characters in data"""
        special_data = {
            "file_path": "special_test.js",
            "imports": [{"name": "module<>", "source": "lib|pipe"}],
            "exports": [{"name": "export&amp;", "is_named": True}],
            "classes": [{"name": 'Class"quote', "methods": []}],
            "variables": [{"name": "var'apostrophe", "type": "string"}],
            "functions": [{"name": "func\ttab", "parameters": []}],
            "statistics": {"function_count": 1, "variable_count": 1},
        }

        # Should handle special characters without errors
        result = formatter._format_full_table(special_data)
        assert isinstance(result, str)
        assert len(result) == 217  # exact output size for this fixed dataset
        assert 'Class"quote' in result

    def test_memory_usage_with_repeated_calls(self, formatter):
        """Test memory usage with repeated formatting calls"""
        import gc

        data = {
            "file_path": "memory_test.js",
            "imports": [{"name": "test", "source": "module"}],
            "exports": [{"name": "test", "is_named": True}],
            "classes": [{"name": "Test", "methods": []}],
            "variables": [{"name": "test", "type": "string"}],
            "functions": [{"name": "test", "parameters": []}],
            "statistics": {"function_count": 1, "variable_count": 1},
        }

        # Perform many formatting operations
        for _ in range(100):
            formatter._format_full_table(data)
            formatter._format_compact_table(data)
            formatter._format_csv(data)
            formatter._format_json(data)

        # Force garbage collection
        gc.collect()

        # Should not cause memory issues (test passes if no exception)
        assert True

    def test_concurrent_formatting(self, formatter):
        """Test concurrent formatting operations"""
        import queue
        import threading

        data = {
            "file_path": "concurrent_test.js",
            "imports": [{"name": "test", "source": "module"}],
            "exports": [{"name": "test", "is_named": True}],
            "classes": [{"name": "Test", "methods": []}],
            "variables": [{"name": "test", "type": "string"}],
            "functions": [{"name": "test", "parameters": []}],
            "statistics": {"function_count": 1, "variable_count": 1},
        }

        results = queue.Queue()

        def format_worker():
            try:
                result = formatter._format_full_table(data)
                results.put(("success", result))
            except Exception as e:
                results.put(("error", str(e)))

        # Start multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=format_worker)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Check results
        success_count = 0
        while not results.empty():
            status, result = results.get()
            if status == "success":
                success_count += 1
                assert isinstance(result, str)
                assert len(result) == 196  # exact output size for this fixed dataset

        # All threads should succeed
        assert success_count == 5
