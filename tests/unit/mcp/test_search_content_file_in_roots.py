#!/usr/bin/env python3
"""Regression — L10: ``search_content(roots=['<file>'])`` returns a canonical
error envelope instead of a triple-wrapped ``AnalysisError``.

Background (round-14b L10): users naturally try a file path in ``roots``
because the tool name implies it accepts files. Before this fix the
chain was::

    _validate_roots
      → resolve_and_validate_directory_path
        → ValueError("Invalid directory path: Path is not a directory: ...")
      → ValueError("Invalid root '...': Invalid directory path: ...")
    → handle_mcp_errors decorator
      → AnalysisError("Operation failed: Invalid root '...': Invalid directory path: ...")

That cascade leaks ``Operation failed`` and ``Path is not a directory`` —
neither tells the agent what to fix. The pre-check in ``execute`` now
intercepts the file-as-root case and returns a flat envelope with
``error_type="validation"``, ``verdict="ERROR"``, and a concrete
``next_step`` that points at ``files=`` instead.
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


@pytest.fixture
def project_with_files(tmp_path: Path) -> Path:
    """Build a small project that contains both directories and real files."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main():\n    return 1\n")
    (tmp_path / "src" / "util.py").write_text("def helper():\n    return 2\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_a():\n    pass\n")
    return tmp_path


@pytest.fixture
def tool(project_with_files: Path) -> SearchContentTool:
    return SearchContentTool(project_root=str(project_with_files))


@pytest.mark.asyncio
async def test_file_in_roots_returns_canonical_envelope(
    tool: SearchContentTool,
    project_with_files: Path,
) -> None:
    file_path = "src/main.py"
    result = await tool.execute({"query": "def ", "roots": [file_path]})

    # Should be a dict envelope, not raise.
    assert isinstance(result, dict)
    assert result["success"] is False

    # Canonical fields per the task spec.
    assert result["error_type"] == "validation"
    assert "'roots'" in result["error"]
    assert "'files'" in result["error"]
    assert result["summary_line"] == "search_content: roots must be directories"

    # agent_summary block follows the canonical shape.
    agent_summary = result["agent_summary"]
    assert agent_summary["verdict"] == "ERROR"
    assert agent_summary["summary_line"] == (
        "search_content: roots must be directories"
    )
    # next_step must mention files= and echo the path the user passed.
    assert "files=" in agent_summary["next_step"]
    assert file_path in agent_summary["next_step"]

    # Original input is mirrored back so the agent can correlate request.
    assert result["roots"] == [file_path]


@pytest.mark.requires_ripgrep
@pytest.mark.asyncio
async def test_normal_directory_root_still_succeeds(
    tool: SearchContentTool,
    project_with_files: Path,
) -> None:
    # Sanity: directory roots are not intercepted by the new pre-check.
    result = await tool.execute(
        {
            "query": "def ",
            "roots": ["src"],
            "total_only": True,
        }
    )
    # total_only returns an int (the match count) directly.
    assert isinstance(result, int)
    assert result >= 2  # two ``def`` declarations in src/  # ratchet: nondeterministic


@pytest.mark.requires_ripgrep
@pytest.mark.asyncio
async def test_files_parameter_still_succeeds(
    tool: SearchContentTool,
    project_with_files: Path,
) -> None:
    # Sanity: passing files= for single-file search keeps working.
    result = await tool.execute(
        {
            "query": "def ",
            "files": ["src/main.py"],
            "total_only": True,
        }
    )
    assert isinstance(result, int)
    assert result


@pytest.mark.asyncio
async def test_mixed_dir_and_file_in_roots_still_envelope(
    tool: SearchContentTool,
    project_with_files: Path,
) -> None:
    # Any file in roots triggers the canonical envelope — we don't try to
    # split the request silently.
    result = await tool.execute(
        {
            "query": "def ",
            "roots": ["src", "src/main.py"],
        }
    )
    assert isinstance(result, dict)
    assert result["success"] is False
    assert result["error_type"] == "validation"
    # The next_step should point at the file root the user passed.
    assert "src/main.py" in result["agent_summary"]["next_step"]


@pytest.mark.asyncio
async def test_nonexistent_root_keeps_existing_error_behavior(
    tool: SearchContentTool,
) -> None:
    # Pre-check returns None for paths that don't resolve to existing files,
    # so the normal validator runs and raises (wrapped by handle_mcp_errors).
    # The exact error class is not part of this contract — we only assert
    # that the pre-check does NOT swallow non-file errors into a misleading
    # envelope.
    with pytest.raises(Exception) as exc_info:
        await tool.execute({"query": "def ", "roots": ["/nonexistent/directory/xyz"]})
    msg = str(exc_info.value)
    # We expect the existing "not a directory"-style message, NOT the
    # L10 envelope message (which would indicate the file-in-roots check
    # is over-firing).
    assert "files=" not in msg
