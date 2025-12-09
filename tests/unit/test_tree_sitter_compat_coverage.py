import sys
import unittest
from unittest.mock import MagicMock, patch

# tree_sitter_analyzer.utils.tree_sitter_compat をインポート
from tree_sitter_analyzer.utils.tree_sitter_compat import (
    TreeSitterQueryCompat,
    create_query_safely,
    get_node_text_safe,
    log_api_info,
)


class TestTreeSitterCompatCoverage(unittest.TestCase):
    def test_execute_query_newest_api(self):
        """Test execution with newest API (QueryCursor)"""
        mock_language = MagicMock()
        mock_root_node = MagicMock()

        # Create mock for tree_sitter module
        mock_tree_sitter = MagicMock()
        # Simulate QueryCursor existing
        mock_tree_sitter.QueryCursor = MagicMock()

        mock_query = MagicMock()
        mock_tree_sitter.Query.return_value = mock_query

        # Setup QueryCursor behavior
        mock_cursor = mock_tree_sitter.QueryCursor.return_value
        # matches returns list of (pattern_index, captures_dict)
        mock_node = MagicMock()
        mock_cursor.matches.return_value = [(0, {"capture_name": [mock_node]})]

        with patch.dict(sys.modules, {"tree_sitter": mock_tree_sitter}):
            # We need to patch the internal import inside execute_query or ensure it uses our mock
            # Since execute_query imports tree_sitter inside, we need to make sure sys.modules has it

            results = TreeSitterQueryCompat.execute_query(
                mock_language, "query", mock_root_node
            )

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0][0], mock_node)
            self.assertEqual(results[0][1], "capture_name")

            # Verify QueryCursor was used
            mock_tree_sitter.QueryCursor.assert_called_once_with(mock_query)

    def test_execute_query_modern_api(self):
        """Test execution with modern API (matches)"""
        mock_language = MagicMock()
        mock_root_node = MagicMock()

        mock_tree_sitter = MagicMock()
        # Ensure QueryCursor does NOT exist
        del mock_tree_sitter.QueryCursor

        mock_query = MagicMock()
        mock_tree_sitter.Query.return_value = mock_query

        # Setup matches method on query object
        mock_match = MagicMock()
        mock_capture = MagicMock()
        mock_node = MagicMock()

        mock_capture.index = 0
        mock_capture.node = mock_node
        mock_match.captures = [mock_capture]

        mock_query.matches.return_value = [mock_match]
        mock_query.capture_names = ["capture_name"]

        with patch.dict(sys.modules, {"tree_sitter": mock_tree_sitter}):
            results = TreeSitterQueryCompat.execute_query(
                mock_language, "query", mock_root_node
            )

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0][0], mock_node)
            self.assertEqual(results[0][1], "capture_name")

    def test_execute_query_legacy_api(self):
        """Test execution with legacy API (captures)"""
        mock_language = MagicMock()
        mock_root_node = MagicMock()

        mock_tree_sitter = MagicMock()
        del mock_tree_sitter.QueryCursor

        mock_query = MagicMock()
        mock_tree_sitter.Query.return_value = mock_query

        # Remove matches, ensure captures exists
        del mock_query.matches

        mock_node = MagicMock()
        mock_query.captures.return_value = [(mock_node, "capture_name")]

        with patch.dict(sys.modules, {"tree_sitter": mock_tree_sitter}):
            results = TreeSitterQueryCompat.execute_query(
                mock_language, "query", mock_root_node
            )

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0][0], mock_node)
            self.assertEqual(results[0][1], "capture_name")

    def test_execute_query_old_api_callable(self):
        """Test execution with old API (callable query)"""
        mock_language = MagicMock()
        mock_root_node = MagicMock()

        mock_tree_sitter = MagicMock()
        del mock_tree_sitter.QueryCursor

        # Mock query as a callable object
        class MockQuery:
            def __call__(self, node):
                return [(mock_node, "capture_name")]

        mock_query = MockQuery()
        mock_node = MagicMock()

        # The logic checks hasattr(query, 'matches') and 'captures'
        # We need to make sure those don't exist or raise AttributeError if accessed,
        # but the code uses hasattr so just not defining them is enough.

        mock_tree_sitter.Query.return_value = mock_query

        with patch.dict(sys.modules, {"tree_sitter": mock_tree_sitter}):
            results = TreeSitterQueryCompat.execute_query(
                mock_language, "query", mock_root_node
            )

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0][0], mock_node)
            self.assertEqual(results[0][1], "capture_name")

    def test_execute_query_old_api_callable_named_tuple(self):
        """Test execution with old API (callable returning objects with node/name attrs)"""
        mock_language = MagicMock()
        mock_root_node = MagicMock()

        mock_tree_sitter = MagicMock()
        del mock_tree_sitter.QueryCursor

        mock_node = MagicMock()
        mock_item = MagicMock()
        mock_item.node = mock_node
        mock_item.name = "capture_name"

        class MockQuery:
            def __call__(self, node):
                return [mock_item]

        mock_query = MockQuery()
        mock_tree_sitter.Query.return_value = mock_query

        with patch.dict(sys.modules, {"tree_sitter": mock_tree_sitter}):
            results = TreeSitterQueryCompat.execute_query(
                mock_language, "query", mock_root_node
            )

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0][0], mock_node)
            self.assertEqual(results[0][1], "capture_name")

    def test_execute_query_no_compatible_api(self):
        """Test execution when no compatible API is found"""
        mock_language = MagicMock()
        mock_root_node = MagicMock()

        mock_tree_sitter = MagicMock()
        del mock_tree_sitter.QueryCursor

        mock_query = MagicMock()  # Not callable, no matches, no captures
        del mock_query.matches
        del mock_query.captures

        mock_tree_sitter.Query.return_value = mock_query

        with patch.dict(sys.modules, {"tree_sitter": mock_tree_sitter}):
            results = TreeSitterQueryCompat.execute_query(
                mock_language, "query", mock_root_node
            )
            self.assertEqual(results, [])

    def test_execute_query_exception(self):
        """Test exception handling during query execution"""
        mock_language = MagicMock()
        mock_root_node = MagicMock()

        mock_tree_sitter = MagicMock()
        mock_tree_sitter.Query.side_effect = Exception("Boom")

        with patch.dict(sys.modules, {"tree_sitter": mock_tree_sitter}):
            results = TreeSitterQueryCompat.execute_query(
                mock_language, "query", mock_root_node
            )
            self.assertEqual(results, [])

    def test_safe_execute_query(self):
        """Test safe_execute_query wrapper"""
        # Success case
        with patch(
            "tree_sitter_analyzer.utils.tree_sitter_compat.TreeSitterQueryCompat.execute_query"
        ) as mock_exec:
            mock_exec.return_value = ["result"]
            result = TreeSitterQueryCompat.safe_execute_query(None, "q", None)
            self.assertEqual(result, ["result"])

        # Failure case
        with patch(
            "tree_sitter_analyzer.utils.tree_sitter_compat.TreeSitterQueryCompat.execute_query"
        ) as mock_exec:
            mock_exec.side_effect = Exception("Fail")
            result = TreeSitterQueryCompat.safe_execute_query(
                None, "q", None, fallback_result=["fallback"]
            )
            self.assertEqual(result, ["fallback"])

    def test_create_query_safely(self):
        """Test create_query_safely"""
        # Success
        with patch.dict(sys.modules, {"tree_sitter": MagicMock()}):
            sys.modules["tree_sitter"].Query.return_value = "query_obj"
            result = create_query_safely(None, "q")
            self.assertEqual(result, "query_obj")

        # Failure
        with patch.dict(sys.modules, {"tree_sitter": MagicMock()}):
            sys.modules["tree_sitter"].Query.side_effect = Exception("Fail")
            result = create_query_safely(None, "q")
            self.assertIsNone(result)

    def test_get_node_text_safe_byte_range(self):
        """Test get_node_text_safe using byte range"""
        mock_node = MagicMock()
        mock_node.start_byte = 0
        mock_node.end_byte = 5
        # Ensure other attributes don't interfere if this path is taken

        text = get_node_text_safe(mock_node, "hello world")
        self.assertEqual(text, "hello")

    def test_get_node_text_safe_text_attr_bytes(self):
        """Test get_node_text_safe using text attribute (bytes)"""
        mock_node = MagicMock()
        del mock_node.start_byte  # Force skip byte range check
        mock_node.text = b"hello"

        text = get_node_text_safe(mock_node, "source")
        self.assertEqual(text, "hello")

    def test_get_node_text_safe_text_attr_str(self):
        """Test get_node_text_safe using text attribute (str)"""
        mock_node = MagicMock()
        del mock_node.start_byte
        mock_node.text = "hello"

        text = get_node_text_safe(mock_node, "source")
        self.assertEqual(text, "hello")

    def test_get_node_text_safe_points_single_line(self):
        """Test get_node_text_safe using points (single line)"""
        mock_node = MagicMock()
        del mock_node.start_byte
        del mock_node.text
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 5)

        text = get_node_text_safe(mock_node, "hello world")
        self.assertEqual(text, "hello")

    def test_get_node_text_safe_points_multi_line(self):
        """Test get_node_text_safe using points (multi line)"""
        mock_node = MagicMock()
        del mock_node.start_byte
        del mock_node.text
        mock_node.start_point = (0, 6)  # start at 'world'
        mock_node.end_point = (1, 4)  # end at 'test'

        source = "hello world\nthis is a test"
        # Line 0: "hello world" -> from col 6: "world"
        # Line 1: "this is a test" -> to col 4: "this"

        text = get_node_text_safe(mock_node, source)
        self.assertEqual(text, "world\nthis")

    def test_get_node_text_safe_fallback_empty(self):
        """Test get_node_text_safe fallback to empty"""
        mock_node = MagicMock()
        del mock_node.start_byte
        del mock_node.text
        del mock_node.start_point

        text = get_node_text_safe(mock_node, "source")
        self.assertEqual(text, "")

    def test_log_api_info(self):
        """Test log_api_info"""
        # Test modern API present
        with patch.dict(sys.modules, {"tree_sitter": MagicMock()}):
            sys.modules["tree_sitter"].Query.matches = lambda: None
            log_api_info()

        # Test legacy API present
        with patch.dict(sys.modules, {"tree_sitter": MagicMock()}):
            del sys.modules["tree_sitter"].Query.matches
            sys.modules["tree_sitter"].Query.captures = lambda: None
            log_api_info()

        # Test no compatible API
        with patch.dict(sys.modules, {"tree_sitter": MagicMock()}):
            del sys.modules["tree_sitter"].Query.matches
            del sys.modules["tree_sitter"].Query.captures
            log_api_info()

    def test_log_api_info_import_error(self):
        """Test log_api_info when tree-sitter import fails (covers lines 288-289)"""
        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "tree_sitter":
                raise ImportError("No module named 'tree_sitter'")
            return original_import(name, *args, **kwargs)

        # Temporarily remove tree_sitter from sys.modules and mock import
        saved_module = sys.modules.get("tree_sitter")
        try:
            if "tree_sitter" in sys.modules:
                del sys.modules["tree_sitter"]

            with patch.object(builtins, "__import__", side_effect=mock_import):
                # This should handle ImportError gracefully
                log_api_info()
        finally:
            # Restore tree_sitter module if it was present
            if saved_module is not None:
                sys.modules["tree_sitter"] = saved_module

    def test_log_api_info_api_detection_exception(self):
        """Test log_api_info when API detection raises an exception (covers lines 285-286)"""
        mock_tree_sitter = MagicMock()

        # Make accessing Query raise an exception
        # This simulates an error during API detection
        type(mock_tree_sitter).Query = property(
            lambda self: (_ for _ in ()).throw(Exception("API detection error"))
        )

        with patch.dict(sys.modules, {"tree_sitter": mock_tree_sitter}):
            # This should handle the exception gracefully
            log_api_info()

    def test_log_api_info_api_detection_exception_via_dir(self):
        """Test log_api_info when dir() on Query raises an exception (covers lines 285-286)"""
        # Create a mock that raises exception when accessing Query attribute
        mock_tree_sitter = MagicMock()

        # Create a class that raises exception when dir() is called
        class QueryThatFailsOnDir:
            @staticmethod
            def __dir__():
                raise RuntimeError("dir() failed")

        mock_tree_sitter.Query = QueryThatFailsOnDir

        with patch.dict(sys.modules, {"tree_sitter": mock_tree_sitter}):
            # This should handle the exception gracefully
            log_api_info()

    def test_execute_modern_api_exception_raises(self):
        """Test _execute_modern_api exception handling (covers lines 102-104)"""
        mock_query = MagicMock()
        mock_root_node = MagicMock()

        # Make matches() raise an exception
        mock_query.matches.side_effect = Exception("Modern API error")

        # The method should raise the exception
        with self.assertRaises(Exception) as context:
            TreeSitterQueryCompat._execute_modern_api(mock_query, mock_root_node)

        self.assertIn("Modern API error", str(context.exception))

    def test_execute_legacy_api_exception_raises(self):
        """Test _execute_legacy_api exception handling (covers lines 116-118)"""
        mock_query = MagicMock()
        mock_root_node = MagicMock()

        # Make captures() raise an exception
        mock_query.captures.side_effect = Exception("Legacy API error")

        # The method should raise the exception
        with self.assertRaises(Exception) as context:
            TreeSitterQueryCompat._execute_legacy_api(mock_query, mock_root_node)

        self.assertIn("Legacy API error", str(context.exception))

    def test_execute_old_api_exception_handling(self):
        """Test _execute_old_api exception handling (covers lines 138-143)"""
        mock_root_node = MagicMock()

        # Create a callable query that raises an exception
        class MockQueryWithException:
            def __call__(self, node):
                raise Exception("Old API error")

        mock_query = MockQueryWithException()

        # The method should handle the exception and return empty list
        result = TreeSitterQueryCompat._execute_old_api(mock_query, mock_root_node)
        self.assertEqual(result, [])

    def test_execute_old_api_with_invalid_result_items(self):
        """Test _execute_old_api with invalid result items"""
        mock_root_node = MagicMock()

        # Create a callable query that returns invalid items
        class MockQueryWithInvalidItems:
            def __call__(self, node):
                return [
                    "invalid_string",  # Not a tuple or object with node/name
                    (1,),  # Tuple with only 1 element
                    None,  # None value
                ]

        mock_query = MockQueryWithInvalidItems()

        # The method should handle invalid items gracefully
        result = TreeSitterQueryCompat._execute_old_api(mock_query, mock_root_node)
        # Should return empty list since no valid items
        self.assertEqual(result, [])

    def test_execute_old_api_non_callable_warning(self):
        """Test _execute_old_api with non-callable query (covers line 138)"""
        mock_root_node = MagicMock()

        # Create a truly non-callable object
        class NonCallableQuery:
            pass

        mock_query = NonCallableQuery()

        # The method should log a warning and return empty list
        result = TreeSitterQueryCompat._execute_old_api(mock_query, mock_root_node)
        self.assertEqual(result, [])
