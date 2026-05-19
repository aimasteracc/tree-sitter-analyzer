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
    execute_batch,
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
            _validate_batch_top_level(
                {"requests": [], "file_path": "a.py"}
            )

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
            _validate_batch_top_level(
                {"requests": [], "suppress_output": True}
            )

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
        with patch("pathlib.Path.stat", side_effect=OSError("boom")):
            with pytest.raises(ValueError, match="Could not stat"):
                _resolve_file(tool, "a.py", fail_fast=True)

    def test_resolve_os_error_no_fail_fast(self, tmp_path):
        tool = self._make_tool(str(tmp_path / "a.py"))
        f = tmp_path / "a.py"
        f.write_text("ok")
        with patch("pathlib.Path.stat", side_effect=OSError("boom")):
            resolved, err = _resolve_file(tool, "a.py", fail_fast=False)
            assert resolved is None
            assert err is not None
            assert "Could not stat" in err["errors"][0]["error"]


class TestExecuteBatch:
    def _make_tool(self, resolved_path="/resolved/a.py"):
        tool = MagicMock()
        tool.resolve_and_validate_file_path.return_value = resolved_path
        return tool

    @pytest.mark.asyncio
    async def test_empty_requests(self):
        tool = self._make_tool()
        result = await execute_batch(tool, {"requests": []}, lambda *a: "")
        assert result["success"] is False
        assert result["count_files"] == 0
        assert result["count_sections"] == 0
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_single_file_single_section(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("line1\nline2\nline3\n")
        tool = self._make_tool(str(f))
        read_fn = MagicMock(return_value="line1\nline2")

        result = await execute_batch(
            tool,
            {
                "requests": [
                    {"file_path": "a.py", "sections": [{"start_line": 1, "end_line": 2}]}
                ]
            },
            read_fn,
        )
        assert result["success"] is True
        assert result["count_sections"] == 1
        assert result["count_files"] == 1
        assert result["errors_summary"]["errors"] == 0

    @pytest.mark.asyncio
    async def test_invalid_file_path_in_batch(self):
        tool = self._make_tool()
        result = await execute_batch(
            tool,
            {"requests": [{"file_path": "", "sections": [{"start_line": 1}]}]},
            lambda *a: "",
        )
        assert result["success"] is False
        assert result["errors_summary"]["errors"] >= 1

    @pytest.mark.asyncio
    async def test_non_dict_request_entry(self):
        tool = self._make_tool()
        result = await execute_batch(
            tool,
            {"requests": ["not_a_dict"]},
            lambda *a: "",
        )
        assert result["errors_summary"]["errors"] >= 1

    @pytest.mark.asyncio
    async def test_fail_fast_on_invalid_entry(self):
        tool = self._make_tool()
        with pytest.raises(ValueError, match="must be an object"):
            await execute_batch(
                tool,
                {"requests": ["bad"], "fail_fast": True},
                lambda *a: "",
            )

    @pytest.mark.asyncio
    async def test_truncation_on_too_many_files(self):
        tool = self._make_tool()
        limit = BATCH_LIMITS["max_files"]
        reqs = [{"file_path": f"f{i}.py", "sections": []} for i in range(limit + 3)]
        result = await execute_batch(
            tool,
            {"requests": reqs, "allow_truncate": True},
            lambda *a: "",
        )
        assert result["truncated"] is True
        assert result["count_files"] == limit

    @pytest.mark.asyncio
    async def test_reject_too_many_files_without_truncate(self):
        tool = self._make_tool()
        limit = BATCH_LIMITS["max_files"]
        reqs = [{"file_path": f"f{i}.py", "sections": []} for i in range(limit + 1)]
        with pytest.raises(ValueError, match="Too many files"):
            await execute_batch(tool, {"requests": reqs}, lambda *a: "")

    @pytest.mark.asyncio
    async def test_invalid_section_entry_in_batch(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("content\n")
        tool = self._make_tool(str(f))
        result = await execute_batch(
            tool,
            {
                "requests": [
                    {
                        "file_path": "a.py",
                        "sections": ["invalid_section"],
                    }
                ]
            },
            lambda *a: "",
        )
        assert result["errors_summary"]["errors"] >= 1

    @pytest.mark.asyncio
    async def test_invalid_start_line_in_section(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("content\n")
        tool = self._make_tool(str(f))
        result = await execute_batch(
            tool,
            {
                "requests": [
                    {
                        "file_path": "a.py",
                        "sections": [{"start_line": -1}],
                    }
                ]
            },
            lambda *a: "",
        )
        assert result["errors_summary"]["errors"] >= 1

    @pytest.mark.asyncio
    async def test_invalid_end_line_in_section(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("content\n")
        tool = self._make_tool(str(f))
        result = await execute_batch(
            tool,
            {
                "requests": [
                    {
                        "file_path": "a.py",
                        "sections": [
                            {"start_line": 5, "end_line": 2},
                        ],
                    }
                ]
            },
            lambda *a: "",
        )
        assert result["errors_summary"]["errors"] >= 1

    @pytest.mark.asyncio
    async def test_empty_content_counts_as_error(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("content\n")
        tool = self._make_tool(str(f))
        result = await execute_batch(
            tool,
            {
                "requests": [
                    {
                        "file_path": "a.py",
                        "sections": [{"start_line": 1, "end_line": 1}],
                    }
                ]
            },
            lambda *a: "",
        )
        assert result["errors_summary"]["errors"] >= 1

    @pytest.mark.asyncio
    async def test_fail_fast_on_section_limit(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("line\n" * 300)
        tool = self._make_tool(str(f))
        limit = BATCH_LIMITS["max_sections_total"]
        sections = [{"start_line": i + 1, "end_line": i + 1} for i in range(limit + 1)]
        with pytest.raises(ValueError, match="Too many sections"):
            await execute_batch(
                tool,
                {
                    "requests": [
                        {"file_path": "a.py", "sections": sections},
                    ],
                    "fail_fast": True,
                },
                lambda r, s, e: "content",
            )

    @pytest.mark.asyncio
    async def test_truncate_on_section_limit(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("line\n" * 300)
        tool = self._make_tool(str(f))
        limit = BATCH_LIMITS["max_sections_total"]
        sections = [
            {"start_line": i + 1, "end_line": i + 1} for i in range(limit + 5)
        ]
        result = await execute_batch(
            tool,
            {
                "requests": [
                    {"file_path": "a.py", "sections": sections},
                ],
                "allow_truncate": True,
            },
            lambda r, s, e: "content",
        )
        assert result["truncated"] is True

    @pytest.mark.asyncio
    async def test_batch_limits_in_response(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("hello\n")
        tool = self._make_tool(str(f))
        result = await execute_batch(
            tool,
            {"requests": []},
            lambda *a: "",
        )
        assert "limits" in result
        assert result["limits"]["max_files"] == 20

    @pytest.mark.asyncio
    async def test_agent_summary_in_response(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("hello\nworld\n")
        tool = self._make_tool(str(f))
        result = await execute_batch(
            tool,
            {
                "requests": [
                    {
                        "file_path": "a.py",
                        "sections": [{"start_line": 1, "end_line": 2}],
                    }
                ]
            },
            lambda r, s, e: "hello\nworld",
        )
        assert "agent_summary" in result
        assert result["agent_summary"]["mode"] == "batch"

    @pytest.mark.asyncio
    async def test_output_format_json(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("code\n")
        tool = self._make_tool(str(f))
        result = await execute_batch(
            tool,
            {
                "requests": [
                    {
                        "file_path": "a.py",
                        "sections": [{"start_line": 1}],
                    }
                ],
                "output_format": "json",
            },
            lambda r, s, e: "code",
        )
        assert result["success"] is True
        assert result["count_sections"] == 1

    @pytest.mark.asyncio
    async def test_output_format_toon(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("code\n")
        tool = self._make_tool(str(f))
        result = await execute_batch(
            tool,
            {
                "requests": [
                    {
                        "file_path": "a.py",
                        "sections": [{"start_line": 1}],
                    }
                ],
                "output_format": "toon",
            },
            lambda r, s, e: "code",
        )
        assert "toon_content" in result or result.get("success") is True

    @pytest.mark.asyncio
    async def test_multiple_files(self, tmp_path):
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("content_a\n")
        f2.write_text("content_b\n")

        def read_fn(resolved, start, end):
            if "a.py" in resolved:
                return "content_a"
            return "content_b"

        tool = MagicMock()
        tool.resolve_and_validate_file_path.side_effect = lambda p: str(
            tmp_path / p
        )
        result = await execute_batch(
            tool,
            {
                "requests": [
                    {"file_path": "a.py", "sections": [{"start_line": 1}]},
                    {"file_path": "b.py", "sections": [{"start_line": 1}]},
                ]
            },
            read_fn,
        )
        assert result["success"] is True
        assert result["count_files"] == 2
        assert result["count_sections"] == 2

    @pytest.mark.asyncio
    async def test_file_resolve_error_continues(self):
        tool = MagicMock()
        tool.resolve_and_validate_file_path.side_effect = ValueError("nope")
        result = await execute_batch(
            tool,
            {
                "requests": [
                    {"file_path": "a.py", "sections": [{"start_line": 1}]},
                ]
            },
            lambda *a: "content",
        )
        assert result["errors_summary"]["errors"] >= 1

    @pytest.mark.asyncio
    async def test_label_preserved_in_section_result(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("hello\n")
        tool = self._make_tool(str(f))
        result = await execute_batch(
            tool,
            {
                "requests": [
                    {
                        "file_path": "a.py",
                        "sections": [
                            {"start_line": 1, "label": "my_label"},
                        ],
                    }
                ],
                "output_format": "json",
            },
            lambda r, s, e: "hello",
        )
        assert result["success"] is True
        sections = result["results"][0]["sections"]
        assert sections[0]["label"] == "my_label"

    @pytest.mark.asyncio
    async def test_end_line_none_in_section(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("hello\n")
        tool = self._make_tool(str(f))
        result = await execute_batch(
            tool,
            {
                "requests": [
                    {
                        "file_path": "a.py",
                        "sections": [{"start_line": 1}],
                    }
                ]
            },
            lambda r, s, e: "hello",
        )
        assert result["success"] is True
        assert result["count_sections"] == 1

    @pytest.mark.asyncio
    async def test_whitespace_only_content_is_error(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("   \n")
        tool = self._make_tool(str(f))
        result = await execute_batch(
            tool,
            {
                "requests": [
                    {
                        "file_path": "a.py",
                        "sections": [{"start_line": 1, "end_line": 1}],
                    }
                ]
            },
            lambda r, s, e: "   ",
        )
        assert result["errors_summary"]["errors"] >= 1

    @pytest.mark.asyncio
    async def test_content_bytes_limit_exceeded(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("x\n")
        tool = self._make_tool(str(f))
        big_content = "x" * (BATCH_LIMITS["max_total_bytes"] + 1)
        with pytest.raises(ValueError, match="exceeds limits"):
            await execute_batch(
                tool,
                {
                    "requests": [
                        {
                            "file_path": "a.py",
                            "sections": [{"start_line": 1}],
                        }
                    ]
                },
                lambda r, s, e: big_content,
            )

    @pytest.mark.asyncio
    async def test_content_bytes_limit_with_truncate(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("x\n")
        tool = self._make_tool(str(f))
        big_content = "x" * (BATCH_LIMITS["max_total_bytes"] + 1)
        result = await execute_batch(
            tool,
            {
                "requests": [
                    {
                        "file_path": "a.py",
                        "sections": [{"start_line": 1}],
                    }
                ],
                "allow_truncate": True,
            },
            lambda r, s, e: big_content,
        )
        assert result["truncated"] is True

    @pytest.mark.asyncio
    async def test_content_lines_limit_exceeded(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("x\n")
        tool = self._make_tool(str(f))
        lines = "\n".join(["x"] * (BATCH_LIMITS["max_total_lines"] + 1))
        with pytest.raises(ValueError, match="exceeds limits"):
            await execute_batch(
                tool,
                {
                    "requests": [
                        {
                            "file_path": "a.py",
                            "sections": [{"start_line": 1, "end_line": BATCH_LIMITS["max_total_lines"] + 1}],
                        }
                    ]
                },
                lambda r, s, e: lines,
            )

    @pytest.mark.asyncio
    async def test_content_raw_format(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("raw_content\n")
        tool = self._make_tool(str(f))
        result = await execute_batch(
            tool,
            {
                "requests": [
                    {
                        "file_path": "a.py",
                        "sections": [{"start_line": 1}],
                    }
                ],
                "format": "raw",
                "output_format": "json",
            },
            lambda r, s, e: "raw_content",
        )
        assert result["success"] is True
        sections = result["results"][0]["sections"]
        assert sections[0]["content"] == "raw_content"

    @pytest.mark.asyncio
    async def test_success_false_when_all_errors(self):
        tool = MagicMock()
        tool.resolve_and_validate_file_path.side_effect = ValueError("err")
        result = await execute_batch(
            tool,
            {
                "requests": [
                    {"file_path": "a.py", "sections": [{"start_line": 1}]},
                ]
            },
            lambda *a: "content",
        )
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_errors_summary_count(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("x\n")
        tool = self._make_tool(str(f))
        result = await execute_batch(
            tool,
            {
                "requests": [
                    {
                        "file_path": "a.py",
                        "sections": ["bad1", "bad2"],
                    }
                ]
            },
            lambda *a: "content",
        )
        assert result["errors_summary"]["errors"] == 2
