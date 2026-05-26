"""Tests for CodeGraph Explore tool — bulk-fetch N related symbols.

Mirrors the structure of ``test_codegraph_navigate_tool.py``: tool
definition, schema, validate_arguments, and execute() across the WARN /
NOT_FOUND / INFO branches with mocked SymbolResolver + ASTCache.
"""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools import _codegraph_explore_helpers as helpers
from tree_sitter_analyzer.mcp.tools.codegraph_explore_tool import (
    CodeGraphExploreTool,
    _extract_snippet,
    _split_query,
)
from tree_sitter_analyzer.symbol_resolver import DefinitionLocation, ResolveResult


@pytest.fixture
def tool():
    return CodeGraphExploreTool()


@pytest.fixture
def tool_with_root(tmp_path):
    return CodeGraphExploreTool(str(tmp_path))


def _make_def(
    file: str,
    name: str,
    line: int = 1,
    end_line: int = 5,
    kind: str = "function",
    language: str = "python",
) -> DefinitionLocation:
    return DefinitionLocation(
        file=file,
        name=name,
        kind=kind,
        line=line,
        end_line=end_line,
        language=language,
    )


def _patch_resolver_with(defs_per_token: dict[str, list[DefinitionLocation]]):
    """Return a context manager patching SymbolResolver so .resolve(tok)
    returns a ResolveResult whose definitions come from ``defs_per_token``.
    """

    def _resolve(tok: str) -> ResolveResult:
        return ResolveResult(symbol=tok, definitions=defs_per_token.get(tok, []))

    mock_resolver = MagicMock()
    mock_resolver.resolve.side_effect = _resolve
    return patch(
        "tree_sitter_analyzer.symbol_resolver.SymbolResolver",
        return_value=mock_resolver,
    )


def _patch_cache_with(total_files: int = 5):
    """Patch ASTCache so the tool's _try_get_cache walks the success branch."""
    mock_cache = MagicMock()
    mock_cache.get_stats.return_value = {"total_files": total_files}
    return patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache)


class TestToolDefinition:
    def test_tool_name(self, tool):
        assert tool.get_tool_definition()["name"] == "codegraph_explore"

    def test_description_starts_with_bulk_fetch(self, tool):
        defn = tool.get_tool_definition()
        assert defn["description"].startswith("BULK FETCH")

    def test_annotations_all_four_hints(self, tool):
        ann = tool.get_tool_definition()["annotations"]
        assert ann["readOnlyHint"] is True
        assert ann["destructiveHint"] is False
        assert ann["idempotentHint"] is True
        assert ann["openWorldHint"] is False

    def test_schema_requires_query(self, tool):
        schema = tool.get_tool_schema()
        assert "query" in schema["properties"]
        assert schema["required"] == ["query"]

    def test_schema_strict_no_additional_properties(self, tool):
        assert tool.get_tool_schema()["additionalProperties"] is False

    def test_schema_output_format_default_is_toon(self, tool):
        assert (
            tool.get_tool_schema()["properties"]["output_format"]["default"] == "toon"
        )

    def test_schema_caps(self, tool):
        props = tool.get_tool_schema()["properties"]
        assert props["maxFiles"]["maximum"] == 30
        assert props["maxSymbols"]["maximum"] == 50
        assert props["maxFiles"]["default"] == 12
        assert props["maxSymbols"]["default"] == 20


class TestValidateArguments:
    def test_missing_query_raises(self, tool):
        with pytest.raises(ValueError, match="query is required"):
            tool.validate_arguments({})

    def test_blank_query_raises(self, tool):
        with pytest.raises(ValueError, match="query is required"):
            tool.validate_arguments({"query": "   "})

    def test_valid_query(self, tool):
        assert tool.validate_arguments({"query": "foo"}) is True


class TestSplitQuery:
    def test_file_tokens_separated_from_symbols(self):
        syms, files = _split_query("CodeGraphExploreTool execute api.py utils/")
        assert "CodeGraphExploreTool" in syms
        assert "execute" in syms
        assert "api.py" in files
        assert "utils/" in files

    def test_short_tokens_dropped(self):
        syms, files = _split_query("a foo")
        assert syms == ["foo"]
        assert files == []


class TestExecuteDegraded:
    @pytest.mark.asyncio
    async def test_no_project_root_returns_warn(self, tool):
        result = await tool.execute({"query": "foo", "output_format": "json"})
        assert result["verdict"] == "WARN"
        assert result["files"] == []
        assert "project_root" in result["hint"]

    @pytest.mark.asyncio
    async def test_empty_cache_returns_warn(self, tool_with_root):
        with _patch_cache_with(total_files=0):
            result = await tool_with_root.execute(
                {"query": "foo", "output_format": "json"}
            )
        assert result["verdict"] == "WARN"
        assert (
            "autoindex" in result["hint"].lower()
            or "ast cache" in result["hint"].lower()
        )


class TestExecuteNotFound:
    @pytest.mark.asyncio
    async def test_zero_matches_returns_not_found(self, tool_with_root):
        with _patch_cache_with(), _patch_resolver_with({}):
            result = await tool_with_root.execute(
                {"query": "no_such_symbol", "output_format": "json"}
            )
        assert result["verdict"] == "NOT_FOUND"
        assert result["files"] == []
        assert "codegraph_symbol_search" in result["hint"]
        assert result["stats"]["symbols_resolved"] == 0

    @pytest.mark.asyncio
    async def test_zero_symbol_matches_returns_concept_matches(self, tool_with_root):
        concept_files = [
            {
                "file_path": "src/activation.ts",
                "language": "typescript",
                "symbols": [],
                "matches": [
                    {
                        "line": 10,
                        "text": "activationEvents",
                        "terms": ["activationevents"],
                    }
                ],
                "matched_terms": ["activationevents"],
            }
        ]
        with (
            _patch_cache_with(),
            _patch_resolver_with({}),
            patch(
                "tree_sitter_analyzer.mcp.tools.codegraph_explore_tool._h.concept_search",
                return_value=concept_files,
            ),
        ):
            result = await tool_with_root.execute(
                {"query": "activationEvents", "output_format": "json"}
            )

        assert result["verdict"] == "INFO"
        assert result["files"] == concept_files
        assert result["stats"]["concept_files_returned"] == 1
        assert "concept matches" in result["hint"]


class TestExecuteHappyPath:
    @pytest.mark.asyncio
    async def test_two_defs_in_two_files_returns_info(self, tool_with_root, tmp_path):
        # Create the actual source files so _extract_snippet can read them.
        a = tmp_path / "alpha.py"
        a.write_text("def alpha():\n    return 1\n")
        b = tmp_path / "beta.py"
        b.write_text("def beta():\n    return 2\n")

        defs = {
            "alpha": [_make_def(str(a), "alpha", line=1, end_line=2)],
            "beta": [_make_def(str(b), "beta", line=1, end_line=2)],
        }
        with _patch_cache_with(), _patch_resolver_with(defs):
            result = await tool_with_root.execute(
                {"query": "alpha beta", "output_format": "json"}
            )

        assert result["verdict"] == "INFO"
        assert len(result["files"]) == 2
        assert result["stats"]["symbols_returned"] == 2
        files_by_path = {f["file_path"]: f for f in result["files"]}
        assert any("code" in s for s in files_by_path[str(a)]["symbols"])

    @pytest.mark.asyncio
    async def test_max_files_cap_trims(self, tool_with_root, tmp_path):
        # 2 defs in 2 files but maxFiles=1 → only 1 file returned.
        a = tmp_path / "alpha.py"
        a.write_text("def alpha():\n    return 1\n")
        b = tmp_path / "beta.py"
        b.write_text("def beta():\n    return 2\n")

        defs = {
            "alpha": [_make_def(str(a), "alpha", line=1, end_line=2)],
            "beta": [_make_def(str(b), "beta", line=1, end_line=2)],
        }
        with _patch_cache_with(), _patch_resolver_with(defs):
            result = await tool_with_root.execute(
                {"query": "alpha beta", "maxFiles": 1, "output_format": "json"}
            )

        assert result["verdict"] == "INFO"
        assert len(result["files"]) == 1

    @pytest.mark.asyncio
    async def test_include_code_false_omits_snippets(self, tool_with_root, tmp_path):
        a = tmp_path / "alpha.py"
        a.write_text("def alpha():\n    return 1\n")
        defs = {"alpha": [_make_def(str(a), "alpha", line=1, end_line=2)]}
        with _patch_cache_with(), _patch_resolver_with(defs):
            result = await tool_with_root.execute(
                {"query": "alpha", "includeCode": False, "output_format": "json"}
            )

        assert result["verdict"] in ("INFO",)
        for f in result["files"]:
            for sym in f["symbols"]:
                assert "code" not in sym or not sym["code"]

    @pytest.mark.asyncio
    async def test_relationships_use_sql_cache_not_full_graph(
        self, tool_with_root, tmp_path
    ):
        a = tmp_path / "alpha.py"
        a.write_text("def alpha():\n    beta()\n")
        defs = {"alpha": [_make_def(str(a), "alpha", line=1, end_line=2)]}

        mock_cache = MagicMock()
        mock_cache.get_stats.return_value = {"total_files": 1}
        mock_cache.query_callers.return_value = [
            {"caller_name": "caller_one"},
            {"caller_name": "caller_one"},
        ]
        mock_cache.query_callees.return_value = [{"callee_name": "beta"}]

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
            _patch_resolver_with(defs),
            patch.object(
                tool_with_root,
                "_get_call_graph",
                side_effect=AssertionError("full graph build should not run"),
            ),
        ):
            result = await tool_with_root.execute(
                {"query": "alpha", "output_format": "json"}
            )

        symbol = result["files"][0]["symbols"][0]
        assert symbol["callers"] == ["caller_one"]
        assert symbol["callees"] == ["beta"]


class TestExecuteOutputFormat:
    @pytest.mark.asyncio
    async def test_toon_format_default(self, tool):
        result = await tool.execute({"query": "foo"})
        assert result["format"] == "toon"
        assert "toon_content" in result

    @pytest.mark.asyncio
    async def test_json_format_no_toon_blob(self, tool):
        result = await tool.execute({"query": "foo", "output_format": "json"})
        assert "toon_content" not in result
        assert result["verdict"] == "WARN"


class TestExtractSnippet:
    def test_valid_range(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("line1\nline2\nline3\n")
        assert _extract_snippet(str(f), 1, 2) == "line1\nline2\n"

    def test_missing_file_returns_empty(self, tmp_path):
        assert _extract_snippet(str(tmp_path / "nope.py"), 1, 1) == ""

    def test_invalid_range_returns_empty(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("only one line\n")
        assert _extract_snippet(str(f), 5, 10) == ""


class TestConceptSearch:
    def test_ranks_src_multi_term_match_above_test_fixture(self, tmp_path):
        src = tmp_path / "src/vs/platform/markers/common/markerService.ts"
        src.parent.mkdir(parents=True)
        src.write_text(
            "export class MarkerService {\n"
            "  public readDiagnosticsMarkerService() { return true; }\n"
            "}\n",
            encoding="utf-8",
        )
        fixture = tmp_path / "extensions/copilot/test/fixtures/service.ts"
        fixture.parent.mkdir(parents=True)
        fixture.write_text(
            "export function service() { return diagnostics; }\n", encoding="utf-8"
        )

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """CREATE TABLE ast_index (
                file_path TEXT,
                language TEXT,
                file_size INTEGER,
                symbols_json TEXT
            )"""
        )
        for path in (fixture, src):
            rel = path.relative_to(tmp_path).as_posix()
            conn.execute(
                "INSERT INTO ast_index VALUES (?, ?, ?, ?)",
                (
                    rel,
                    "typescript",
                    path.stat().st_size,
                    json.dumps(
                        {"symbols": [{"name": path.stem, "kind": "class", "line": 1}]}
                    ),
                ),
            )

        cache = MagicMock()
        cache._get_conn.return_value = conn
        result = helpers.concept_search(
            cache,
            ["diagnostics", "marker", "service"],
            [],
            str(tmp_path),
            max_files=2,
        )

        assert (
            result[0]["file_path"] == "src/vs/platform/markers/common/markerService.ts"
        )
        assert result[0]["matches"]
        assert result[0]["symbols"][0]["name"] == "markerService"
