import pytest

from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool


@pytest.fixture(autouse=True)
def mock_external_commands(monkeypatch):
    """Auto-mock external command availability checks for all tests in this module."""
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
        lambda cmd: True,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fd_92_git_dir_handling(tmp_path, monkeypatch):
    """Test .git directory handling - corresponds to fd's test_git_dir."""
    # Create .git directory structure
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("git config")
    (tmp_path / ".git" / "objects").mkdir()
    (tmp_path / "file.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-H" in cmd:  # Hidden files included
            files = [
                str(tmp_path / ".git" / "config"),
                str(tmp_path / ".git" / "objects"),
                str(tmp_path / "file.txt"),
            ]
        else:  # .git normally ignored
            files = [str(tmp_path / "file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test without hidden flag (should ignore .git)
    result1 = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "hidden": False,
            "output_format": "json",
        }
    )

    assert result1["success"] is True
    assert result1["count"] == 1

    # Test with hidden flag (should include .git)
    result2 = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "hidden": True,
            "output_format": "json",
        }
    )

    assert result2["success"] is True
    assert result2["count"] == 3


@pytest.mark.asyncio
async def test_fd_93_gitignore_parent_handling(tmp_path, monkeypatch):
    """Test gitignore parent directory handling - corresponds to fd's test_gitignore_parent."""
    # Create parent .gitignore
    (tmp_path / ".gitignore").write_text("*.log\n")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "file.txt").write_text("content")
    (tmp_path / "subdir" / "debug.log").write_text("log content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-I" in cmd:  # No ignore
            files = [
                str(tmp_path / ".gitignore"),
                str(tmp_path / "subdir" / "file.txt"),
                str(tmp_path / "subdir" / "debug.log"),
            ]
        else:  # Respect parent .gitignore
            files = [
                str(tmp_path / ".gitignore"),
                str(tmp_path / "subdir" / "file.txt"),
                # debug.log is ignored by parent .gitignore
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test with parent gitignore
    result1 = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "no_ignore": False,
            "output_format": "json",
        }
    )

    assert result1["success"] is True
    assert result1["count"] == 2

    # Test ignoring parent gitignore
    result2 = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "no_ignore": True,
            "output_format": "json",
        }
    )

    assert result2["success"] is True
    assert result2["count"] == 3


@pytest.mark.asyncio
async def test_fd_94_hyperlink_output_advanced(tmp_path, monkeypatch):
    """Test advanced hyperlink output - corresponds to fd's test_hyperlink."""
    # Create test files
    (tmp_path / "file.txt").write_text("content")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "nested.txt").write_text("nested content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate hyperlink-ready output (absolute paths)
        files = [str(tmp_path / "file.txt"), str(tmp_path / "subdir" / "nested.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test hyperlink-ready output
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "absolute": True,  # Ensure absolute paths for hyperlinks
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert result["count"] == 2

    # Verify paths are absolute (suitable for hyperlinks) when results exist
    if result["success"] and result["count"] > 0:
        for item in result["results"]:
            path = item["path"]
            # Check if path is absolute (Unix or Windows style)
            assert path.startswith("/") or (
                len(path) > 1 and path[1] == ":"
            )  # Unix or Windows absolute path
