import json

import pytest

from tree_sitter_analyzer.mcp.tools import fd_rg_utils
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


@pytest.mark.unit
def test_rg_01_build_cmd_default_smart_case(tmp_path):
    """Default build: --json, smart case (-S), default max-filesize."""
    cmd = fd_rg_utils.build_rg_command(
        query="test",
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
        count_only_matches=False,
    )

    assert cmd[0] == "rg"
    assert "--json" in cmd
    assert "-S" in cmd  # smart case
    assert "--max-filesize" in cmd
    sz_idx = cmd.index("--max-filesize")
    assert cmd[sz_idx + 1] == "10M"


@pytest.mark.unit
def test_rg_02_build_cmd_case_insensitive(tmp_path):
    cmd = fd_rg_utils.build_rg_command(
        query="test",
        case="insensitive",
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
        count_only_matches=False,
    )
    assert "-i" in cmd
    assert "-S" not in cmd
    assert "-s" not in cmd


@pytest.mark.unit
def test_rg_03_build_cmd_case_sensitive(tmp_path):
    cmd = fd_rg_utils.build_rg_command(
        query="test",
        case="sensitive",
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
        count_only_matches=False,
    )
    assert "-s" in cmd
    assert "-S" not in cmd
    assert "-i" not in cmd


@pytest.mark.unit
def test_rg_04_build_cmd_fixed_strings_flag(tmp_path):
    cmd = fd_rg_utils.build_rg_command(
        query="a+b?",
        case="smart",
        fixed_strings=True,
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
        count_only_matches=False,
    )
    assert "-F" in cmd


@pytest.mark.unit
def test_rg_05_build_cmd_word_boundaries(tmp_path):
    cmd = fd_rg_utils.build_rg_command(
        query="test",
        case="smart",
        fixed_strings=False,
        word=True,
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
        count_only_matches=False,
    )
    assert "-w" in cmd


@pytest.mark.unit
def test_rg_06_build_cmd_multiline(tmp_path):
    cmd = fd_rg_utils.build_rg_command(
        query="class \\w+",
        case="smart",
        fixed_strings=False,
        word=False,
        multiline=True,
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
        count_only_matches=False,
    )
    assert "--multiline" in cmd


@pytest.mark.unit
def test_rg_07_build_cmd_globs_include_exclude(tmp_path):
    cmd = fd_rg_utils.build_rg_command(
        query="import",
        case="smart",
        fixed_strings=False,
        word=False,
        multiline=False,
        include_globs=["*.py", "src/*.ts"],
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

    def has_pair(flag: str, value: str) -> bool:
        return any(
            i < len(cmd) - 1 and cmd[i] == flag and cmd[i + 1] == value
            for i in range(len(cmd))
        )

    assert has_pair("-g", "*.py")
    assert has_pair("-g", "src/*.ts")
    assert has_pair("-g", "!*_test.py")
    assert has_pair("-g", "!build/**")


@pytest.mark.unit
def test_rg_08_build_cmd_hidden_and_no_ignore(tmp_path):
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
    assert "-H" in cmd  # hidden
    assert "-u" in cmd  # no_ignore


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_09_search_content_exec_roots_basic_match_parsing(
    monkeypatch, tmp_path
):
    tool = SearchContentTool(str(tmp_path))
    f = tmp_path / "a.txt"
    f.write_text("hello world\n", encoding="utf-8")

    rg_json = {
        "type": "match",
        "data": {
            "path": {"text": str(f)},
            "lines": {"text": "hello world\n"},
            "line_number": 1,
            "submatches": [{"match": {"text": "hello"}, "start": 0, "end": 5}],
        },
    }

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        assert cmd and cmd[0] == "rg"
        out = (json.dumps(rg_json) + "\n").encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute({"roots": [str(tmp_path)], "query": "hello"})
    assert result["success"] is True
    assert result["count"] == 1
    assert result["results"][0]["file"] == str(f)
    assert result["results"][0]["line"] == 1
    assert result["results"][0]["matches"] == [[0, 5]]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_10_search_content_exec_files_list_uses_parent_dirs(
    monkeypatch, tmp_path
):
    tool = SearchContentTool(str(tmp_path))
    f = tmp_path / "b.txt"
    f.write_text("abc\n", encoding="utf-8")

    rg_json = {
        "type": "match",
        "data": {
            "path": {"text": str(f)},
            "lines": {"text": "abc\n"},
            "line_number": 1,
            "submatches": [{"match": {"text": "a"}, "start": 0, "end": 1}],
        },
    }

    parent_dir = str(f.parent)

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # Ensure parent directory of file is used as a root in the command
        assert parent_dir in cmd
        out = (json.dumps(rg_json) + "\n").encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute({"files": [str(f)], "query": "a"})
    assert result["success"] is True
    assert result["count"] == 1
    assert result["results"][0]["file"] == str(f)
