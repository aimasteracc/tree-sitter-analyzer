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


async def test_new_unindexed_source_makes_absence_unknown(project: str) -> None:
    # RFC-0041 §3：未入索引的同语言新文件可能含有定义，0 行不是不存在的证据。
    (Path(project) / "pkg" / "late.py").write_text("def ghost():\n    pass\n")
    out = await _uql(project, "symbol('ghost')")
    assert (out["completeness"], out["completeness_reasons"]) == (
        "unknown",
        ["symbol:UNINDEXED_SOURCE_FILES"],
    )


async def test_new_unindexed_source_makes_found_rows_a_lower_bound(
    project: str,
) -> None:
    (Path(project) / "pkg" / "late.py").write_text("def target():\n    pass\n")
    out = await _uql(project, "symbol('target')")
    assert out["stages"][0]["c"] == "incomplete"


def test_unreadable_unindexed_check_is_unknown(project: str, monkeypatch) -> None:
    import tree_sitter_analyzer.mcp.tools.unindexed_sources as unindexed
    from tree_sitter_analyzer.uql.backends import IndexBackends

    monkeypatch.setattr(unindexed, "unindexed_source_files", lambda *a: None)
    gate = IndexBackends(project).source_gate([], frozenset({"python"}))
    assert (gate.status, gate.reasons) == ("unknown", ("UNINDEXED_SOURCE_UNCHECKED",))


def test_definition_count_counts_indexed_definitions(project: str) -> None:
    from tree_sitter_analyzer.uql.backends import IndexBackends

    backends = IndexBackends(project)
    assert (backends.definition_count("target"), backends.definition_count("nope")) == (
        1,
        0,
    )


async def test_same_file_callees_are_listed(project: str) -> None:
    # #1814：`helper` 调用同文件的 `target`（`callee_resolution: "local"`），曾被当作
    # 未解析丢弃、阶段标为 CALLEE_UNRESOLVED。nav callees 不做覆盖声明，故为 unknown。
    out = await _uql(project, "symbol('helper', file='pkg/core.py').callees()")
    assert (out["results"]["callees"], out["stages"][1]) == (
        ["pkg/core.py target"],
        {"op": "callees", "n": 1, "c": "unknown", "r": ["CALLEES_COVERAGE_UNREPORTED"]},
    )


async def test_missing_project_root_is_a_typed_error() -> None:
    out = await UqlTool(None).execute({"query": "symbol('f')"})
    assert (out["error_code"], out["error"]) == (
        "UQL_INDEX_UNAVAILABLE",
        "Project root not set. Call set_project_path first.",
    )


async def test_unlisted_edited_file_blocks_a_complete_census(project: str) -> None:
    # Codex P1 on #1802: an edit outside the returned files (renaming outer to
    # target without re-indexing) must not leave symbol('target') complete.
    other = Path(project) / "pkg" / "other.py"
    other.write_text(
        "from pkg.core import helper\n\n\ndef target():\n    return helper()\n"
    )
    out = await _uql(project, "symbol('target')")
    assert (out["stages"][0]["c"], out["completeness_reasons"]) == (
        "incomplete",
        ["symbol:SOURCE_INDEX_MISMATCH"],
    )


def test_full_recheck_past_its_deadline_names_the_deadline(
    project: str, monkeypatch
) -> None:
    # RFC-0041 §3：全量复核超出 2 s 期限时降级为 unknown，原因码点名期限而不是泛泛的未知。
    import tree_sitter_analyzer.mcp.tools.relation_freshness as freshness
    from tree_sitter_analyzer.uql.backends import IndexBackends

    # 确定性地模拟“复核超时”：复核返回范围未知，期限设为 0（不依赖机器速度）。
    monkeypatch.setattr(freshness, "_ABSENCE_SCAN_DEADLINE_SECONDS", 0.0)
    monkeypatch.setattr(
        freshness,
        "relation_source_evidence",
        lambda *a, **k: (
            {"freshness": "unknown", "reason": freshness.UNKNOWN_REASON},
            [],
        ),
    )
    gate = IndexBackends(project).source_gate(["pkg/core.py"], frozenset({"python"}))
    assert (gate.status, gate.reasons) == ("unknown", ("SOURCE_RECHECK_DEADLINE",))


async def test_backend_single_callers_is_a_one_element_batch(project: str) -> None:
    from tree_sitter_analyzer.uql.backends import IndexBackends

    backends = IndexBackends(project)
    single = await backends.callers("target", "pkg/core.py")
    (batched,) = await backends.callers_many([("target", "pkg/core.py")])
    assert (single["caller_count"], single == batched) == (2, True)


def test_definition_kinds_reads_indexed_kinds(project: str) -> None:
    from tree_sitter_analyzer.uql.backends import IndexBackends

    kinds = IndexBackends(project).definition_kinds(
        [("pkg/core.py", 5, "helper"), ("pkg/core.py", 99, "nope")]
    )
    assert kinds == {("pkg/core.py", 5, "helper"): "function"}


def test_definition_kinds_unreadable_index_is_empty(project: str, monkeypatch) -> None:
    import sqlite3

    from tree_sitter_analyzer.uql.backends import IndexBackends

    backends = IndexBackends(project)

    def broken():
        raise sqlite3.OperationalError("locked")

    monkeypatch.setattr(backends.cache, "get_conn", broken)
    assert backends.definition_kinds([("pkg/core.py", 5, "helper")]) == {}
