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
    line: int = 1,
    end_line: int = 2,
) -> DefinitionLocation:
    return DefinitionLocation(
        file=file,
        name=name,
        kind="function",
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
