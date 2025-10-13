import json

import pytest

from tree_sitter_analyzer.mcp.tools import fd_rg_utils
from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool


@pytest.fixture(autouse=True)
def mock_external_commands(monkeypatch):
    """Auto-mock external command availability checks for all tests in this module."""
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
        lambda cmd: True
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_56_find_and_grep_with_globs_and_exclude(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))
    f1 = tmp_path / "a.py"
    f2 = tmp_path / "b_test.py"
    f1.write_text("import os\n", encoding="utf-8")
    f2.write_text("import sys\n", encoding="utf-8")

    rg_json = {
        "type": "match",
        "data": {
            "path": {"text": str(f1)},
            "lines": {"text": "import os\n"},
            "line_number": 1,
            "submatches": [],
        },
    }

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd[0] == "fd":
            return 0, f"{f1}\n{f2}\n".encode(), b""
        # ensure -g '!*_test.py' present
        assert any(
            cmd[i] == "-g" and cmd[i + 1] == "!*_test.py" for i in range(len(cmd) - 1)
        )
        return 0, (json.dumps(rg_json) + "\n").encode(), b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*.py",
            "glob": True,
            "query": "import",
            "exclude_globs": ["*_test.py"],
        }
    )
    assert res["success"] is True
    assert res["count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_57_find_and_grep_follow_symlinks(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))
    f = tmp_path / "a.py"
    f.write_text("import os\n", encoding="utf-8")

    rg_json = {
        "type": "match",
        "data": {
            "path": {"text": str(f)},
            "lines": {"text": "import os\n"},
            "line_number": 1,
            "submatches": [],
        },
    }

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd[0] == "fd":
            assert "-L" in cmd
            return 0, f"{f}\n".encode(), b""
        return 0, (json.dumps(rg_json) + "\n").encode(), b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "import", "follow_symlinks": True}
    )
    assert res["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_58_find_and_grep_hidden_no_ignore(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))
    f = tmp_path / ".hidden.py"
    f.write_text("todo\n", encoding="utf-8")

    rg_json = {
        "type": "match",
        "data": {
            "path": {"text": str(f)},
            "lines": {"text": "todo\n"},
            "line_number": 1,
            "submatches": [],
        },
    }

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd[0] == "fd":
            assert "-H" in cmd and "-I" in cmd
            return 0, f"{f}\n".encode(), b""
        return 0, (json.dumps(rg_json) + "\n").encode(), b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "todo", "hidden": True, "no_ignore": True}
    )
    assert res["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_59_find_and_grep_depth_and_types(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd[0] == "fd":
            assert "-d" in cmd and "-t" in cmd
            return 0, b"/a.py\n", b""
        return 0, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "x", "depth": 2, "types": ["f"]}
    )
    assert res["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_60_find_and_grep_file_limit_truncates_fd(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))

    # Create a long fd output
    lines = b"".join(f"/f{i}.txt\n".encode() for i in range(3000))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd[0] == "fd":
            return 0, lines, b""
        return 0, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "x", "file_limit": 100}
    )
    assert res["success"] is True
    assert res["meta"]["searched_file_count"] == 100


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_61_find_and_grep_size_and_changed(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd[0] == "fd":
            # -S and --changed-within should be present
            assert any(
                cmd[i] == "-S" and cmd[i + 1] == "+10M" for i in range(len(cmd) - 1)
            )
            assert any(cmd[i] == "--changed-within" for i in range(len(cmd)))
            return 0, b"/a.py\n", b""
        return 0, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "query": "x",
            "size": ["+10M"],
            "changed_within": "7d",
        }
    )
    assert res["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_62_find_and_grep_full_path_match(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd[0] == "fd":
            assert "-p" in cmd and "-a" in cmd
            return 0, b"/a/b/c.txt\n", b""
        return 0, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "x", "full_path_match": True}
    )
    assert res["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_63_find_and_grep_grouped_summary(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))
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
        if cmd[0] == "fd":
            return 0, f"{f}\n".encode(), b""
        return 0, evt, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "query": "x",
            "group_by_file": True,
            "summary_only": True,
        }
    )
    assert res["success"] is True
    assert res["summary"]["total_matches"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_64_find_and_grep_encoding_and_context(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd[0] == "rg":
            assert "--encoding" in cmd and "-B" in cmd and "-A" in cmd
        return 0, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "query": "x",
            "encoding": "utf-8",
            "context_before": 1,
            "context_after": 1,
        }
    )
    assert res["success"] is True


@pytest.mark.unit
def test_rg_65_build_fd_command_roots_and_pattern(tmp_path):
    cmd = fd_rg_utils.build_fd_command(
        pattern="*.py",
        glob=True,
        types=["f"],
        extensions=["py"],
        exclude=["__pycache__"],
        depth=3,
        follow_symlinks=False,
        hidden=False,
        no_ignore=False,
        size=None,
        changed_within=None,
        changed_before=None,
        full_path_match=False,
        absolute=True,
        limit=100,
        roots=[str(tmp_path)],
    )
    # Sanity assertions
    assert cmd[0] == "fd" and "--glob" in cmd and "-e" in cmd and "-E" in cmd
    assert any(
        cmd[i] == "--max-results" and cmd[i + 1] == "100" for i in range(len(cmd) - 1)
    )
