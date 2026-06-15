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
async def test_fd_21_glob_searches(tmp_path, monkeypatch):
    """Test glob searches - corresponds to fd's test_glob_searches."""
    # Create test files
    (tmp_path / "test.txt").write_text("content")
    (tmp_path / "test.py").write_text("content")
    (tmp_path / "example.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Check for glob patterns
        if "--glob" in cmd:
            if "*.txt" in cmd:
                files = [str(tmp_path / "test.txt"), str(tmp_path / "example.txt")]
            elif "test.*" in cmd:
                files = [str(tmp_path / "test.txt"), str(tmp_path / "test.py")]
            else:
                files = []
        else:
            files = [
                str(tmp_path / "test.txt"),
                str(tmp_path / "test.py"),
                str(tmp_path / "example.txt"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test glob pattern for txt files
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*.txt", "glob": True}
    )

    assert result1["success"] is True
    assert result1["count"] == 2

    # Test glob pattern for test files
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "test.*", "glob": True}
    )

    assert result2["success"] is True
    assert result2["count"] == 2


@pytest.mark.asyncio
async def test_fd_22_full_path_glob_searches(tmp_path, monkeypatch):
    """Test full path glob searches - corresponds to fd's test_full_path_glob_searches."""
    # Create nested structure
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("content")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "main.py").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Full path glob search
        if "--glob" in cmd and "-p" in cmd:
            if "**/src/**" in cmd:
                files = [str(tmp_path / "src" / "main.py")]
            else:
                files = [
                    str(tmp_path / "src" / "main.py"),
                    str(tmp_path / "tests" / "main.py"),
                ]
        else:
            files = [
                str(tmp_path / "src" / "main.py"),
                str(tmp_path / "tests" / "main.py"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test full path glob
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "**/src/**",
            "glob": True,
            "full_path_match": True,
        }
    )

    assert result["success"] is True
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_fd_23_smart_case_glob_searches(tmp_path, monkeypatch):
    """Test smart case glob searches - corresponds to fd's test_smart_case_glob_searches."""
    # Create test files
    (tmp_path / "Test.txt").write_text("content")
    (tmp_path / "test.txt").write_text("content")
    (tmp_path / "example.TXT").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Smart case glob search
        if "--glob" in cmd:
            if "*.txt" in cmd:  # Lowercase pattern matches all cases
                files = [
                    str(tmp_path / "Test.txt"),
                    str(tmp_path / "test.txt"),
                    str(tmp_path / "example.TXT"),
                ]
            elif "*.TXT" in cmd:  # Uppercase pattern is exact
                files = [str(tmp_path / "example.TXT")]
            else:
                files = []
        else:
            files = [
                str(tmp_path / "Test.txt"),
                str(tmp_path / "test.txt"),
                str(tmp_path / "example.TXT"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test smart case glob (lowercase matches all)
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*.txt", "glob": True}
    )

    assert result1["success"] is True
    assert result1["count"] == 3

    # Test smart case glob (uppercase is exact)
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*.TXT", "glob": True}
    )

    assert result2["success"] is True
    assert result2["count"] == 1


@pytest.mark.asyncio
async def test_fd_24_case_sensitive_glob_searches(tmp_path, monkeypatch):
    """Test case sensitive glob searches - corresponds to fd's test_case_sensitive_glob_searches."""
    # Create test files
    (tmp_path / "Test.txt").write_text("content")
    (tmp_path / "test.txt").write_text("content")
    (tmp_path / "example.TXT").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Case sensitive glob search
        if "--glob" in cmd:
            if "*.txt" in cmd:
                files = [str(tmp_path / "Test.txt"), str(tmp_path / "test.txt")]
            elif "*.TXT" in cmd:
                files = [str(tmp_path / "example.TXT")]
            else:
                files = []
        else:
            files = [
                str(tmp_path / "Test.txt"),
                str(tmp_path / "test.txt"),
                str(tmp_path / "example.TXT"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test case sensitive glob
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*.txt", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] == 2


@pytest.mark.asyncio
async def test_fd_25_glob_searches_with_extension(tmp_path, monkeypatch):
    """Test glob searches with extension - corresponds to fd's test_glob_searches_with_extension."""
    # Create test files
    (tmp_path / "test.txt").write_text("content")
    (tmp_path / "test.py").write_text("content")
    (tmp_path / "example.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Glob with extension filter
        has_glob = "--glob" in cmd and "test*" in cmd
        has_extension = "-e" in cmd and "txt" in cmd

        if has_glob and has_extension:
            files = [str(tmp_path / "test.txt")]  # Only test.txt matches both
        elif has_glob:
            files = [str(tmp_path / "test.txt"), str(tmp_path / "test.py")]
        elif has_extension:
            files = [str(tmp_path / "test.txt"), str(tmp_path / "example.txt")]
        else:
            files = [
                str(tmp_path / "test.txt"),
                str(tmp_path / "test.py"),
                str(tmp_path / "example.txt"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test glob with extension filter
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "test*",
            "glob": True,
            "extensions": ["txt"],
        }
    )

    assert result["success"] is True
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_fd_29_hidden_files(tmp_path, monkeypatch):
    """Test hidden files search - corresponds to fd's test_hidden."""
    # Create hidden and visible files
    (tmp_path / ".hidden").write_text("hidden content")
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config" / "settings").write_text("config")
    (tmp_path / "visible.txt").write_text("visible content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-H" in cmd:  # Include hidden files
            files = [
                str(tmp_path / ".hidden"),
                str(tmp_path / ".config"),
                str(tmp_path / ".config" / "settings"),
                str(tmp_path / "visible.txt"),
            ]
        else:  # Exclude hidden files
            files = [str(tmp_path / "visible.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test without hidden files
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "hidden": False}
    )

    assert result1["success"] is True
    assert result1["count"] == 1

    # Test with hidden files
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "hidden": True}
    )

    assert result2["success"] is True
    assert result2["count"] == 4


@pytest.mark.asyncio
async def test_fd_30_hidden_file_attribute(tmp_path, monkeypatch):
    """Test Windows hidden file attribute - corresponds to fd's test_hidden_file_attribute."""
    # Create test files (Windows hidden attribute simulation)
    (tmp_path / "normal.txt").write_text("normal content")
    (tmp_path / "hidden_attr.txt").write_text("hidden attr content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate Windows hidden attribute handling
        if "-H" in cmd:  # Include files with hidden attribute
            files = [str(tmp_path / "normal.txt"), str(tmp_path / "hidden_attr.txt")]
        else:  # Exclude files with hidden attribute
            files = [str(tmp_path / "normal.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test hidden attribute handling
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "hidden": True}
    )

    assert result["success"] is True
    assert result["count"] == 2


@pytest.mark.asyncio
async def test_fd_31_type_filtering(tmp_path, monkeypatch):
    """Test file type filtering - corresponds to fd's test_type."""
    # Create different file types
    (tmp_path / "file.txt").write_text("content")
    (tmp_path / "directory").mkdir()
    (tmp_path / "directory" / "nested.txt").write_text("nested")

    # Create symlink (if supported)
    try:
        import os

        os.symlink(str(tmp_path / "file.txt"), str(tmp_path / "link.txt"))
        has_symlink = True
    except (OSError, NotImplementedError):
        has_symlink = False

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-t" in cmd:
            if "f" in cmd:  # Files only
                files = [
                    str(tmp_path / "file.txt"),
                    str(tmp_path / "directory" / "nested.txt"),
                ]
                if has_symlink:
                    files.append(str(tmp_path / "link.txt"))
            elif "d" in cmd:  # Directories only
                files = [str(tmp_path / "directory")]
            elif "l" in cmd:  # Symlinks only
                files = [str(tmp_path / "link.txt")] if has_symlink else []
            else:
                files = []
        else:  # All types
            files = [
                str(tmp_path / "file.txt"),
                str(tmp_path / "directory"),
                str(tmp_path / "directory" / "nested.txt"),
            ]
            if has_symlink:
                files.append(str(tmp_path / "link.txt"))

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test files only
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "types": ["f"]}
    )

    assert result1["success"] is True
    assert result1["count"] == 3

    # Test directories only
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "types": ["d"]}
    )

    assert result2["success"] is True
    assert result2["count"] == 1


@pytest.mark.asyncio
async def test_fd_32_type_executable(tmp_path, monkeypatch):
    """Test executable file type - corresponds to fd's test_type_executable."""
    # Create executable and non-executable files
    (tmp_path / "script.sh").write_text("#!/bin/bash\necho hello")
    (tmp_path / "data.txt").write_text("data content")

    # Make script executable (if supported)
    try:
        import os

        os.chmod(str(tmp_path / "script.sh"), 0o755)
        has_executable = True
    except (OSError, AttributeError):
        has_executable = False

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-t" in cmd and "x" in cmd:  # Executable files only
            files = [str(tmp_path / "script.sh")] if has_executable else []
        else:
            files = [str(tmp_path / "script.sh"), str(tmp_path / "data.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test executable files
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "types": ["x"]}
    )

    assert result["success"] is True
    assert result["count"] == 1
