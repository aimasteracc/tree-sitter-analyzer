"""RFC-0043: the per-text decorator and definition tables are memoized by content digest.

The registering-decorator gate re-parsed the declaring file on every gated
query (zod: about 0.7 s per query). The tables are now kept per
``(language, text digest)`` (default on, ``TSA_RESIDENT_PARSE_MEMO=0`` turns it
off). The text is still read live on every request, so a changed file has a
new digest and is parsed again. The answer for every line must equal the
unmemoized answer.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools import callers_decorators as cd
from tree_sitter_analyzer.mcp.tools.callers_decorators import (
    Decorator,
    declaration_decorators,
)
from tree_sitter_analyzer.resident import parse_facts

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
_PY = (
    "import functools\n"
    "from x import register\n"
    "@register(\n"
    "    'multi',\n"
    ")\n"
    "def target():\n"
    "    @functools.lru_cache(maxsize=1)\n"
    "    def inner():\n"
    "        return 1\n"
    "    return inner\n"
    "class C:\n"
    "    @staticmethod\n"
    "    # note\n"
    "    def s():\n"
    "        pass\n"
    "    @property\n"
    "    def p(self):\n"
    "        return 1\n"
)
_CASES = [(_TS, "typescript"), (_JAVA, "java"), (_PY, "python")]
_IDS = ["typescript", "java", "python"]


@pytest.fixture(autouse=True)
def _fresh_memo(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(parse_facts.ENV_VAR, raising=False)
    monkeypatch.delenv("TSA_RESIDENT", raising=False)
    parse_facts.clear()
    yield
    parse_facts.clear()


def _all_lines(text: str, language: str) -> list[list[Decorator] | None]:
    return [
        declaration_decorators(text, line, language)
        for line in range(0, text.count("\n") + 3)
    ]


@pytest.mark.parametrize(("text", "language"), _CASES, ids=_IDS)
def test_memo_answers_equal_the_live_parse_on_every_line(
    monkeypatch: pytest.MonkeyPatch, text: str, language: str
) -> None:
    monkeypatch.setenv(parse_facts.ENV_VAR, "0")
    live = _all_lines(text, language)
    monkeypatch.delenv(parse_facts.ENV_VAR)
    first = _all_lines(text, language)
    again = _all_lines(text, language)

    assert first == live
    assert again == live
    assert any(found for found in live), "fixture must exercise decorators"


def test_memo_is_on_by_default_and_reuses_one_table() -> None:
    _all_lines(_TS, "typescript")

    assert parse_facts.stats()["entries"] == 1


def test_off_switch_keeps_no_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(cd.PARSE_MEMO_ENV, "off")
    _all_lines(_TS, "typescript")
    _all_lines(_PY, "python")

    assert parse_facts.stats()["entries"] == 0


def test_one_parse_per_text(monkeypatch: pytest.MonkeyPatch) -> None:
    parses = []
    real = cd._parse_tree_sitter

    def counting(text: str, language: str):
        parses.append(language)
        return real(text, language)

    monkeypatch.setattr(cd, "_parse_tree_sitter", counting)
    _all_lines(_TS, "typescript")

    assert parses == ["typescript"]


def test_one_python_parse_per_text(monkeypatch: pytest.MonkeyPatch) -> None:
    parses = []
    real = cd._build_python_definitions

    def counting(text: str):
        parses.append(1)
        return real(text)

    monkeypatch.setattr(cd, "_build_python_definitions", counting)
    _all_lines(_PY, "python")

    assert parses == [1]


def test_changed_text_is_parsed_again() -> None:
    before = declaration_decorators(_TS, 7, "typescript")
    edited = _TS.replace("  @Get(\n    '/x')\n", "  \n    \n")
    after = declaration_decorators(edited, 7, "typescript")

    assert before == [Decorator("@Get( '/x')", None)]
    assert after == []


def test_changed_python_text_is_parsed_again() -> None:
    before = declaration_decorators(_PY, 6, "python")
    after = declaration_decorators(_PY.replace("@register(", "@other("), 6, "python")

    assert before == [Decorator("@register( 'multi', )", "x.register")]
    assert after == [Decorator("@other( 'multi', )", None)]


def test_same_text_other_language_is_a_separate_entry() -> None:
    declaration_decorators(_TS, 7, "typescript")
    declaration_decorators(_TS, 7, "javascript")

    assert parse_facts.stats()["entries"] == 2


def test_unreadable_stays_unreadable() -> None:
    assert declaration_decorators("@x\nfun target() {}\n", 2, "no-such-lang") is None
    assert declaration_decorators("@x\nfun target() {}\n", 2, "no-such-lang") is None
    assert declaration_decorators("def target(:\n", 1, "python") is None
    assert declaration_decorators("def target(:\n", 1, "python") is None


def test_parse_error_from_grammar_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(text: str, language: str):
        raise RuntimeError("grammar fault")

    monkeypatch.setattr(cd, "_parse_tree_sitter", broken)

    assert declaration_decorators(_TS, 7, "typescript") is None


def test_python_definition_table_keeps_walk_order() -> None:
    table = cd.python_definition_table(_PY)

    assert table is not None
    assert [name for name, _first, _header, _decorators in table] == [
        "target",
        "C",
        "inner",
        "s",
        "p",
    ]
