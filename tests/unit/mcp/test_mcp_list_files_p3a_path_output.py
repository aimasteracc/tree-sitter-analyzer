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
async def test_fd_50_symlink_and_full_path(tmp_path, monkeypatch):
    """Test symlinks with full path matching - corresponds to fd's test_symlink_and_full_path."""
    # Create nested structure with symlinks
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("main content")

    # Create symlink (if supported)
    try:
        import os

        os.symlink(str(tmp_path / "src"), str(tmp_path / "source"))
        has_symlink = True
    except (OSError, NotImplementedError):
        has_symlink = False

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-p" in cmd and "src" in cmd:  # Full path match for "src"
            files = [str(tmp_path / "src" / "main.py")]
            if has_symlink and "source" not in cmd:
                # Only match actual "src" path, not "source" symlink
                pass
        else:
            files = [str(tmp_path / "src" / "main.py")]
            if has_symlink:
                files.append(str(tmp_path / "source" / "main.py"))

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test full path matching with symlinks
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "src", "full_path_match": True}
    )

    assert result["success"] is True
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_fd_51_print0_output_simulation(tmp_path, monkeypatch):
    """Test print0 output simulation - corresponds to fd's test_print0."""
    # Create test files
    (tmp_path / "file1.txt").write_text("content1")
    (tmp_path / "file2.txt").write_text("content2")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Our tool returns JSON, not null-separated output
        files = [str(tmp_path / "file1.txt"), str(tmp_path / "file2.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test structured output (our equivalent of print0)
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert result["count"] == 2
    # Verify structured JSON output
    assert "results" in result
    assert isinstance(result["results"], list)


@pytest.mark.asyncio
async def test_fd_52_absolute_path_output(tmp_path, monkeypatch):
    """Test absolute path output - corresponds to fd's test_absolute_path."""
    # Create test files
    (tmp_path / "file.txt").write_text("content")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "nested.txt").write_text("nested content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-a" in cmd:  # Absolute paths
            files = [
                str(tmp_path / "file.txt"),
                str(tmp_path / "subdir"),
                str(tmp_path / "subdir" / "nested.txt"),
            ]
        else:  # Relative paths
            files = ["file.txt", "subdir", "subdir/nested.txt"]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test absolute paths
    result1 = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "absolute": True,
            "output_format": "json",
        }
    )

    assert result1["success"] is True
    assert result1["count"] == 3
    # Verify absolute paths
    for item in result1["results"]:
        path = item["path"]
        assert path.startswith("/") or (len(path) > 1 and path[1] == ":")

    # Test relative paths
    result2 = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "absolute": False,
            "output_format": "json",
        }
    )

    assert result2["success"] is True
    assert result2["count"] == 3


@pytest.mark.asyncio
async def test_fd_53_implicit_absolute_path(tmp_path, monkeypatch):
    """Test implicit absolute path - corresponds to fd's test_implicit_absolute_path."""
    # Create test files
    (tmp_path / "file.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Default behavior should be absolute paths
        files = [str(tmp_path / "file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test default (implicit absolute) paths
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_fd_54_normalized_absolute_path(tmp_path, monkeypatch):
    """Test normalized absolute path - corresponds to fd's test_normalized_absolute_path."""
    # Create test structure with potential path normalization issues
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "file.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Return normalized absolute paths
        files = [
            (
                str(tmp_path / "subdir" / "file.txt").replace("\\", "/")
                if "\\" in str(tmp_path)
                else str(tmp_path / "subdir" / "file.txt")
            )
        ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test normalized paths
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "absolute": True}
    )

    assert result["success"] is True
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_fd_55_custom_path_separator(tmp_path, monkeypatch):
    """Test custom path separator - corresponds to fd's test_custom_path_separator."""
    # Create nested structure
    (tmp_path / "dir").mkdir()
    (tmp_path / "dir" / "file.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Our tool uses OS-appropriate separators
        files = [str(tmp_path / "dir" / "file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test path separator handling
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert result["count"] == 1
    # Verify proper path separators
    for item in result["results"]:
        path = item["path"]
        # Should use OS-appropriate separators
        assert "/" in path or "\\" in path


@pytest.mark.asyncio
async def test_fd_56_base_directory_output(tmp_path, monkeypatch):
    """Test base directory output - corresponds to fd's test_base_directory."""
    # Create test structure
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "file.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Check if searching from subdir as base
        if str(tmp_path / "subdir") in cmd:
            files = [str(tmp_path / "subdir" / "file.txt")]
        else:
            files = [str(tmp_path / "subdir"), str(tmp_path / "subdir" / "file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test with subdir as base
    result = await tool.execute(
        {"roots": [str(tmp_path / "subdir")], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] == 2


@pytest.mark.asyncio
async def test_fd_57_strip_cwd_prefix(tmp_path, monkeypatch):
    """Test stripping current working directory prefix - corresponds to fd's test_strip_cwd_prefix."""
    # Create test files
    (tmp_path / "file.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate stripping CWD prefix (relative paths)
        if "-a" not in cmd:
            files = ["file.txt"]  # Relative to CWD
        else:
            files = [str(tmp_path / "file.txt")]  # Absolute

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test relative paths (CWD prefix stripped)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "absolute": False}
    )

    assert result["success"] is True
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_fd_58_format_output_structured(tmp_path, monkeypatch):
    """Test structured format output - corresponds to fd's format test."""
    # Create test files
    (tmp_path / "file.txt").write_text("content")
    (tmp_path / "subdir").mkdir()

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [str(tmp_path / "file.txt"), str(tmp_path / "subdir")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test structured JSON format (our default)
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert result["count"] == 2
    # Verify structured format
    assert "results" in result
    assert "count" in result
    assert "success" in result
    for item in result["results"]:
        assert "path" in item
        assert "is_dir" in item


@pytest.mark.asyncio
async def test_fd_65_exec_invalid_utf8_simulation(tmp_path, monkeypatch):
    """Test exec invalid UTF-8 simulation - corresponds to fd's test_exec_invalid_utf8."""
    # Create test files with valid names
    (tmp_path / "valid_utf8.txt").write_text("valid UTF-8 content")
    (tmp_path / "another_file.txt").write_text("another content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [str(tmp_path / "valid_utf8.txt"), str(tmp_path / "another_file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test UTF-8 handling in execution context
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*.txt", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] == 2


@pytest.mark.asyncio
async def test_fd_38_gitignore_and_fdignore_advanced(tmp_path, monkeypatch):
    """Test advanced gitignore and fdignore handling - corresponds to fd's test_gitignore_and_fdignore."""
    # Create complex directory structure
    (tmp_path / ".gitignore").write_text("*.log\ntemp/\n")
    (tmp_path / ".fdignore").write_text("*.tmp\ncache/\n")
    (tmp_path / "file.txt").write_text("content")
    (tmp_path / "debug.log").write_text("log content")
    (tmp_path / "temp.tmp").write_text("temp content")
    (tmp_path / "temp").mkdir()
    (tmp_path / "temp" / "data.txt").write_text("temp data")
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "data.txt").write_text("cache data")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-I" in cmd:  # No ignore
            files = [
                str(tmp_path / ".gitignore"),
                str(tmp_path / ".fdignore"),
                str(tmp_path / "file.txt"),
                str(tmp_path / "debug.log"),
                str(tmp_path / "temp.tmp"),
                str(tmp_path / "temp" / "data.txt"),
                str(tmp_path / "cache" / "data.txt"),
            ]
        else:
            # Respect both .gitignore and .fdignore
            files = [
                str(tmp_path / ".gitignore"),
                str(tmp_path / ".fdignore"),
                str(tmp_path / "file.txt"),
                # debug.log, temp.tmp, temp/, cache/ are ignored
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test with ignore rules
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "no_ignore": False}
    )

    assert result1["success"] is True
    assert result1["count"] == 3

    # Test without ignore rules
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "no_ignore": True}
    )

    assert result2["success"] is True
    assert result2["count"] == 7
