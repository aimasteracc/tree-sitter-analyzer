"""Tests for CodeGraph Status tool — index health at-a-glance."""

from __future__ import annotations

import os
import sqlite3

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import (
    CodeGraphStatusTool,
)


@pytest.fixture
def tool():
    return CodeGraphStatusTool()


@pytest.fixture
def tool_with_root(tmp_path):
    return CodeGraphStatusTool(str(tmp_path))


class TestToolDefinition:
    def test_tool_name(self, tool):
        defn = tool.get_tool_definition()
        assert defn["name"] == "codegraph_status"

    def test_description_starts_with_index_health(self, tool):
        defn = tool.get_tool_definition()
        assert defn["description"].startswith("INDEX HEALTH")

    def test_annotations_all_four_hints(self, tool):
        defn = tool.get_tool_definition()
        annotations = defn["annotations"]
        assert annotations["readOnlyHint"] is True
        assert annotations["destructiveHint"] is False
        assert annotations["idempotentHint"] is True
        assert annotations["openWorldHint"] is False

    def test_schema_strict_no_additional_properties(self, tool):
        schema = tool.get_tool_schema()
        assert schema["additionalProperties"] is False

    def test_schema_output_format_default_is_toon(self, tool):
        schema = tool.get_tool_schema()
        assert schema["properties"]["output_format"]["default"] == "toon"

    def test_schema_include_lag_default_true(self, tool):
        schema = tool.get_tool_schema()
        assert schema["properties"]["include_lag"]["default"] is True


class TestValidateArguments:
    def test_empty_args_accepted(self, tool):
        assert tool.validate_arguments({}) is True

    def test_include_lag_must_be_bool(self, tool):
        with pytest.raises(ValueError, match="include_lag"):
            tool.validate_arguments({"include_lag": "yes"})


class TestExecuteNoProjectRoot:
    @pytest.mark.asyncio
    async def test_no_project_root_returns_not_found(self, tool):
        result = await tool.execute({"output_format": "json"})
        assert result["verdict"] == "NOT_FOUND"
        assert result["indexed"] is False
        assert result["total_files"] == 0
        assert result["total_symbols"] == 0
        assert result["project_root"] is None
        assert "hint" in result, "NOT_FOUND response must carry a 'hint' field"
        assert "project_root" in result["hint"]


class TestExecuteNoCache:
    @pytest.mark.asyncio
    async def test_project_set_but_no_cache_returns_warn(self, tool_with_root):
        result = await tool_with_root.execute({"output_format": "json"})
        assert result["verdict"] == "WARN"
        assert result["indexed"] is False
        assert result["total_files"] == 0
        assert result["cache_path"] is None
        assert result["agent_summary"]["summary_line"] == (
            "codegraph_status: index missing or empty"
        )
        assert "hint" in result, "WARN response must carry a 'hint' field"
        assert "warm" in result["hint"].lower() or "index" in result["hint"].lower()


class TestExecuteOutputFormat:
    @pytest.mark.asyncio
    async def test_toon_format_default(self, tool):
        result = await tool.execute({})
        assert result["format"] == "toon"
        assert "toon_content" in result

    @pytest.mark.asyncio
    async def test_json_format_no_toon_blob(self, tool):
        result = await tool.execute({"output_format": "json"})
        assert "toon_content" not in result
        assert result["verdict"] == "NOT_FOUND"


class TestLagCompatibility:
    @pytest.mark.asyncio
    async def test_include_lag_false_does_not_scan(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_lag as lag
        import tree_sitter_analyzer.index_snapshot as owner

        snapshot = owner.IndexSnapshot(
            "idxsnap_test",
            "source",
            "index",
            "generation",
            "complete",
            None,
            str(tmp_path),
            1,
        )
        monkeypatch.setattr(owner, "read_existing_snapshot", lambda _root: snapshot)
        monkeypatch.setattr(
            owner,
            "read_snapshot_stats",
            lambda *_args: {
                "total_files": 1,
                "total_symbols": 0,
                "snapshot_id": "idxsnap_test",
                "source_generation": "generation",
                "source_fingerprint": "source",
                "index_fingerprint": "index",
            },
        )
        monkeypatch.setattr(
            lag,
            "compute_qualitative_lag",
            lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected scan")),
        )

        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"include_lag": False, "output_format": "json"}
        )
        assert result["lag_seconds"] is None

    @pytest.mark.asyncio
    async def test_include_lag_true_reports_qualitative_signal(
        self, tmp_path, monkeypatch
    ):
        import tree_sitter_analyzer.index_lag as lag
        import tree_sitter_analyzer.index_snapshot as owner

        snapshot = owner.IndexSnapshot(
            "idxsnap_test",
            "source",
            "index",
            "generation",
            "complete",
            None,
            str(tmp_path),
            1,
        )
        monkeypatch.setattr(owner, "read_existing_snapshot", lambda _root: snapshot)
        monkeypatch.setattr(
            owner,
            "read_snapshot_stats",
            lambda *_args: {
                "total_files": 1,
                "total_symbols": 0,
                "snapshot_id": "idxsnap_test",
                "source_generation": "generation",
                "source_fingerprint": "source",
                "index_fingerprint": "index",
            },
        )
        monkeypatch.setattr(lag, "compute_qualitative_lag", lambda *_args: 12.5)

        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"include_lag": True, "output_format": "json"}
        )
        assert result["lag_seconds"] == 12.5
        assert result["completeness"] == "complete"


class TestSnapshotFallbackBounds:
    @staticmethod
    def _connection(symbols_json="{}"):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE ast_index(file_path TEXT, symbols_json TEXT, language TEXT)"
        )
        conn.execute(
            "INSERT INTO ast_index VALUES ('sample.py', ?, 'python')",
            (symbols_json,),
        )
        return conn

    def test_symbol_fallback_rejects_non_list_payload(self):
        import tree_sitter_analyzer.index_snapshot as owner

        conn = self._connection('{"symbols": {}}')
        with pytest.raises(ValueError, match="CORRUPT_INDEX"):
            owner._fallback_symbol_counts(conn)
        conn.close()

    def test_symbol_fallback_enforces_byte_budget(self, monkeypatch):
        import tree_sitter_analyzer.index_snapshot as owner

        conn = self._connection()
        monkeypatch.setattr(owner, "_SYMBOL_FALLBACK_BYTE_BUDGET", 0)
        with pytest.raises(RuntimeError, match="INDEX_SYMBOL_FALLBACK_BUDGET"):
            owner._fallback_symbol_counts(conn)
        conn.close()

    def test_symbol_fallback_enforces_row_budget(self, monkeypatch):
        import tree_sitter_analyzer.index_snapshot as owner

        conn = self._connection('{"symbols": [{"kind": "function"}]}')
        monkeypatch.setattr(owner, "_SYMBOL_FALLBACK_ROW_BUDGET", 0)
        with pytest.raises(RuntimeError, match="INDEX_SYMBOL_FALLBACK_BUDGET"):
            owner._fallback_symbol_counts(conn)
        conn.close()


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
@pytest.mark.asyncio
async def test_final_pinned_path_identity_mismatch_is_concurrent_writer(
    tmp_path, monkeypatch
):
    import tree_sitter_analyzer.index_snapshot as owner
    from tree_sitter_analyzer.ast_cache import ASTCache

    source = tmp_path / "sample.py"
    source.write_text("value = 1\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    owner.stamp_full_index_manifest(cache.get_conn(), str(tmp_path))
    cache.close()
    matches = iter((True, False))
    monkeypatch.setattr(
        owner, "_path_matches_pinned_database", lambda *_args: next(matches)
    )

    result = await CodeGraphStatusTool(str(tmp_path)).execute({"output_format": "json"})
    assert result["oracle_reason"] == "CONCURRENT_WRITER"
