"""RFC-0041 §4：有界的 compact 输出、分页与续页句柄。"""

from __future__ import annotations

import asyncio
import json

import pytest

from tests.unit.uql._fake_backends import FakeBackends, callers_payload, sym
from tree_sitter_analyzer.uql import answer
from tree_sitter_analyzer.uql.output import canonical, encode_cursor, query_digest
from tree_sitter_analyzer.uql.parser import parse_query


def _answer(args: dict, fb: FakeBackends) -> dict:
    return asyncio.run(answer(args, fb))


def _five_callers(**kw) -> FakeBackends:
    rows = [(f"c{i}", "src/b.py", 10 + i) for i in range(5)]
    return FakeBackends({"t": [sym("t")]}, {"t": callers_payload(*rows)}, **kw)


Q = "symbol('t').callers()"


def _key(text: str) -> str:
    return canonical(parse_query(text).value)  # type: ignore[union-attr]


def test_compact_rows_are_file_line_name_strings() -> None:
    out = _answer({"query": Q}, _five_callers())
    assert out["results"]["callers"][:2] == ["src/b.py:10 c0", "src/b.py:11 c1"]


def test_class_qualified_label() -> None:
    fb = FakeBackends({"m": [sym("m", **{"class": "Cls"})]})
    out = _answer({"query": "symbol('m')"}, fb)
    assert out["results"]["symbol"] == ["src/a.py:1 Cls.m"]


def test_first_page_is_bounded_and_returns_a_cursor() -> None:
    out = _answer({"query": Q, "limit": 4}, _five_callers())
    assert (
        out["page"]["returned"],
        out["page"]["total"],
        out["page"]["next_cursor"],
    ) == (
        4,
        6,
        encode_cursor(_key(Q), 4, "gen-1"),
    )


def test_pages_concatenate_to_the_whole_answer() -> None:
    fb = _five_callers()
    first = _answer({"query": Q, "limit": 4}, fb)
    second = _answer(
        {"query": Q, "limit": 4, "cursor": first["page"]["next_cursor"]}, fb
    )
    rows = [r for page in (first, second) for g in page["results"].values() for r in g]
    whole = _answer({"query": Q, "limit": 50}, fb)
    assert rows == [r for g in whole["results"].values() for r in g]


def test_last_page_has_no_cursor() -> None:
    fb = _five_callers()
    first = _answer({"query": Q, "limit": 4}, fb)
    second = _answer(
        {"query": Q, "limit": 4, "cursor": first["page"]["next_cursor"]}, fb
    )
    assert second["page"]["next_cursor"] is None


def test_paging_does_not_change_completeness() -> None:
    out = _answer({"query": Q, "limit": 1}, _five_callers())
    assert out["completeness"] == "complete"


def test_cursor_from_another_query_is_rejected() -> None:
    cursor = encode_cursor(_key("symbol('other')"), 1, "gen-1")
    out = _answer({"query": Q, "cursor": cursor}, _five_callers())
    assert out["error_code"] == "UQL_INVALID_CURSOR"


def test_malformed_cursor_is_rejected() -> None:
    out = _answer({"query": Q, "cursor": "uql1:!!!"}, _five_callers())
    assert out["error_code"] == "UQL_INVALID_CURSOR"


def test_cursor_from_another_generation_is_stale() -> None:
    cursor = encode_cursor(_key(Q), 2, "gen-0")
    out = _answer({"query": Q, "cursor": cursor}, _five_callers())
    assert out["error_code"] == "UQL_STALE_CURSOR"


def test_unverifiable_generation_downgrades_continuation_pages() -> None:
    fb = _five_callers(generation=None)
    cursor = encode_cursor(_key(Q), 2, None)
    out = _answer({"query": Q, "cursor": cursor}, fb)
    assert (out["completeness"], out["completeness_reasons"]) == (
        "incomplete",
        ["page:CURSOR_GENERATION_UNVERIFIED"],
    )


def test_evidence_handles_only_for_non_complete_inputs() -> None:
    fb = FakeBackends(
        {"t": [sym("t")]},
        {
            "t": callers_payload(
                ("a", "src/b.py", 2), completeness="unknown", reasons=("X",)
            )
        },
    )
    out = _answer({"query": Q}, fb)
    assert out["evidence"] == [
        {
            "stage": "callers",
            "nav": {"action": "callers", "function_name": "t"},
            "r": ["X"],
        }
    ]


def test_complete_answer_carries_no_evidence_block() -> None:
    assert "evidence" not in _answer({"query": Q}, _five_callers())


def test_full_detail_returns_structured_rows_with_provenance() -> None:
    out = _answer({"query": Q, "detail": "full"}, _five_callers())
    assert out["results"]["callers"][0] == {
        "name": "c0",
        "file": "src/b.py",
        "line": 10,
        "depth": 1,
        "via": "src/a.py:1:t",
    }


def test_compact_is_smaller_than_full() -> None:
    fb = _five_callers()
    compact = json.dumps(_answer({"query": Q}, fb))
    full = json.dumps(_answer({"query": Q, "detail": "full"}, fb))
    assert len(compact) < len(full)


def test_invalid_limit_is_typed_tool_argument_error() -> None:
    out = _answer({"query": Q, "limit": 0}, _five_callers())
    assert out["error_code"] == "UQL_INVALID_TOOL_ARGUMENT"


def test_parse_error_payload_keeps_fixed_query() -> None:
    out = _answer({"query": "symbol('t') | callers()"}, _five_callers())
    assert (out["success"], out["error_detail"]["fixed_query"]) == (
        False,
        "symbol('t').callers()",
    )


def test_cursor_is_bound_to_the_ir_not_the_spelling() -> None:
    # #1801 上的 Codex P2：answer 缓存按 IR 共享同一条目，因此一种写法产生的
    # 游标必须能续接另一种写法。
    fb = _five_callers()
    first = _answer({"query": "symbol('t').callers()", "limit": 4}, fb)
    out = _answer(
        {"query": 'symbol("t").callers()', "cursor": first["page"]["next_cursor"]}, fb
    )
    assert (out["success"], out["page"]["offset"]) == (True, 4)


@pytest.mark.parametrize(
    "payload",
    [b"[1]", b'{"q": "x"}'],
)
def test_cursor_with_wrong_payload_shape_is_rejected(payload: bytes) -> None:
    import base64

    cursor = "uql1:" + base64.urlsafe_b64encode(payload).decode().rstrip("=")
    out = _answer({"query": Q, "cursor": cursor}, _five_callers())
    assert out["error_code"] == "UQL_INVALID_CURSOR"


def test_cursor_with_negative_offset_is_rejected() -> None:
    import base64
    import json as _json

    body = _json.dumps({"q": query_digest(_key(Q)), "o": -1, "g": None}).encode()
    cursor = "uql1:" + base64.urlsafe_b64encode(body).decode().rstrip("=")
    out = _answer({"query": Q, "cursor": cursor}, _five_callers())
    assert out["error_code"] == "UQL_INVALID_CURSOR"


def test_cursor_with_non_string_generation_is_rejected() -> None:
    import base64
    import json as _json

    body = _json.dumps({"q": query_digest(_key(Q)), "o": 1, "g": 5}).encode()
    cursor = "uql1:" + base64.urlsafe_b64encode(body).decode().rstrip("=")
    out = _answer({"query": Q, "cursor": cursor}, _five_callers())
    assert out["error_code"] == "UQL_INVALID_CURSOR"


def test_cursor_past_the_end_is_rejected() -> None:
    out = _answer(
        {"query": Q, "cursor": encode_cursor(_key(Q), 99, "gen-1")}, _five_callers()
    )
    assert out["error_code"] == "UQL_INVALID_CURSOR"


def test_integral_float_limit_is_accepted() -> None:
    out = _answer({"query": Q, "limit": 2.0}, _five_callers())
    assert out["page"]["returned"] == 2


def test_unknown_detail_level_is_a_typed_tool_error() -> None:
    out = _answer({"query": Q, "detail": "verbose"}, _five_callers())
    assert out["error_code"] == "UQL_INVALID_TOOL_ARGUMENT"


def test_full_detail_reports_class_and_indexed_files() -> None:
    fb = FakeBackends({"m": [sym("m", **{"class": "Cls"})]})
    out = _answer({"query": "symbol('m')", "detail": "full"}, fb)
    assert (out["results"]["symbol"][0]["class"], out["indexed_files"]) == ("Cls", 10)


def test_impact_output_splits_callers_tests_and_files() -> None:
    fb = FakeBackends(
        {"t": [sym("t")]},
        {
            "t": callers_payload(("a", "src/b.py", 2)),
            "a": callers_payload(("test_a", "tests/test_b.py", 4)),
        },
    )
    out = _answer({"query": "symbol('t').impact()"}, fb)
    assert (out["results"]["impact"], out["results"]["impact.tests"], out["files"]) == (
        ["src/b.py:2 a"],
        ["tests/test_b.py:4 test_a"],
        ["src/a.py", "src/b.py", "tests/test_b.py"],
    )


def test_unproven_selector_stage_carries_a_note() -> None:
    fb = FakeBackends(selection=[sym("a")])
    out = _answer({"query": ".function:calls(#t)"}, fb)
    assert out["stages"][0]["note"] == (
        "unproven predicates: :calls. :calls reads call edges without a coverage "
        "proof; symbol('X').callers() answers the same question with nav-callers "
        "completeness."
    )


def test_evidence_handles_are_capped_at_three() -> None:
    gap_payload = callers_payload(completeness="unknown", reasons=("X",))
    rows = [(f"c{i}", "src/b.py", i + 1) for i in range(5)]
    callers = {"t": callers_payload(*rows)} | {f"c{i}": gap_payload for i in range(5)}
    fb = FakeBackends({"t": [sym("t")]}, callers)
    out = _answer({"query": "symbol('t').callers().callers()"}, fb)
    assert len(out["evidence"]) == 3
