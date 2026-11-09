"""§12 的 agent 原生面是产品契约：任何一项被删掉都必须让 CI 变红。

这些能力不是可选装饰——agent 的「重问几乎免费」和「空答案带证明」直接依赖它们。
本契约只断言**面存在且形状正确**（结构棘轮），行为正确性由各自的单元测试保证。
"""

from __future__ import annotations


def _callers_schema_properties() -> dict:
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    return CodeGraphCallersTool(".").get_tool_schema()["properties"]


def _callees_schema_properties() -> dict:
    from tree_sitter_analyzer.mcp.tools.callees_tool import CodeGraphCalleesTool

    return CodeGraphCalleesTool(".").get_tool_schema()["properties"]


def test_callers_exposes_the_incremental_parameters() -> None:
    properties = _callers_schema_properties()

    assert {"if_none_match", "previous_entries"} <= set(properties)


def test_callees_exposes_if_none_match() -> None:
    assert "if_none_match" in _callees_schema_properties()


def test_every_relation_answer_honours_the_etag_protocol() -> None:
    from tree_sitter_analyzer.mcp.tools.callees_tool import (
        answer_etag as callees_etag,
    )
    from tree_sitter_analyzer.mcp.tools.callers_tool import (
        answer_etag as callers_etag,
    )

    sample = {
        "function": "f",
        "callee_count": 1,
        "caller_count": 1,
        "completeness": "complete",
    }

    assert callers_etag(dict(sample)) == callers_etag({**sample, "elapsed_ms": 3})
    assert callees_etag(dict(sample)) == callees_etag({**sample, "elapsed_ms": 3})


def test_callers_answers_carry_an_absence_rule() -> None:
    from tree_sitter_analyzer.mcp.tools.callers_tool import absence_certificate

    certificate = absence_certificate({"caller_count": 0, "completeness": "complete"})
    assert (certificate["kind"], certificate["confidence"]) == (
        "unreferenced",
        "proven",
    )
    assert absence_certificate({"caller_count": 0, "verdict": "NOT_FOUND"}) is None


def test_test_map_certifies_untested_and_carries_an_etag() -> None:
    from tree_sitter_analyzer.mcp.tools.nav_facade import _test_map_etag

    first = _test_map_etag({"symbol": "f", "test_files": []}, "gen-1")
    second = _test_map_etag({"symbol": "f", "test_files": []}, "gen-2")

    assert (first.startswith("sha256:"), first != second) == (True, True)


def test_uql_hints_at_absence_instead_of_claiming_it() -> None:
    from tree_sitter_analyzer.uql import output

    hint = output._absence_hint(
        type(
            "Exec",
            (),
            {
                "stages": [
                    type(
                        "R",
                        (),
                        {
                            "op": "callers",
                            "count": 0,
                            "effective": type("E", (), {"complete": True})(),
                        },
                    )()
                ]
            },
        )(),
        1,
    )

    assert (hint["kind"], hint["confidence"]) == ("possibly_unreferenced", "possible")


def test_the_capability_manifest_stays_complete() -> None:
    from tree_sitter_analyzer.capabilities import build_capability_manifest

    manifest = build_capability_manifest(".")

    assert len(manifest["tools"]) == 8
    assert sum(len(tool["actions"]) for tool in manifest["tools"].values()) == 94
    assert manifest["tools"]["index"]["actions"]["build"]["preconditions"] == []


def test_the_capabilities_flag_is_wired_into_the_real_parser() -> None:
    from tree_sitter_analyzer.cli_main import create_argument_parser

    args = create_argument_parser().parse_args(["--capabilities", "nav.callers"])

    assert args.capabilities == "nav.callers"
