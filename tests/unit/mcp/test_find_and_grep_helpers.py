#!/usr/bin/env python3
"""Tests for find_and_grep_helpers — dataclasses, response builders, and output handling."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.mcp.tools.find_and_grep_helpers import (
    TOOL_SCHEMA,
    FindAndGrepCountOnlyContext,
    FindAndGrepFullMatchContext,
    FindAndGrepRgModeContext,
    _handle_file_output,
    _make_minimal,
    build_count_only_response,
    build_empty_response,
    build_missing_commands_response,
    build_search_meta,
    handle_output,
)


class TestToolSchema:
    def test_schema_is_dict(self):
        assert isinstance(TOOL_SCHEMA, dict)

    def test_schema_type_is_object(self):
        assert TOOL_SCHEMA["type"] == "object"

    def test_schema_has_required_fields(self):
        assert set(TOOL_SCHEMA["required"]) == {"roots", "query"}

    def test_schema_has_roots_property(self):
        assert "roots" in TOOL_SCHEMA["properties"]
        assert TOOL_SCHEMA["properties"]["roots"]["type"] == "array"

    def test_schema_has_query_property(self):
        assert "query" in TOOL_SCHEMA["properties"]
        assert TOOL_SCHEMA["properties"]["query"]["type"] == "string"

    def test_schema_has_pattern_property(self):
        assert "pattern" in TOOL_SCHEMA["properties"]

    def test_schema_has_output_format_with_enum(self):
        prop = TOOL_SCHEMA["properties"]["output_format"]
        assert set(prop["enum"]) == {"json", "toon"}

    def test_schema_has_sort_with_enum(self):
        prop = TOOL_SCHEMA["properties"]["sort"]
        assert set(prop["enum"]) == {"path", "mtime", "size"}

    def test_schema_has_case_with_enum(self):
        prop = TOOL_SCHEMA["properties"]["case"]
        assert set(prop["enum"]) == {"smart", "insensitive", "sensitive"}

    def test_schema_additional_properties_false(self):
        assert TOOL_SCHEMA["additionalProperties"] is False

    def test_schema_boolean_defaults(self):
        bool_props = [
            "glob",
            "follow_symlinks",
            "hidden",
            "no_ignore",
            "full_path_match",
            "fixed_strings",
            "word",
            "multiline",
            "count_only_matches",
            "summary_only",
            "optimize_paths",
            "group_by_file",
            "total_only",
            "suppress_output",
        ]
        for name in bool_props:
            assert TOOL_SCHEMA["properties"][name]["type"] == "boolean"

    def test_schema_integer_properties(self):
        int_props = ["depth", "file_limit", "context_before", "context_after", "max_count", "timeout_ms"]
        for name in int_props:
            assert TOOL_SCHEMA["properties"][name]["type"] == "integer"


class TestFindAndGrepFullMatchContext:
    def test_creation(self):
        ctx = FindAndGrepFullMatchContext(
            arguments={"roots": ["src/"], "query": "TODO"},
            rg_out=b"data",
            fd_elapsed_ms=10,
            rg_elapsed_ms=20,
            searched_file_count=100,
            truncated_fd=False,
            output_format="toon",
        )
        assert ctx.arguments["roots"] == ["src/"]
        assert ctx.rg_out == b"data"
        assert ctx.fd_elapsed_ms == 10
        assert ctx.rg_elapsed_ms == 20
        assert ctx.searched_file_count == 100
        assert ctx.truncated_fd is False
        assert ctx.output_format == "toon"

    def test_frozen(self):
        ctx = FindAndGrepFullMatchContext(
            arguments={}, rg_out=b"", fd_elapsed_ms=0,
            rg_elapsed_ms=0, searched_file_count=0,
            truncated_fd=False, output_format="json",
        )
        with pytest.raises(AttributeError):
            ctx.fd_elapsed_ms = 99  # type: ignore[misc]

    def test_equality(self):
        kw = {"arguments": {}, "rg_out": b"", "fd_elapsed_ms": 0,
              "rg_elapsed_ms": 0, "searched_file_count": 0,
              "truncated_fd": False, "output_format": "json"}
        ctx1 = FindAndGrepFullMatchContext(**kw)
        ctx2 = FindAndGrepFullMatchContext(**kw)
        assert ctx1 == ctx2

    def test_unhashable_due_to_dict(self):
        kw = {"arguments": {}, "rg_out": b"", "fd_elapsed_ms": 0,
              "rg_elapsed_ms": 0, "searched_file_count": 0,
              "truncated_fd": False, "output_format": "json"}
        ctx = FindAndGrepFullMatchContext(**kw)
        with pytest.raises(TypeError, match="unhashable"):
            hash(ctx)


class TestFindAndGrepCountOnlyContext:
    def test_creation(self):
        ctx = FindAndGrepCountOnlyContext(
            arguments={"query": "test"},
            count_data={"file.py": 5, "__total__": 10},
            output_format="json",
            searched_file_count=50,
            truncated=False,
            fd_elapsed_ms=5,
            rg_elapsed_ms=15,
        )
        assert ctx.count_data["__total__"] == 10
        assert ctx.output_format == "json"

    def test_frozen(self):
        ctx = FindAndGrepCountOnlyContext(
            arguments={}, count_data={}, output_format="json",
            searched_file_count=0, truncated=False,
            fd_elapsed_ms=0, rg_elapsed_ms=0,
        )
        with pytest.raises(AttributeError):
            ctx.output_format = "toon"  # type: ignore[misc]


class TestFindAndGrepRgModeContext:
    def test_creation(self):
        ctx = FindAndGrepRgModeContext(
            arguments={"roots": ["src/"]},
            files=["a.py", "b.py"],
            fd_elapsed_ms=5,
            truncated_fd=False,
            output_format="json",
        )
        assert len(ctx.files) == 2
        assert "a.py" in ctx.files

    def test_frozen(self):
        ctx = FindAndGrepRgModeContext(
            arguments={}, files=[], fd_elapsed_ms=0,
            truncated_fd=False, output_format="json",
        )
        with pytest.raises(AttributeError):
            ctx.output_format = "toon"  # type: ignore[misc]


class TestBuildMissingCommandsResponse:
    def test_returns_none_when_no_missing(self):
        assert build_missing_commands_response([]) is None

    def test_returns_none_when_none_input(self):
        assert build_missing_commands_response(None) is None  # type: ignore[arg-type]

    def test_returns_error_for_missing_fd(self):
        result = build_missing_commands_response(["fd"])
        assert result is not None
        assert result["success"] is False
        assert "fd" in result["error"]
        assert result["count"] == 0
        assert result["results"] == []

    def test_returns_error_for_missing_rg(self):
        result = build_missing_commands_response(["rg"])
        assert result is not None
        assert "rg" in result["error"]

    def test_returns_error_for_both_missing(self):
        result = build_missing_commands_response(["fd", "rg"])
        assert result is not None
        assert "fd" in result["error"]
        assert "rg" in result["error"]

    def test_error_mentions_install(self):
        result = build_missing_commands_response(["fd"])
        assert "install" in result["error"].lower()


class TestBuildSearchMeta:
    def test_basic_meta(self):
        meta = build_search_meta(
            searched_file_count=100,
            truncated=False,
            fd_elapsed_ms=10,
            rg_elapsed_ms=20,
        )
        assert meta["searched_file_count"] == 100
        assert meta["truncated"] is False
        assert meta["fd_elapsed_ms"] == 10
        assert meta["rg_elapsed_ms"] == 20

    def test_meta_keys(self):
        meta = build_search_meta(
            searched_file_count=0, truncated=True,
            fd_elapsed_ms=0, rg_elapsed_ms=0,
        )
        assert set(meta.keys()) == {
            "searched_file_count", "truncated",
            "fd_elapsed_ms", "rg_elapsed_ms",
        }

    def test_meta_with_truncated_true(self):
        meta = build_search_meta(
            searched_file_count=2000, truncated=True,
            fd_elapsed_ms=50, rg_elapsed_ms=100,
        )
        assert meta["truncated"] is True
        assert meta["searched_file_count"] == 2000

    def test_meta_preserves_zero_values(self):
        meta = build_search_meta(
            searched_file_count=0, truncated=False,
            fd_elapsed_ms=0, rg_elapsed_ms=0,
        )
        assert meta["searched_file_count"] == 0
        assert meta["fd_elapsed_ms"] == 0


class TestBuildEmptyResponse:
    def test_basic_empty_response(self):
        result = build_empty_response(
            {"roots": ["src/"], "query": "nonexistent"},
            truncated=False,
            fd_elapsed_ms=5,
        )
        assert result["success"] is True
        assert result["results"] == []
        assert result["count"] == 0

    def test_empty_response_has_meta(self):
        result = build_empty_response(
            {"roots": ["src/"], "query": "test"},
            truncated=False,
            fd_elapsed_ms=3,
        )
        assert "meta" in result
        assert result["meta"]["searched_file_count"] == 0
        assert result["meta"]["rg_elapsed_ms"] == 0

    def test_empty_response_has_agent_summary(self):
        result = build_empty_response(
            {"roots": ["src/"], "query": "test"},
            truncated=False,
            fd_elapsed_ms=3,
        )
        assert "agent_summary" in result
        assert result["agent_summary"]["mode"] == "empty"

    def test_empty_response_with_truncated(self):
        result = build_empty_response(
            {"roots": ["src/"], "query": "test"},
            truncated=True,
            fd_elapsed_ms=5,
        )
        assert result["meta"]["truncated"] is True


class TestBuildCountOnlyResponse:
    def _make_context(self, **overrides: Any) -> FindAndGrepCountOnlyContext:
        defaults: dict[str, Any] = {
            "arguments": {"roots": ["src/"], "query": "test"},
            "count_data": {"file.py": 5, "__total__": 10},
            "output_format": "json",
            "searched_file_count": 50,
            "truncated": False,
            "fd_elapsed_ms": 5,
            "rg_elapsed_ms": 15,
        }
        defaults.update(overrides)
        return FindAndGrepCountOnlyContext(**defaults)

    def test_basic_count_only_response(self):
        ctx = self._make_context()
        result = build_count_only_response(ctx)
        assert result["success"] is True
        assert result["count_only"] is True
        assert result["total_matches"] == 10

    def test_count_only_extracts_total(self):
        ctx = self._make_context(count_data={"a.py": 3, "__total__": 42})
        result = build_count_only_response(ctx)
        assert result["total_matches"] == 42

    def test_count_only_file_counts_without_total(self):
        ctx = self._make_context(count_data={"a.py": 3, "b.py": 7, "__total__": 10})
        result = build_count_only_response(ctx)
        assert result["file_counts"] == {"a.py": 3, "b.py": 7}
        assert "__total__" not in result["file_counts"]

    def test_count_only_missing_total_defaults_zero(self):
        ctx = self._make_context(count_data={"a.py": 3})
        result = build_count_only_response(ctx)
        assert result["total_matches"] == 0

    def test_count_only_has_meta(self):
        ctx = self._make_context()
        result = build_count_only_response(ctx)
        assert "meta" in result
        assert result["meta"]["searched_file_count"] == 50

    def test_count_only_has_agent_summary(self):
        ctx = self._make_context()
        result = build_count_only_response(ctx)
        assert "agent_summary" in result
        assert result["agent_summary"]["mode"] == "count_only"

    def test_count_only_toon_format(self):
        ctx = self._make_context(output_format="toon")
        result = build_count_only_response(ctx)
        assert "toon_content" in result or result.get("success") is True

    def test_count_only_json_format_no_toon(self):
        ctx = self._make_context(output_format="json")
        result = build_count_only_response(ctx)
        assert "toon_content" not in result


class TestHandleOutput:
    def test_returns_none_when_no_output_file_and_no_suppress(self):
        result = {"success": True, "count": 5}
        ret = handle_output(result, {"roots": ["src/"]}, MagicMock())
        assert ret is None

    def test_suppress_without_output_file(self):
        result = {"success": True, "count": 5, "meta": {}}
        ret = handle_output(result, {"suppress_output": True}, MagicMock())
        assert ret is not None
        assert ret["success"] is True
        assert ret["count"] == 5

    def test_suppress_includes_agent_summary(self):
        result = {
            "success": True,
            "count": 3,
            "meta": {},
            "agent_summary": {"mode": "normal"},
        }
        ret = handle_output(result, {"suppress_output": True}, MagicMock())
        assert "agent_summary" in ret

    def test_output_file_triggers_file_output(self):
        result = {"success": True, "count": 5, "meta": {}}
        mgr = MagicMock()
        mgr.save_to_file.return_value = "/tmp/output.json"
        ret = handle_output(
            result,
            {"output_file": "out.json"},
            mgr,
        )
        assert ret is None
        mgr.save_to_file.assert_called_once()

    def test_output_file_updates_result(self):
        result = {"success": True, "count": 5, "meta": {}}
        mgr = MagicMock()
        mgr.save_to_file.return_value = "/tmp/output.json"
        handle_output(result, {"output_file": "out.json"}, mgr)
        assert result["output_file"] == "out.json"
        assert "file_saved" in result


class TestHandleFileOutput:
    def test_save_with_summary_only(self):
        result = {"success": True, "count": 3, "meta": {}}
        mgr = MagicMock()
        mgr.save_to_file.return_value = "/tmp/summary.json"
        ret = _handle_file_output(
            result, "summary.json", False,
            {"output_file": "summary.json", "summary_only": True, "output_format": "json"},
            mgr, None,
        )
        assert ret is None
        mgr.save_to_file.assert_called_once()

    def test_save_with_matches(self):
        result = {"success": True, "count": 2, "meta": {}}
        mgr = MagicMock()
        mgr.save_to_file.return_value = "/tmp/out.json"
        matches = [{"file": "a.py", "line": 1, "text": "found"}]
        ret = _handle_file_output(
            result, "out.json", False,
            {"output_file": "out.json", "output_format": "json"},
            mgr, matches,
        )
        assert ret is None
        mgr.save_to_file.assert_called_once()

    def test_suppress_returns_minimal(self):
        result = {"success": True, "count": 10, "meta": {}, "agent_summary": {"mode": "normal"}}
        mgr = MagicMock()
        mgr.save_to_file.return_value = "/tmp/out.json"
        ret = _handle_file_output(
            result, "out.json", True,
            {"output_file": "out.json", "output_format": "json"},
            mgr, None,
        )
        assert ret is not None
        assert "file_saved" in ret

    def test_exception_sets_error(self):
        result = {"success": True, "count": 1, "meta": {}}
        mgr = MagicMock()
        mgr.save_to_file.side_effect = OSError("disk full")
        _handle_file_output(
            result, "out.json", False,
            {"output_file": "out.json", "output_format": "json"},
            mgr, None,
        )
        assert "file_save_error" in result
        assert result["file_saved"] is False


class TestMakeMinimal:
    def test_basic_minimal(self):
        result = {
            "success": True,
            "count": 5,
            "meta": {"searched_file_count": 10},
            "results": [{"file": "a.py"}],
        }
        minimal = _make_minimal(result)
        assert minimal["success"] is True
        assert minimal["count"] == 5
        assert "results" not in minimal
        assert "meta" in minimal

    def test_minimal_without_summary(self):
        result = {
            "success": True,
            "count": 3,
            "meta": {},
            "summary": {"files": 2},
        }
        minimal = _make_minimal(result, include_summary=False)
        assert "summary" not in minimal

    def test_minimal_with_summary(self):
        result = {
            "success": True,
            "count": 3,
            "meta": {},
            "summary": {"files": 2},
        }
        minimal = _make_minimal(result, include_summary=True)
        assert minimal["summary"] == {"files": 2}

    def test_minimal_includes_agent_summary(self):
        result = {
            "success": True,
            "count": 1,
            "meta": {},
            "agent_summary": {"mode": "normal"},
        }
        minimal = _make_minimal(result, include_summary=True)
        assert minimal["agent_summary"] == {"mode": "normal"}

    def test_minimal_without_agent_summary(self):
        result = {
            "success": True,
            "count": 1,
            "meta": {},
        }
        minimal = _make_minimal(result, include_summary=True)
        assert "agent_summary" not in minimal

    def test_minimal_defaults_success_true(self):
        result = {"count": 0, "meta": {}}
        minimal = _make_minimal(result)
        assert minimal["success"] is True

    def test_minimal_defaults_count_zero(self):
        result = {"success": True, "meta": {}}
        minimal = _make_minimal(result)
        assert minimal["count"] == 0


class TestBuildEmptyResponseIntegration:
    def test_empty_response_meta_fd_elapsed(self):
        result = build_empty_response(
            {"roots": ["/tmp"], "query": "x"},
            truncated=False,
            fd_elapsed_ms=42,
        )
        assert result["meta"]["fd_elapsed_ms"] == 42

    def test_empty_response_meta_rg_elapsed_zero(self):
        result = build_empty_response(
            {"roots": ["/tmp"], "query": "x"},
            truncated=False,
            fd_elapsed_ms=1,
        )
        assert result["meta"]["rg_elapsed_ms"] == 0


class TestBuildCountOnlyResponseEdgeCases:
    def test_empty_count_data(self):
        ctx = FindAndGrepCountOnlyContext(
            arguments={"roots": ["src/"], "query": "test"},
            count_data={},
            output_format="json",
            searched_file_count=0,
            truncated=False,
            fd_elapsed_ms=0,
            rg_elapsed_ms=0,
        )
        result = build_count_only_response(ctx)
        assert result["total_matches"] == 0
        assert result["file_counts"] == {}

    def test_only_total_no_file_counts(self):
        ctx = FindAndGrepCountOnlyContext(
            arguments={"roots": ["src/"], "query": "test"},
            count_data={"__total__": 7},
            output_format="json",
            searched_file_count=10,
            truncated=False,
            fd_elapsed_ms=1,
            rg_elapsed_ms=2,
        )
        result = build_count_only_response(ctx)
        assert result["total_matches"] == 7
        assert result["file_counts"] == {}

    def test_truncated_true(self):
        ctx = FindAndGrepCountOnlyContext(
            arguments={"roots": ["src/"], "query": "test"},
            count_data={"__total__": 500},
            output_format="json",
            searched_file_count=2000,
            truncated=True,
            fd_elapsed_ms=10,
            rg_elapsed_ms=20,
        )
        result = build_count_only_response(ctx)
        assert result["meta"]["truncated"] is True
