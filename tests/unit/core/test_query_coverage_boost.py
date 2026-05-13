#!/usr/bin/env python3
"""Targeted tests for uncovered paths in core/query.py (77.6% -> target 85%+).

Covers: execute_query error paths, _process_captures edge cases,
get_available_queries error handling, get_query_description error handling,
validate_query full paths, module-level functions.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from tree_sitter_analyzer.core.query import (
    QueryExecutor,
    get_all_queries_for_language,
    get_available_queries,
    get_query_description,
)

# ── helpers ────────────────────────────────────────────────────────────


def _mock_tree():
    tree = MagicMock()
    root = Mock()
    root.children = []
    tree.root_node = root
    return tree


def _mock_language():
    lang = MagicMock()
    mock_query = MagicMock()
    mock_query.captures.return_value = []
    lang.query.return_value = mock_query
    return lang


# ── execute_query error paths ──────────────────────────────────────────


class TestExecuteQueryErrors:
    def test_capture_processing_failure(self):
        """Line 109-111: when _process_captures raises an exception."""
        executor = QueryExecutor()
        tree = _mock_tree()
        language = _mock_language()

        with (
            patch(
                "tree_sitter_analyzer.core.query.TreeSitterQueryCompat.safe_execute_query",
                return_value=[],
            ),
            patch.object(
                executor,
                "_process_captures",
                side_effect=RuntimeError("simulated processing error"),
            ),
        ):
            result = executor.execute_query(tree, language, "functions", "code")
            assert isinstance(result, dict)
            assert "error" in result

    def test_query_execution_exception(self):
        """Line 127-129: when safe_execute_query raises an exception."""
        executor = QueryExecutor()
        tree = _mock_tree()
        language = _mock_language()

        with patch(
            "tree_sitter_analyzer.core.query.TreeSitterQueryCompat.safe_execute_query",
            side_effect=ValueError("simulated query error"),
        ):
            result = executor.execute_query(tree, language, "functions", "code")
            assert isinstance(result, dict)
            assert "error" in result

    def test_unexpected_error(self):
        """Line 133-136: unexpected exception in outer try/except."""
        executor = QueryExecutor()
        tree = _mock_tree()
        language = _mock_language()

        with patch.object(
            executor._query_loader,
            "get_query",
            side_effect=KeyError("simulated unexpected"),
        ):
            result = executor.execute_query(tree, language, "functions", "code")
            assert isinstance(result, dict)
            assert "error" in result


# ── _process_captures edge cases ───────────────────────────────────────


class TestProcessCaptures:
    def test_tuple_capture(self):
        """Lines 347-348: capture is a tuple (name, node)."""
        executor = QueryExecutor()
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 0
        mock_node.type = "test_type"
        mock_node.text = b"test"
        mock_node.children = []

        captures = [("test_name", mock_node)]

        result = executor._process_captures(captures, "source code")
        assert isinstance(result, list)

    def test_unexpected_capture_type(self):
        """Lines 356-361: unexpected capture format (neither tuple nor dict)."""
        executor = QueryExecutor()

        captures = ["not_a_valid_capture"]

        result = executor._process_captures(captures, "source code")
        assert isinstance(result, list)

    def test_dict_capture_without_node(self):
        """Cover dict branch where "node" is None."""
        executor = QueryExecutor()

        captures = [{"name": "test_name", "node": None}]

        result = executor._process_captures(captures, "source code")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_process_captures_outer_exception(self):
        """Cover outer exception handler in _process_captures."""
        executor = QueryExecutor()

        with patch.object(
            executor, "_create_result_dict", side_effect=Exception("inner")
        ):
            result = executor._process_captures(
                [
                    (
                        "name",
                        Mock(
                            start_point=(0, 0),
                            end_point=(0, 0),
                            start_byte=0,
                            end_byte=0,
                            type="x",
                            text=b"x",
                            children=[],
                        ),
                    )
                ],
                "source",
            )
            assert isinstance(result, list)


# ── get_available_queries / get_query_description ─────────────────────


class TestQueryInfoMethods:
    def test_get_available_queries_dict(self):
        """Cover dict path: queries is a dict, return keys."""
        executor = QueryExecutor()
        mock_loader = Mock()
        mock_loader.get_all_queries_for_language.return_value = {
            "functions": {},
            "classes": {},
        }
        executor._query_loader = mock_loader

        result = executor.get_available_queries("python")
        assert result == ["functions", "classes"]

    def test_get_available_queries_error(self):
        """Line 436-438: exception path."""
        executor = QueryExecutor()
        mock_loader = Mock()
        mock_loader.get_all_queries_for_language.side_effect = RuntimeError("fail")
        executor._query_loader = mock_loader

        result = executor.get_available_queries("python")
        assert result == []

    def test_get_query_description_error(self):
        """Line 453-455: exception path."""
        executor = QueryExecutor()
        mock_loader = Mock()
        mock_loader.get_query_description.side_effect = RuntimeError("fail")
        executor._query_loader = mock_loader

        result = executor.get_query_description("python", "functions")
        assert result is None

    def test_get_query_description_success(self):
        """Cover success path."""
        executor = QueryExecutor()
        mock_loader = Mock()
        mock_loader.get_query_description.return_value = "Finds all functions"
        executor._query_loader = mock_loader

        result = executor.get_query_description("python", "functions")
        assert result == "Finds all functions"


# ── validate_query ────────────────────────────────────────────────────


class TestValidateQuery:
    def test_validate_query_language_not_found(self):
        """Line 477: language loading fails."""
        executor = QueryExecutor()

        with patch("tree_sitter_analyzer.core.query.get_loader") as mock_get_loader:
            mock_loader_obj = Mock()
            mock_loader_obj.load_language.return_value = None
            mock_get_loader.return_value = mock_loader_obj

            result = executor.validate_query("nonexistent_lang", "query_string")
            assert result is False

    def test_validate_query_success(self):
        """Cover validate_query success path."""
        executor = QueryExecutor()

        with patch("tree_sitter_analyzer.core.query.get_loader") as mock_get_loader:
            mock_lang = MagicMock()
            mock_loader_obj = Mock()
            mock_loader_obj.load_language.return_value = mock_lang
            mock_get_loader.return_value = mock_loader_obj

            result = executor.validate_query("python", "(function_definition) @func")
            assert result is True

    def test_validate_query_exception(self):
        """Cover validate_query exception when query creation fails."""
        executor = QueryExecutor()

        with patch("tree_sitter_analyzer.core.query.get_loader") as mock_get_loader:
            mock_lang = MagicMock()
            mock_lang.query.side_effect = Exception("bad query")
            mock_loader_obj = Mock()
            mock_loader_obj.load_language.return_value = mock_lang
            mock_get_loader.return_value = mock_loader_obj

            result = executor.validate_query("python", "invalid!!!query")
            assert result is False


# ── Module-level functions ────────────────────────────────────────────


class TestModuleLevelFunctions:
    def test_get_available_queries_no_language(self):
        """Lines 539-541: module-level get_available_queries without language."""
        with patch(
            "tree_sitter_analyzer.core.query.get_query_loader"
        ) as mock_get_loader:
            mock_loader = Mock()
            mock_loader.list_supported_languages.return_value = ["python", "javascript"]
            mock_loader.list_queries_for_language.side_effect = [
                ["functions", "classes"],
                ["functions", "imports"],
            ]
            mock_get_loader.return_value = mock_loader

            result = get_available_queries()
            assert isinstance(result, list)
            assert "classes" in result
            assert "functions" in result
            assert "imports" in result

    def test_get_query_description_error(self):
        """Lines 560-562: exception in module-level get_query_description."""
        with patch(
            "tree_sitter_analyzer.core.query.get_query_loader"
        ) as mock_get_loader:
            mock_loader = Mock()
            mock_loader.get_query_description.side_effect = RuntimeError("fail")
            mock_get_loader.return_value = mock_loader

            result = get_query_description("_nonexistent_lang_", "_nonexistent_query_")
            assert result is None

    def test_get_all_queries_for_language_deprecated(self):
        """Cover get_all_queries_for_language deprecation path."""
        with pytest.warns(DeprecationWarning, match="deprecated"):
            result = get_all_queries_for_language("python")
        assert result == []


# ── execute_query_with_language_name error paths ───────────────────────


class TestExecuteQueryWithLanguage:
    def test_unknown_query_name(self):
        """Line 194: query name not found in loaded queries."""
        executor = QueryExecutor()
        tree = _mock_tree()
        language = _mock_language()

        with patch.object(
            executor._query_loader,
            "get_query",
            return_value=None,
        ):
            result = executor.execute_query_with_language_name(
                tree, language, "nonexistent", "code", "python"
            )
            assert "error" in result

    def test_query_execution_exception(self):
        """Line 212: safe_execute_query raises exception."""
        executor = QueryExecutor()
        tree = _mock_tree()
        language = _mock_language()

        with (
            patch.object(
                executor._query_loader,
                "get_query",
                return_value="(test) @capture",
            ),
            patch(
                "tree_sitter_analyzer.core.query.TreeSitterQueryCompat.safe_execute_query",
                side_effect=ValueError("query failed"),
            ),
        ):
            result = executor.execute_query_with_language_name(
                tree, language, "functions", "code", "python"
            )
            assert "error" in result

    def test_unexpected_error(self):
        """Line 218: unexpected exception in outer try."""
        executor = QueryExecutor()
        tree = _mock_tree()
        language = _mock_language()

        with patch.object(
            executor._query_loader,
            "get_query",
            side_effect=KeyError("unexpected"),
        ):
            result = executor.execute_query_with_language_name(
                tree, language, "functions", "code", "python"
            )
            assert "error" in result


# ── execute_query_string error paths ──────────────────────────────────


class TestExecuteQueryString:
    def test_unknown_language(self):
        """Line 266: language not found."""
        executor = QueryExecutor()
        tree = _mock_tree()

        with patch("tree_sitter_analyzer.core.query.get_loader") as mock_get_loader:
            mock_loader_obj = Mock()
            mock_loader_obj.load_language.return_value = None
            mock_get_loader.return_value = mock_loader_obj

            result = executor.execute_query_string(tree, "nonexistent", "query", "code")
            assert "error" in result

    def test_query_execution_error(self):
        """Line 289: safe_execute_query raises exception."""
        executor = QueryExecutor()
        tree = _mock_tree()

        with patch("tree_sitter_analyzer.core.query.get_loader") as mock_get_loader:
            mock_lang = MagicMock()
            mock_loader_obj = Mock()
            mock_loader_obj.load_language.return_value = mock_lang
            mock_get_loader.return_value = mock_loader_obj

            with patch(
                "tree_sitter_analyzer.core.query.TreeSitterQueryCompat.safe_execute_query",
                side_effect=ValueError("query_failed"),
            ):
                result = executor.execute_query_string(tree, "python", "query", "code")
                assert "error" in result
