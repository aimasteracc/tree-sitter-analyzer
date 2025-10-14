import json

import pytest

from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


@pytest.fixture(autouse=True)
def mock_external_commands(monkeypatch):
    """Auto-mock external command availability checks for all tests in this module."""
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
        lambda cmd: True
    )


@pytest.mark.unit
def test_rg_26_build_count_only_mode(tmp_path):
    from tree_sitter_analyzer.mcp.tools import fd_rg_utils

    cmd = fd_rg_utils.build_rg_command(
        query="x",
        case="smart",
        fixed_strings=False,
        word=False,
        multiline=False,
        include_globs=None,
        exclude_globs=None,
        follow_symlinks=False,
        hidden=False,
        no_ignore=False,
        max_filesize=None,
        context_before=None,
        context_after=None,
        encoding=None,
        max_count=None,
        timeout_ms=None,
        roots=[str(tmp_path)],
        files_from=None,
        count_only_matches=True,
    )
    assert "--count-matches" in cmd and "--json" not in cmd


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_27_fd_rg_composed_success(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))
    f = tmp_path / "a.txt"
    f.write_text("hello\n", encoding="utf-8")

    rg_json = {
        "type": "match",
        "data": {
            "path": {"text": str(f)},
            "lines": {"text": "hello\n"},
            "line_number": 1,
            "submatches": [],
        },
    }

    call = {"i": 0}

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        call["i"] += 1
        if call["i"] == 1:
            assert cmd[0] == "fd"
            return 0, f"{f}\n".encode(), b""
        else:
            assert cmd[0] == "rg"
            return 0, (json.dumps(rg_json) + "\n").encode(), b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*.txt", "glob": True, "query": "hello"}
    )
    assert res["success"] is True and res["count"] == 1
    assert res["meta"]["searched_file_count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_28_fd_empty_list_returns_empty(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd[0] == "fd":
            return 0, b"", b""
        return 0, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute({"roots": [str(tmp_path)], "query": "x"})
    assert res["success"] is True
    assert res["count"] == 0
    assert res["meta"]["searched_file_count"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_29_fd_error_bubbles(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd[0] == "fd":
            return 2, b"", b"fd failed"
        return 0, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute({"roots": [str(tmp_path)], "query": "x"})
    assert res["success"] is False
    assert res["error"]
    assert res["returncode"] == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_30_rg_error_bubbles(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd[0] == "fd":
            return 0, b"/a.txt\n", b""
        return 2, b"", b"rg failed"

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute({"roots": [str(tmp_path)], "query": "x"})
    assert res["success"] is False
    assert res["returncode"] == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_31_find_and_grep_group_by_file(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))
    f = tmp_path / "a.txt"
    f.write_text("hello\n", encoding="utf-8")

    rg_json = {
        "type": "match",
        "data": {
            "path": {"text": str(f)},
            "lines": {"text": "hello\n"},
            "line_number": 1,
            "submatches": [],
        },
    }

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd[0] == "fd":
            return 0, f"{f}\n".encode(), b""
        return 0, (json.dumps(rg_json) + "\n").encode(), b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "query": "hello",
            "group_by_file": True,
        }
    )
    assert res["success"] is True
    assert "files" in res
    assert res["meta"]["searched_file_count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_32_find_and_grep_count_only(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd[0] == "fd":
            return 0, b"file1.py\nfile2.py\n", b""
        return 0, b"file1.py:2\nfile2.py:3\n", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "x", "count_only_matches": True}
    )
    assert res["success"] is True and res["count_only"] is True
    assert res["total_matches"] == 5
    assert res["meta"]["searched_file_count"] == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_33_find_and_grep_total_only(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd[0] == "fd":
            return 0, b"file1.py\n", b""
        return 0, b"file1.py:7\n", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    total = await tool.execute(
        {"roots": [str(tmp_path)], "query": "x", "total_only": True}
    )
    assert isinstance(total, int) and total == 7


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_34_find_and_grep_summary_only(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))
    f = tmp_path / "a.txt"
    f.write_text("hello\n", encoding="utf-8")

    rg_json = {
        "type": "match",
        "data": {
            "path": {"text": str(f)},
            "lines": {"text": "hello\n"},
            "line_number": 1,
            "submatches": [],
        },
    }

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd[0] == "fd":
            return 0, f"{f}\n".encode(), b""
        return 0, (json.dumps(rg_json) + "\n").encode(), b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "hello", "summary_only": True}
    )
    assert res["success"] is True and res.get("summary_only") is True
    assert res["summary"]["total_matches"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_35_search_content_encoding_flag(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        assert "--encoding" in cmd
        e_idx = cmd.index("--encoding")
        assert cmd[e_idx + 1] == "utf-8"
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
async def test_rg_36_context_lines_flags(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        assert "-B" in cmd and "-A" in cmd
        return 0, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "query": "x",
            "context_before": 2,
            "context_after": 3,
        }
    )
    assert res["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_37_validate_arguments_errors(tmp_path):
    tool = SearchContentTool(str(tmp_path))
    with pytest.raises(ValueError):
        tool.validate_arguments({"roots": [str(tmp_path)]})
    with pytest.raises(ValueError):
        tool.validate_arguments({"query": "x"})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_38_files_validation(tmp_path):
    tool = SearchContentTool(str(tmp_path))
    f = tmp_path / "a.txt"
    f.write_text("x\n", encoding="utf-8")

    # Should work
    tool.validate_arguments({"files": [str(f)], "query": "x"})

    # Nonexistent file should raise
    with pytest.raises(ValueError):
        tool.validate_arguments(
            {"files": [str(tmp_path / "missing.txt")], "query": "x"}
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_39_no_ignore_auto_detection(monkeypatch, tmp_path):
    """We only assert that execution succeeds and respects boolean; auto-detection is internal."""
    tool = SearchContentTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # The flag may or may not include -u depending on detector; just return ok
        return 0, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute({"roots": [str(tmp_path)], "query": "x"})
    assert res["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_40_parse_multiple_json_events(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))
    f = tmp_path / "a.txt"
    f.write_text("x\n", encoding="utf-8")

    def j(path: str, line_no: int):
        return (
            json.dumps(
                {
                    "type": "match",
                    "data": {
                        "path": {"text": path},
                        "lines": {"text": "x\n"},
                        "line_number": line_no,
                        "submatches": [],
                    },
                }
            ).encode()
            + b"\n"
        )

    out = j(str(f), 1) + j(str(f), 2) + j(str(f), 3)

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute({"roots": [str(tmp_path)], "query": "x"})
    assert res["success"] is True
    assert res["count"] == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_41_match_text_normalized(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))
    f = tmp_path / "a.txt"
    f.write_text("x\n", encoding="utf-8")

    evt = (
        json.dumps(
            {
                "type": "match",
                "data": {
                    "path": {"text": str(f)},
                    "lines": {"text": "a   b\t c\n"},
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
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute({"roots": [str(tmp_path)], "query": "x"})
    assert res["success"] is True
    assert res["results"][0]["text"] == "a b c"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_42_find_and_grep_sort_by_path(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd[0] == "fd":
            return 0, b"/z.txt\n/a.txt\n", b""
        return 0, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute({"roots": [str(tmp_path)], "query": "x", "sort": "path"})
    assert res["success"] is True
    assert res["meta"]["searched_file_count"] == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_43_find_and_grep_sort_by_size(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))
    # Create files of different sizes
    f1 = tmp_path / "small.txt"
    f1.write_text("a", encoding="utf-8")
    f2 = tmp_path / "large.txt"
    f2.write_text("a" * 100, encoding="utf-8")

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd[0] == "fd":
            return 0, f"{f1}\n{f2}\n".encode(), b""
        return 1, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute({"roots": [str(tmp_path)], "query": "x", "sort": "size"})
    assert res["success"] is True
    assert res["meta"]["searched_file_count"] == 2
