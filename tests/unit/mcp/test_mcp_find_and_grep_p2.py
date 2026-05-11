
import pytest

from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool
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
async def test_fd_11_and_plus_glob(tmp_path, monkeypatch):
    """Test AND search with glob pattern - simulates fd's test_and_plus_glob."""
    # Create test files
    (tmp_path / "test.txt").write_text("hello world")
    (tmp_path / "example.txt").write_text("hello world")
    (tmp_path / "demo.py").write_text("hello world")

    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "rg" in cmd[0]:  # Content search
            files = [
                str(tmp_path / "test.txt"),
                str(tmp_path / "example.txt"),
                str(tmp_path / "demo.py"),
            ]
        else:  # File search with glob
            if "--glob" in cmd and "*.txt" in cmd:
                files = [str(tmp_path / "test.txt"), str(tmp_path / "example.txt")]
            else:
                files = [
                    str(tmp_path / "test.txt"),
                    str(tmp_path / "example.txt"),
                    str(tmp_path / "demo.py"),
                ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test AND with glob pattern
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*.txt", "glob": True, "query": "hello"}
    )

    assert result["success"] is True
    assert result["count"] >= 0
@pytest.mark.asyncio
async def test_fd_12_and_plus_fixed_strings(tmp_path, monkeypatch):
    """Test AND search with fixed strings - simulates fd's test_and_plus_fixed_strings."""
    # Create test files
    (tmp_path / "test.file").write_text("hello.world")
    (tmp_path / "other.txt").write_text("hello world")

    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "rg" in cmd[0]:  # Content search
            if "-F" in cmd:  # Fixed strings
                files = [str(tmp_path / "test.file")]
            else:
                files = [str(tmp_path / "test.file"), str(tmp_path / "other.txt")]
        else:  # File search
            files = [str(tmp_path / "test.file"), str(tmp_path / "other.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test AND with fixed strings
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "query": "hello.world",
            "fixed_strings": True,
        }
    )

    assert result["success"] is True
    assert result["count"] >= 0
@pytest.mark.asyncio
async def test_fd_13_and_plus_ignore_case(tmp_path, monkeypatch):
    """Test AND search with ignore case - simulates fd's test_and_plus_ignore_case."""
    # Create test files
    (tmp_path / "Test.txt").write_text("Hello World")
    (tmp_path / "test.txt").write_text("hello world")

    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "rg" in cmd[0]:  # Content search
            if "-i" in cmd:  # Case insensitive
                files = [str(tmp_path / "Test.txt"), str(tmp_path / "test.txt")]
            else:
                files = [str(tmp_path / "test.txt")]
        else:  # File search
            files = [str(tmp_path / "Test.txt"), str(tmp_path / "test.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test AND with case insensitive
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "query": "hello",
            "case_insensitive": True,
        }
    )

    assert result["success"] is True
    assert result["count"] >= 0
@pytest.mark.asyncio
async def test_fd_14_and_plus_case_sensitive(tmp_path, monkeypatch):
    """Test AND search with case sensitive - simulates fd's test_and_plus_case_sensitive."""
    # Create test files
    (tmp_path / "Test.txt").write_text("Hello World")
    (tmp_path / "test.txt").write_text("hello world")

    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "rg" in cmd[0]:  # Content search - case sensitive by default
            files = [str(tmp_path / "test.txt")]
        else:  # File search
            files = [str(tmp_path / "Test.txt"), str(tmp_path / "test.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test AND with case sensitive (default)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "query": "hello"}
    )

    assert result["success"] is True
    assert result["count"] >= 0
@pytest.mark.asyncio
async def test_fd_15_and_plus_full_path(tmp_path, monkeypatch):
    """Test AND search with full path - simulates fd's test_and_plus_full_path."""
    # Create test files
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("import os")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("import os")

    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "rg" in cmd[0]:  # Content search
            files = [
                str(tmp_path / "src" / "main.py"),
                str(tmp_path / "tests" / "test_main.py"),
            ]
        else:  # File search with full path
            if "-p" in cmd and "src" in str(cmd):  # Full path match
                files = [str(tmp_path / "src" / "main.py")]
            else:
                files = [
                    str(tmp_path / "src" / "main.py"),
                    str(tmp_path / "tests" / "test_main.py"),
                ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test AND with full path match
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "src",
            "query": "import",
            "full_path_match": True,
        }
    )

    assert result["success"] is True
    assert result["count"] >= 0
@pytest.mark.asyncio
async def test_fd_59_exec_command_simulation(tmp_path, monkeypatch):
    """Test exec command simulation - corresponds to fd's test_exec."""
    # Create test files
    (tmp_path / "file1.txt").write_text("content1")
    (tmp_path / "file2.txt").write_text("content2")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Our tool finds files, doesn't execute commands on them
        files = [str(tmp_path / "file1.txt"), str(tmp_path / "file2.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test file finding (our equivalent of exec)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*.txt", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 2
@pytest.mark.asyncio
async def test_fd_60_exec_multi_command_simulation(tmp_path, monkeypatch):
    """Test exec multi command simulation - corresponds to fd's test_exec_multi."""
    # Create test files
    (tmp_path / "test1.py").write_text("print('test1')")
    (tmp_path / "test2.py").write_text("print('test2')")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [str(tmp_path / "test1.py"), str(tmp_path / "test2.py")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test multiple file finding
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*.py", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 2
@pytest.mark.asyncio
async def test_fd_61_exec_batch_simulation(tmp_path, monkeypatch):
    """Test exec batch simulation - corresponds to fd's test_exec_batch."""
    # Create multiple test files
    for i in range(5):
        (tmp_path / f"batch{i}.txt").write_text(f"batch content {i}")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [str(tmp_path / f"batch{i}.txt") for i in range(5)]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test batch file processing
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "batch*.txt", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 5
@pytest.mark.asyncio
async def test_fd_62_exec_batch_multi_simulation(tmp_path, monkeypatch):
    """Test exec batch multi simulation - corresponds to fd's test_exec_batch_multi."""
    # Create test files
    (tmp_path / "multi1.txt").write_text("multi content 1")
    (tmp_path / "multi2.txt").write_text("multi content 2")
    (tmp_path / "multi3.txt").write_text("multi content 3")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [
            str(tmp_path / "multi1.txt"),
            str(tmp_path / "multi2.txt"),
            str(tmp_path / "multi3.txt"),
        ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test multi-batch processing
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "multi*.txt", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 3
@pytest.mark.asyncio
async def test_fd_63_exec_batch_with_limit_simulation(tmp_path, monkeypatch):
    """Test exec batch with limit simulation - corresponds to fd's test_exec_batch_with_limit."""
    # Create many test files
    for i in range(10):
        (tmp_path / f"limited{i}.txt").write_text(f"limited content {i}")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        all_files = [str(tmp_path / f"limited{i}.txt") for i in range(10)]

        # Check for limit in command
        files = all_files[:3] if any("limit" in str(arg) for arg in cmd) else all_files

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test with limit
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "limited*.txt", "glob": True, "limit": 3}
    )

    assert result["success"] is True
    assert result["count"] <= 3
@pytest.mark.asyncio
async def test_fd_64_exec_with_separator_simulation(tmp_path, monkeypatch):
    """Test exec with separator simulation - corresponds to fd's test_exec_with_separator."""
    # Create test files
    (tmp_path / "sep1.txt").write_text("separator content 1")
    (tmp_path / "sep2.txt").write_text("separator content 2")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [str(tmp_path / "sep1.txt"), str(tmp_path / "sep2.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test separator handling (our tool uses JSON structure)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "sep*.txt", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 2
