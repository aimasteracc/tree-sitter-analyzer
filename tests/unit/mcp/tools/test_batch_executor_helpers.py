#!/usr/bin/env python3

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.batch_executor import (
    BATCH_LIMITS,
    _clamp_requests,
    _make_error_result,
    _resolve_file,
    _validate_batch_top_level,
    _validate_file_request,
)


class TestBatchLimits:
    def test_batch_limits_values(self):
        assert BATCH_LIMITS["max_files"] == 20
        assert BATCH_LIMITS["max_sections_per_file"] == 50
        assert BATCH_LIMITS["max_sections_total"] == 200
        assert BATCH_LIMITS["max_total_bytes"] == 1024 * 1024
        assert BATCH_LIMITS["max_total_lines"] == 5000
        assert BATCH_LIMITS["max_file_size_bytes"] == 5 * 1024 * 1024


class TestValidateBatchTopLevel:
    def test_returns_requests_list(self):
        reqs = [{"file_path": "a.py", "sections": []}]
        result = _validate_batch_top_level({"requests": reqs})
        assert result == reqs

    def test_rejects_file_path_with_requests(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            _validate_batch_top_level({"requests": [], "file_path": "a.py"})

    def test_rejects_start_line_with_requests(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            _validate_batch_top_level({"requests": [], "start_line": 1})

    def test_rejects_end_line_with_requests(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            _validate_batch_top_level({"requests": [], "end_line": 10})

    def test_rejects_start_column_with_requests(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            _validate_batch_top_level({"requests": [], "start_column": 0})

    def test_rejects_end_column_with_requests(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            _validate_batch_top_level({"requests": [], "end_column": 5})

    def test_rejects_output_file_with_requests(self):
        with pytest.raises(ValueError, match="not supported"):
            _validate_batch_top_level({"requests": [], "output_file": "out.txt"})

    def test_rejects_suppress_output_with_requests(self):
        with pytest.raises(ValueError, match="not supported"):
            _validate_batch_top_level({"requests": [], "suppress_output": True})

    def test_rejects_non_list_requests(self):
        with pytest.raises(ValueError, match="must be a list"):
            _validate_batch_top_level({"requests": "not a list"})

    def test_rejects_dict_requests(self):
        with pytest.raises(ValueError, match="must be a list"):
            _validate_batch_top_level({"requests": {}})

    def test_accepts_empty_requests_list(self):
        result = _validate_batch_top_level({"requests": []})
        assert result == []


class TestClampRequests:
    def test_no_clamping_under_limit(self):
        reqs = [{"file_path": f"f{i}.py"} for i in range(5)]
        result, truncated = _clamp_requests(reqs, allow_truncate=True)
        assert result == reqs
        assert truncated is False

    def test_clamps_when_over_limit_with_truncate(self):
        limit = BATCH_LIMITS["max_files"]
        reqs = [{"file_path": f"f{i}.py"} for i in range(limit + 5)]
        result, truncated = _clamp_requests(reqs, allow_truncate=True)
        assert len(result) == limit
        assert truncated is True

    def test_raises_when_over_limit_without_truncate(self):
        limit = BATCH_LIMITS["max_files"]
        reqs = [{"file_path": f"f{i}.py"} for i in range(limit + 1)]
        with pytest.raises(ValueError, match="Too many files"):
            _clamp_requests(reqs, allow_truncate=False)

    def test_exact_limit_not_clamped(self):
        limit = BATCH_LIMITS["max_files"]
        reqs = [{"file_path": f"f{i}.py"} for i in range(limit)]
        result, truncated = _clamp_requests(reqs, allow_truncate=True)
        assert len(result) == limit
        assert truncated is False


class TestMakeErrorResult:
    def test_basic_error_result(self):
        result = _make_error_result("a.py", "/abs/a.py", "some error")
        assert result["file_path"] == "a.py"
        assert result["resolved_path"] == "/abs/a.py"
        assert result["sections"] == []
        assert len(result["errors"]) == 1
        assert result["errors"][0]["error"] == "some error"

    def test_empty_strings(self):
        result = _make_error_result("", "", "error")
        assert result["file_path"] == ""
        assert result["resolved_path"] == ""

    def test_error_is_dict(self):
        result = _make_error_result("f.py", "r", "e")
        assert isinstance(result, dict)
        assert isinstance(result["errors"], list)
        assert isinstance(result["errors"][0], dict)


class TestValidateFileRequest:
    def test_non_dict_with_fail_fast(self):
        with pytest.raises(ValueError, match="must be an object"):
            _validate_file_request("not a dict", fail_fast=True, allow_truncate=False)

    def test_non_dict_without_fail_fast(self):
        fp, secs, err, trunc = _validate_file_request(
            "string", fail_fast=False, allow_truncate=False
        )
        assert fp == ""
        assert secs == []
        assert err is not None
        assert "Invalid request entry" in err["errors"][0]["error"]
        assert trunc is False

    def test_missing_file_path_with_fail_fast(self):
        with pytest.raises(ValueError, match="non-empty string"):
            _validate_file_request(
                {"sections": []}, fail_fast=True, allow_truncate=False
            )

    def test_missing_file_path_without_fail_fast(self):
        fp, secs, err, trunc = _validate_file_request(
            {"sections": []}, fail_fast=False, allow_truncate=False
        )
        assert fp == ""
        assert err is not None
        assert "Invalid file_path" in err["errors"][0]["error"]

    def test_empty_file_path_with_fail_fast(self):
        with pytest.raises(ValueError, match="non-empty string"):
            _validate_file_request(
                {"file_path": "  ", "sections": []},
                fail_fast=True,
                allow_truncate=False,
            )

    def test_missing_sections_with_fail_fast(self):
        with pytest.raises(ValueError, match="sections must be a list"):
            _validate_file_request(
                {"file_path": "a.py"}, fail_fast=True, allow_truncate=False
            )

    def test_missing_sections_without_fail_fast(self):
        fp, secs, err, trunc = _validate_file_request(
            {"file_path": "a.py"}, fail_fast=False, allow_truncate=False
        )
        assert fp == "a.py"
        assert err is not None
        assert "Invalid sections" in err["errors"][0]["error"]

    def test_valid_request(self):
        fp, secs, err, trunc = _validate_file_request(
            {"file_path": "a.py", "sections": [{"start_line": 1}]},
            fail_fast=True,
            allow_truncate=False,
        )
        assert fp == "a.py"
        assert secs == [{"start_line": 1}]
        assert err is None
        assert trunc is False

    def test_too_many_sections_without_truncate_fail_fast(self):
        limit = BATCH_LIMITS["max_sections_per_file"]
        sections = [{"start_line": i} for i in range(limit + 1)]
        with pytest.raises(ValueError, match="Too many sections"):
            _validate_file_request(
                {"file_path": "a.py", "sections": sections},
                fail_fast=True,
                allow_truncate=False,
            )

    def test_too_many_sections_with_truncate(self):
        limit = BATCH_LIMITS["max_sections_per_file"]
        sections = [{"start_line": i} for i in range(limit + 5)]
        fp, secs, err, trunc = _validate_file_request(
            {"file_path": "a.py", "sections": sections},
            fail_fast=False,
            allow_truncate=True,
        )
        assert fp == "a.py"
        assert len(secs) == limit
        assert err is None
        assert trunc is True

    def test_too_many_sections_without_truncate_no_fail_fast(self):
        limit = BATCH_LIMITS["max_sections_per_file"]
        sections = [{"start_line": i} for i in range(limit + 1)]
        fp, secs, err, trunc = _validate_file_request(
            {"file_path": "a.py", "sections": sections},
            fail_fast=False,
            allow_truncate=False,
        )
        assert err is not None
        assert "Too many sections" in err["errors"][0]["error"]
        assert trunc is False


class TestResolveFile:
    def _make_tool(self, resolved_path="/resolved/a.py"):
        tool = MagicMock()
        tool.resolve_and_validate_file_path.return_value = resolved_path
        return tool

    def test_resolve_success(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("hello")
        tool = self._make_tool(str(f))
        resolved, err = _resolve_file(tool, "a.py", fail_fast=True)
        assert resolved == str(f)
        assert err is None

    def test_resolve_validation_error_fail_fast(self):
        tool = MagicMock()
        tool.resolve_and_validate_file_path.side_effect = ValueError("bad path")
        with pytest.raises(ValueError, match="bad path"):
            _resolve_file(tool, "bad.py", fail_fast=True)

    def test_resolve_validation_error_no_fail_fast(self):
        tool = MagicMock()
        tool.resolve_and_validate_file_path.side_effect = ValueError("bad path")
        resolved, err = _resolve_file(tool, "bad.py", fail_fast=False)
        assert resolved is None
        assert err is not None
        assert "bad path" in err["errors"][0]["error"]

    def test_resolve_file_not_exist_fail_fast(self, tmp_path):
        tool = self._make_tool(str(tmp_path / "nonexistent.py"))
        with pytest.raises(ValueError, match="does not exist"):
            _resolve_file(tool, "nonexistent.py", fail_fast=True)

    def test_resolve_file_not_exist_no_fail_fast(self, tmp_path):
        tool = self._make_tool(str(tmp_path / "nonexistent.py"))
        resolved, err = _resolve_file(tool, "nonexistent.py", fail_fast=False)
        assert resolved is None
        assert err is not None
        assert "does not exist" in err["errors"][0]["error"]

    def test_resolve_file_too_large_fail_fast(self, tmp_path):
        f = tmp_path / "big.py"
        f.write_bytes(b"x" * (BATCH_LIMITS["max_file_size_bytes"] + 1))
        tool = self._make_tool(str(f))
        with pytest.raises(ValueError, match="too large"):
            _resolve_file(tool, "big.py", fail_fast=True)

    def test_resolve_file_too_large_no_fail_fast(self, tmp_path):
        f = tmp_path / "big.py"
        f.write_bytes(b"x" * (BATCH_LIMITS["max_file_size_bytes"] + 1))
        tool = self._make_tool(str(f))
        resolved, err = _resolve_file(tool, "big.py", fail_fast=False)
        assert resolved is None
        assert err is not None
        assert "too large" in err["errors"][0]["error"]

    def test_resolve_file_exact_size_limit(self, tmp_path):
        f = tmp_path / "exact.py"
        f.write_bytes(b"x" * BATCH_LIMITS["max_file_size_bytes"])
        tool = self._make_tool(str(f))
        resolved, err = _resolve_file(tool, "exact.py", fail_fast=True)
        assert resolved == str(f)
        assert err is None

    def test_resolve_os_error_fail_fast(self, tmp_path):
        tool = self._make_tool(str(tmp_path / "a.py"))
        f = tmp_path / "a.py"
        f.write_text("ok")
        # ``Path.exists()`` calls ``Path.stat()`` internally on CPython
        # 3.10/3.11/3.12 — patching ``pathlib.Path.stat`` alone makes
        # ``exists()`` raise OSError BEFORE the code under test reaches
        # the size-check stat call. Mock ``exists()`` to keep returning
        # True so the OSError surfaces from the right call site.
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.stat", side_effect=OSError("boom")),
        ):
            with pytest.raises(ValueError, match="Could not stat"):
                _resolve_file(tool, "a.py", fail_fast=True)

    def test_resolve_os_error_no_fail_fast(self, tmp_path):
        tool = self._make_tool(str(tmp_path / "a.py"))
        f = tmp_path / "a.py"
        f.write_text("ok")
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.stat", side_effect=OSError("boom")),
        ):
            resolved, err = _resolve_file(tool, "a.py", fail_fast=False)
            assert resolved is None
            assert err is not None
            assert "Could not stat" in err["errors"][0]["error"]
