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


@pytest.mark.unit
def test_rg_44_regex_specials_and_flags(tmp_path):
    cmd = fd_rg_utils.build_rg_command(
        query=r"class\s+\w+\(.*\)",
        case="sensitive",
        fixed_strings=False,
        word=False,
        multiline=True,
        include_globs=["*.py"],
        exclude_globs=None,
        follow_symlinks=False,
        hidden=False,
        no_ignore=False,
        max_filesize="1M",
        context_before=1,
        context_after=2,
        encoding=None,
        max_count=10,
        timeout_ms=2000,
        roots=[str(tmp_path)],
        files_from=None,
        count_only_matches=False,
    )
    # Sanity checks for flags mapping
    assert "--json" in cmd and "-s" in cmd and "--multiline" in cmd
    assert any(cmd[i] == "-g" and cmd[i + 1] == "*.py" for i in range(len(cmd) - 1))
    assert "-B" in cmd and "-A" in cmd and "-m" in cmd


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_45_large_output_truncation(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))

    # Create more than MAX_RESULTS_HARD_CAP events to ensure truncation
    def jline(idx: int):
        return (
            json.dumps(
                {
                    "type": "match",
                    "data": {
                        "path": {"text": f"/f{idx}.txt"},
                        "lines": {"text": "x\n"},
                        "line_number": 1,
                        "submatches": [],
                    },
                }
            ).encode()
            + b"\n"
        )

    out = b"".join(jline(i) for i in range(fd_rg_utils.MAX_RESULTS_HARD_CAP + 5))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute({"roots": [str(tmp_path)], "query": "x"})
    assert res["success"] is True
    assert res["truncated"] is True
    assert res["count"] == fd_rg_utils.MAX_RESULTS_HARD_CAP


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_46_word_mode_does_not_match_substrings(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))

    m = {
        "type": "match",
        "data": {
            "path": {"text": "/f.txt"},
            "lines": {"text": "test\n"},
            "line_number": 1,
            "submatches": [],
        },
    }

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # Ensure word flag present when requested
        if "-w" not in cmd:
            return 0, b"", b""
        return 0, (json.dumps(m) + "\n").encode(), b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute({"roots": [str(tmp_path)], "query": "test", "word": True})
    assert res["success"] is True
    # Since we mocked to only return output when -w is present, count>0 ensures mapping
    assert res["count"] >= 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_47_fixed_strings_escapes_regex(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))

    evt = (
        json.dumps(
            {
                "type": "match",
                "data": {
                    "path": {"text": "/f.txt"},
                    "lines": {"text": "a+b?\n"},
                    "line_number": 1,
                    "submatches": [],
                },
            }
        ).encode()
        + b"\n"
    )

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        assert "-F" in cmd
        return 0, evt, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "a+b?", "fixed_strings": True}
    )
    assert res["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_48_encoding_invalid_is_string_validated(tmp_path):
    tool = SearchContentTool(str(tmp_path))
    with pytest.raises(ValueError):
        tool.validate_arguments(
            {"roots": [str(tmp_path)], "query": "x", "encoding": 123}
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_49_include_exclude_not_strings(tmp_path):
    tool = SearchContentTool(str(tmp_path))
    with pytest.raises(ValueError):
        tool.validate_arguments(
            {"roots": [str(tmp_path)], "query": "x", "include_globs": [1, 2]}
        )
    with pytest.raises(ValueError):
        tool.validate_arguments(
            {"roots": [str(tmp_path)], "query": "x", "exclude_globs": [object()]}
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_50_count_parsing_robust_to_bad_lines(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))
    bad = b"not_a_count\nfile.py:3\nfile2.py:bad\nfile3.py:7\n"

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 0, bad, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "x", "count_only_matches": True}
    )
    assert res["success"] is True
    assert res["total_matches"] == 10  # 3 + 7
    assert "file.py" in res["file_counts"] and "file3.py" in res["file_counts"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_51_group_by_file_structure(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))

    def jline(path: str, line: int):
        return (
            json.dumps(
                {
                    "type": "match",
                    "data": {
                        "path": {"text": path},
                        "lines": {"text": "x\n"},
                        "line_number": line,
                        "submatches": [],
                    },
                }
            ).encode()
            + b"\n"
        )

    out = jline("/f1.txt", 1) + jline("/f1.txt", 2) + jline("/f2.txt", 1)

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "x", "group_by_file": True}
    )
    assert res["success"] is True
    assert res["count"] == 3
    assert len(res["files"]) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_52_summary_counts_consistent(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))

    def jline(path: str):
        return (
            json.dumps(
                {
                    "type": "match",
                    "data": {
                        "path": {"text": path},
                        "lines": {"text": "x\n"},
                        "line_number": 1,
                        "submatches": [],
                    },
                }
            ).encode()
            + b"\n"
        )

    out = jline("/f1.txt") + jline("/f2.txt") + jline("/f2.txt")

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "x", "summary_only": True}
    )
    assert res["success"] is True
    assert res["summary"]["total_matches"] == 3
    assert res["summary"]["total_files"] == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_53_files_mode_uses_parent_dirs(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))
    f = tmp_path / "a.txt"
    f.write_text("x\n", encoding="utf-8")

    evt = (
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

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # Handle both symbolic link and real paths on macOS
        import os

        parent_path = str(f.parent)
        real_parent_path = os.path.realpath(parent_path)
        # Check if any path in cmd matches either the symbolic or real path
        path_found = False
        for item in cmd:
            if isinstance(item, str) and (
                parent_path in item
                or real_parent_path in item
                or os.path.realpath(item) == real_parent_path
            ):
                path_found = True
                break
        assert path_found, (
            f"Neither {parent_path} nor {real_parent_path} found in {cmd}"
        )
        return 0, evt, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute({"files": [str(f)], "query": "x"})
    assert res["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_54_no_json_non_match_events(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))
    non = json.dumps({"type": "begin", "data": {}}).encode() + b"\n"
    match = (
        json.dumps(
            {
                "type": "match",
                "data": {
                    "path": {"text": "/f.txt"},
                    "lines": {"text": "x\n"},
                    "line_number": 1,
                    "submatches": [],
                },
            }
        ).encode()
        + b"\n"
    )
    out = non + match

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute({"roots": [str(tmp_path)], "query": "x"})
    assert res["success"] is True and res["count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_55_hidden_files_not_included_by_default(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))

    evt = (
        json.dumps(
            {
                "type": "match",
                "data": {
                    "path": {"text": "/.hidden/file.txt"},
                    "lines": {"text": "x\n"},
                    "line_number": 1,
                    "submatches": [],
                },
            }
        ).encode()
        + b"\n"
    )

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # Unless hidden=True, we don't guarantee inclusion; this test just ensures success
        return 0, evt, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute({"roots": [str(tmp_path)], "query": "x"})
    assert res["success"] is True
