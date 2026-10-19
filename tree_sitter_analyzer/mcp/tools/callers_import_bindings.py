"""#1643：``from m import name`` 只是把同名绑定进导入方文件，本身不是引用。

dogfood 第 7 轮：跨文件调用方几乎都先 ``from mod import fn`` 再 ``fn()``。
非调用引用门若把导入行计为引用，有调用方的答案就永远停在 ``incomplete``。

为什么可以跳过：未改名的导入让导入方文件里的名字仍是 ``name``，该文件的每次
使用（调用、回调传递、别名赋值、``__all__`` 字符串）都由同一扫描逐一检查；
导入行本身不产生任何调用。只跳过“导入的就是该名字且未改名”的出现：

* ``from m import name as alias``：之后的 ``alias()`` 名字不同，导入行默认就是引用；
  #1670：只有当该文件里 ``alias`` 的每一次使用都已被核对——是解析到目标的调用边——
  且 ``alias`` 没有被再导出时，调用方才把它列入 ``masked_aliases``，导入行随之跳过；
* ``from m import other as name``：本地的 ``name`` 指向别处，保守保留；
* ``import name`` / ``from name import x``：模块名，保守保留。
"""

from __future__ import annotations

import re
from collections.abc import Set as AbstractSet

#: ``from <module> import <names>``：括号内可跨行，或以反斜杠续行。
_FROM_IMPORT = re.compile(
    r"^[ \t]*from[ \t]+[\w.]+[ \t]+import[ \t]*(\([^)]*\)|(?:[^\n\\]|\\\n)*)",
    re.MULTILINE,
)
_AS_BEFORE = re.compile(r"\bas\s+$")
_AS_AFTER = re.compile(r"\s+as\b")
#: ``as <alias>``：紧跟在被导入名之后的改名。
_AS_ALIAS = re.compile(r"\s+as\s+([A-Za-z_]\w*)")


def mask_import_bindings(
    text: str, bare: str, masked_aliases: AbstractSet[str] = frozenset()
) -> str:
    """把未改名导入 ``bare`` 的出现替换为等长空白，保留行号与其余文本。

    ``masked_aliases``（#1670）中的改名导入 ``bare as alias`` 同样替换。
    """
    if bare not in text:
        return text
    spans = [
        (begin, finish)
        for begin, finish, alias in _binding_spans(text, bare)
        if alias is None or alias in masked_aliases
    ]
    return _blank(text, spans)


def alias_bindings(text: str, bare: str) -> list[tuple[str, int, int]]:
    """``from m import bare as alias`` 的 ``(alias, 语句起点, 语句终点)``（改名为自身的除外）。"""
    if bare not in text:
        return []
    found: list[tuple[str, int, int]] = []
    for statement in _FROM_IMPORT.finditer(text):
        for _begin, _finish, alias in _clause_spans(
            statement.group(1), bare, statement.start(1)
        ):
            if alias is not None:
                found.append((alias, statement.start(), statement.end()))
    return found


def _binding_spans(text: str, bare: str) -> list[tuple[int, int, str | None]]:
    spans: list[tuple[int, int, str | None]] = []
    for statement in _FROM_IMPORT.finditer(text):
        spans.extend(_clause_spans(statement.group(1), bare, statement.start(1)))
    return spans


def _clause_spans(
    names: str, bare: str, offset: int
) -> list[tuple[int, int, str | None]]:
    """``names`` 子句中 ``bare`` 作为被导入名的出现：未改名为 None，改名给出别名。"""
    name = re.compile(r"(?<![\w$])" + re.escape(bare) + r"(?![\w$])")
    spans: list[tuple[int, int, str | None]] = []
    for found in name.finditer(names):
        if _AS_BEFORE.search(names[: found.start()]):
            continue
        alias: str | None = None
        if _AS_AFTER.match(names, found.end()):
            renamed = _AS_ALIAS.match(names, found.end())
            # `bare as bare` 是显式再导出：从不跳过。
            if renamed is None or renamed.group(1) == bare:
                continue
            alias = renamed.group(1)
        spans.append((offset + found.start(), offset + found.end(), alias))
    return spans


def _blank(text: str, spans: list[tuple[int, int]]) -> str:
    if not spans:
        return text
    pieces: list[str] = []
    last = 0
    for begin, finish in sorted(spans):
        pieces.append(text[last:begin])
        pieces.append(" " * (finish - begin))
        last = finish
    pieces.append(text[last:])
    return "".join(pieces)
