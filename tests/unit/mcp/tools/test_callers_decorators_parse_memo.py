"""RFC-0043 prototype: opt-in memo of the per-text tree-sitter decorator table.

The registering-decorator gate re-parsed the declaring file and walked its
whole tree on every gated query (zod: about 0.7 s per query on one large file).
With ``TSA_RESIDENT_PARSE_MEMO=1`` the walk's result is kept per
``(language, text digest)``: the text is still read live on every request, so
a changed file has a new digest and is parsed again. The answer for every line
must equal the unmemoized walk's answer.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools import callers_decorators as cd
from tree_sitter_analyzer.mcp.tools.callers_decorators import (
    Decorator,
    declaration_decorators,
)

_TS = (
    "import { Get, Injectable } from './decorators';\n"
    "@Injectable()\n"
    "export class A {\n"
    "  @Get(\n"
    "    '/x')\n"
    "  // note\n"
    "  target() { return 1; }\n"
    "  plain(@Param('id') id: string) { return 2; }\n"
    "  @Get('/y') @Other() both() { return 3; }\n"
    "}\n"
    "@Component({})\n"
    "export class Target {}\n"
    "function free() { return 0; }\n"
)
_JAVA = (
    "@Service\n"
    "class A {\n"
    "    @Override\n"
    "    @Handler(\n"
    '        "x")\n'
    "    void target() {}\n"
    "    void other(@Named String s) {}\n"
    "    @Deprecated public A() {}\n"
    "}\n"
)
_CASES = [(_TS, "typescript"), (_JAVA, "java")]


@pytest.fixture(autouse=True)
def _fresh_memo(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(cd.PARSE_MEMO_ENV, raising=False)
    cd.clear_parse_memo()
    yield
    cd.clear_parse_memo()


def _all_lines(text: str, language: str) -> list[list[Decorator] | None]:
    return [
        declaration_decorators(text, line, language)
        for line in range(0, text.count("\n") + 3)
    ]


@pytest.mark.parametrize(("text", "language"), _CASES, ids=["typescript", "java"])
def test_memo_answers_equal_the_live_walk_on_every_line(
    monkeypatch: pytest.MonkeyPatch, text: str, language: str
) -> None:
    live = _all_lines(text, language)
    monkeypatch.setenv(cd.PARSE_MEMO_ENV, "1")
    first = _all_lines(text, language)
    again = _all_lines(text, language)

    assert first == live
    assert again == live
    assert any(found for found in live), "fixture must exercise decorators"


def test_default_is_off_and_keeps_no_state() -> None:
    _all_lines(_TS, "typescript")

    assert cd.parse_memo_size() == 0


def test_one_parse_per_text_when_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(cd.PARSE_MEMO_ENV, "1")
    parses = []
    real = cd._parse_tree_sitter

    def counting(text: str, language: str):
        parses.append(language)
        return real(text, language)

    monkeypatch.setattr(cd, "_parse_tree_sitter", counting)
    _all_lines(_TS, "typescript")

    assert parses == ["typescript"]


def test_changed_text_is_parsed_again(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(cd.PARSE_MEMO_ENV, "1")
    before = declaration_decorators(_TS, 7, "typescript")
    edited = _TS.replace("  @Get(\n    '/x')\n", "  \n    \n")
    after = declaration_decorators(edited, 7, "typescript")

    assert before == [Decorator("@Get( '/x')", None)]
    assert after == []


def test_same_text_other_language_is_a_separate_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(cd.PARSE_MEMO_ENV, "1")
    declaration_decorators(_TS, 7, "typescript")
    declaration_decorators(_TS, 7, "javascript")

    assert cd.parse_memo_size() == 2


def test_unreadable_stays_unreadable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(cd.PARSE_MEMO_ENV, "1")

    assert declaration_decorators("@x\nfun target() {}\n", 2, "no-such-lang") is None
    assert declaration_decorators("@x\nfun target() {}\n", 2, "no-such-lang") is None


def test_memo_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(cd.PARSE_MEMO_ENV, "1")
    monkeypatch.setattr(cd, "PARSE_MEMO_MAX_ENTRIES", 3)
    for index in range(6):
        declaration_decorators(f"class C{index} {{}}\n", 1, "typescript")

    assert cd.parse_memo_size() == 3


def test_parse_error_from_grammar_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(cd.PARSE_MEMO_ENV, "1")

    def broken(text: str, language: str):
        raise RuntimeError("grammar fault")

    monkeypatch.setattr(cd, "_parse_tree_sitter", broken)

    assert declaration_decorators(_TS, 7, "typescript") is None
