"""#1762：TS/JS 以字符串字面量下标调用（``this["~validate"](data)``）的方法必须匹配到定义。

dogfood ts1（zod）：``"~validate"(data) {...}`` 是 ``ZodType`` 的字符串名方法，构造函数里
``validate: (data) => this["~validate"](data)`` 调用它。调用边把整个下标表达式记为被调名，
定义名保留引号，二者从不相等，``ZodType."~validate"`` 答 ``complete, 0``。
计算下标（``this[name]()``）不是任何特定方法的调用，但必须让声明文件里的同名方法保持非 complete。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.mcp.tools.test_callers_bare_name_gates_1740 import _callers, _index

_LITERAL = {
    "src/schema.ts": (
        "export class Schema {\n"
        "  constructor() {\n"
        "    this.standard = {\n"
        '      validate: (data: unknown) => this["~validate"](data),\n'
        "    };\n"
        "  }\n"
        "  standard: { validate: (data: unknown) => unknown };\n"
        '  "~validate"(data: unknown): unknown {\n'
        "    return data;\n"
        "  }\n"
        "  run(x: number): number {\n"
        "    return this['plain'](x);\n"
        "  }\n"
        "  plain(x: number): number {\n"
        "    return x;\n"
        "  }\n"
        "}\n"
    ),
}
_COMPUTED = {
    "src/table.ts": (
        "export class Table {\n"
        "  dispatch(name: string) {\n"
        "    return (this as any)[name]();\n"
        "  }\n"
        "  reset() {\n"
        "    return 0;\n"
        "  }\n"
        "}\n"
    ),
}


def _caller_lines(answer: dict) -> set[int]:
    return {int(c.get("line") or 0) for c in answer.get("callers", [])}


# slow_ok：真实全量索引一次，再做 callers 查询。
@pytest.mark.slow_ok
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "caller_line"),
    [
        ('Schema."~validate"', 2),
        ('"~validate"', 2),
        ("Schema.~validate", 2),
        ("Schema.plain", 11),
        ("plain", 11),
    ],
    ids=[
        "qualified-quoted",
        "bare-quoted",
        "qualified-unquoted",
        "single-quoted-key",
        "bare-single-quoted",
    ],
)
async def test_a_literal_element_access_call_is_a_call_of_that_member(
    tmp_path: Path, name: str, caller_line: int
) -> None:
    root = await _index(tmp_path, _LITERAL)

    answer = await _callers(root, name, "src/schema.ts")

    assert caller_line in _caller_lines(answer), answer.get("callers")


@pytest.mark.slow_ok
@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["Table.reset", "reset"], ids=["qualified", "bare"])
async def test_a_computed_element_access_keeps_the_declaring_file_non_complete(
    tmp_path: Path, name: str
) -> None:
    root = await _index(tmp_path, _COMPUTED)

    answer = await _callers(root, name, "src/table.ts")

    assert answer["completeness"] != "complete"
    reasons = answer.get("completeness_reasons", [])
    assert "UNRESOLVED_IN_DECLARING_FILE" in reasons or "UNRESOLVED_INBOUND" in reasons
