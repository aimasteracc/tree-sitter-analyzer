"""#1762：字符串字面量成员名的归一——只接受无转义、无插值的常量字符串。"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.function_extraction import (
    _js_string_literal,
    _literal_subscript_member,
)
from tree_sitter_analyzer.member_names import unquote_member_name


class _Node:
    def __init__(self, type_: str, text: str, **fields: _Node) -> None:
        self.type = type_
        self.text = text.encode("utf-8")
        self._fields = fields

    def child_by_field_name(self, name: str) -> _Node | None:
        return self._fields.get(name)


@pytest.mark.parametrize(
    ("node", "expected"),
    [
        (_Node("string", '"~validate"'), "~validate"),
        (_Node("string", "'plain'"), "plain"),
        (_Node("string", '""'), None),  # 空名不是成员
        (_Node("string", '"a\\"b"'), None),  # 含转义：不猜
        (_Node("string", "'it''s'"), None),  # 内含同种引号
        (_Node("string", '"open'), None),  # 未闭合
        (_Node("string", "x"), None),  # 太短
        (_Node("template_string", "`k`"), None),  # 模板串不归一
        (_Node("identifier", "name"), None),  # 计算式下标
        (None, None),
    ],
)
def test_only_constant_string_literals_name_a_member(node, expected) -> None:
    assert _js_string_literal(node) == expected


def test_a_literal_subscript_callee_reads_as_a_member_call() -> None:
    func = _Node(
        "subscript_expression",
        'this["~validate"]',
        object=_Node("this", "this"),
        index=_Node("string", '"~validate"'),
    )
    assert _literal_subscript_member(func, "") == {
        "name": "~validate",
        "full_name": "this.~validate",
        "receiver": "this",
    }


def test_a_computed_subscript_callee_keeps_its_source_text() -> None:
    func = _Node(
        "subscript_expression",
        "this[name]",
        object=_Node("this", "this"),
        index=_Node("identifier", "name"),
    )
    assert _literal_subscript_member(func, "") is None


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ('ZodType."~validate"', "ZodType.~validate"),
        ('"~validate"', "~validate"),
        ("Schema.'plain'", "Schema.plain"),
        ("Schema.plain", "Schema.plain"),
        ('"', '"'),
    ],
)
def test_a_quoted_last_segment_is_matched_unquoted(name: str, expected: str) -> None:
    assert unquote_member_name(name) == expected


def test_an_escaped_string_method_name_keeps_its_source_text() -> None:
    """不能静态读出的字符串名（含转义）按原文记录，不猜测成员名。"""
    from tree_sitter_analyzer.cache.extraction import _extract_symbols
    from tree_sitter_analyzer.core.parser import Parser

    source = 'class A {\n  "a\\"b"() {\n    return 1;\n  }\n  "ok"() {}\n}\n'
    parsed = Parser().parse_code(source, "typescript")
    assert parsed.success
    names = {
        s["name"]
        for s in _extract_symbols(parsed.tree, source, "typescript")["symbols"]
    }
    assert {'"a\\"b"', "ok"} <= names
