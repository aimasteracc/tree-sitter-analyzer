#!/usr/bin/env python3

from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.mcp.tools.batch_executor import (
    BATCH_LIMITS,
    execute_batch,
)


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
                    {
                        "file_path": "a.py",
                        "sections": [{"start_line": 1, "end_line": 2}],
                    }
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
        assert result["errors_summary"]["errors"] == 1

    @pytest.mark.asyncio
    async def test_non_dict_request_entry(self):
        tool = self._make_tool()
        result = await execute_batch(
            tool,
            {"requests": ["not_a_dict"]},
            lambda *a: "",
        )
        assert result["errors_summary"]["errors"] == 1

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
        assert result["errors_summary"]["errors"] == 1

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
        assert result["errors_summary"]["errors"] == 1

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
        assert result["errors_summary"]["errors"] == 1

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
        assert result["errors_summary"]["errors"] == 1

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
        sections = [{"start_line": i + 1, "end_line": i + 1} for i in range(limit + 5)]
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
        tool.resolve_and_validate_file_path.side_effect = lambda p: str(tmp_path / p)
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
        assert result["errors_summary"]["errors"] == 1

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
        assert result["errors_summary"]["errors"] == 1

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
                            "sections": [
                                {
                                    "start_line": 1,
                                    "end_line": BATCH_LIMITS["max_total_lines"] + 1,
                                }
                            ],
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
