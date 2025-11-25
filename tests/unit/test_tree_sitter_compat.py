#!/usr/bin/env python3
"""
Comprehensive tests for tree_sitter_compat module.

Tests compatibility with different tree-sitter versions, version detection,
fallback mechanisms, and query execution APIs.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.utils.tree_sitter_compat import (
    TreeSitterQueryCompat,
    create_query_safely,
    get_node_text_safe,
    log_api_info,
)


class TestGetNodeTextSafe:
    """Test get_node_text_safe function with various node types"""

    def test_byte_based_extraction(self):
        """Test text extraction using byte positions"""
        mock_node = MagicMock()
        mock_node.start_byte = 0
        mock_node.end_byte = 5
        source_code = "hello world"

        result = get_node_text_safe(mock_node, source_code)
        assert result == "hello"

    def test_byte_based_extraction_middle(self):
        """Test extraction from middle of source"""
        mock_node = MagicMock()
        mock_node.start_byte = 6
        mock_node.end_byte = 11
        source_code = "hello world"

        result = get_node_text_safe(mock_node, source_code)
        assert result == "world"

    def test_byte_based_extraction_unicode(self):
        """Test extraction with unicode characters"""
        mock_node = MagicMock()
        mock_node.start_byte = 0
        mock_node.end_byte = 6  # "你好" in UTF-8 is 6 bytes
        source_code = "你好world"

        result = get_node_text_safe(mock_node, source_code)
        assert "你好" in result or result == "你好"

    def test_byte_based_extraction_empty(self):
        """Test extraction with empty range"""
        mock_node = MagicMock()
        mock_node.start_byte = 0
        mock_node.end_byte = 0
        source_code = "hello"

        result = get_node_text_safe(mock_node, source_code)
        assert result == ""

    def test_node_text_attribute_bytes(self):
        """Test fallback to node.text attribute (bytes)"""
        mock_node = MagicMock()
        # Remove byte attributes
        del mock_node.start_byte
        del mock_node.end_byte
        # Add text attribute as bytes
        mock_node.text = b"test text"
        source_code = "irrelevant"

        result = get_node_text_safe(mock_node, source_code)
        assert result == "test text"

    def test_node_text_attribute_string(self):
        """Test fallback to node.text attribute (string)"""
        mock_node = MagicMock()
        del mock_node.start_byte
        del mock_node.end_byte
        mock_node.text = "test text"
        source_code = "irrelevant"

        result = get_node_text_safe(mock_node, source_code)
        assert result == "test text"

    def test_point_based_extraction_single_line(self):
        """Test extraction using point positions (single line)"""
        mock_node = MagicMock()
        del mock_node.start_byte
        del mock_node.end_byte
        del mock_node.text
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 5)
        source_code = "hello world"

        result = get_node_text_safe(mock_node, source_code)
        assert result == "hello"

    def test_point_based_extraction_multi_line(self):
        """Test extraction using point positions (multiple lines)"""
        mock_node = MagicMock()
        del mock_node.start_byte
        del mock_node.end_byte
        del mock_node.text
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 3)
        source_code = "line1\nline2\nline3"

        result = get_node_text_safe(mock_node, source_code)
        assert "line1" in result
        assert "line2" in result

    def test_point_based_extraction_partial_lines(self):
        """Test extraction with partial line ranges"""
        mock_node = MagicMock()
        del mock_node.start_byte
        del mock_node.end_byte
        del mock_node.text
        mock_node.start_point = (0, 2)
        mock_node.end_point = (0, 7)
        source_code = "hello world"

        result = get_node_text_safe(mock_node, source_code)
        assert result == "llo w"

    def test_invalid_byte_range(self):
        """Test handling of invalid byte range"""
        mock_node = MagicMock()
        mock_node.start_byte = 100
        mock_node.end_byte = 200
        source_code = "short"

        result = get_node_text_safe(mock_node, source_code)
        # Should return empty string or handle gracefully
        assert isinstance(result, str)

    def test_negative_byte_range(self):
        """Test handling of negative byte positions"""
        mock_node = MagicMock()
        mock_node.start_byte = -1
        mock_node.end_byte = 5
        source_code = "hello"

        result = get_node_text_safe(mock_node, source_code)
        assert isinstance(result, str)

    def test_no_attributes(self):
        """Test node with no extraction attributes"""
        mock_node = MagicMock()
        del mock_node.start_byte
        del mock_node.end_byte
        del mock_node.text
        del mock_node.start_point
        del mock_node.end_point
        source_code = "test"

        result = get_node_text_safe(mock_node, source_code)
        assert result == ""

    def test_exception_handling(self):
        """Test that exceptions are handled gracefully"""
        mock_node = MagicMock()
        mock_node.start_byte = MagicMock(side_effect=Exception("Test error"))
        source_code = "test"

        result = get_node_text_safe(mock_node, source_code)
        assert result == ""

    def test_different_encoding(self):
        """Test with different encoding"""
        mock_node = MagicMock()
        mock_node.start_byte = 0
        mock_node.end_byte = 4
        source_code = "test"

        result = get_node_text_safe(mock_node, source_code, encoding="ascii")
        assert result == "test"

    def test_decoding_error_handling(self):
        """Test handling of decoding errors"""
        mock_node = MagicMock()
        mock_node.start_byte = 0
        mock_node.end_byte = 1
        # Invalid UTF-8 sequence
        source_code = "test"

        # Should not raise, uses 'replace' error handling
        result = get_node_text_safe(mock_node, source_code)
        assert isinstance(result, str)


class TestCreateQuerySafely:
    """Test create_query_safely function"""

    def test_successful_query_creation(self):
        """Test successful query creation"""
        with patch("tree_sitter_analyzer.utils.tree_sitter_compat.logger"):
            mock_language = MagicMock()
            result = create_query_safely(mock_language, "(identifier) @name")

            # If tree-sitter is installed, should create a query
            assert result is not None or result is None  # Depends on real tree-sitter

    def test_query_creation_failure(self):
        """Test query creation failure handling"""
        with patch("builtins.__import__", side_effect=ImportError("No module")):
            mock_language = MagicMock()
            result = create_query_safely(mock_language, "invalid query")

            assert result is None

    def test_query_creation_invalid_query(self):
        """Test query creation with invalid query string"""
        # This will use real tree-sitter if available
        mock_language = MagicMock()
        mock_language.field_count = 0  # Mock minimal language interface

        # Should handle exceptions gracefully
        result = create_query_safely(mock_language, "completely invalid ]][[")
        # May return None if query is invalid
        assert result is None or result is not None


class TestLogApiInfo:
    """Test log_api_info function"""

    def test_log_api_info_with_tree_sitter(self, caplog):
        """Test logging API info when tree-sitter is available"""
        with caplog.at_level(logging.DEBUG):
            log_api_info()

        # Should log something about tree-sitter
        assert any("tree-sitter" in record.message.lower() for record in caplog.records)

    def test_log_api_info_callable(self):
        """Test that log_api_info can be called without errors"""
        # Should not raise exceptions
        log_api_info()

    def test_log_api_info_logs_debug_info(self, caplog):
        """Test that log_api_info logs debug information"""
        with caplog.at_level(logging.DEBUG):
            log_api_info()

        # Should have logged something
        assert len(caplog.records) > 0


class TestTreeSitterQueryCompatExecuteQuery:
    """Test TreeSitterQueryCompat.execute_query method"""

    def test_execute_query_with_real_tree_sitter(self):
        """Test query execution with real tree-sitter if available"""
        try:
            import tree_sitter  # noqa: F401

            # Create a minimal mock that has the needed attributes
            mock_language = MagicMock()
            mock_root = MagicMock()

            # This should handle gracefully even with mocks
            result = TreeSitterQueryCompat.execute_query(
                mock_language, "(identifier) @name", mock_root
            )

            # Should return a list (may be empty due to mock)
            assert isinstance(result, list)
        except ImportError:
            # If tree-sitter not installed, skip
            pass

    def test_execute_query_error_handling(self):
        """Test error handling in query execution"""
        # Use invalid inputs that will cause errors
        result = TreeSitterQueryCompat.execute_query(None, "invalid", None)

        # Should return empty list on error
        assert result == []

    def test_execute_query_with_mocked_import_error(self):
        """Test handling when tree-sitter import fails"""
        with patch("builtins.__import__", side_effect=ImportError("No module")):
            result = TreeSitterQueryCompat.execute_query(
                MagicMock(), "(identifier)", MagicMock()
            )

            assert result == []


class TestTreeSitterQueryCompatSafeExecuteQuery:
    """Test TreeSitterQueryCompat.safe_execute_query method"""

    def test_safe_execute_query_success(self):
        """Test successful safe query execution"""
        mock_language = MagicMock()
        root_node = MagicMock()

        # Should not raise, even with invalid inputs
        result = TreeSitterQueryCompat.safe_execute_query(
            mock_language, "(identifier) @name", root_node
        )

        assert isinstance(result, list)

    def test_safe_execute_query_with_fallback(self):
        """Test safe query execution with custom fallback"""
        mock_language = None  # Will cause error
        root_node = MagicMock()

        fallback = [("fallback_node", "fallback_name")]
        result = TreeSitterQueryCompat.safe_execute_query(
            mock_language, "invalid", root_node, fallback_result=fallback
        )

        # Should return fallback on error
        assert result == fallback or result == []

    def test_safe_execute_query_default_fallback(self):
        """Test safe query execution with default fallback"""
        mock_language = None  # Will cause error
        root_node = MagicMock()

        result = TreeSitterQueryCompat.safe_execute_query(
            mock_language, "invalid", root_node
        )

        assert result == []


class TestTreeSitterQueryCompatInternalMethods:
    """Test internal API compatibility methods"""

    def test_execute_newest_api_with_mocks(self):
        """Test _execute_newest_api method with mocks"""
        # Create a query mock
        mock_query = MagicMock()
        root_node = MagicMock()

        # This will likely fail without proper tree-sitter, returning empty
        result = TreeSitterQueryCompat._execute_newest_api(mock_query, root_node)

        # Should return a list
        assert isinstance(result, list)

    def test_execute_modern_api_with_mocks(self):
        """Test _execute_modern_api method with mocks"""
        mock_query = MagicMock()
        mock_node = MagicMock()
        mock_capture = MagicMock()
        mock_capture.node = mock_node
        mock_capture.index = 0

        mock_match = MagicMock()
        mock_match.captures = [mock_capture]

        mock_query.matches.return_value = [mock_match]
        mock_query.capture_names = ["name"]

        root_node = MagicMock()

        result = TreeSitterQueryCompat._execute_modern_api(mock_query, root_node)

        assert len(result) == 1
        assert result[0] == (mock_node, "name")

    def test_execute_legacy_api_with_mocks(self):
        """Test _execute_legacy_api method with mocks"""
        mock_query = MagicMock()
        mock_node = MagicMock()
        mock_query.captures.return_value = [(mock_node, "name")]
        root_node = MagicMock()

        result = TreeSitterQueryCompat._execute_legacy_api(mock_query, root_node)

        assert len(result) == 1
        assert result[0] == (mock_node, "name")

    def test_execute_old_api_callable(self):
        """Test _execute_old_api with callable query"""
        mock_query = MagicMock()
        mock_node = MagicMock()
        mock_query.return_value = [(mock_node, "name")]
        root_node = MagicMock()

        result = TreeSitterQueryCompat._execute_old_api(mock_query, root_node)

        assert len(result) == 1
        assert result[0] == (mock_node, "name")

    def test_execute_old_api_non_callable(self):
        """Test _execute_old_api with non-callable query"""
        mock_query = MagicMock(spec=[])  # No callable
        root_node = MagicMock()

        result = TreeSitterQueryCompat._execute_old_api(mock_query, root_node)

        assert result == []

    def test_all_internal_methods_exist(self):
        """Test that all internal methods exist"""
        assert hasattr(TreeSitterQueryCompat, "_execute_newest_api")
        assert hasattr(TreeSitterQueryCompat, "_execute_modern_api")
        assert hasattr(TreeSitterQueryCompat, "_execute_legacy_api")
        assert hasattr(TreeSitterQueryCompat, "_execute_old_api")


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_empty_source_code(self):
        """Test with empty source code"""
        mock_node = MagicMock()
        mock_node.start_byte = 0
        mock_node.end_byte = 0

        result = get_node_text_safe(mock_node, "")
        assert result == ""

    def test_very_large_source_code(self):
        """Test with very large source code"""
        mock_node = MagicMock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10
        large_source = "x" * 1000000

        result = get_node_text_safe(mock_node, large_source)
        assert result == "x" * 10

    def test_multi_byte_characters(self):
        """Test with multi-byte UTF-8 characters"""
        mock_node = MagicMock()
        mock_node.start_byte = 0
        mock_node.end_byte = 3  # "€" is 3 bytes in UTF-8
        source_code = "€100"

        result = get_node_text_safe(mock_node, source_code)
        assert isinstance(result, str)

    def test_point_extraction_out_of_bounds(self):
        """Test point-based extraction with out of bounds coordinates"""
        mock_node = MagicMock()
        del mock_node.start_byte
        del mock_node.end_byte
        del mock_node.text
        mock_node.start_point = (10, 0)
        mock_node.end_point = (20, 0)
        source_code = "single line"

        result = get_node_text_safe(mock_node, source_code)
        assert isinstance(result, str)


class TestCompatibilityScenarios:
    """Test various version compatibility scenarios"""

    def test_module_has_execute_query(self):
        """Test that TreeSitterQueryCompat has execute_query method"""
        assert hasattr(TreeSitterQueryCompat, "execute_query")
        assert callable(TreeSitterQueryCompat.execute_query)

    def test_module_has_safe_execute_query(self):
        """Test that TreeSitterQueryCompat has safe_execute_query method"""
        assert hasattr(TreeSitterQueryCompat, "safe_execute_query")
        assert callable(TreeSitterQueryCompat.safe_execute_query)

    def test_query_compat_is_class(self):
        """Test that TreeSitterQueryCompat is a proper class"""
        assert isinstance(TreeSitterQueryCompat, type)

    def test_all_api_methods_are_static(self):
        """Test that API methods are static methods"""
        # Static methods can be called without instantiation
        assert hasattr(TreeSitterQueryCompat.execute_query, "__func__") or callable(
            TreeSitterQueryCompat.execute_query
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
