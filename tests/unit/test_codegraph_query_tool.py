"""Tests for codegraph_query_tool.py — chained graph query surface."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_query_tool import (
    CodeGraphQueryTool,
    parse_chain,
)
from tree_sitter_analyzer.symbol_resolver import DefinitionLocation, ResolveResult


def _make_def(
    file: str = "main.py",
    name: str = "run",
    kind: str = "function",
    line: int = 1,
    end_line: int = 2,
) -> DefinitionLocation:
    return DefinitionLocation(
        file=file,
        name=name,
        kind=kind,
        line=line,
        end_line=end_line,
        language="python",
    )


def _patch_resolver_with(defs_per_token: dict[str, list[DefinitionLocation]]):
    def _resolve(token: str) -> ResolveResult:
        return ResolveResult(symbol=token, definitions=defs_per_token.get(token, []))

    mock_resolver = MagicMock()
    mock_resolver.resolve.side_effect = _resolve
    return patch(
        "tree_sitter_analyzer.symbol_resolver.SymbolResolver",
        return_value=mock_resolver,
    )


class TestParseChain:
    def test_plain_query_expands_to_explore_related(self):
        steps = parse_chain("CommandService executeCommand")

        assert [step.name for step in steps] == ["explore", "related"]
        assert steps[0].args == ["CommandService executeCommand"]

    def test_parses_dotted_chain_without_splitting_inside_quotes(self):
        steps = parse_chain(
            "search('src/a.b.ts CommandService').explore(max_files=4).callees(depth=2)"
        )

        assert [step.name for step in steps] == ["search", "explore", "callees"]
        assert steps[0].args == ["src/a.b.ts CommandService"]
        assert steps[1].kwargs == {"max_files": 4}
        assert steps[2].kwargs == {"depth": 2}

    def test_rejects_unsupported_step(self):
        with pytest.raises(ValueError, match="unsupported chain step"):
            parse_chain("search('x').delete()")

    def test_parses_selection_and_terminal_steps(self):
        steps = parse_chain(
            "search('run').where(kind='function').paths('src app')."
            "exclude_tests().explore().end().why().answer()"
        )

        assert [step.name for step in steps] == [
            "search",
            "where",
            "paths",
            "exclude_tests",
            "explore",
            "end",
            "why",
            "answer",
        ]
        assert steps[1].kwargs == {"kind": "function"}

    def test_parses_list_literals_for_where(self):
        steps = parse_chain("search('run').where(kind=['function', 'method'])")

        assert steps[1].kwargs == {"kind": ["function", "method"]}


class TestCodeGraphQueryTool:
    def test_definition(self):
        definition = CodeGraphQueryTool().get_tool_definition()

        assert definition["name"] == "codegraph_query"
        assert definition["annotations"]["readOnlyHint"] is True

    def test_schema_requires_query(self):
        schema = CodeGraphQueryTool().get_tool_schema()

        assert schema["required"] == ["query"]
        assert schema["additionalProperties"] is False

    def test_validate_requires_query(self):
        with pytest.raises(ValueError, match="query is required"):
            CodeGraphQueryTool().validate_arguments({})

    @pytest.mark.asyncio
    async def test_execute_runs_chain_in_one_tool(self, tmp_path):
        source = tmp_path / "main.py"
        source.write_text(
            "def run():\n    return helper()\n\ndef helper():\n    return 1\n",
            encoding="utf-8",
        )
        mock_cache = MagicMock()
        mock_cache.query_callees.return_value = [
            {
                "caller_name": "run",
                "caller_file": "main.py",
                "caller_line": 1,
                "callee_name": "helper",
                "callee_file": "main.py",
                "callee_line": 4,
                "depth": 1,
            }
        ]
        mock_cache.query_callers.return_value = []

        with (
            patch(
                "tree_sitter_analyzer.ast_cache.ASTCache",
                return_value=mock_cache,
            ),
            _patch_resolver_with({"run": [_make_def(name="run")]}),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": "search('run').explore(max_files=2).callees(depth=1)",
                    "output_format": "json",
                }
            )

        assert result["success"] is True
        assert result["verdict"] == "INFO"
        assert result["stats"]["steps"] == 3
        assert result["stats"]["symbols_returned"] == 2
        assert result["files"][0]["file_path"] == "main.py"
        assert "code" in result["files"][0]["symbols"][0]
        assert (
            result["relationships"]["callees"]["main.py:1:run"][0]["name"] == "helper"
        )

    @pytest.mark.asyncio
    async def test_execute_uses_concept_fallback_for_unresolved_query(self, tmp_path):
        mock_cache = MagicMock()
        concept_files = [
            {
                "file_path": "tree.go",
                "language": "go",
                "symbols": [],
                "matches": [{"line": 42, "text": "type HandlerFunc func(*Context)"}],
                "matched_terms": ["handlerfunc"],
            }
        ]

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
            _patch_resolver_with({"HandlerFunc": []}),
            patch(
                "tree_sitter_analyzer.mcp.tools._codegraph_query_runtime._h.concept_search",
                return_value=concept_files,
            ) as concept_search,
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": "search('HandlerFunc').explore(max_files=2)",
                    "output_format": "json",
                }
            )

        assert result["success"] is True
        assert result["verdict"] == "INFO"
        assert result["files"] == concept_files
        concept_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_merges_concept_matches_for_broad_query(self, tmp_path):
        source = tmp_path / "main.py"
        source.write_text("def run():\n    return 1\n", encoding="utf-8")
        mock_cache = MagicMock()
        concept_files = [
            {
                "file_path": "types.go",
                "language": "go",
                "symbols": [],
                "matches": [{"line": 1, "text": "type HandlerFunc func(*Context)"}],
                "matched_terms": ["handlerfunc"],
            }
        ]

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
            _patch_resolver_with({"run": [_make_def(name="run")], "HandlerFunc": []}),
            patch(
                "tree_sitter_analyzer.mcp.tools._codegraph_query_runtime._h.concept_search",
                return_value=concept_files,
            ),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": "search('run HandlerFunc').explore(max_files=2)",
                    "output_format": "json",
                }
            )

        assert [entry["file_path"] for entry in result["files"]] == [
            "main.py",
            "types.go",
        ]

    @pytest.mark.asyncio
    async def test_execute_includes_truncated_code_for_long_symbol(self, tmp_path):
        source = tmp_path / "main.py"
        source.write_text(
            "\n".join(["def big():", *("    pass" for _ in range(220))]) + "\n",
            encoding="utf-8",
        )
        mock_cache = MagicMock()

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
            _patch_resolver_with(
                {"big": [_make_def(name="big", line=1, end_line=221)]}
            ),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": "search('big').explore(max_files=1)",
                    "output_format": "json",
                }
            )

        symbol = result["files"][0]["symbols"][0]
        assert symbol["truncated"] is True
        assert symbol["truncated_end_line"] == 160
        assert symbol["code"].startswith("def big():")

    @pytest.mark.asyncio
    async def test_execute_filters_selection_and_returns_answer_pack(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        app = src / "app.py"
        app.write_text("def run():\n    return 1\n", encoding="utf-8")
        test_file = tmp_path / "tests" / "test_app.py"
        test_file.parent.mkdir()
        test_file.write_text("def run():\n    return 1\n", encoding="utf-8")
        mock_cache = MagicMock()

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
            _patch_resolver_with(
                {
                    "run": [
                        _make_def(file="src/app.py", name="run", kind="function"),
                        _make_def(
                            file="tests/test_app.py", name="run", kind="function"
                        ),
                    ]
                }
            ),
        ):
            result = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": (
                        "search('run').where(kind='function').exclude_tests()."
                        "explore(max_files=4).why().answer()"
                    ),
                    "output_format": "json",
                }
            )

        assert [symbol["file"] for symbol in result["symbols"]] == ["src/app.py"]
        assert [entry["file_path"] for entry in result["files"]] == ["src/app.py"]
        assert result["answer_pack"]["stop_signal"] is True
        assert result["answer_pack"]["core_files"] == ["src/app.py"]
        assert result["query_plan"][-1]["step"]["name"] == "answer"

    @pytest.mark.asyncio
    async def test_execute_paths_filter_and_end_restore_previous_selection(
        self, tmp_path
    ):
        src = tmp_path / "src"
        other = tmp_path / "other"
        src.mkdir()
        other.mkdir()
        (src / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")
        (other / "app.py").write_text("def run():\n    return 2\n", encoding="utf-8")
        mock_cache = MagicMock()

        with (
            patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
            _patch_resolver_with(
                {
                    "run": [
                        _make_def(file="src/app.py", name="run"),
                        _make_def(file="other/app.py", name="run"),
                    ]
                }
            ),
        ):
            filtered = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": "search('run').paths('src').explore(max_files=4)",
                    "output_format": "json",
                }
            )
            restored = await CodeGraphQueryTool(str(tmp_path)).execute(
                {
                    "query": "search('run').paths('src').end().explore(max_files=4)",
                    "output_format": "json",
                }
            )

        assert [entry["file_path"] for entry in filtered["files"]] == ["src/app.py"]
        assert [entry["file_path"] for entry in restored["files"]] == [
            "src/app.py",
            "other/app.py",
        ]

    @pytest.mark.asyncio
    async def test_execute_returns_error_envelope_for_bad_chain(self):
        with patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=MagicMock()):
            result = await CodeGraphQueryTool("/tmp").execute(
                {
                    "query": "search('run').delete()",
                    "output_format": "json",
                }
            )

        assert result["success"] is False
        assert result["verdict"] == "ERROR"
        assert "unsupported chain step" in result["error"]
