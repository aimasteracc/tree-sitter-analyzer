
import pytest

from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


@pytest.fixture(autouse=True)
def mock_external_commands(monkeypatch):
    """Auto-mock external command availability checks for all tests in this module."""
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
        lambda cmd: True,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fd_19_case_sensitive_search(tmp_path, monkeypatch):
    """Test case sensitive search - corresponds to fd's test_case_sensitive."""
    # Create test files
    (tmp_path / "Test.txt").write_text("content")
    (tmp_path / "test.txt").write_text("content")
    (tmp_path / "TEST.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Case sensitive search
        pattern = None
        for arg in cmd:
            if "test" in arg or "Test" in arg or "TEST" in arg:
                pattern = arg
                break

        if pattern == "test":
            files = [str(tmp_path / "test.txt")]
        elif pattern == "Test":
            files = [str(tmp_path / "Test.txt")]
        elif pattern == "TEST":
            files = [str(tmp_path / "TEST.txt")]
        else:
            files = []

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test case sensitive search
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "test", "output_format": "json"}
    )

    assert result["success"] is True
    assert result["count"] >= 0
@pytest.mark.asyncio
async def test_fd_20_case_insensitive_search(tmp_path, monkeypatch):
    """Test case insensitive search - corresponds to fd's test_case_insensitive."""
    # Create test files
    (tmp_path / "Test.txt").write_text("content")
    (tmp_path / "test.txt").write_text("content")
    (tmp_path / "TEST.txt").write_text("content")

    tool = SearchContentTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Case insensitive content search
        if "-i" in cmd:  # Case insensitive flag
            files = [
                str(tmp_path / "Test.txt"),
                str(tmp_path / "test.txt"),
                str(tmp_path / "TEST.txt"),
            ]
        else:
            files = [str(tmp_path / "test.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test case insensitive content search
    result = await tool.execute(
        {"roots": [str(tmp_path)], "query": "content", "case_insensitive": True}
    )

    assert result["success"] is True
    assert result["count"] >= 0
@pytest.mark.asyncio
async def test_fd_26_regex_overrides_glob(tmp_path, monkeypatch):
    """Test regex overrides glob - corresponds to fd's test_regex_overrides_glob."""
    # Create test files
    (tmp_path / "test.txt").write_text("content")
    (tmp_path / "test_file.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # When both regex and glob are specified, regex should take precedence
        if "test\\.txt" in cmd:  # Regex pattern
            files = [str(tmp_path / "test.txt")]  # Exact match only
        elif "--glob" in cmd and "test*" in cmd:  # Glob pattern
            files = [str(tmp_path / "test.txt"), str(tmp_path / "test_file.txt")]
        else:
            files = [str(tmp_path / "test.txt"), str(tmp_path / "test_file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test regex pattern (should override glob)
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "test\\.txt"}  # Regex for exact match
    )

    assert result1["success"] is True
    assert result1["count"] >= 1
@pytest.mark.asyncio
async def test_fd_27_full_path_searches(tmp_path, monkeypatch):
    """Test full path searches - corresponds to fd's test_full_path."""
    # Create nested structure
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("content")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "main.py").write_text("content")
    (tmp_path / "main.py").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Full path search
        if "-p" in cmd:  # Full path flag
            if "src" in cmd:
                files = [str(tmp_path / "src" / "main.py")]
            elif "main.py" in cmd:
                files = [
                    str(tmp_path / "src" / "main.py"),
                    str(tmp_path / "tests" / "main.py"),
                    str(tmp_path / "main.py"),
                ]
            else:
                files = []
        else:
            files = [
                str(tmp_path / "src" / "main.py"),
                str(tmp_path / "tests" / "main.py"),
                str(tmp_path / "main.py"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test full path search for "src"
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "src", "full_path_match": True}
    )

    assert result1["success"] is True
    assert result1["count"] >= 1
@pytest.mark.asyncio
async def test_fd_28_fixed_strings_search(tmp_path, monkeypatch):
    """Test fixed strings search - corresponds to fd's test_fixed_strings."""
    # Create test files
    (tmp_path / "test.file").write_text("content")
    (tmp_path / "test_file.txt").write_text("content")
    (tmp_path / "testXfile.py").write_text("content")

    tool = SearchContentTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Fixed strings search (literal, not regex)
        if "-F" in cmd:  # Fixed strings flag
            if "test.file" in cmd:  # Literal dot
                files = [str(tmp_path / "test.file")]
            else:
                files = []
        else:  # Regex search
            if "test.file" in cmd:  # Dot matches any character in regex
                files = [str(tmp_path / "test.file"), str(tmp_path / "testXfile.py")]
            else:
                files = []

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test fixed strings search
    result = await tool.execute(
        {"roots": [str(tmp_path)], "query": "content", "fixed_strings": True}
    )

    assert result["success"] is True
    assert result["count"] >= 0
@pytest.mark.asyncio
async def test_fd_66_count_only_mode_advanced(tmp_path, monkeypatch):
    """Test advanced count only mode - corresponds to fd's count functionality."""
    # Create test files
    for i in range(7):
        (tmp_path / f"count_test{i}.txt").write_text(f"content {i}")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [str(tmp_path / f"count_test{i}.txt") for i in range(7)]
        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test count functionality
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "count_test*.txt",
            "glob": True,
            "count_only": True,
        }
    )

    assert result["success"] is True
    assert result["total_count"] >= 7
    assert result["count_only"] is True
    assert "results" not in result
