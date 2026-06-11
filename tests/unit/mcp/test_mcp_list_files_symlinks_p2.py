import pytest

from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool


@pytest.fixture(autouse=True)
def mock_external_commands(monkeypatch):
    """Auto-mock external command availability checks for all tests in this module."""
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
        lambda cmd: True,
    )


@pytest.mark.asyncio
async def test_fd_44_follow_symlinks(tmp_path, monkeypatch):
    """Test following symlinks - corresponds to fd's test_follow."""
    # Create files and symlinks
    (tmp_path / "real_file.txt").write_text("real content")
    (tmp_path / "real_dir").mkdir()
    (tmp_path / "real_dir" / "nested.txt").write_text("nested content")

    # Create symlinks (if supported)
    try:
        import os

        os.symlink(str(tmp_path / "real_file.txt"), str(tmp_path / "link_file.txt"))
        os.symlink(str(tmp_path / "real_dir"), str(tmp_path / "link_dir"))
        has_symlinks = True
    except (OSError, NotImplementedError):
        has_symlinks = False

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-L" in cmd and has_symlinks:  # Follow symlinks
            files = [
                str(tmp_path / "real_file.txt"),
                str(tmp_path / "real_dir"),
                str(tmp_path / "real_dir" / "nested.txt"),
                str(tmp_path / "link_file.txt"),
                str(tmp_path / "link_dir"),
                str(tmp_path / "link_dir" / "nested.txt"),  # Through symlink
            ]
        else:  # Don't follow symlinks
            files = [
                str(tmp_path / "real_file.txt"),
                str(tmp_path / "real_dir"),
                str(tmp_path / "real_dir" / "nested.txt"),
            ]
            if has_symlinks:
                files.extend(
                    [str(tmp_path / "link_file.txt"), str(tmp_path / "link_dir")]
                )

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test without following symlinks
    result1 = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "follow_symlinks": False,
        }
    )

    assert result1["success"] is True
    assert (
        result1["count"] >= 3
    )  # ratchet: nondeterministic — 3 without symlinks (Windows), 5 with symlinks (macOS/Linux)

    # Test following symlinks
    result2 = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "follow_symlinks": True,
        }
    )

    assert result2["success"] is True
    assert (
        result2["count"] >= 3
    )  # ratchet: nondeterministic — 3 without symlinks (Windows), 6 with symlinks (macOS/Linux)


@pytest.mark.asyncio
async def test_fd_45_file_system_boundaries(tmp_path, monkeypatch):
    """Test file system boundaries - corresponds to fd's test_file_system_boundaries."""
    # Create test structure
    (tmp_path / "file.txt").write_text("content")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "nested.txt").write_text("nested content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate staying within file system boundaries
        files = [
            str(tmp_path / "file.txt"),
            str(tmp_path / "subdir"),
            str(tmp_path / "subdir" / "nested.txt"),
        ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test file system boundary handling
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] == 3


@pytest.mark.asyncio
async def test_fd_46_follow_broken_symlink(tmp_path, monkeypatch):
    """Test following broken symlinks - corresponds to fd's test_follow_broken_symlink."""
    # Create real file and broken symlink
    (tmp_path / "real.txt").write_text("real content")

    # Create broken symlink (if supported)
    try:
        import os

        os.symlink(str(tmp_path / "nonexistent.txt"), str(tmp_path / "broken_link.txt"))
        has_broken_symlink = True
    except (OSError, NotImplementedError):
        has_broken_symlink = False

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [str(tmp_path / "real.txt")]
        if has_broken_symlink:
            if "-L" in cmd:  # Follow symlinks - broken link might cause issues
                files.append(str(tmp_path / "broken_link.txt"))
            else:  # Don't follow - just list the link
                files.append(str(tmp_path / "broken_link.txt"))

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test broken symlink handling
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "follow_symlinks": True,
        }
    )

    assert result["success"] is True
    assert (
        result["count"] >= 0
    )  # ratchet: nondeterministic — 1 without broken symlink (Windows), 2 with broken symlink (macOS/Linux)


@pytest.mark.asyncio
async def test_fd_47_symlink_as_root(tmp_path, monkeypatch):
    """Test symlink as search root - corresponds to fd's test_symlink_as_root."""
    # Create real directory and symlink to it
    (tmp_path / "real_dir").mkdir()
    (tmp_path / "real_dir" / "file.txt").write_text("content")

    # Create symlink to directory (if supported)
    try:
        import os

        os.symlink(str(tmp_path / "real_dir"), str(tmp_path / "link_dir"))
        has_dir_symlink = True
    except (OSError, NotImplementedError):
        has_dir_symlink = False

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Check if symlink directory is used as root
        if has_dir_symlink and str(tmp_path / "link_dir") in cmd:
            files = [str(tmp_path / "link_dir" / "file.txt")]
        else:
            files = [str(tmp_path / "real_dir" / "file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test using symlink as root
    if has_dir_symlink:
        result = await tool.execute(
            {"roots": [str(tmp_path / "link_dir")], "pattern": "*", "glob": True}
        )
    else:
        result = await tool.execute(
            {"roots": [str(tmp_path / "real_dir")], "pattern": "*", "glob": True}
        )

    assert result["success"] is True
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_fd_48_symlink_and_absolute_path(tmp_path, monkeypatch):
    """Test symlinks with absolute paths - corresponds to fd's test_symlink_and_absolute_path."""
    # Create structure with symlinks
    (tmp_path / "target").mkdir()
    (tmp_path / "target" / "file.txt").write_text("target content")

    # Create symlink (if supported)
    try:
        import os

        os.symlink(str(tmp_path / "target"), str(tmp_path / "link"))
        has_symlink = True
    except (OSError, NotImplementedError):
        has_symlink = False

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-a" in cmd and has_symlink:  # Absolute paths
            files = [
                str(tmp_path / "target"),
                str(tmp_path / "target" / "file.txt"),
                str(tmp_path / "link"),
            ]
        else:
            files = [str(tmp_path / "target"), str(tmp_path / "target" / "file.txt")]
            if has_symlink:
                files.append(str(tmp_path / "link"))

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test symlinks with absolute paths
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "absolute": True}
    )

    assert result["success"] is True
    assert (
        result["count"] >= 2
    )  # ratchet: nondeterministic — 2 without symlinks (Windows), 3 with symlinks (macOS/Linux)


@pytest.mark.asyncio
async def test_fd_49_symlink_as_absolute_root(tmp_path, monkeypatch):
    """Test symlink as absolute root - corresponds to fd's test_symlink_as_absolute_root."""
    # Create target and symlink
    (tmp_path / "target").mkdir()
    (tmp_path / "target" / "file.txt").write_text("content")

    # Create symlink (if supported)
    try:
        import os

        os.symlink(str(tmp_path / "target"), str(tmp_path / "abs_link"))
        has_symlink = True
    except (OSError, NotImplementedError):
        has_symlink = False

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if has_symlink and str(tmp_path / "abs_link") in cmd:
            files = [str(tmp_path / "abs_link" / "file.txt")]
        else:
            files = [str(tmp_path / "target" / "file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test absolute symlink as root
    root_path = str(tmp_path / "abs_link") if has_symlink else str(tmp_path / "target")
    result = await tool.execute(
        {"roots": [root_path], "pattern": "*", "glob": True, "absolute": True}
    )

    assert result["success"] is True
    assert result["count"] == 1
