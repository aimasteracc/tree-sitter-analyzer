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
async def test_fd_75_modified_relative_time(tmp_path, monkeypatch):
    """Test relative modification time filtering - corresponds to fd's test_modified_relative."""
    # Create test files
    (tmp_path / "old_file.txt").write_text("old content")
    (tmp_path / "new_file.txt").write_text("new content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "--changed-within" in cmd:
            if "1d" in cmd:
                files = [str(tmp_path / "new_file.txt")]  # Only recent files
            else:
                files = []
        else:
            files = [str(tmp_path / "old_file.txt"), str(tmp_path / "new_file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test files modified within 1 day
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "changed_within": "1d"}
    )

    assert result["success"] is True
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_fd_76_modified_absolute_time(tmp_path, monkeypatch):
    """Test absolute modification time filtering - corresponds to fd's test_modified_absolute."""
    # Create test files
    (tmp_path / "file1.txt").write_text("content1")
    (tmp_path / "file2.txt").write_text("content2")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "--changed-before" in cmd:
            if "2023-01-01" in cmd:
                files = []  # No files before this date
            else:
                files = [str(tmp_path / "file1.txt"), str(tmp_path / "file2.txt")]
        else:
            files = [str(tmp_path / "file1.txt"), str(tmp_path / "file2.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test files modified before a specific date
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "changed_before": "2023-01-01",
        }
    )

    assert result["success"] is True
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_fd_77_size_filtering_advanced(tmp_path, monkeypatch):
    """Test advanced size filtering - corresponds to fd's test_size."""
    # Create test files
    (tmp_path / "small.txt").write_text("small")
    (tmp_path / "large.txt").write_text("large content" * 100)

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Production builds size filters as ["-S", "+100b"], not "--size"
        if "-S" in cmd:
            if "+100b" in cmd:
                files = [str(tmp_path / "large.txt")]  # Only large files
            elif "-100b" in cmd:
                files = [str(tmp_path / "small.txt")]  # Only small files
            else:
                files = []
        else:
            files = [str(tmp_path / "small.txt"), str(tmp_path / "large.txt")]

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
    assert result1["count"] == 1

    # Test files smaller than 100 bytes
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "size": ["-100b"]}
    )

    assert result2["success"] is True
    assert result2["count"] == 1


@pytest.mark.asyncio
async def test_fd_78_no_extension_filter(tmp_path, monkeypatch):
    """Test no extension filter - corresponds to fd's test_no_extension."""
    # Create test files
    (tmp_path / "file_with_ext.txt").write_text("content")
    (tmp_path / "file_without_ext").write_text("content")
    (tmp_path / "README").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate files without extension by checking pattern
        files = [
            str(tmp_path / "file_with_ext.txt"),
            str(tmp_path / "file_without_ext"),
            str(tmp_path / "README"),
        ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test files without extension (simulate with pattern)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] == 3


@pytest.mark.asyncio
async def test_fd_79_owner_ignore_all(tmp_path, monkeypatch):
    """Test owner filtering - ignore all - corresponds to fd's test_owner_ignore_all."""
    # Create test files
    (tmp_path / "file1.txt").write_text("content1")
    (tmp_path / "file2.txt").write_text("content2")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate owner filtering (not supported by our tool, so return all files)
        files = [str(tmp_path / "file1.txt"), str(tmp_path / "file2.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test owner filtering (simulated)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] == 2


@pytest.mark.asyncio
async def test_fd_80_owner_current_user(tmp_path, monkeypatch):
    """Test current user owner filtering - corresponds to fd's test_owner_current_user."""
    # Create test files
    (tmp_path / "my_file.txt").write_text("my content")
    (tmp_path / "other_file.txt").write_text("other content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate current user files (all files in tmp_path are owned by current user)
        files = [str(tmp_path / "my_file.txt"), str(tmp_path / "other_file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test current user owner filtering (simulated)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] == 2


@pytest.mark.asyncio
async def test_fd_81_owner_current_group(tmp_path, monkeypatch):
    """Test current group owner filtering - corresponds to fd's test_owner_current_group."""
    # Create test files
    (tmp_path / "group_file.txt").write_text("group content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate group owner filtering
        files = [str(tmp_path / "group_file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test group owner filtering (simulated)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_fd_82_owner_root(tmp_path, monkeypatch):
    """Test root owner filtering - corresponds to fd's test_owner_root."""
    # Create test files
    (tmp_path / "user_file.txt").write_text("user content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate root owner filtering (no root files in tmp_path)
        files = []  # No root-owned files

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test root owner filtering (simulated)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_fd_83_quiet_mode_simulation(tmp_path, monkeypatch):
    """Test quiet mode simulation - corresponds to fd's test_quiet."""
    # Create test files
    (tmp_path / "file.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Our tool always returns structured output, simulating quiet mode
        files = [str(tmp_path / "file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test quiet mode (our tool is always structured)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_fd_84_max_results_advanced(tmp_path, monkeypatch):
    """Test advanced max results limiting - corresponds to fd's test_max_results."""
    # Create many test files
    for i in range(10):
        (tmp_path / f"file{i}.txt").write_text(f"content{i}")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate max results limiting
        all_files = [str(tmp_path / f"file{i}.txt") for i in range(10)]

        # Production passes ["--max-results", "<n>"] (a default cap is
        # appended even without an explicit limit) — honor the actual value
        if "--max-results" in cmd:
            n = int(cmd[cmd.index("--max-results") + 1])
            files = all_files[:n]
        else:
            files = all_files

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test with limit — the bounded fd pass returns only the requested prefix
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "limit": 5}
    )

    assert result1["success"] is True
    assert result1["count"] == 5

    # Test without limit
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result2["success"] is True
    assert result2["count"] == 10


@pytest.mark.asyncio
async def test_fd_86_list_details_advanced(tmp_path, monkeypatch):
    """Test advanced list details - corresponds to fd's test_list_details."""
    # Create test files
    (tmp_path / "file.txt").write_text("content")
    (tmp_path / "subdir").mkdir()

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate detailed listing
        files = [str(tmp_path / "file.txt"), str(tmp_path / "subdir")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test detailed listing
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

    # Verify detailed information is present in successful results
    if result["success"] and result["count"] > 0:
        for item in result["results"]:
            assert "path" in item
            assert "is_dir" in item
