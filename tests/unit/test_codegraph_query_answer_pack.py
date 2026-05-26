"""Tests for codegraph_query answer-pack and planner output."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_query_tool import CodeGraphQueryTool
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


@pytest.mark.asyncio
async def test_answer_pack_v2_contains_stop_decision_and_citations(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    app = src / "app.py"
    app.write_text("def run():\n    return 1\n", encoding="utf-8")
    mock_cache = MagicMock()

    with (
        patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
        _patch_resolver_with(
            {"run": [_make_def(file="src/app.py", name="run", kind="function")]}
        ),
    ):
        result = await CodeGraphQueryTool(str(tmp_path)).execute(
            {
                "query": "search('run').explore(max_files=2).answer()",
                "output_format": "json",
            }
        )

    pack = result["answer_pack"]
    assert pack["version"] == 2
    assert pack["decision"]["should_stop"] is True
    assert pack["decision"]["followup_allowed"] is False
    assert pack["coverage"]["has_code"] is True
    assert pack["coverage"]["file_count"] == 1
    assert pack["citations"][0] == {
        "file": "src/app.py",
        "line": 1,
        "symbol": "run",
        "source": "symbol",
    }
    assert pack["core_path"][0]["name"] == "run"


@pytest.mark.asyncio
async def test_query_planner_reports_intent_budget_and_execution_steps(tmp_path):
    source = tmp_path / "gin.py"
    source.write_text("def ServeHTTP():\n    return None\n", encoding="utf-8")
    mock_cache = MagicMock()

    with (
        patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache),
        _patch_resolver_with(
            {"ServeHTTP": [_make_def(file="gin.py", name="ServeHTTP")]}
        ),
    ):
        result = await CodeGraphQueryTool(str(tmp_path)).execute(
            {
                "query": (
                    "flow('request routing').prefer(exclude_tests=True).why().answer()"
                ),
                "output_format": "json",
            }
        )

    planner = result["query_planner"]
    assert planner["intent"] == "flow"
    assert planner["budget"] == {
        "max_cli_calls": 1,
        "max_followups": 0,
        "should_stop": True,
    }
    assert planner["signals"]["raw_reads_allowed"] is False
    assert planner["signals"]["exclude_tests_applied"] is True
    assert planner["execution_steps"] == result["query_plan"]
