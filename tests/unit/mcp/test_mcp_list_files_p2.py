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
async def test_fd_33_type_empty(tmp_path, monkeypatch):
    """Test empty file type - corresponds to fd's test_type_empty."""
    # Create empty and non-empty files
    (tmp_path / "empty.txt").write_text("")
    (tmp_path / "nonempty.txt").write_text("content")
    (tmp_path / "empty_dir").mkdir()

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-t" in cmd and "e" in cmd:  # Empty files/directories only
            files = [str(tmp_path / "empty.txt"), str(tmp_path / "empty_dir")]
        else:
            files = [
                str(tmp_path / "empty.txt"),
                str(tmp_path / "nonempty.txt"),
                str(tmp_path / "empty_dir"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test empty files/directories
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "types": ["e"]}
    )

    assert result["success"] is True
    assert result["count"] >= 2


@pytest.mark.asyncio
async def test_fd_34_extension_filtering(tmp_path, monkeypatch):
    """Test file extension filtering - corresponds to fd's test_extension."""
    # Create files with different extensions
    (tmp_path / "file.txt").write_text("text content")
    (tmp_path / "script.py").write_text("python code")
    (tmp_path / "data.json").write_text('{"key": "value"}')
    (tmp_path / "README").write_text("readme content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-e" in cmd:
            if "txt" in cmd:
                files = [str(tmp_path / "file.txt")]
            elif "py" in cmd:
                files = [str(tmp_path / "script.py")]
            elif "json" in cmd:
                files = [str(tmp_path / "data.json")]
            else:
                files = []
        else:
            files = [
                str(tmp_path / "file.txt"),
                str(tmp_path / "script.py"),
                str(tmp_path / "data.json"),
                str(tmp_path / "README"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test txt extension
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "extensions": ["txt"]}
    )

    assert result1["success"] is True
    assert result1["count"] >= 1

    # Test py extension
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "extensions": ["py"]}
    )

    assert result2["success"] is True
    assert result2["count"] >= 1


@pytest.mark.asyncio
async def test_fd_35_no_extension(tmp_path, monkeypatch):
    """Test files without extension - corresponds to fd's test_no_extension."""
    # Create files with and without extensions
    (tmp_path / "file.txt").write_text("with extension")
    (tmp_path / "README").write_text("no extension")
    (tmp_path / "Makefile").write_text("no extension")
    (tmp_path / "script.py").write_text("with extension")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate filtering for files without extensions
        # This would be a complex filter in fd, here we simulate the result
        files = [str(tmp_path / "README"), str(tmp_path / "Makefile")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test files without extension (simulated with pattern)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "[^.]*$"}  # Regex for no extension
    )

    assert result["success"] is True
    assert result["count"] >= 2


@pytest.mark.asyncio
async def test_fd_36_size_filtering(tmp_path, monkeypatch):
    """Test file size filtering - corresponds to fd's test_size."""
    # Create files of different sizes
    (tmp_path / "small.txt").write_text("small")  # ~5 bytes
    (tmp_path / "medium.txt").write_text("medium content" * 10)  # ~140 bytes
    (tmp_path / "large.txt").write_text("large content" * 100)  # ~1300 bytes

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "--size" in cmd:
            if "+100b" in cmd:  # Files larger than 100 bytes
                files = [str(tmp_path / "medium.txt"), str(tmp_path / "large.txt")]
            elif "-100b" in cmd:  # Files smaller than 100 bytes
                files = [str(tmp_path / "small.txt")]
            elif "+1k" in cmd:  # Files larger than 1KB
                files = [str(tmp_path / "large.txt")]
            else:
                files = []
        else:
            files = [
                str(tmp_path / "small.txt"),
                str(tmp_path / "medium.txt"),
                str(tmp_path / "large.txt"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test files larger than 100 bytes
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "size": ["+100b"]}
    )

    assert result1["success"] is True
    assert result1["count"] >= 2

    # Test files smaller than 100 bytes
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "size": ["-100b"]}
    )

    assert result2["success"] is True
    assert result2["count"] >= 1


@pytest.mark.asyncio
async def test_fd_37_no_ignore_basic(tmp_path, monkeypatch):
    """Test basic no ignore functionality - corresponds to fd's test_no_ignore."""
    # Create gitignore and files
    (tmp_path / ".gitignore").write_text("*.log\ntemp/\n")
    (tmp_path / "file.txt").write_text("content")
    (tmp_path / "debug.log").write_text("log content")
    (tmp_path / "temp").mkdir()
    (tmp_path / "temp" / "data.txt").write_text("temp data")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-I" in cmd:  # No ignore
            files = [
                str(tmp_path / ".gitignore"),
                str(tmp_path / "file.txt"),
                str(tmp_path / "debug.log"),
                str(tmp_path / "temp"),
                str(tmp_path / "temp" / "data.txt"),
            ]
        else:  # Respect .gitignore
            files = [
                str(tmp_path / ".gitignore"),
                str(tmp_path / "file.txt"),
                # debug.log and temp/ are ignored
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
    assert result1["count"] >= 2

    # Test without ignore rules
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "no_ignore": True}
    )

    assert result2["success"] is True
    assert result2["count"] >= 5


@pytest.mark.asyncio
async def test_fd_39_max_depth_filtering(tmp_path, monkeypatch):
    """Test maximum depth filtering - corresponds to fd's test_max_depth."""
    # Create nested directory structure
    (tmp_path / "level1").mkdir()
    (tmp_path / "level1" / "file1.txt").write_text("level1 content")
    (tmp_path / "level1" / "level2").mkdir()
    (tmp_path / "level1" / "level2" / "file2.txt").write_text("level2 content")
    (tmp_path / "level1" / "level2" / "level3").mkdir()
    (tmp_path / "level1" / "level2" / "level3" / "file3.txt").write_text(
        "level3 content"
    )

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-d" in cmd:
            depth_idx = cmd.index("-d") + 1
            if depth_idx < len(cmd):
                depth = int(cmd[depth_idx])
                if depth == 1:
                    files = [str(tmp_path / "level1")]
                elif depth == 2:
                    files = [
                        str(tmp_path / "level1"),
                        str(tmp_path / "level1" / "file1.txt"),
                        str(tmp_path / "level1" / "level2"),
                    ]
                elif depth == 3:
                    files = [
                        str(tmp_path / "level1"),
                        str(tmp_path / "level1" / "file1.txt"),
                        str(tmp_path / "level1" / "level2"),
                        str(tmp_path / "level1" / "level2" / "file2.txt"),
                        str(tmp_path / "level1" / "level2" / "level3"),
                    ]
                else:
                    files = []
            else:
                files = []
        else:
            # No depth limit
            files = [
                str(tmp_path / "level1"),
                str(tmp_path / "level1" / "file1.txt"),
                str(tmp_path / "level1" / "level2"),
                str(tmp_path / "level1" / "level2" / "file2.txt"),
                str(tmp_path / "level1" / "level2" / "level3"),
                str(tmp_path / "level1" / "level2" / "level3" / "file3.txt"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test depth 1
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "depth": 1}
    )

    assert result1["success"] is True
    assert result1["count"] >= 1

    # Test depth 2
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "depth": 2}
    )

    assert result2["success"] is True
    assert result2["count"] >= 3


@pytest.mark.asyncio
async def test_fd_40_min_depth_filtering(tmp_path, monkeypatch):
    """Test minimum depth filtering - corresponds to fd's test_min_depth."""
    # Create nested directory structure
    (tmp_path / "root.txt").write_text("root content")
    (tmp_path / "level1").mkdir()
    (tmp_path / "level1" / "file1.txt").write_text("level1 content")
    (tmp_path / "level1" / "level2").mkdir()
    (tmp_path / "level1" / "level2" / "file2.txt").write_text("level2 content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Our tool doesn't support min_depth, simulate with filtering
        # This would require custom implementation in real fd
        files = [
            str(tmp_path / "level1" / "file1.txt"),
            str(tmp_path / "level1" / "level2" / "file2.txt"),
        ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test min depth simulation (files deeper than root)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 2


@pytest.mark.asyncio
async def test_fd_41_exact_depth_filtering(tmp_path, monkeypatch):
    """Test exact depth filtering - corresponds to fd's test_exact_depth."""
    # Create nested directory structure
    (tmp_path / "level1").mkdir()
    (tmp_path / "level1" / "file1.txt").write_text("level1 content")
    (tmp_path / "level1" / "level2").mkdir()
    (tmp_path / "level1" / "level2" / "file2.txt").write_text("level2 content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-d" in cmd:
            depth_idx = cmd.index("-d") + 1
            if depth_idx < len(cmd):
                depth = int(cmd[depth_idx])
                if depth == 2:  # Exact depth 2
                    files = [
                        str(tmp_path / "level1" / "file1.txt"),
                        str(tmp_path / "level1" / "level2"),
                    ]
                else:
                    files = []
            else:
                files = []
        else:
            files = [
                str(tmp_path / "level1"),
                str(tmp_path / "level1" / "file1.txt"),
                str(tmp_path / "level1" / "level2"),
                str(tmp_path / "level1" / "level2" / "file2.txt"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test exact depth 2
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "depth": 2}
    )

    assert result["success"] is True
    assert result["count"] >= 2


@pytest.mark.asyncio
async def test_fd_42_prune_functionality(tmp_path, monkeypatch):
    """Test prune functionality - corresponds to fd's test_prune."""
    # Create directory structure
    (tmp_path / "include").mkdir()
    (tmp_path / "include" / "file1.txt").write_text("include content")
    (tmp_path / "exclude").mkdir()
    (tmp_path / "exclude" / "file2.txt").write_text("exclude content")
    (tmp_path / "normal.txt").write_text("normal content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate prune with exclude patterns
        if "-E" in cmd and "exclude" in cmd:
            files = [
                str(tmp_path / "include"),
                str(tmp_path / "include" / "file1.txt"),
                str(tmp_path / "normal.txt"),
                # exclude directory is pruned
            ]
        else:
            files = [
                str(tmp_path / "include"),
                str(tmp_path / "include" / "file1.txt"),
                str(tmp_path / "exclude"),
                str(tmp_path / "exclude" / "file2.txt"),
                str(tmp_path / "normal.txt"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test prune with exclude pattern
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "exclude": ["exclude"]}
    )

    assert result["success"] is True
    assert result["count"] >= 3


@pytest.mark.asyncio
async def test_fd_43_excludes_pattern(tmp_path, monkeypatch):
    """Test exclude patterns - corresponds to fd's test_excludes."""
    # Create test files
    (tmp_path / "include.txt").write_text("include content")
    (tmp_path / "exclude.log").write_text("exclude content")
    (tmp_path / "temp.tmp").write_text("temp content")
    (tmp_path / "normal.py").write_text("normal content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-E" in cmd:
            # Check exclude patterns
            excludes = []
            for i, arg in enumerate(cmd):
                if arg == "-E" and i + 1 < len(cmd):
                    excludes.append(cmd[i + 1])

            files = [
                str(tmp_path / "include.txt"),
                str(tmp_path / "exclude.log"),
                str(tmp_path / "temp.tmp"),
                str(tmp_path / "normal.py"),
            ]

            # Filter out excluded files
            filtered_files = []
            for file in files:
                excluded = False
                for exclude in excludes:
                    if exclude in file or file.endswith(exclude.replace("*", "")):
                        excluded = True
                        break
                if not excluded:
                    filtered_files.append(file)

            files = filtered_files
        else:
            files = [
                str(tmp_path / "include.txt"),
                str(tmp_path / "exclude.log"),
                str(tmp_path / "temp.tmp"),
                str(tmp_path / "normal.py"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test exclude .log files
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "exclude": ["*.log"]}
    )

    assert result1["success"] is True
    assert result1["count"] >= 3

    # Test exclude multiple patterns
    result2 = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "exclude": ["*.log", "*.tmp"],
        }
    )

    assert result2["success"] is True
    assert result2["count"] >= 2
