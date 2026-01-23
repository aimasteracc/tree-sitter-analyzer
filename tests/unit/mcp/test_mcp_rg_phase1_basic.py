import json

import pytest

from tree_sitter_analyzer.mcp.tools.fd_rg import RgCommandBuilder, RgCommandConfig
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


@pytest.fixture(autouse=True)
def mock_external_commands(monkeypatch):
    """Auto-mock external command availability checks for all tests in this module."""
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg.utils.check_external_command",
        lambda cmd: True,
    )


@pytest.mark.unit
def test_rg_01_build_cmd_default_smart_case(tmp_path):
    """Default build: --json, smart case (-S), default max-filesize."""
    config = RgCommandConfig(
        query="test",
        case="smart",
        roots=(str(tmp_path),),
    )
    cmd = RgCommandBuilder().build(config)

    assert cmd[0] == "rg"
    assert "--json" in cmd
    assert "-S" in cmd  # smart case
    assert "--max-filesize" in cmd
    sz_idx = cmd.index("--max-filesize")
    assert cmd[sz_idx + 1] == "1G"


@pytest.mark.unit
def test_rg_02_build_cmd_case_insensitive(tmp_path):
    config = RgCommandConfig(
        query="test",
        case="insensitive",
        roots=(str(tmp_path),),
    )
    cmd = RgCommandBuilder().build(config)
    assert "-i" in cmd
    assert "-S" not in cmd
    assert "-s" not in cmd


@pytest.mark.unit
def test_rg_03_build_cmd_case_sensitive(tmp_path):
    config = RgCommandConfig(
        query="test",
        case="sensitive",
        roots=(str(tmp_path),),
    )
    cmd = RgCommandBuilder().build(config)
    assert "-s" in cmd
    assert "-S" not in cmd
    assert "-i" not in cmd


@pytest.mark.unit
def test_rg_04_build_cmd_fixed_strings_flag(tmp_path):
    config = RgCommandConfig(
        query="a+b?",
        case="smart",
        fixed_strings=True,
        roots=(str(tmp_path),),
    )
    cmd = RgCommandBuilder().build(config)
    assert "-F" in cmd


@pytest.mark.unit
def test_rg_05_build_cmd_word_boundaries(tmp_path):
    config = RgCommandConfig(
        query="test",
        case="smart",
        word=True,
        roots=(str(tmp_path),),
    )
    cmd = RgCommandBuilder().build(config)
    assert "-w" in cmd


@pytest.mark.unit
def test_rg_06_build_cmd_multiline(tmp_path):
    config = RgCommandConfig(
        query="class \\w+",
        case="smart",
        multiline=True,
        roots=(str(tmp_path),),
    )
    cmd = RgCommandBuilder().build(config)
    assert "--multiline" in cmd


@pytest.mark.unit
def test_rg_07_build_cmd_globs_include_exclude(tmp_path):
    config = RgCommandConfig(
        query="import",
        case="smart",
        include_globs=("*.py", "src/*.ts"),
        exclude_globs=("*_test.py", "build/**"),
        roots=(str(tmp_path),),
    )
    cmd = RgCommandBuilder().build(config)

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
    config = RgCommandConfig(
        query="TODO",
        case="smart",
        hidden=True,
        no_ignore=True,
        roots=(str(tmp_path),),
    )
    cmd = RgCommandBuilder().build(config)
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
        "tree_sitter_analyzer.mcp.tools.search_strategies.content_search.run_command_capture",
        fake_run,
    )

    result = await tool.execute(
        {"roots": [str(tmp_path)], "query": "hello", "output_format": "json"}
    )
    assert result["success"] is True
    assert result["count"] == 1
    assert result["results"][0]["file"] == str(f)
    assert result["results"][0]["line"] == 1
    assert result["results"][0]["matches"] == [[0, 5]]
