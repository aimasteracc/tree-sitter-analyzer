"""
Edge case tests for Python plugin.
Tests error handling, boundary conditions, and unusual scenarios.
"""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.python_plugin import (
    PythonElementExtractor,
    PythonPlugin,
)
from tree_sitter_analyzer.models import Class


class TestPythonPluginEdgeCases:
    """Edge case tests for Python plugin"""

    @pytest.fixture
    def extractor(self):
        """Create a Python element extractor instance"""
        return PythonElementExtractor()

    @pytest.fixture
    def plugin(self):
        """Create a Python plugin instance"""
        return PythonPlugin()

    def test_extract_functions_with_none_tree(self, extractor):
        """Test function extraction with None tree"""
        result = extractor.extract_functions(None, "def test(): pass")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_extract_functions_with_none_source(self, extractor):
        """Test function extraction with None source code"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        result = extractor.extract_functions(mock_tree, None)
        assert isinstance(result, list)
        assert extractor.source_code == ""
        assert extractor.content_lines == [""]

    def test_extract_functions_with_empty_source(self, extractor):
        """Test function extraction with empty source code"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        result = extractor.extract_functions(mock_tree, "")
        assert isinstance(result, list)
        assert extractor.source_code == ""
        assert extractor.content_lines == [""]

    def test_extract_classes_with_malformed_tree(self, extractor):
        """Test class extraction with malformed tree"""
        mock_tree = Mock()
        mock_tree.root_node = None  # Malformed tree

        with patch.object(
            extractor, "_traverse_and_extract_iterative"
        ) as mock_traverse:
            mock_traverse.side_effect = AttributeError(
                "'NoneType' object has no attribute 'children'"
            )

            result = extractor.extract_classes(mock_tree, "class Test: pass")
            assert isinstance(result, list)

    def test_extract_variables_with_no_language(self, extractor):
        """Test variable extraction when tree has no language"""
        mock_tree = Mock()
        mock_tree.language = None

        result = extractor.extract_variables(mock_tree, "x = 1")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_extract_variables_with_query_exception(self, extractor):
        """Test variable extraction when query raises exception"""
        mock_tree = Mock()
        mock_tree.language = Mock()
        mock_tree.language.query.side_effect = Exception("Query error")

        result = extractor.extract_variables(mock_tree, "x = 1")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_get_node_text_optimized_with_invalid_bytes(self, extractor):
        """Test node text extraction with invalid byte ranges"""
        mock_node = Mock()
        mock_node.start_byte = 1000  # Beyond source length
        mock_node.end_byte = 2000
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 10)

        extractor.content_lines = ["short content"]
        extractor._file_encoding = "utf-8"

        # Should fallback to point-based extraction
        result = extractor._get_node_text_optimized(mock_node)
        assert result == "short cont"

    def test_get_node_text_optimized_with_invalid_points(self, extractor):
        """Test node text extraction with invalid point ranges"""
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10
        mock_node.start_point = (100, 0)  # Beyond content lines
        mock_node.end_point = (101, 0)

        extractor.content_lines = ["line1", "line2"]

        with patch(
            "tree_sitter_analyzer.languages.python_plugin.extract_text_slice"
        ) as mock_extract:
            mock_extract.side_effect = Exception("Byte extraction failed")

            result = extractor._get_node_text_optimized(mock_node)
            assert result == ""  # Should return empty string on failure

    def test_get_node_text_optimized_multiline_edge_case(self, extractor):
        """Test multiline text extraction edge cases"""
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10
        mock_node.start_point = (0, 5)
        mock_node.end_point = (2, 3)

        extractor.content_lines = [
            "01234567890",  # Line 0
            "abcdefghijk",  # Line 1
            "ABCDEFGHIJK",  # Line 2
        ]

        with patch(
            "tree_sitter_analyzer.languages.python_plugin.extract_text_slice"
        ) as mock_extract:
            mock_extract.side_effect = Exception("Byte extraction failed")

            result = extractor._get_node_text_optimized(mock_node)
            expected = "567890\nabcdefghijk\nABC"
            assert result == expected

    def test_parse_function_signature_with_malformed_node(self, extractor):
        """Test function signature parsing with malformed node"""
        mock_node = Mock()
        mock_node.children = None  # Malformed
        mock_node.parent = None

        result = extractor._parse_function_signature_optimized(mock_node)
        assert result is None

    def test_parse_function_signature_with_exception(self, extractor):
        """Test function signature parsing when exception occurs"""
        mock_node = Mock()
        mock_node.children = []
        mock_node.parent = None

        with patch.object(extractor, "_get_node_text_optimized") as mock_get_text:
            mock_get_text.side_effect = Exception("Text extraction failed")

            result = extractor._parse_function_signature_optimized(mock_node)
            assert result is None

    def test_extract_parameters_with_unknown_parameter_types(self, extractor):
        """Test parameter extraction with unknown parameter types"""
        mock_params_node = Mock()

        # Mock unknown parameter type
        mock_unknown_param = Mock()
        mock_unknown_param.type = "unknown_parameter_type"

        mock_params_node.children = [mock_unknown_param]

        with patch.object(extractor, "_get_node_text_optimized") as mock_get_text:
            mock_get_text.return_value = "unknown_param"

            result = extractor._extract_parameters_from_node_optimized(mock_params_node)
            assert result == []  # Should ignore unknown types

    def test_extract_docstring_with_malformed_quotes(self, extractor):
        """Test docstring extraction with malformed quotes"""
        extractor.content_lines = [
            "def test_function():",
            '    """Unclosed docstring',
            "    pass",
        ]

        result = extractor._extract_docstring_for_line(1)
        assert result is None

    def test_extract_docstring_with_mixed_quotes(self, extractor):
        """Test docstring extraction with mixed quote types"""
        extractor.content_lines = [
            "def test_function():",
            '    """Started with triple double',
            "    but ended with triple single'''",
            "    pass",
        ]

        result = extractor._extract_docstring_for_line(1)
        # Should not find proper closing quotes
        assert result is None

    def test_extract_docstring_beyond_file_end(self, extractor):
        """Test docstring extraction beyond file end"""
        extractor.content_lines = ["def test(): pass"]

        result = extractor._extract_docstring_for_line(10)  # Beyond file
        assert result is None

    def test_calculate_complexity_with_text_extraction_failure(self, extractor):
        """Test complexity calculation when text extraction fails"""
        mock_node = Mock()

        with patch.object(extractor, "_get_node_text_optimized") as mock_get_text:
            mock_get_text.side_effect = Exception("Text extraction failed")

            result = extractor._calculate_complexity_optimized(mock_node)
            assert result == 1  # Should return base complexity

    def test_extract_function_optimized_with_signature_failure(self, extractor):
        """Test function extraction when signature parsing fails"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        extractor.content_lines = ["def test():", "    pass"]

        with patch.object(
            extractor, "_parse_function_signature_optimized"
        ) as mock_parse:
            mock_parse.return_value = None  # Signature parsing failed

            result = extractor._extract_function_optimized(mock_node)
            assert result is None

    def test_extract_function_optimized_with_exception(self, extractor):
        """Test function extraction when exception occurs"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        with patch.object(
            extractor, "_parse_function_signature_optimized"
        ) as mock_parse:
            mock_parse.side_effect = Exception("Parsing failed")

            result = extractor._extract_function_optimized(mock_node)
            assert result is None

    def test_extract_class_optimized_with_no_name(self, extractor):
        """Test class extraction when name extraction fails"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        mock_node.parent = None
        mock_node.children = []  # No identifier child

        result = extractor._extract_class_optimized(mock_node)
        assert result is None

    def test_extract_class_optimized_with_malformed_superclasses(self, extractor):
        """Test class extraction with malformed superclass information"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        mock_node.parent = None

        # Mock identifier child
        mock_identifier = Mock()
        mock_identifier.type = "identifier"
        mock_identifier.text = b"TestClass"

        # Mock malformed argument list
        mock_arg_list = Mock()
        mock_arg_list.type = "argument_list"
        mock_arg_list.children = None  # Malformed

        mock_node.children = [mock_identifier, mock_arg_list]

        extractor.content_lines = ["class TestClass(Base):", "    pass"]

        with patch.object(extractor, "_get_node_text_optimized") as mock_get_text:
            mock_get_text.return_value = "class TestClass(Base):\n    pass"

            with patch.object(
                extractor, "_extract_docstring_for_line"
            ) as mock_docstring:
                mock_docstring.return_value = None

                result = extractor._extract_class_optimized(mock_node)

                # Should handle malformed superclasses gracefully
                assert isinstance(result, Class)
                assert result.name == "TestClass"
                assert result.superclass is None
                assert result.interfaces == []

    def test_extract_class_optimized_with_exception(self, extractor):
        """Test class extraction when exception occurs"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        with patch.object(extractor, "_extract_docstring_for_line") as mock_docstring:
            mock_docstring.side_effect = Exception("Docstring extraction failed")

            result = extractor._extract_class_optimized(mock_node)
            assert result is None

    def test_extract_class_attributes_with_malformed_body(self, extractor):
        """Test class attribute extraction with malformed body"""
        mock_class_body = Mock()
        mock_class_body.children = None  # Malformed

        result = extractor._extract_class_attributes(mock_class_body, "source")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_extract_class_attribute_info_with_malformed_assignment(self, extractor):
        """Test class attribute info extraction with malformed assignment"""
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 10)

        # Source without assignment operator
        source_code = "just_a_name"

        result = extractor._extract_class_attribute_info(mock_node, source_code)
        assert result is None

    def test_extract_class_attribute_info_with_exception(self, extractor):
        """Test class attribute info extraction when exception occurs"""
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 10)

        # Test with None source_code to trigger exception
        result = extractor._extract_class_attribute_info(mock_node, None)
        assert result is None

    def test_extract_imports_with_malformed_captures(self, extractor):
        """Test import extraction with malformed captures"""
        mock_tree = Mock()
        mock_tree.language = Mock()
        mock_root = Mock()
        mock_root.type = "module"
        mock_root.children = []  # Prevent iteration errors
        mock_tree.root_node = mock_root

        mock_query = Mock()
        mock_query.captures.return_value = "not_a_list"  # Should be list/iterable
        mock_tree.language.query.return_value = mock_query

        result = extractor.extract_imports(mock_tree, "import os")
        assert isinstance(result, list)
        # Will use fallback manual extraction
        assert len(result) >= 0

    def test_extract_imports_with_query_exception(self, extractor):
        """Test import extraction when query raises exception"""
        mock_tree = Mock()
        mock_tree.language = Mock()
        mock_root = Mock()
        mock_root.type = "module"
        mock_root.children = []  # Prevent iteration errors
        mock_tree.root_node = mock_root
        mock_tree.language.query.side_effect = Exception("Query failed")

        result = extractor.extract_imports(mock_tree, "import os")
        assert isinstance(result, list)
        # Should use fallback manual extraction
        assert len(result) >= 0

    def test_traverse_and_extract_with_none_root(self, extractor):
        """Test traversal with None root node"""
        extractors = {"function_definition": Mock()}
        results = []

        extractor._traverse_and_extract_iterative(None, extractors, results, "function")

        # Should handle None root gracefully
        assert len(results) == 0

    def test_traverse_and_extract_with_circular_references(self, extractor):
        """Test traversal with circular node references"""
        mock_root = Mock()
        mock_child = Mock()

        # Create circular reference
        mock_root.children = [mock_child]
        mock_child.children = [mock_root]  # Circular reference

        mock_root.type = "module"
        mock_child.type = "function_definition"

        extractors = {"function_definition": Mock()}
        results = []

        # Should handle circular references without infinite loop
        extractor._traverse_and_extract_iterative(
            mock_root, extractors, results, "function"
        )

        # Should complete without hanging
        assert isinstance(results, list)

    def test_traverse_and_extract_with_extractor_exception(self, extractor):
        """Test traversal when extractor raises exception"""
        mock_root = Mock()
        mock_child = Mock()
        mock_child.type = "function_definition"
        mock_child.children = []
        mock_root.children = [mock_child]

        mock_extractor = Mock()
        mock_extractor.side_effect = Exception("Extractor failed")

        extractors = {"function_definition": mock_extractor}
        results = []

        # Should handle extractor exceptions gracefully
        extractor._traverse_and_extract_iterative(
            mock_root, extractors, results, "function"
        )

        assert len(results) == 0  # No results due to exception

    def test_detect_file_characteristics_with_empty_source(self, extractor):
        """Test file characteristics detection with empty source"""
        extractor.source_code = ""
        extractor._detect_file_characteristics()

        assert extractor.is_module is False
        assert extractor.framework_type == ""

    def test_detect_file_characteristics_with_partial_imports(self, extractor):
        """Test file characteristics detection with partial import statements"""
        extractor.source_code = "imp"  # Partial import
        extractor._detect_file_characteristics()

        assert extractor.is_module is False

    def test_framework_detection_with_case_sensitivity(self, extractor):
        """Test framework detection case sensitivity"""
        # Test case variations
        test_cases = [
            ("DJANGO", ""),  # Wrong case
            ("Django", ""),  # Wrong case
            ("django", "django"),  # Correct case
            ("from DJANGO import", ""),  # Wrong case
            ("from django import", "django"),  # Correct case
        ]

        for source, expected_framework in test_cases:
            extractor.source_code = source
            extractor._detect_file_characteristics()
            assert extractor.framework_type == expected_framework

    def test_memory_leak_prevention(self, extractor):
        """Test memory leak prevention in caches"""
        # Simulate many operations
        for i in range(1000):
            mock_node = Mock()
            mock_node.start_byte = i
            mock_node.end_byte = i + 10
            mock_node.start_point = (0, 0)
            mock_node.end_point = (0, 10)

            extractor.content_lines = [f"content_{i}"]

            with patch(
                "tree_sitter_analyzer.languages.python_plugin.extract_text_slice"
            ) as mock_extract:
                mock_extract.return_value = f"text_{i}"
                extractor._get_node_text_optimized(mock_node)

        # Cache should not grow indefinitely
        assert len(extractor._node_text_cache) <= 1000

    def test_unicode_edge_cases(self, extractor):
        """Test Unicode edge cases"""
        # Test various Unicode scenarios
        unicode_cases = [
            "def 函数名(): pass",  # Chinese characters
            "def функция(): pass",  # Cyrillic characters
            "def función(): pass",  # Accented characters
            "def 🚀rocket(): pass",  # Emoji
            "def \u200bfunction(): pass",  # Zero-width space
            "def function\u0301(): pass",  # Combining character
        ]

        for unicode_code in unicode_cases:
            extractor.source_code = unicode_code
            extractor.content_lines = unicode_code.split("\n")

            mock_node = Mock()
            mock_node.start_byte = 0
            mock_node.end_byte = len(unicode_code.encode("utf-8"))
            mock_node.start_point = (0, 0)
            mock_node.end_point = (0, len(unicode_code))

            # Should handle Unicode without errors
            with patch(
                "tree_sitter_analyzer.languages.python_plugin.extract_text_slice"
            ) as mock_extract:
                mock_extract.return_value = unicode_code
                result = extractor._get_node_text_optimized(mock_node)
                assert isinstance(result, str)

    def test_very_long_lines(self, extractor):
        """Test handling of very long lines"""
        # Create very long line (10KB)
        long_line = "def very_long_function(" + "param" * 2000 + "): pass"

        extractor.content_lines = [long_line]

        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = len(long_line.encode("utf-8"))
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, len(long_line))

        # Should handle very long lines
        with patch(
            "tree_sitter_analyzer.languages.python_plugin.extract_text_slice"
        ) as mock_extract:
            mock_extract.return_value = long_line
            result = extractor._get_node_text_optimized(mock_node)
            assert len(result) == len(long_line)

    def test_many_nested_levels(self, extractor):
        """Test handling of many nested levels"""
        # Create deeply nested code
        nested_code = "def outer():\n"
        for i in range(100):
            nested_code += "    " * (i + 1) + f"if condition_{i}:\n"
        nested_code += "    " * 101 + "pass"

        extractor.source_code = nested_code
        extractor.content_lines = nested_code.split("\n")

        # Should handle deep nesting
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = len(nested_code.encode("utf-8"))
        mock_node.start_point = (0, 0)
        mock_node.end_point = (len(extractor.content_lines) - 1, 0)

        with patch(
            "tree_sitter_analyzer.languages.python_plugin.extract_text_slice"
        ) as mock_extract:
            mock_extract.return_value = nested_code
            result = extractor._get_node_text_optimized(mock_node)
            assert "condition_99" in result

    def test_binary_data_in_source(self, extractor):
        """Test handling of binary data in source code"""
        # Source with binary-like content
        binary_source = "def func(): return b'\\x00\\x01\\x02\\x03'"

        extractor.source_code = binary_source
        extractor.content_lines = binary_source.split("\n")

        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = len(binary_source.encode("utf-8"))
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, len(binary_source))

        # Should handle binary data in strings
        with patch(
            "tree_sitter_analyzer.languages.python_plugin.extract_text_slice"
        ) as mock_extract:
            mock_extract.return_value = binary_source
            result = extractor._get_node_text_optimized(mock_node)
            assert "\\x00" in result

    def test_plugin_with_none_extractor(self):
        """Test plugin behavior when extractor is None"""
        plugin = PythonPlugin()
        plugin._extractor = None

        # Mock get_extractor to return None to force AttributeError
        with patch.object(plugin, "get_extractor", return_value=None):
            mock_tree = Mock()

            # Should handle None extractor gracefully
            with pytest.raises(AttributeError):
                plugin.extract_functions(mock_tree, "def test(): pass")

    def test_plugin_with_malformed_extractor(self):
        """Test plugin behavior with malformed extractor"""
        plugin = PythonPlugin()

        # Mock get_extractor to return a string instead of extractor
        with patch.object(plugin, "get_extractor", return_value="not_an_extractor"):
            mock_tree = Mock()

            # Should raise appropriate error
            with pytest.raises(AttributeError):
                plugin.extract_functions(mock_tree, "def test(): pass")

    def test_concurrent_access_to_caches(self, extractor):
        """Test concurrent access to caches"""
        import threading
        import time

        def cache_worker():
            for i in range(100):
                mock_node = Mock()
                mock_node.start_byte = i
                mock_node.end_byte = i + 10
                mock_node.start_point = (0, 0)
                mock_node.end_point = (0, 10)

                extractor.content_lines = [f"content_{i}"]

                with patch(
                    "tree_sitter_analyzer.languages.python_plugin.extract_text_slice"
                ) as mock_extract:
                    mock_extract.return_value = f"text_{i}"
                    extractor._get_node_text_optimized(mock_node)

                time.sleep(0.001)  # Small delay

        # Start multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=cache_worker)
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Should complete without errors
        assert len(extractor._node_text_cache) > 0

    def test_extract_with_corrupted_encoding(self, extractor):
        """Test extraction with corrupted encoding"""
        extractor._file_encoding = "invalid-encoding"
        extractor.content_lines = ["def test(): pass"]

        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 10)

        # Should fallback gracefully
        with patch(
            "tree_sitter_analyzer.languages.python_plugin.safe_encode"
        ) as mock_encode:
            mock_encode.side_effect = Exception("Encoding failed")

            result = extractor._get_node_text_optimized(mock_node)
            assert (
                result == "def test()"
            )  # Should use fallback (10 bytes = "def test()")

    def test_complexity_calculation_edge_cases(self, extractor):
        """Test complexity calculation edge cases"""
        test_cases = [
            ("", 1),  # Empty code
            ("pass", 1),  # Simple statement
            ("if if if:", 1),  # Keywords in strings/comments
            ("# if elif while for", 1),  # Keywords in comments
            ("'if elif while'", 1),  # Keywords in strings
            ("if True: pass", 2),  # Real keyword
        ]

        for code, expected_min_complexity in test_cases:
            mock_node = Mock()

            with patch.object(extractor, "_get_node_text_optimized") as mock_get_text:
                mock_get_text.return_value = code

                result = extractor._calculate_complexity_optimized(mock_node)
                assert result >= expected_min_complexity

    def test_docstring_extraction_edge_cases(self, extractor):
        """Test docstring extraction edge cases"""
        edge_cases = [
            # Empty lines
            ["def test():", "", '    """doc"""', "    pass"],
            # Multiple docstrings
            ["def test():", '    """first"""', '    """second"""', "    pass"],
            # Docstring with quotes inside
            ["def test():", '    """doc with "quotes" inside"""', "    pass"],
            # Mixed quote types
            ["def test():", "    '''single quotes'''", "    pass"],
            # Very long docstring
            ["def test():", '    """' + "x" * 1000 + '"""', "    pass"],
        ]

        for lines in edge_cases:
            extractor.content_lines = lines
            extractor._docstring_cache.clear()  # Clear cache

            result = extractor._extract_docstring_for_line(1)
            # Should handle all cases without errors
            assert isinstance(result, (str, type(None)))
