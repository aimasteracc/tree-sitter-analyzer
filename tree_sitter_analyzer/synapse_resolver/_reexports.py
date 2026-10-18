"""``from facade import f``：``facade`` 只是再导出时，调用解析到真正定义 ``f`` 的文件。

导入表把 ``f`` 映射到 ``facade`` 的文件；那里没有名为 ``f`` 的定义，原有级联只
记下“文件已知、符号未知”，``callee_resolved_file`` 指向再导出文件。按定义文件查询
``f`` 的调用方就看不到这个调用，而它已被计为已解析，答复会错误地成为 ``complete``。

这里沿再导出文件自己的导入继续找定义（含 ``from x import g as f`` 的改名），
最多 ``MAX_HOPS`` 跳；找不到定义就返回 ``None``，交回原有级联（不猜）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._context import ResolverContext
    from ._imports import ImportEntry

#: 沿包再导出追踪的最大跳数（与 RFC-0038 的类型解析一致）。
MAX_HOPS = 4
#: 可作为被调定义的符号种类。
_CALLABLE_KINDS = ("function", "method", "class")


def resolve_reexported_name(
    base: str, caller_file: str, ctx: ResolverContext
) -> tuple[int, str] | None:
    """``base`` 经导入落在只是再导出它的文件时，返回 ``(符号 id, 定义文件)``。"""
    target = ctx.name_to_source.get(caller_file, {}).get(base)
    if not target or symbol_id(ctx, target, base) is not None:
        return None
    entry = imported_entry(ctx, caller_file, base)
    if entry is not None and entry.alias_of:
        # 改名导入（``from m import f as g``）不在此处理。
        return None
    found = follow_reexports(ctx, target, base)
    if found is None:
        return None
    return found[0], found[1]


def follow_reexports(
    ctx: ResolverContext, file_path: str, name: str
) -> tuple[int, str, str] | None:
    """在 ``file_path`` 中找 ``name`` 的定义；只是再导出时沿导入继续找。

    返回 ``(符号 id, 定义文件, 定义名)``。
    """
    current_file, current_name = file_path, name
    for _hop in range(MAX_HOPS + 1):
        found = symbol_id(ctx, current_file, current_name)
        if found is not None:
            return found, current_file, current_name
        next_file = ctx.name_to_source.get(current_file, {}).get(current_name)
        if not next_file or next_file == current_file:
            return None
        entry = imported_entry(ctx, current_file, current_name)
        if entry is not None and entry.alias_of:
            current_name = entry.alias_of
        current_file = next_file
    return None


def imported_entry(
    ctx: ResolverContext, file_path: str, local_name: str
) -> ImportEntry | None:
    """``file_path`` 中把 ``local_name`` 绑定进来的导入行（星号导入除外）。"""
    for entry in ctx.imports_by_file.get(file_path, []):
        if entry.local_name == local_name and not entry.is_star:
            return entry
    return None


def symbol_id(ctx: ResolverContext, file_path: str, name: str) -> int | None:
    """``file_path`` 中名为 ``name`` 的可调用定义的符号 id。"""
    for sym_name, kind, sym_id in ctx.file_symbols.get(file_path, []):
        if sym_name == name and kind in _CALLABLE_KINDS:
            return sym_id
    return None


__all__ = [
    "MAX_HOPS",
    "follow_reexports",
    "imported_entry",
    "resolve_reexported_name",
    "symbol_id",
]
