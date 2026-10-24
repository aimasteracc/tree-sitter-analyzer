"""基于真实索引的 RFC-0041 ``search action=uql``：契约与适配器一致性。"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit._ast_cache_helpers import legacy_cache
from tree_sitter_analyzer.mcp.tools.search_facade import build_search_facade
from tree_sitter_analyzer.mcp.tools.uql_tool import QUERY_DESCRIPTION, UqlTool

_FILES = {
    "pkg/__init__.py": "",
    "pkg/core.py": (
        "def target(x):\n"
        "    return x + 1\n"
        "\n"
        "\n"
        "def helper():\n"
        "    return target(1)\n"
        "\n"
        "\n"
        "class Runner:\n"
        "    def run(self):\n"
        "        return helper()\n"
    ),
    "pkg/other.py": (
        "from pkg.core import helper\n\n\ndef outer():\n    return helper()\n"
    ),
    "tests/test_core.py": (
        "from pkg.core import helper, target\n"
        "\n"
        "\n"
        "def test_target():\n"
        "    assert target(1) == 2\n"
        "\n"
        "\n"
        "def _assist():\n"
        "    return helper()\n"
        "\n"
        "\n"
        "def test_helper():\n"
        "    assert _assist() == 2\n"
    ),
}


@pytest.fixture
def project(tmp_path: Path) -> str:
    for rel, body in _FILES.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    cache = legacy_cache(str(tmp_path))
    try:
        cache.index_project()
    finally:
        cache.close()
    return str(tmp_path)


async def _uql(root: str, query: str, **extra) -> dict:
    return await build_search_facade(root).execute(
        {"action": "uql", "query": query, "limit": 500, **extra}
    )


def _labels(payload: dict, group: str) -> list[str]:
    return sorted(payload["results"][group])


async def test_callers_group_lists_direct_callers(project: str) -> None:
    out = await _uql(project, "symbol('target').callers()")
    assert _labels(out, "callers") == [
        "pkg/core.py:5 helper",
        "tests/test_core.py:4 test_target",
    ]


async def test_callers_stage_consumes_nav_callers_completeness_as_is(
    project: str,
) -> None:
    from tree_sitter_analyzer.mcp.tools.nav_facade import build_nav_facade

    nav = await build_nav_facade(project).execute(
        {"action": "callers", "function_name": "target", "include_bodies": False}
    )
    out = await _uql(project, "symbol('target').callers()")
    stage = out["stages"][1]
    assert (stage["c"], stage.get("r", [])) == (
        nav["completeness"],
        nav["completeness_reasons"],
    )


async def test_tests_relation_walks_test_helper(project: str) -> None:
    out = await _uql(project, "symbol('helper').tests()")
    assert _labels(out, "tests") == ["tests/test_core.py:12 test_helper"]


async def test_total_is_complete_only_if_every_stage_is(project: str) -> None:
    out = await _uql(project, "symbol('target').callers().tests()")
    rank = {"complete": 0, "incomplete": 1, "unknown": 2}
    worst = max((s["c"] for s in out["stages"]), key=rank.__getitem__)
    assert out["completeness"] == worst


async def test_tql_execute_and_uql_select_return_the_same_symbols(
    project: str,
) -> None:
    facade = build_search_facade(project)
    tql = await facade.execute(
        {"action": "tql_execute", "selector": ".function:in(pkg/)", "max_results": 1000}
    )
    out = await _uql(project, ".function:in(pkg/)")
    legacy = sorted(f"{s['file']}:{s['line']} {s['name']}" for s in tql["symbols"])
    unified = sorted(
        label.split(" ")[0] + " " + label.split(" ")[1].split(".")[-1]
        for label in out["results"]["select"]
    )
    assert unified == legacy


async def test_chain_and_uql_callers_agree(project: str) -> None:
    facade = build_search_facade(project)
    chain = await facade.execute(
        {"action": "chain", "query": "search('target').callers()", "compact": True}
    )
    out = await _uql(project, "search('target').callers()")
    legacy = sorted(
        {
            f"{s['file']}:{s['line']} {s['name']}"
            for s in chain["symbols"]
            if s.get("depth")
        }
    )
    assert _labels(out, "callers") == legacy


async def test_unknown_pseudo_class_is_rejected_identically_by_both_adapters(
    project: str,
) -> None:
    facade = build_search_facade(project)
    tql = await facade.execute(
        {"action": "tql_execute", "selector": ".function:cals(#x)"}
    )
    out = await _uql(project, ".function:cals(#x)")
    assert (tql["error_code"], tql["fixed_selector"]) == (
        out["error_code"],
        out["error_detail"]["fixed_query"],
    )


async def test_missing_index_is_a_typed_error(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def f():\n    pass\n", encoding="utf-8")
    out = await UqlTool(str(tmp_path)).execute({"query": "symbol('f')"})
    assert (out["success"], out["error_code"], out["completeness"]) == (
        False,
        "UQL_INDEX_UNAVAILABLE",
        "unknown",
    )


def test_tool_schema_is_strict_and_requires_query() -> None:
    schema = UqlTool(None).get_tool_definition()["inputSchema"]
    assert (
        schema["required"],
        schema["additionalProperties"],
        sorted(schema["properties"]),
    ) == (
        ["query"],
        False,
        ["cursor", "detail", "limit", "output_format", "query"],
    )


async def test_help_serves_the_grammar_card() -> None:
    help_out = await build_search_facade(None).execute(
        {"action": "help", "target_action": "uql"}
    )
    assert help_out["action_schema"]["properties"]["query"]["description"] == (
        QUERY_DESCRIPTION
    )


def test_search_facade_advertises_uql_action() -> None:
    schema = build_search_facade(None).get_tool_definition()["inputSchema"]
    assert "uql" in schema["properties"]["action"]["enum"]
