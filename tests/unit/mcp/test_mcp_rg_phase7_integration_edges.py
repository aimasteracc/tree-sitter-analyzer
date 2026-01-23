import json

import pytest

from tree_sitter_analyzer.mcp.tools.fd_rg import FdCommandBuilder, FdCommandConfig
from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


@pytest.fixture(autouse=True)
def mock_external_commands(monkeypatch):
    """Auto-mock external command availability checks for all tests in this module."""
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg.utils.check_external_command",
        lambda cmd: True,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_81_find_and_grep_hidden_and_globs(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))
    f = tmp_path / ".hidden" / "a.py"
    f.parent.mkdir(exist_ok=True)
    f.write_text("todo\n", encoding="utf-8")

    evt = (
        json.dumps(
            {
                "type": "match",
                "data": {
                    "path": {"text": str(f)},
                    "lines": {"text": "todo\n"},
                    "line_number": 1,
                    "submatches": [],
                },
            }
        ).encode()
        + b"\n"
    )

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd[0] == "fd":
            assert "-H" in cmd
            return 0, f"{f}\n".encode(), b""
        return 0, evt, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*.py",
            "glob": True,
            "hidden": True,
            "query": "todo",
        }
    )
    assert res["success"] is True and res["count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_82_find_and_grep_mtime_sort(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))
    f1 = tmp_path / "old.txt"
    f2 = tmp_path / "new.txt"
    f1.write_text("x\n", encoding="utf-8")
    f2.write_text("x\n", encoding="utf-8")

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd[0] == "fd":
            return 0, f"{f1}\n{f2}\n".encode(), b""
        return 1, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute({"roots": [str(tmp_path)], "query": "x", "sort": "mtime"})
    assert res["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_83_find_and_grep_fd_elapsed_and_rg_elapsed(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd[0] == "fd":
            return 0, b"/a.txt\n", b""
        return 0, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute({"roots": [str(tmp_path)], "query": "x"})
    assert res["success"] is True
    assert "fd_elapsed_ms" in res["meta"] and "rg_elapsed_ms" in res["meta"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_84_search_content_no_ignore_autodetect_flag(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # May or may not include -u; just ensure it doesn't crash
        return 0, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute({"roots": [str(tmp_path)], "query": "x"})
    assert res["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_85_find_and_grep_encoding_passthrough(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd[0] == "fd":
            return 0, b"/a.txt\n", b""
        assert "--encoding" in cmd
        return 0, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "x", "encoding": "utf-8"}
    )
    assert res["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_86_find_and_grep_context_passthrough(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd[0] == "fd":
            return 0, b"/a.txt\n", b""
        assert "-B" in cmd and "-A" in cmd
        return 0, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "query": "x",
            "context_before": 1,
            "context_after": 1,
        }
    )
    assert res["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_87_find_and_grep_hidden_no_ignore_passthrough(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd[0] == "fd":
            assert "-H" in cmd and "-I" in cmd
            return 0, b"/a.txt\n", b""
        assert "-H" in cmd and "-u" in cmd
        return 0, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "x", "hidden": True, "no_ignore": True}
    )
    assert res["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_88_find_and_grep_glob_pattern(tmp_path):
    config = FdCommandConfig(
        pattern="*.py",
        glob=True,
        absolute=True,
        roots=(str(tmp_path),),
    )
    cmd = FdCommandBuilder().build(config)
    assert "--glob" in cmd and "*.py" in cmd


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_90_search_content_group_by_file_then_summary(monkeypatch, tmp_path):
    """Test group_by_file format parameter (only one format parameter allowed)"""
    tool = SearchContentTool(str(tmp_path))

    evt = (
        json.dumps(
            {
                "type": "match",
                "data": {
                    "path": {"text": "/a.txt"},
                    "lines": {"text": "x\n"},
                    "line_number": 1,
                    "submatches": [],
                },
            }
        ).encode()
        + b"\n"
    )

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 0, evt, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.search_strategies.content_search.run_command_capture",
        fake_run,
    )

    # Test group_by_file format parameter
    res = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "query": "x",
            "group_by_file": True,
            "output_format": "json",
        }
    )
    assert "files" in res and "summary" not in res


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_91_search_content_total_only_then_normal_cache(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))
    evt = (
        json.dumps(
            {
                "type": "match",
                "data": {
                    "path": {"text": "/a.txt"},
                    "lines": {"text": "x\n"},
                    "line_number": 1,
                    "submatches": [],
                },
            }
        ).encode()
        + b"\n"
    )

    # First call: total_only
    async def fake_run_total(cmd, input_data=None, timeout_ms=None):
        return 0, b"/a.txt:1\n", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.search_strategies.content_search.run_command_capture",
        fake_run_total,
    )

    total = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "query": "x",
            "total_only": True,
            "output_format": "json",
        }
    )
    assert total == 1

    # Second call: normal; allow subprocess call, but ensure it still succeeds
    async def fake_run_normal(cmd, input_data=None, timeout_ms=None):
        return 0, evt, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.search_strategies.content_search.run_command_capture",
        fake_run_normal,
    )

    res = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "query": "x",
            "output_format": "json",
        }
    )
    assert res["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_92_search_content_roots_validation(tmp_path):
    tool = SearchContentTool(str(tmp_path))
    with pytest.raises(ValueError):
        tool.validate_arguments({"query": "x"})
    with pytest.raises(ValueError):
        tool.validate_arguments({"roots": [str(tmp_path)], "query": ""})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_93_find_and_grep_roots_validation(tmp_path):
    tool = FindAndGrepTool(str(tmp_path))
    with pytest.raises(ValueError):
        tool.validate_arguments({"query": "x"})
    with pytest.raises(ValueError):
        tool.validate_arguments({"roots": "not-an-array", "query": "x"})
