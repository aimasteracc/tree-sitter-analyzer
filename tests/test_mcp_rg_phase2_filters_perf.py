import json

import pytest

from tree_sitter_analyzer.mcp.tools import fd_rg_utils
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


@pytest.fixture(autouse=True)
def mock_external_commands(monkeypatch):
    """Auto-mock external command availability checks for all tests in this module."""
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
        lambda cmd: True,
    )


from tree_sitter_analyzer.mcp.utils.search_cache import clear_cache


@pytest.mark.unit
def test_rg_11_include_globs_mapping(tmp_path):
    cmd = fd_rg_utils.build_rg_command(
        query="import",
        case="smart",
        fixed_strings=False,
        word=False,
        multiline=False,
        include_globs=["*.py", "src/**/*.ts"],
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
        count_only_matches=False,
    )
    # Ensure '-g pattern' pairs exist
    assert any(cmd[i] == "-g" and cmd[i + 1] == "*.py" for i in range(len(cmd) - 1))
    assert any(
        cmd[i] == "-g" and cmd[i + 1] == "src/**/*.ts" for i in range(len(cmd) - 1)
    )


@pytest.mark.unit
def test_rg_12_exclude_globs_mapping(tmp_path):
    cmd = fd_rg_utils.build_rg_command(
        query="import",
        case="smart",
        fixed_strings=False,
        word=False,
        multiline=False,
        include_globs=None,
        exclude_globs=["*_test.py", "build/**"],
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
        count_only_matches=False,
    )
    # ripgrep exclusion is '-g !pattern'
    assert any(
        cmd[i] == "-g" and cmd[i + 1] == "!*_test.py" for i in range(len(cmd) - 1)
    )
    assert any(
        cmd[i] == "-g" and cmd[i + 1] == "!build/**" for i in range(len(cmd) - 1)
    )


@pytest.mark.unit
def test_rg_13_hidden_and_no_ignore_flags(tmp_path):
    cmd = fd_rg_utils.build_rg_command(
        query="TODO",
        case="smart",
        fixed_strings=False,
        word=False,
        multiline=False,
        include_globs=None,
        exclude_globs=None,
        follow_symlinks=False,
        hidden=True,
        no_ignore=True,
        max_filesize=None,
        context_before=None,
        context_after=None,
        encoding=None,
        max_count=None,
        timeout_ms=None,
        roots=[str(tmp_path)],
        files_from=None,
        count_only_matches=False,
    )
    assert "-H" in cmd
    assert "-u" in cmd


@pytest.mark.unit
def test_rg_14_follow_symlinks_flag(tmp_path):
    cmd = fd_rg_utils.build_rg_command(
        query="foo",
        case="smart",
        fixed_strings=False,
        word=False,
        multiline=False,
        include_globs=None,
        exclude_globs=None,
        follow_symlinks=True,
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
        count_only_matches=False,
    )
    assert "-L" in cmd


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_15_max_count_clamped(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))
    f = tmp_path / "a.txt"
    f.write_text("x\n", encoding="utf-8")

    rg_json = {
        "type": "match",
        "data": {
            "path": {"text": str(f)},
            "lines": {"text": "x\n"},
            "line_number": 1,
            "submatches": [],
        },
    }

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # max_count should be clamped to DEFAULT_RESULTS_LIMIT (2000)
        assert "-m" in cmd
        m_idx = cmd.index("-m")
        assert cmd[m_idx + 1] == str(fd_rg_utils.DEFAULT_RESULTS_LIMIT)
        return 0, (json.dumps(rg_json) + "\n").encode(), b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "x", "max_count": 999999}
    )
    assert res["success"] is True


@pytest.mark.unit
def test_rg_16_max_filesize_normalization(tmp_path):
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
        max_filesize="9999G",
        context_before=None,
        context_after=None,
        encoding=None,
        max_count=None,
        timeout_ms=None,
        roots=[str(tmp_path)],
        files_from=None,
        count_only_matches=False,
    )
    idx = cmd.index("--max-filesize")
    assert cmd[idx + 1] == "200M"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_17_timeout_forwarded(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))
    f = tmp_path / "a.txt"
    f.write_text("x\n", encoding="utf-8")

    seen_timeout = {"val": None}

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        seen_timeout["val"] = timeout_ms
        return 0, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    await tool.execute({"roots": [str(tmp_path)], "query": "x", "timeout_ms": 1234})
    assert seen_timeout["val"] == 1234


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_18_count_only_matches_output(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))

    count_out = b"file1.py:3\nfile2.py:2\n"

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        assert "--count-matches" in cmd
        return 0, count_out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "x", "count_only_matches": True}
    )
    assert res["success"] is True
    assert res["count_only"] is True
    assert res["total_matches"] == 5
    assert res["file_counts"]["file1.py"] == 3
    assert res["file_counts"]["file2.py"] == 2
    assert "elapsed_ms" in res


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_19_total_only_caches_and_derives_count(monkeypatch, tmp_path):
    clear_cache()
    tool = SearchContentTool(str(tmp_path))

    count_out = b"file1.py:3\nfile2.py:2\n"
    calls = {"n": 0}

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        calls["n"] += 1
        return 0, count_out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    total = await tool.execute(
        {"roots": [str(tmp_path)], "query": "x", "total_only": True}
    )
    assert isinstance(total, int) and total == 5

    # Now request count_only for same params; should be served from cache
    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "x", "count_only_matches": True}
    )
    assert res["success"] is True and res["count_only"] is True
    assert res.get("derived_from_total_only") is True
    # Only one subprocess call should have happened
    assert calls["n"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_20_summary_only(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))
    f1 = tmp_path / "a.py"
    f2 = tmp_path / "b.py"

    def jline(path: str, line: str, line_no: int):
        return (
            json.dumps(
                {
                    "type": "match",
                    "data": {
                        "path": {"text": path},
                        "lines": {"text": line},
                        "line_number": line_no,
                        "submatches": [],
                    },
                }
            ).encode()
            + b"\n"
        )

    out = b"".join(
        [jline(str(f1), "import os\n", 1), jline(str(f2), "import sys\n", 1)]
    )

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "import", "summary_only": True}
    )
    assert res["success"] is True
    assert "summary" in res
    assert res["summary"]["total_matches"] == 2
    assert len(res["summary"]["top_files"]) >= 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_21_group_by_file(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))
    f1 = tmp_path / "a.py"

    rg_json = {
        "type": "match",
        "data": {
            "path": {"text": str(f1)},
            "lines": {"text": "print(1)\n"},
            "line_number": 1,
            "submatches": [],
        },
    }

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 0, (json.dumps(rg_json) + "\n").encode(), b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "print", "group_by_file": True}
    )
    assert res["success"] is True
    assert "files" in res
    assert res["count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_22_optimize_paths(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))
    f1 = tmp_path / "dir1" / "dir2" / "a.py"
    f1.parent.mkdir(parents=True, exist_ok=True)
    f1.write_text("print(1)\n", encoding="utf-8")

    def jline(path: str):
        return (
            json.dumps(
                {
                    "type": "match",
                    "data": {
                        "path": {"text": path},
                        "lines": {"text": "print(1)\n"},
                        "line_number": 1,
                        "submatches": [],
                    },
                }
            ).encode()
            + b"\n"
        )

    out = jline(str(f1)) + jline(str(f1))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "print", "optimize_paths": True}
    )
    assert res["success"] is True
    # Optimized file path should not be the full absolute path when common prefix exists
    assert not res["results"][0]["file"].startswith(str(tmp_path))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_23_no_matches_rc1(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 1, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute({"roots": [str(tmp_path)], "query": "neverfind"})
    assert res["success"] is True
    assert res["count"] == 0


@pytest.mark.unit
def test_rg_24_globs_with_flags_combined(tmp_path):
    cmd = fd_rg_utils.build_rg_command(
        query="TODO",
        case="smart",
        fixed_strings=False,
        word=False,
        multiline=False,
        include_globs=["*.py"],
        exclude_globs=["*_test.py"],
        follow_symlinks=True,
        hidden=True,
        no_ignore=True,
        max_filesize=None,
        context_before=None,
        context_after=None,
        encoding=None,
        max_count=None,
        timeout_ms=None,
        roots=[str(tmp_path)],
        files_from=None,
        count_only_matches=False,
    )
    assert "-L" in cmd and "-H" in cmd and "-u" in cmd
    assert any(cmd[i] == "-g" and cmd[i + 1] == "*.py" for i in range(len(cmd) - 1))
    assert any(
        cmd[i] == "-g" and cmd[i + 1] == "!*_test.py" for i in range(len(cmd) - 1)
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_25_json_parser_ignores_non_match(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))
    f = tmp_path / "a.txt"
    f.write_text("x\n", encoding="utf-8")

    begin_evt = json.dumps({"type": "begin", "data": {}}).encode() + b"\n"
    match_evt = (
        json.dumps(
            {
                "type": "match",
                "data": {
                    "path": {"text": str(f)},
                    "lines": {"text": "x\n"},
                    "line_number": 1,
                    "submatches": [],
                },
            }
        ).encode()
        + b"\n"
    )
    out = begin_evt + match_evt

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute({"roots": [str(tmp_path)], "query": "x"})
    assert res["success"] is True
    assert res["count"] == 1
