"""Tests for core/_query_execution.py and core/_query_results.py extracted helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.core._query_execution import (
    _execute_query_string,
    _input_error,
    _language_name_from_object,
    _process_captures_or_error,
    _success_result,
    execute_query_by_explicit_language,
    execute_query_by_name,
    execute_raw_query_string,
)
from tree_sitter_analyzer.core._query_results import (
    _unpack_capture,
    create_error_result,
    create_result_dict,
    process_captures,
    query_statistics,
)


def _make_executor(**overrides):
    executor = MagicMock()
    executor._execution_stats = {
        "total_queries": 0,
        "successful_queries": 0,
        "failed_queries": 0,
        "total_execution_time": 0.0,
    }
    executor._create_error_result.side_effect = lambda msg, **kw: {
        "captures": [],
        "error": msg,
        "success": False,
        **kw,
    }
    for k, v in overrides.items():
        setattr(executor, k, v)
    return executor


def _safe_query(*args, **kwargs):
    return []


class TestInputError:
    def test_none_tree_returns_error(self):
        executor = _make_executor()
        result = _input_error(executor, None, MagicMock(), query_name="q")
        assert result is not None
        assert result["success"] is False
        assert "None" in result["error"]

    def test_none_language_returns_error(self):
        executor = _make_executor()
        result = _input_error(executor, MagicMock(), None, query_name="q")
        assert result is not None
        assert result["success"] is False

    def test_both_valid_returns_none(self):
        executor = _make_executor()
        assert _input_error(executor, MagicMock(), MagicMock()) is None

    def test_without_query_name(self):
        executor = _make_executor()
        result = _input_error(executor, None, MagicMock())
        assert result is not None
        assert result.get("query_name") is None


class TestLanguageNameFromObject:
    def test_name_attribute(self):
        lang = MagicMock()
        lang.name = "Python"
        assert _language_name_from_object(lang) == "python"

    def test_private_name_attribute(self):
        lang = MagicMock(spec=[])
        lang._name = "Java"
        assert _language_name_from_object(lang) == "java"

    def test_fallback_class_name(self):
        class _Language:
            pass
        lang = _Language()
        result = _language_name_from_object(lang)
        assert "_language" in result.lower() or result == "unknown"

    def test_unknown_when_no_name(self):
        lang = object()
        result = _language_name_from_object(lang)
        assert isinstance(result, str)

    def test_unknown_when_none_string(self):
        lang = MagicMock()
        lang.name = "None"
        lang._name = None
        assert _language_name_from_object(lang) == "unknown"


class TestSuccessResult:
    def test_basic(self):
        result = _success_result(
            [{"a": 1}], "(class)", 0.01, query_name="classes"
        )
        assert result["success"] is True
        assert result["captures"] == [{"a": 1}]
        assert result["query_string"] == "(class)"
        assert result["execution_time"] == 0.01
        assert result["query_name"] == "classes"

    def test_with_query_string_field(self):
        result = _success_result(
            [], "(raw)", 0.0, query_string_field="(raw_override)"
        )
        assert result["query_string"] == "(raw_override)"

    def test_no_optional_fields(self):
        result = _success_result([], "(q)", 0.0)
        assert "query_name" not in result
        assert result["success"] is True


class TestExecuteQueryByName:
    def test_none_tree(self):
        executor = _make_executor()
        result = execute_query_by_name(
            executor, None, MagicMock(), "q", "code", _safe_query
        )
        assert result["success"] is False
        assert executor._execution_stats["total_queries"] == 1

    def test_query_not_found(self):
        executor = _make_executor()
        executor._query_loader.get_query.return_value = None
        lang = MagicMock()
        lang.name = "python"
        result = execute_query_by_name(
            executor, MagicMock(), lang, "missing", "code", _safe_query
        )
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_success(self):
        executor = _make_executor()
        executor._query_loader.get_query.return_value = "(class_definition)"
        executor._process_captures.return_value = [{"capture_name": "cls"}]
        lang = MagicMock()
        lang.name = "python"
        result = execute_query_by_name(
            executor, MagicMock(), lang, "classes", "code", _safe_query
        )
        assert result["success"] is True
        assert result["query_name"] == "classes"
        assert executor._execution_stats["successful_queries"] == 1

    def test_exception_increments_failed(self):
        executor = _make_executor()
        executor._query_loader.get_query.side_effect = RuntimeError("boom")
        lang = MagicMock()
        lang.name = "python"
        result = execute_query_by_name(
            executor, MagicMock(), lang, "q", "code", _safe_query
        )
        assert result["success"] is False
        assert executor._execution_stats["failed_queries"] == 1


class TestExecuteQueryByExplicitLanguage:
    def test_none_tree(self):
        executor = _make_executor()
        result = execute_query_by_explicit_language(
            executor, None, MagicMock(), "q", "code", "python", _safe_query
        )
        assert result["success"] is False

    def test_empty_language_name_becomes_unknown(self):
        executor = _make_executor()
        executor._query_loader.get_query.return_value = None
        execute_query_by_explicit_language(
            executor, MagicMock(), MagicMock(), "q", "code", "", _safe_query
        )
        executor._query_loader.get_query.assert_called_with("unknown", "q")

    def test_success(self):
        executor = _make_executor()
        executor._query_loader.get_query.return_value = "(fn)"
        executor._process_captures.return_value = []
        result = execute_query_by_explicit_language(
            executor, MagicMock(), MagicMock(), "functions", "code", "Python", _safe_query
        )
        assert result["success"] is True
        executor._query_loader.get_query.assert_called_with("python", "functions")

    def test_whitespace_language_name_stripped(self):
        executor = _make_executor()
        executor._query_loader.get_query.return_value = "(x)"
        executor._process_captures.return_value = []
        execute_query_by_explicit_language(
            executor, MagicMock(), MagicMock(), "q", "code", "  JAVA  ", _safe_query
        )
        executor._query_loader.get_query.assert_called_with("java", "q")


class TestExecuteRawQueryString:
    def test_none_tree(self):
        executor = _make_executor()
        result = execute_raw_query_string(
            executor, None, MagicMock(), "(q)", "code", _safe_query
        )
        assert result["success"] is False

    def test_success(self):
        executor = _make_executor()
        executor._process_captures.return_value = []
        result = execute_raw_query_string(
            executor, MagicMock(), MagicMock(), "(class_definition)", "code", _safe_query
        )
        assert result["success"] is True
        assert result["query_string"] == "(class_definition)"

    def test_exception(self):
        executor = _make_executor()
        executor._process_captures.side_effect = RuntimeError("fail")
        result = execute_raw_query_string(
            executor, MagicMock(), MagicMock(), "(q)", "code", _safe_query
        )
        assert result["success"] is False


class TestExecuteQueryStringInternal:
    def test_captures_processed(self):
        executor = _make_executor()
        executor._process_captures.return_value = [{"n": "c"}]
        mock_safe = MagicMock(return_value=[])
        result = _execute_query_string(
            executor, MagicMock(), MagicMock(), "(q)", "code", mock_safe, 0.0
        )
        assert result["success"] is True
        assert executor._execution_stats["successful_queries"] == 1

    def test_process_captures_returns_error_dict(self):
        executor = _make_executor()
        executor._process_captures.return_value = {"success": False, "error": "bad"}
        mock_safe = MagicMock(return_value=[])
        result = _execute_query_string(
            executor, MagicMock(), MagicMock(), "(q)", "code", mock_safe, 0.0
        )
        assert result["success"] is False

    def test_exception_during_query(self):
        executor = _make_executor()
        mock_safe = MagicMock(side_effect=RuntimeError("crash"))
        result = _execute_query_string(
            executor, MagicMock(), MagicMock(), "(q)", "code", mock_safe, 0.0, query_name="q"
        )
        assert result["success"] is False
        assert "failed" in result["error"].lower()

    def test_exception_without_query_name(self):
        executor = _make_executor()
        mock_safe = MagicMock(side_effect=RuntimeError("crash"))
        result = _execute_query_string(
            executor, MagicMock(), MagicMock(), "(q)", "code", mock_safe, 0.0
        )
        assert result["success"] is False
        assert "query_string" in result


class TestProcessCapturesOrError:
    def test_success(self):
        executor = _make_executor()
        executor._process_captures.return_value = [{"a": 1}]
        result = _process_captures_or_error(executor, [], "code", query_name="q")
        assert isinstance(result, list)

    def test_exception(self):
        executor = _make_executor()
        executor._process_captures.side_effect = RuntimeError("x")
        result = _process_captures_or_error(executor, [], "code", query_name="q")
        assert isinstance(result, dict)
        assert result["success"] is False

    def test_exception_no_query_name(self):
        executor = _make_executor()
        executor._process_captures.side_effect = RuntimeError("x")
        result = _process_captures_or_error(executor, [], "code")
        assert isinstance(result, dict)
        assert result["success"] is False


class TestUnpackCapture:
    def test_tuple(self):
        node = MagicMock()
        assert _unpack_capture((node, "name")) == (node, "name")

    def test_dict(self):
        node = MagicMock()
        assert _unpack_capture({"node": node, "name": "n"}) == (node, "n")

    def test_invalid_returns_none(self):
        assert _unpack_capture("string") is None
        assert _unpack_capture(42) is None
        assert _unpack_capture((1,)) is None
        assert _unpack_capture({}) is None


class TestProcessCapturesResults:
    def test_empty(self):
        assert process_captures([], "code", lambda n, c, s: {}) == []

    def test_tuple_captures(self):
        node = MagicMock()
        node.type = "class"
        node.start_point = (0, 0)
        node.end_point = (1, 0)
        node.start_byte = 0
        node.end_byte = 5
        results = process_captures(
            [(node, "cls")], "code", lambda n, c, s: {"name": c}
        )
        assert len(results) == 1
        assert results[0]["name"] == "cls"

    def test_dict_captures(self):
        node = MagicMock()
        results = process_captures(
            [{"node": node, "name": "fn"}], "code", lambda n, c, s: {"name": c}
        )
        assert len(results) == 1

    def test_none_node_skipped(self):
        results = process_captures(
            [(None, "x")], "code", lambda n, c, s: {"name": c}
        )
        assert len(results) == 0

    def test_bad_capture_format_skipped(self):
        results = process_captures(
            ["bad"], "code", lambda n, c, s: {}
        )
        assert len(results) == 0


class TestCreateResultDictResults:
    def test_normal(self):
        node = MagicMock()
        node.type = "function_definition"
        node.start_point = (2, 4)
        node.end_point = (5, 1)
        node.start_byte = 10
        node.end_byte = 50
        result = create_result_dict(node, "fn", "code", lambda n, s: "text")
        assert result["capture_name"] == "fn"
        assert result["node_type"] == "function_definition"
        assert result["line_number"] == 3
        assert result["column_number"] == 4
        assert result["text"] == "text"

    def test_exception_in_text(self):
        node = MagicMock()
        node.type = "x"
        result = create_result_dict(node, "c", "code", lambda n, s: (_ for _ in ()).throw(RuntimeError("e")))
        assert result["node_type"] == "error"
        assert "error" in result


class TestCreateErrorResultResults:
    def test_basic(self):
        r = create_error_result("fail")
        assert r["success"] is False
        assert r["error"] == "fail"
        assert r["captures"] == []
        assert "query_name" not in r

    def test_with_query_name(self):
        r = create_error_result("fail", query_name="q")
        assert r["query_name"] == "q"

    def test_extra_kwargs(self):
        r = create_error_result("e", extra="val")
        assert r["extra"] == "val"


class TestQueryStatisticsResults:
    def test_empty(self):
        s = query_statistics({
            "total_queries": 0,
            "successful_queries": 0,
            "failed_queries": 0,
            "total_execution_time": 0.0,
        })
        assert s["success_rate"] == 0.0
        assert s["average_execution_time"] == 0.0

    def test_with_data(self):
        s = query_statistics({
            "total_queries": 10,
            "successful_queries": 8,
            "failed_queries": 2,
            "total_execution_time": 1.0,
        })
        assert s["success_rate"] == pytest.approx(0.8)
        assert s["average_execution_time"] == pytest.approx(0.1)

    def test_does_not_mutate_input(self):
        original = {
            "total_queries": 5,
            "successful_queries": 5,
            "failed_queries": 0,
            "total_execution_time": 0.5,
        }
        original_copy = dict(original)
        query_statistics(original)
        assert original == original_copy
