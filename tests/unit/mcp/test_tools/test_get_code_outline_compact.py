"""Outline lists are sent once, at the top level (#1956).

``classes`` / ``top_level_functions`` / ``top_level_fields`` / ``imports`` /
``total_lines`` / ``package`` used to be hoisted to the top level AND kept
inside ``outline``, so a large module's outline was bigger than the file.
The top-level keys stay (the documented convention, and what consumers
read); ``outline`` keeps only what is not hoisted, plus a pointer.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
    OUTLINE_HOISTED_KEYS,
    GetCodeOutlineTool,
)

_PY = """\
    import os

    LIMIT = 3


    class Box:
        def size(self):
            return LIMIT


    def helper(x):
        return os.path.join(x, "y")
"""


async def _outline(root: Path, name: str, code: str, **extra: object) -> dict:
    (root / name).write_text(textwrap.dedent(code), encoding="utf-8")
    tool = GetCodeOutlineTool(project_root=str(root))
    return await tool.execute({"file_path": name, "output_format": "json", **extra})


@pytest.mark.asyncio
async def test_hoisted_lists_are_not_repeated_inside_outline(tmp_path: Path) -> None:
    resp = await _outline(tmp_path, "mod.py", _PY, include_imports=True)

    assert resp["classes"][0]["name"] == "Box"
    assert resp["top_level_functions"][0]["name"] == "helper"
    assert resp["top_level_fields"][0]["name"] == "LIMIT"
    assert resp["imports"]
    for key in OUTLINE_HOISTED_KEYS:
        assert key not in resp["outline"], key


@pytest.mark.asyncio
async def test_outline_keeps_unhoisted_data_and_names_moved_keys(
    tmp_path: Path,
) -> None:
    resp = await _outline(tmp_path, "mod.py", _PY)

    outline = resp["outline"]
    assert outline["statistics"]["class_count"] == 1
    assert outline["language"] == "python"
    assert outline["moved_to_top_level"] == [
        key for key in OUTLINE_HOISTED_KEYS if key in resp
    ]


@pytest.mark.asyncio
async def test_no_list_is_sent_twice(tmp_path: Path) -> None:
    resp = await _outline(tmp_path, "mod.py", _PY, include_imports=True)

    for key, value in resp["outline"].items():
        if isinstance(value, (list, dict)) and key in resp:
            assert resp[key] != value, f"{key} is sent twice"


@pytest.mark.asyncio
async def test_markdown_sections_stay_in_outline(tmp_path: Path) -> None:
    resp = await _outline(tmp_path, "doc.md", "# Title\n\n## Part\n\ntext\n")

    assert [h["text"] for h in resp["outline"]["headings"]] == ["Title", "Part"]


@pytest.mark.asyncio
async def test_outline_block_is_smaller_than_the_lists(tmp_path: Path) -> None:
    resp = await _outline(tmp_path, "mod.py", _PY)

    lists = len(json.dumps(resp["classes"])) + len(
        json.dumps(resp["top_level_functions"])
    )
    assert len(json.dumps(resp["outline"])) < lists
