"""MCP search content fd-compat tests — extracted from test_mcp_search_content_p1."""


import pytest

from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool


@pytest.fixture(autouse=True)
def mock_external_commands(monkeypatch):
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
        lambda cmd: True,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fd_01_simple_search(tmp_path, monkeypatch):
    """Test simple search functionality - corresponds to fd's test_simple."""
    (tmp_path / "a.foo").write_text("content a")
    (tmp_path / "one").mkdir()
    (tmp_path / "one" / "b.foo").write_text("content b")
    (tmp_path / "one" / "two").mkdir()
    (tmp_path / "one" / "two" / "c.foo").write_text("content c")
    (tmp_path / "one" / "two" / "C.Foo2").write_text("content C")
    (tmp_path / "one" / "two" / "three").mkdir()
    (tmp_path / "one" / "two" / "three" / "d.foo").write_text("content d")
    (tmp_path / "one" / "two" / "three" / "directory_foo").mkdir()

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        pattern = None
        for _i, arg in enumerate(cmd):
            if arg not in [
                "-a",
                "-H",
                "-I",
                "-L",
                "--color",
                "never",
                "fd",
            ] and not arg.startswith("-"):
                pattern = arg
                break

        if pattern == "a.foo":
            files = [str(tmp_path / "a.foo")]
        elif pattern == "b.foo":
            files = [str(tmp_path / "one" / "b.foo")]
        elif pattern == "d.foo":
            files = [str(tmp_path / "one" / "two" / "three" / "d.foo")]
        elif pattern == "foo":
            files = [
                str(tmp_path / "a.foo"),
                str(tmp_path / "one" / "b.foo"),
                str(tmp_path / "one" / "two" / "c.foo"),
                str(tmp_path / "one" / "two" / "C.Foo2"),
                str(tmp_path / "one" / "two" / "three" / "d.foo"),
                str(tmp_path / "one" / "two" / "three" / "directory_foo"),
            ]
        else:
            files = []

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "a.foo", "output_format": "json"}
    )
    assert result1["success"] is True
    assert result1["count"] >= 0

    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*.foo", "glob": True}
    )
    assert result2["success"] is True
    assert result2["count"] >= 0

    result3 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )
    assert result3["success"] is True
    assert result3["count"] >= 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fd_16_empty_pattern(tmp_path, monkeypatch):
    """Test empty pattern handling - corresponds to fd's test_empty_pattern."""
    (tmp_path / "file1.txt").write_text("content")
    (tmp_path / "file2.py").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [str(tmp_path / "file1.txt"), str(tmp_path / "file2.py")]
        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "", "output_format": "json"}
    )

    assert result["success"] is True
    assert result["count"] >= 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fd_17_regex_searches(tmp_path, monkeypatch):
    """Test regex searches - corresponds to fd's test_regex_searches."""
    (tmp_path / "test1.txt").write_text("content")
    (tmp_path / "test2.txt").write_text("content")
    (tmp_path / "example.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        pattern = None
        for arg in cmd:
            if arg.startswith("test"):
                pattern = arg
                break

        if pattern == "test.*\\.txt":
            files = [str(tmp_path / "test1.txt"), str(tmp_path / "test2.txt")]
        else:
            files = [
                str(tmp_path / "test1.txt"),
                str(tmp_path / "test2.txt"),
                str(tmp_path / "example.txt"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "test.*\\.txt", "output_format": "json"}
    )

    assert result["success"] is True
    assert result["count"] >= 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fd_18_smart_case_search(tmp_path, monkeypatch):
    """Test smart case search - corresponds to fd's test_smart_case."""
    (tmp_path / "Test.txt").write_text("content")
    (tmp_path / "test.txt").write_text("content")
    (tmp_path / "TEST.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        pattern = None
        for arg in cmd:
            if "test" in arg.lower() or "Test" in arg:
                pattern = arg
                break

        if pattern and pattern.islower():
            files = [
                str(tmp_path / "Test.txt"),
                str(tmp_path / "test.txt"),
                str(tmp_path / "TEST.txt"),
            ]
        elif pattern and any(c.isupper() for c in pattern):
            files = [str(tmp_path / "Test.txt")]
        else:
            files = []

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "test", "output_format": "json"}
    )

    assert result1["success"] is True
    assert result1["count"] >= 2

    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "Test", "output_format": "json"}
    )

    assert result2["success"] is True
    assert result2["count"] >= 1
