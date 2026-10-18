"""#1670：改名导入 ``from m import f as g`` 的调用 ``g()`` 解析到 ``m.f``。

导入表里 ``g`` 只映射到 ``m`` 的文件，``m`` 中并没有名为 ``g`` 的定义，于是调用边
停在“文件已知、符号未知”，按名字查询 ``f`` 的调用方时永远看不到它。这里按导入行
记录的原名 ``alias_of`` 在目标文件里找定义；目标文件只是再导出（``__init__`` 中的
``from .impl import f``）时沿再导出最多走 ``_MAX_HOPS`` 跳。找不到定义就返回
``None``，交回原有的级联（不猜）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._context import ResolverContext
    from ._imports import ImportEntry

#: 沿包再导出追踪的最大跳数（与 RFC-0038 的类型解析一致）。
_MAX_HOPS = 4
#: 可作为被调定义的符号种类。
_CALLABLE_KINDS = ("function", "method", "class")


def resolve_import_alias(
    base: str, caller_file: str, ctx: ResolverContext
) -> tuple[int, str, dict[str, Any]] | None:
    """``base`` 是改名导入的本地名时返回 ``(符号 id, 定义文件, 来源)``。"""
    entry = _alias_entry(ctx, caller_file, base)
    if entry is None:
        return None
    target = ctx.name_to_source.get(caller_file, {}).get(base)
    if not target:
        return None
    found = _follow_reexports(ctx, target, entry.alias_of)
    if found is None:
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


def _follow_reexports(
    ctx: ResolverContext, file_path: str, name: str
) -> tuple[int, str, str] | None:
    """在 ``file_path`` 中找 ``name`` 的定义；只是再导出时沿导入继续找。"""
    current_file, current_name = file_path, name
    for _hop in range(_MAX_HOPS + 1):
        symbol_id = _symbol_id(ctx, current_file, current_name)
        if symbol_id is not None:
            return symbol_id, current_file, current_name
        next_file = ctx.name_to_source.get(current_file, {}).get(current_name)
        if not next_file or next_file == current_file:
            return None
        entry = _imported_entry(ctx, current_file, current_name)
        if entry is not None and entry.alias_of:
            current_name = entry.alias_of
        current_file = next_file
    return None


def _imported_entry(
    ctx: ResolverContext, file_path: str, local_name: str
) -> ImportEntry | None:
    for entry in ctx.imports_by_file.get(file_path, []):
        if entry.local_name == local_name and not entry.is_star:
            return entry
    return None


def _symbol_id(ctx: ResolverContext, file_path: str, name: str) -> int | None:
    for sym_name, kind, sym_id in ctx.file_symbols.get(file_path, []):
        if sym_name == name and kind in _CALLABLE_KINDS:
            return sym_id
    return None


__all__ = ["resolve_import_alias"]
