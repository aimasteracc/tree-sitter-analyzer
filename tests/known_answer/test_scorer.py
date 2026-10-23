"""``scripts.wrong_complete.scorer`` 的单元测试：评分器自身必须可信。"""

from __future__ import annotations

from typing import Any

import pytest

from scripts.wrong_complete.scorer import (
    ListedCaller,
    caller_keys,
    evidence_keys,
    listed_callers,
    normalize_path,
    score,
)
from scripts.wrong_complete.sites import OTHER, POSSIBLE, TARGET, Site

_SITE = Site("pkg/use.py", 9, "call", POSSIBLE, "unresolved_receiver", "build")
_PY = "def build(schema, plugins):\n    out = []\n    for p in plugins:\n        out.append(p.m())\n    return out\n"


def _answer(completeness: str, **fields: Any) -> dict[str, Any]:
    return {"completeness": completeness, **fields}


def _caller(
    line: int, end_line: int | None, name: str = "build", file: str = "pkg/use.py"
) -> dict[str, Any]:
    return {"file": file, "name": name, "line": line, "end_line": end_line}


def test_a_complete_answer_that_misses_a_possible_site_is_wrong() -> None:
    # #1772：complete, 0 而未证明接收者的调用点不在任何字段里。
    result = score(_answer("complete", callers=[]), [_SITE])
    assert [s.key() for s in result.wrong_complete] == [("pkg/use.py", 9)]


def test_a_non_complete_answer_is_never_a_wrong_complete() -> None:
    result = score(_answer("unknown", callers=[]), [_SITE])
    assert result.wrong_complete == ()


def test_a_silent_site_is_reported_as_silent() -> None:
    result = score(_answer("unknown", callers=[]), [_SITE])
    assert [s.key() for s in result.silent] == [("pkg/use.py", 9)]


def test_a_site_in_an_evidence_field_is_evidenced() -> None:
    answer = _answer("unknown", name_only_sites=[{"file": "pkg/use.py", "line": 9}])
    assert [s.key() for s in score(answer, [_SITE]).evidenced] == [("pkg/use.py", 9)]


def test_an_evidenced_site_still_makes_a_complete_answer_wrong() -> None:
    # 证据字段不能替代列出：complete 必须把调用方列出来。
    answer = _answer("complete", unresolved_sites=[{"file": "pkg/use.py", "line": 9}])
    assert [s.key() for s in score(answer, [_SITE]).wrong_complete] == [
        ("pkg/use.py", 9)
    ]


@pytest.mark.parametrize(
    ("line", "end_line", "covered"),
    [(6, 10, True), (9, 9, True), (10, 12, False), (1, 8, False)],
)
def test_a_listed_caller_covers_sites_inside_its_span(
    line: int, end_line: int, covered: bool
) -> None:
    result = score(_answer("complete", callers=[_caller(line, end_line)]), [_SITE])
    assert (result.wrong_complete == ()) is covered


def test_a_caller_in_another_file_does_not_cover() -> None:
    answer = _answer("complete", callers=[_caller(1, 99, file="pkg/other.py")])
    assert [s.key() for s in score(answer, [_SITE]).wrong_complete] == [
        ("pkg/use.py", 9)
    ]


def test_other_verdict_sites_need_no_coverage() -> None:
    other = Site("pkg/use.py", 9, "call", OTHER, "constructed_other", "build")
    assert score(_answer("complete", callers=[]), [other]).wrong_complete == ()


def test_a_python_caller_without_end_line_gets_its_span_from_ast() -> None:
    # SQL 快路径的 callers 行不带 end_line。
    site = Site("pkg/use.py", 4, "call", TARGET, "self", "build")
    answer = _answer("complete", callers=[_caller(1, None)])
    assert score(answer, [site], {"pkg/use.py": _PY}).wrong_complete == ()


def test_a_caller_without_end_line_and_without_source_is_one_line() -> None:
    site = Site("pkg/use.py", 4, "call", TARGET, "self", "build")
    answer = _answer("complete", callers=[_caller(1, None)])
    assert [s.key() for s in score(answer, [site]).wrong_complete] == [
        ("pkg/use.py", 4)
    ]


def test_a_ts_caller_without_end_line_gets_its_span_from_braces() -> None:
    text = "export function install() {\n  const s = '}';\n  return cors();\n}\nexport const x = 1;\n"
    callers = listed_callers(
        _answer("complete", callers=[_caller(1, None, "install", "src/app.ts")]),
        {"src/app.ts": text},
    )
    assert callers == [ListedCaller("src/app.ts", "install", 1, 4)]


def test_a_module_caller_without_a_line_covers_module_level_sites_only() -> None:
    module_site = Site("pkg/use.py", 9, "call", TARGET, "module_function", "<module>")
    answer = _answer("complete", callers=[_caller(0, None, "<module>")])
    assert score(answer, [module_site, _SITE]).wrong_complete == (_SITE,)


def test_a_module_caller_with_a_call_line_covers_that_line() -> None:
    # ``module_scope_caller``：``<module>`` 调用方的 line / end_line 就是调用行。
    module_site = Site("pkg/use.py", 3, "call", TARGET, "module_function", "<module>")
    answer = _answer("complete", callers=[_caller(3, 3, "<module>")])
    assert score(answer, [module_site, _SITE]).wrong_complete == (_SITE,)


def test_backslash_paths_are_normalised() -> None:
    assert normalize_path("pkg\\use.py") == "pkg/use.py"


def test_evidence_keys_collect_every_evidence_field() -> None:
    answer = {
        "name_only_sites": [{"file": "a.py", "line": 1}],
        "unresolved_sites": [{"file": "b.py", "line": 2}],
        "unresolved_inbound_sites": [{"file": "c.py", "line": 3}],
        "excluded_sites": [{"file": "d.py", "line": 4}],
        "non_call_reference_sites": [{"file": "e.py", "line": 5}],
    }
    assert evidence_keys(answer) == {
        ("a.py", 1),
        ("b.py", 2),
        ("c.py", 3),
        ("d.py", 4),
        ("e.py", 5),
    }


def test_caller_keys_are_file_and_name() -> None:
    answer = _answer(
        "complete", callers=[_caller(1, 2), _caller(5, 6, "run", "pkg\\x.py")]
    )
    assert caller_keys(answer) == frozenset(
        {("pkg/use.py", "build"), ("pkg/x.py", "run")}
    )
