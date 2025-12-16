#!/usr/bin/env python3
"""
Batch metrics tests for AnalyzeScaleTool.

Focus:
- metrics_only + file_paths[] batch mode
- TOON default output (and TOON response must not include JSON details like results)
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool


@pytest.mark.asyncio
async def test_analyze_scale_metrics_batch_json() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        p = Path(temp_dir)
        (p / "a.py").write_text("print('a')\n", encoding="utf-8")
        (p / "b.py").write_text("print('b')\n", encoding="utf-8")

        tool = AnalyzeScaleTool(project_root=temp_dir)
        res = await tool.execute(
            {
                "file_paths": [str(p / "a.py"), str(p / "b.py")],
                "metrics_only": True,
                "output_format": "json",
            }
        )

        assert res["success"] is True
        assert "results" in res
        assert len(res["results"]) == 2
        assert all("metrics" in x or "error" in x for x in res["results"])


@pytest.mark.asyncio
async def test_analyze_scale_metrics_batch_toon_default_strips_json_details() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        p = Path(temp_dir)
        (p / "a.py").write_text("print('a')\n", encoding="utf-8")

        tool = AnalyzeScaleTool(project_root=temp_dir)
        res = await tool.execute(
            {"file_paths": [str(p / "a.py")], "metrics_only": True}
        )

        assert res.get("format") == "toon"
        assert "toon_content" in res
        assert "results" not in res


@pytest.mark.asyncio
async def test_analyze_scale_metrics_batch_requires_metrics_only() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        p = Path(temp_dir)
        (p / "a.py").write_text("print('a')\n", encoding="utf-8")

        tool = AnalyzeScaleTool(project_root=temp_dir)
        with pytest.raises(ValueError):
            await tool.execute({"file_paths": [str(p / "a.py")], "metrics_only": False})
