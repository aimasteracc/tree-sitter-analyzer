import json

import pytest

from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


@pytest.fixture(autouse=True)
def mock_external_commands(monkeypatch):
    """Auto-mock external command availability checks for all tests in this module."""
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
        lambda cmd: True,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_66_non_utf8_encoding_flag(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        assert "--encoding" in cmd
        i = cmd.index("--encoding")
        assert cmd[i + 1] == "latin1"
        return 0, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "x", "encoding": "latin1"}
    )
    assert res["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_67_binary_file_handling(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))

    # Simulate no match output (rg usually skips binary unless overridden)
    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 0, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Should just succeed with count 0
    res = await tool.execute({"roots": [str(tmp_path)], "query": "x"})
    assert res["success"] is True and res["count"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_68_large_file_size_cap(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        idx = cmd.index("--max-filesize")
        # If user provides absurd value, utils clamps to 200M
        assert cmd[idx + 1] == "200M"
        return 0, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "x", "max_filesize": "1000G"}
    )
    assert res["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_69_context_values_validate_types(tmp_path):
    tool = SearchContentTool(str(tmp_path))
    with pytest.raises(ValueError):
        tool.validate_arguments(
            {"roots": [str(tmp_path)], "query": "x", "context_before": "1"}
        )
    with pytest.raises(ValueError):
        tool.validate_arguments(
            {"roots": [str(tmp_path)], "query": "x", "context_after": "2"}
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_70_timeout_type_validation(tmp_path):
    tool = SearchContentTool(str(tmp_path))
    with pytest.raises(ValueError):
        tool.validate_arguments(
            {"roots": [str(tmp_path)], "query": "x", "timeout_ms": "100"}
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_71_group_by_file_positions_key(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))

    evt = (
        json.dumps(
            {
                "type": "match",
                "data": {
                    "path": {"text": "/f.txt"},
                    "lines": {"text": "x\n"},
                    "line_number": 1,
                    "submatches": [{"start": 0, "end": 1}],
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

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "x", "group_by_file": True}
    )
    assert res["success"] is True
    files = res["files"]
    assert len(files) == 1 and files[0]["matches"][0]["positions"] == [[0, 1]]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_72_summary_text_contains_totals(monkeypatch, tmp_path):
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

    out = jline("/a.txt") + jline("/b.txt")

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "x", "summary_only": True}
    )
    assert res["success"] is True
    assert "Found 2 matches" in res["summary"]["summary"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_73_total_only_returns_int(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 0, b"a:2\nb:3\n", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    total = await tool.execute(
        {"roots": [str(tmp_path)], "query": "x", "total_only": True}
    )
    assert isinstance(total, int) and total == 5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_74_count_only_returns_dict(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 0, b"a:2\n", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "x", "count_only_matches": True}
    )
    assert isinstance(res, dict) and res["count_only"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_75_normal_mode_returns_results_array(monkeypatch, tmp_path):
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
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute({"roots": [str(tmp_path)], "query": "x"})
    assert res["success"] is True and isinstance(res.get("results", []), list)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_76_malformed_json_lines_are_skipped(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))
    bad = b'{not json}\n{"type": "match", "data": {}}\n'

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 0, bad, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute({"roots": [str(tmp_path)], "query": "x"})
    assert res["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_77_cache_hit_field_present(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))

    # First run - store normal result
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

    async def fake_run_once(cmd, input_data=None, timeout_ms=None):
        return 0, evt, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run_once
    )

    await tool.execute({"roots": [str(tmp_path)], "query": "x"})

    # Second run - simulate cache return by preventing subprocess; tool should return cached
    async def fake_run_fail(cmd, input_data=None, timeout_ms=None):
        raise AssertionError("Should not be called if cache is used")

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run_fail
    )

    res2 = await tool.execute({"roots": [str(tmp_path)], "query": "x"})
    assert res2.get("cache_hit") is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_78_group_by_file_priority_over_summary(monkeypatch, tmp_path):
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
    # group_by_file takes priority and returns grouped structure
    assert "files" in res and "summary" not in res


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_79_optimize_paths_has_effect(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))
    evt = (
        json.dumps(
            {
                "type": "match",
                "data": {
                    "path": {
                        "text": str(tmp_path / "dir" / "long" / "path" / "file.txt")
                    },
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
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    res = await tool.execute(
        {"roots": [str(tmp_path)], "query": "x", "optimize_paths": True}
    )
    assert res["success"] is True
    assert "..." in res["results"][0]["file"] or not res["results"][0][
        "file"
    ].startswith(str(tmp_path))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rg_80_cache_key_stability(tmp_path):
    from tree_sitter_analyzer.mcp.utils.search_cache import get_default_cache

    cache = get_default_cache()
    key1 = cache.create_cache_key("Query ", [str(tmp_path)], include_globs=["*.py"])
    key2 = cache.create_cache_key("query", [str(tmp_path)], include_globs=["*.py"])
    assert key1 == key2
