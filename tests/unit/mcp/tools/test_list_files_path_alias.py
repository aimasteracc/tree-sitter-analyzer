#!/usr/bin/env python3
"""Wave 1b (audit project-05): ``list_files`` honors the ``path`` alias.

The project facade's ``files`` action advertises a ``path`` param, but the inner
``ListFilesTool`` reads ``roots``. Before this fix the facade whitelist dropped
``path`` and the tool silently fell back to the project root — so
``files path=nonexistent_dir`` returned the WHOLE project (a confident wrong
answer). ``path`` is now a first-class single-directory alias for ``roots`` and
a non-existent directory is rejected, never silently widened to the whole tree.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool


def test_path_is_declared_in_schema() -> None:
    """``path`` must be in the inner schema or the facade whitelist drops it."""
    tool = ListFilesTool()
    assert "path" in tool.get_tool_schema()["properties"]


def test_path_maps_to_roots_when_roots_absent(tmp_path) -> None:
    tool = ListFilesTool(str(tmp_path))
    args = {"path": str(tmp_path)}
    tool.validate_arguments(args)
    assert args["roots"] == [str(tmp_path)]


def test_explicit_roots_wins_over_path(tmp_path) -> None:
    tool = ListFilesTool(str(tmp_path))
    sub = tmp_path / "sub"
    sub.mkdir()
    args = {"path": str(tmp_path), "roots": [str(sub)]}
    tool.validate_arguments(args)
    assert args["roots"] == [str(sub)]


def test_empty_path_is_rejected_not_silently_widened(tmp_path) -> None:
    """Review issue 2: an explicit-but-empty ``path`` must be a user error, NOT
    a silent fallback to scanning the whole project (the project-05 bug class)."""
    tool = ListFilesTool(str(tmp_path))
    with pytest.raises(ValueError, match="path must be a non-empty string"):
        tool.validate_arguments({"path": ""})


def test_consumed_path_alias_is_removed(tmp_path) -> None:
    """Once mapped to roots, the ``path`` alias is popped so it never lingers
    into fd-command building or the echoed response."""
    tool = ListFilesTool(str(tmp_path))
    args = {"path": str(tmp_path)}
    tool.validate_arguments(args)
    assert "path" not in args
    assert args["roots"] == [str(tmp_path)]


@pytest.mark.requires_fd
@pytest.mark.asyncio
@pytest.mark.requires_fd
async def test_nonexistent_path_is_rejected_not_silently_widened(tmp_path) -> None:
    """A non-existent ``path`` must surface an error — NOT silently fall back to
    the project root and return the whole tree (the project-05 bug)."""
    tool = ListFilesTool(str(tmp_path))
    with pytest.raises(Exception) as exc:
        await tool.execute({"path": "nonexistent_dir_zzz", "output_format": "json"})
    # The failure must reference the bad directory, proving the filter was
    # honored rather than dropped.
    assert "nonexistent_dir_zzz" in str(exc.value)
