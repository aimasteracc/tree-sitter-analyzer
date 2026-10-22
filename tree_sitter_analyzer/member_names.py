"""#1762：成员名的引号归一（字符串字面量方法名 `"~validate"` 与 `~validate` 同名）。"""

from __future__ import annotations


def unquote_member_name(name: str) -> str:
    """去掉最后一段两侧成对的引号：`ZodType."~validate"` -> `ZodType.~validate`。"""
    head, dot, last = name.rpartition(".") if not _quoted(name) else ("", "", name)
    if _quoted(last):
        last = last[1:-1]
    return f"{head}{dot}{last}"


def _quoted(text: str) -> bool:
    return len(text) >= 2 and text[0] in "'\"" and text[-1] == text[0]
