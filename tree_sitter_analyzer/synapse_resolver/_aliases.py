"""#1670：改名导入 ``from m import f as g`` 的调用 ``g()`` 解析到 ``m.f``。

导入表里 ``g`` 只映射到 ``m`` 的文件，``m`` 中并没有名为 ``g`` 的定义，于是调用边
停在“文件已知、符号未知”，按名字查询 ``f`` 的调用方时永远看不到它。这里按导入行
记录的原名 ``alias_of`` 在目标文件里找定义；目标文件只是再导出时沿再导出继续找
（``_reexports``）。找不到定义就返回 ``None``，交回原有的级联（不猜）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._reexports import follow_reexports, imported_entry

if TYPE_CHECKING:
    from ._context import ResolverContext
    from ._imports import ImportEntry


def resolve_import_alias(
    base: str, caller_file: str, ctx: ResolverContext
) -> tuple[int, str, dict[str, Any]] | None:
    """``base`` 是改名导入的本地名时返回 ``(符号 id, 定义文件, 来源)``。

    原样导入的名字若在再导出链上被改过名（``hub`` 中 ``from core import f as _f``，
    调用方 ``from hub import _f``），同样记下来源：调用点的本地名不是目标的名字。
    """
    target = ctx.name_to_source.get(caller_file, {}).get(base)
    if not target:
        return None
    entry = _alias_entry(ctx, caller_file, base)
    if entry is not None:
        found = follow_reexports(ctx, target, entry.alias_of)
    else:
        entry = imported_entry(ctx, caller_file, base)
        if entry is None:
            return None
        found = follow_reexports(ctx, target, base)
    if found is None or found[2] == base:
        return None
    symbol_id, defining_file, name = found
    provenance = {"local": base, "name": name, "line": entry.line}
    return symbol_id, defining_file, provenance


def _alias_entry(
    ctx: ResolverContext, caller_file: str, local_name: str
) -> ImportEntry | None:
    """``from M import orig as local_name`` 这一行（模块别名与星号导入除外）。"""
    for entry in ctx.imports_by_file.get(caller_file, []):
        if (
            entry.local_name == local_name
            and entry.alias_of
            and entry.alias_of != local_name
            # ``import a.b as c`` 的 alias_of 是模块路径，不是被导入的名字。
            and "." not in entry.alias_of
            and not entry.is_star
        ):
            return entry
    return None


__all__ = ["resolve_import_alias"]
