#!/usr/bin/env python3
"""
Batch tests for ReadPartialTool (extract_code_section).

Focus:
- requests[] batch mode (multi-file x multi-range)
- TOON default output (and TOON response must not include JSON details like results/content)
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool


@pytest.mark.asyncio
async def test_read_partial_batch_json_structure() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        p = Path(temp_dir)
        (p / "a.txt").write_text(
            "\n".join([f"A{i}" for i in range(1, 21)]), encoding="utf-8"
        )
        (p / "b.txt").write_text(
            "\n".join([f"B{i}" for i in range(1, 11)]), encoding="utf-8"
        )

        tool = ReadPartialTool(temp_dir)
        res = await tool.execute(
            {
                "requests": [
                    {
                        "file_path": str(p / "a.txt"),
                        "sections": [{"start_line": 1, "end_line": 3, "label": "head"}],
                    },
                    {
                        "file_path": str(p / "b.txt"),
                        "sections": [{"start_line": 5, "end_line": 6, "label": "mid"}],
                    },
                ],
                "output_format": "json",
            }
        )

        assert res["success"] is True
        assert "results" in res
        assert len(res["results"]) == 2
        a0 = res["results"][0]
        assert a0["file_path"].endswith("a.txt")
        assert len(a0["sections"]) == 1
        assert "content" in a0["sections"][0]


@pytest.mark.asyncio
async def test_read_partial_batch_toon_default_strips_json_details() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        p = Path(temp_dir)
        (p / "a.txt").write_text(
            "\n".join([f"A{i}" for i in range(1, 21)]), encoding="utf-8"
        )

        tool = ReadPartialTool(temp_dir)
        res = await tool.execute(
            {
                "requests": [
                    {
                        "file_path": str(p / "a.txt"),
                        "sections": [{"start_line": 1, "end_line": 3, "label": "head"}],
                    }
                ]
            }
        )

        assert res.get("format") == "toon"
        assert "toon_content" in res
        # Token-savings requirement: JSON details must not be included in TOON response
        assert "results" not in res


@pytest.mark.asyncio
async def test_read_partial_batch_mutual_exclusion() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        p = Path(temp_dir)
        (p / "a.txt").write_text("A1\nA2\nA3", encoding="utf-8")
        tool = ReadPartialTool(temp_dir)

        with pytest.raises(ValueError):
            await tool.execute(
                {
                    "requests": [
                        {"file_path": str(p / "a.txt"), "sections": [{"start_line": 1}]}
                    ],
                    "file_path": str(p / "a.txt"),
                    "start_line": 1,
                }
            )
