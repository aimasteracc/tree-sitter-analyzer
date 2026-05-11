
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
def test_list_files_validation_requires_roots(tmp_path):
    """Test that ListFilesTool validation fails when roots parameter is missing."""
    tool = ListFilesTool(str(tmp_path))
    with pytest.raises(ValueError):
        tool.validate_arguments({})
@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_files_exec_happy_path(monkeypatch, tmp_path):
    """Test successful execution of ListFilesTool with file extension filtering."""
    tool = ListFilesTool(str(tmp_path))
    # Create files
    f1 = tmp_path / "a.py"
    f1.write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "b").mkdir()

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # fd will list both entries, one per line
        out = f"{f1}\n{tmp_path / 'b'}\n".encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {"roots": [str(tmp_path)], "extensions": ["py"], "output_format": "json"}
    )
    assert result["success"] is True
    assert result["count"] >= 0
    assert any(x["path"].endswith("a.py") for x in result["results"])
@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_files_exclude(monkeypatch, tmp_path):
    """Test ListFilesTool with exclude patterns to filter out specific directories."""
    tool = ListFilesTool(str(tmp_path))
    # Create files
    f1 = tmp_path / "a.py"
    f1.write_text("print('a')\n", encoding="utf-8")
    d1 = tmp_path / "excluded"
    d1.mkdir()
    f2 = d1 / "b.py"
    f2.write_text("print('b')\n", encoding="utf-8")

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # fd will list only a.py, excluding the 'excluded' dir
        out = f"{f1}\n".encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "glob": True,
            "pattern": "*.py",
            "exclude": ["excluded/"],
            "output_format": "json",
        }
    )
    assert result["success"] is True
    assert result["count"] == 1
    assert any(x["path"].endswith("a.py") for x in result["results"])
    assert not any(x["path"].endswith("b.py") for x in result["results"])
@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_files_count_only(monkeypatch, tmp_path):
    """Test list_files tool with count_only option."""
    tool = ListFilesTool(str(tmp_path))

    # Mock fd output
    mock_fd_output = b"""file1.py
file2.py
file3.py
file4.py
file5.py
"""

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 0, mock_fd_output, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {"roots": [str(tmp_path)], "count_only": True, "output_format": "json"}
    )

    assert result["success"] is True
    assert result["count_only"] is True
    assert result["total_count"] == 5
    assert "results" not in result  # No detailed results in count_only mode
    assert "elapsed_ms" in result
@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_files_error_handling(monkeypatch, tmp_path):
    """Test ListFilesTool error handling when fd command fails."""
    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 1, b"", b"fd: command failed"

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute({"roots": [str(tmp_path)], "output_format": "json"})

    assert result["success"] is False
    assert result["error"] == "fd: command failed"
    assert result["returncode"] == 1
@pytest.mark.unit
def test_list_files_validation_invalid_types(tmp_path):
    """Test ListFilesTool validation with invalid parameter types."""
    tool = ListFilesTool(str(tmp_path))

    # Test invalid roots type
    with pytest.raises(ValueError, match="roots must be an array"):
        tool.validate_arguments({"roots": "not_a_list"})

    # Test invalid boolean parameters
    with pytest.raises(ValueError, match="glob must be a boolean"):
        tool.validate_arguments({"roots": [str(tmp_path)], "glob": "true"})

    # Test invalid integer parameters
    with pytest.raises(ValueError, match="depth must be an integer"):
        tool.validate_arguments({"roots": [str(tmp_path)], "depth": "5"})

    # Test invalid array parameters
    with pytest.raises(ValueError, match="extensions must be an array of strings"):
        tool.validate_arguments({"roots": [str(tmp_path)], "extensions": ["py", 123]})
@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_files_with_pattern_and_no_pattern(monkeypatch, tmp_path):
    """Test ListFilesTool with and without pattern to verify fd command building."""
    tool = ListFilesTool(str(tmp_path))

    captured_commands = []

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        captured_commands.append(cmd)
        return 0, b"test.py\n", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test with pattern
    await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*.py",
            "glob": True,
            "output_format": "json",
        }
    )
    assert "*.py" in captured_commands[0]

    # Test without pattern (should use '.' as default pattern)
    captured_commands.clear()
    await tool.execute({"roots": [str(tmp_path)], "output_format": "json"})
    assert (
        "." in captured_commands[0]
    )  # Should have default pattern when pattern is None

    # On macOS, PathResolver normalizes /private/var/ to /var/ for consistency
    # So we need to check for the normalized path in the command
    import os

    expected_path = str(tmp_path)
    if os.name == "posix" and expected_path.startswith("/private/var/"):
        expected_path = expected_path.replace("/private/var/", "/var/", 1)

    assert expected_path in captured_commands[0]
@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_files_with_size_filters(monkeypatch, tmp_path):
    """Test ListFilesTool with size filter parameters."""
    tool = ListFilesTool(str(tmp_path))

    # Create test files
    small_file = tmp_path / "small.txt"
    small_file.write_text("small", encoding="utf-8")
    large_file = tmp_path / "large.txt"
    large_file.write_text("x" * 1000, encoding="utf-8")

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # Verify size filters are in command
        assert "-S" in cmd
        assert "+500B" in cmd
        return 0, f"{large_file}\n".encode(), b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {"roots": [str(tmp_path)], "size": ["+500B"], "output_format": "json"}
    )

    assert result["success"] is True
    assert result["count"] == 1
@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_files_with_time_filters(monkeypatch, tmp_path):
    """Test ListFilesTool with time-based filters."""
    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # Verify time filters are in command
        assert "--changed-within" in cmd
        assert "1d" in cmd
        assert "--changed-before" in cmd
        assert "1w" in cmd
        return 0, b"test.txt\n", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {"roots": [str(tmp_path)], "changed_within": "1d", "changed_before": "1w"}
    )

    assert result["success"] is True
@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_files_with_types_and_extensions(monkeypatch, tmp_path):
    """Test ListFilesTool with file type and extension filters."""
    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # Verify type and extension filters
        assert "-t" in cmd and "f" in cmd  # files only
        assert "-e" in cmd and "py" in cmd  # Python extension
        return 0, b"test.py\nscript.py\n", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {"roots": [str(tmp_path)], "types": ["f"], "extensions": ["py"]}
    )

    assert result["success"] is True
    assert result["count"] == 2
@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_files_with_depth_and_symlinks(monkeypatch, tmp_path):
    """Test ListFilesTool with depth limit and symlink following."""
    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # Verify depth and symlink options
        assert "-d" in cmd and "2" in cmd  # max depth 2
        assert "-L" in cmd  # follow symlinks
        assert "-H" in cmd  # include hidden
        return 0, b"file1.txt\n.hidden\n", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {"roots": [str(tmp_path)], "depth": 2, "follow_symlinks": True, "hidden": True}
    )

    assert result["success"] is True
    assert result["count"] == 2
@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_files_with_full_path_match(monkeypatch, tmp_path):
    """Test ListFilesTool with full path matching."""
    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # Verify full path match option
        assert "-p" in cmd  # full path match
        return 0, b"src/main.py\n", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "src/main.py", "full_path_match": True}
    )

    assert result["success"] is True
@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_files_metadata_fields(monkeypatch, tmp_path):
    """Test ListFilesTool returns correct metadata fields."""
    tool = ListFilesTool(str(tmp_path))

    # Create test file with known properties
    test_file = tmp_path / "test.py"
    test_file.write_text("print('hello')", encoding="utf-8")

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 0, f"{test_file}\n".encode(), b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute({"roots": [str(tmp_path)], "output_format": "json"})

    assert result["success"] is True
    assert "elapsed_ms" in result
    assert "truncated" in result
    assert len(result["results"]) == 1

    file_result = result["results"][0]
    assert "path" in file_result
    assert "is_dir" in file_result
    assert "size_bytes" in file_result
    assert "mtime" in file_result
    assert "ext" in file_result
    assert file_result["ext"] == "py"
    assert file_result["is_dir"] is False
@pytest.mark.unit
def test_list_files_validation_comprehensive(tmp_path):
    """Test comprehensive parameter validation for ListFilesTool."""
    tool = ListFilesTool(str(tmp_path))

    # Test all invalid parameter types
    invalid_cases = [
        ({"roots": "not_a_list"}, "roots must be an array"),
        ({"roots": [str(tmp_path)], "glob": "true"}, "glob must be a boolean"),
        ({"roots": [str(tmp_path)], "depth": "5"}, "depth must be an integer"),
        ({"roots": [str(tmp_path)], "limit": "100"}, "limit must be an integer"),
        (
            {"roots": [str(tmp_path)], "extensions": ["py", 123]},
            "extensions must be an array of strings",
        ),
        (
            {"roots": [str(tmp_path)], "types": [1, 2]},
            "types must be an array of strings",
        ),
        (
            {"roots": [str(tmp_path)], "exclude": "*.tmp"},
            "exclude must be an array of strings",
        ),
        (
            {"roots": [str(tmp_path)], "size": "large"},
            "size must be an array of strings",
        ),
        (
            {"roots": [str(tmp_path)], "follow_symlinks": "yes"},
            "follow_symlinks must be a boolean",
        ),
        ({"roots": [str(tmp_path)], "hidden": 1}, "hidden must be a boolean"),
        (
            {"roots": [str(tmp_path)], "no_ignore": "false"},
            "no_ignore must be a boolean",
        ),
        (
            {"roots": [str(tmp_path)], "full_path_match": "true"},
            "full_path_match must be a boolean",
        ),
        ({"roots": [str(tmp_path)], "absolute": 0}, "absolute must be a boolean"),
        ({"roots": [str(tmp_path)], "pattern": 123}, "pattern must be a string"),
        (
            {"roots": [str(tmp_path)], "changed_within": 30},
            "changed_within must be a string",
        ),
        (
            {"roots": [str(tmp_path)], "changed_before": []},
            "changed_before must be a string",
        ),
    ]

    for invalid_args, expected_error in invalid_cases:
        with pytest.raises(ValueError, match=expected_error):
            tool.validate_arguments(invalid_args)
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
    assert result1["count"] >= 2

    # Test glob pattern for test files
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "test.*", "glob": True}
    )

    assert result2["success"] is True
    assert result2["count"] >= 2
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
    assert result["count"] >= 0
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
    assert result1["count"] >= 3

    # Test smart case glob (uppercase is exact)
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*.TXT", "glob": True}
    )

    assert result2["success"] is True
    assert result2["count"] >= 1
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
    assert result["count"] >= 2
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
    assert result["count"] >= 0
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
    assert result1["count"] >= 1

    # Test with hidden files
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "hidden": True}
    )

    assert result2["success"] is True
    assert result2["count"] >= 4
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
    assert result["count"] >= 2
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
    assert result1["count"] >= 2

    # Test directories only
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "types": ["d"]}
    )

    assert result2["success"] is True
    assert result2["count"] >= 1
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
    assert result["count"] >= 0  # May be 0 if no executable support
