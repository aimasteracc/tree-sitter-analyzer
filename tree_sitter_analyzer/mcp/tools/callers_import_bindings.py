"""#1643：``from m import name`` 只是把同名绑定进导入方文件，本身不是引用。

dogfood 第 7 轮：跨文件调用方几乎都先 ``from mod import fn`` 再 ``fn()``。
非调用引用门若把导入行计为引用，有调用方的答案就永远停在 ``incomplete``。

为什么可以跳过：未改名的导入让导入方文件里的名字仍是 ``name``，该文件的每次
使用（调用、回调传递、别名赋值、``__all__`` 字符串）都由同一扫描逐一检查；
导入行本身不产生任何调用。只跳过“导入的就是该名字且未改名”的出现：

* ``from m import name as alias``：之后的 ``alias()`` 名字不同，导入行就是引用；
* ``from m import other as name``：本地的 ``name`` 指向别处，保守保留；
* ``import name`` / ``from name import x``：模块名，保守保留。
"""

from __future__ import annotations

import re

#: ``from <module> import <names>``：括号内可跨行，或以反斜杠续行。
_FROM_IMPORT = re.compile(
    r"^[ \t]*from[ \t]+[\w.]+[ \t]+import[ \t]*(\([^)]*\)|(?:[^\n\\]|\\\n)*)",
    re.MULTILINE,
)
_AS_BEFORE = re.compile(r"\bas\s+$")
_AS_AFTER = re.compile(r"\s+as\b")


def mask_import_bindings(text: str, bare: str) -> str:
    """把未改名导入 ``bare`` 的出现替换为等长空白，保留行号与其余文本。"""
    if bare not in text:
        return text
    name = re.compile(r"(?<![\w$])" + re.escape(bare) + r"(?![\w$])")
    spans: list[tuple[int, int]] = []
    for statement in _FROM_IMPORT.finditer(text):
        start, end = statement.span(1)
        names = text[start:end]
        for found in name.finditer(names):
            if _AS_BEFORE.search(names[: found.start()]):
                continue
            if _AS_AFTER.match(names, found.end()):
                continue
            spans.append((start + found.start(), start + found.end()))
    if not spans:
        return text
    pieces: list[str] = []
    last = 0
    for begin, finish in spans:
        pieces.append(text[last:begin])
        pieces.append(" " * (finish - begin))
        last = finish
    pieces.append(text[last:])
    return "".join(pieces)
