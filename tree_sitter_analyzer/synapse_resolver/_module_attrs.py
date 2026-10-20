"""#1705：经模块对象调用再导出的名字（``import pkg.hub as owner; owner._f()``）。

``hub`` 中 ``from .core import f as _f`` 把 ``f`` 改名绑定为 ``hub`` 的模块属性。
原有级联把 ``owner._f()`` 解析到 ``hub`` 的文件，但 ``hub`` 里没有名为 ``_f`` 的定义，
边停在“文件已知、符号未知”，按 ``f`` 查询调用方永远看不到它。

这里在 ``owner`` 指向的模块里查 ``_f`` 的绑定：是导入（改名或原样再导出）时，
沿再导出找到定义（与 #1670 相同的跳数上限）。以下情形不解析，交回原有级联，
调用点只是“可能”的调用：

* ``owner`` 在调用文件里绑定到多个模块，且无法按调用所在函数的导入区分；
* 目标模块重新绑定了这个属性（赋值、``global``、``del``）；
* 调用文件给这个属性赋值，或以字符串点名它（``owner._f = fake``、
  ``monkeypatch.setattr(owner, "_f", ...)``）。
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any

from ._reexports import follow_reexports, imported_entry, symbol_id

if TYPE_CHECKING:
    from ._context import ResolverContext

#: 可作为模块对象的接收者：点分标识符（不含调用、下标）。
_DOTTED = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")
_SELF_QUALIFIERS = frozenset({"self", "cls", "super()"})
#: 赋值运算符（含增强赋值与注解赋值），其后不能紧跟 ``=``。
_ASSIGN_OP = r"[ \t]*(?::[^=\n]*)?(?:[-+*/%&|^@]|//|\*\*|<<|>>)?=(?!=)"


def resolve_module_attribute(
    callee_full: str,
    caller_file: str,
    caller_line: int,
    call_line: int,
    ctx: ResolverContext,
) -> tuple[int, str, dict[str, Any] | None] | None:
    """``M.name()`` 经 ``M`` 的导入绑定解析时返回 ``(符号 id, 定义文件, 来源)``。

    来源只在调用点的名字与定义名不同（改名再导出）时给出，形如
    ``{local, name, line, module}``；原样再导出返回 ``None``。
    """
    qualifier, _dot, base = callee_full.rpartition(".")
    if (
        not qualifier
        or qualifier in _SELF_QUALIFIERS
        or not _DOTTED.fullmatch(qualifier)
        or not base.isidentifier()
    ):
        return None
    binding = _module_binding(ctx, caller_file, qualifier, caller_line, call_line)
    if binding is None:
        return None
    binding_line, module_file = binding
    if module_file == caller_file or symbol_id(ctx, module_file, base) is not None:
        # 模块自己定义了这个名字：原有级联已能解析到符号。
        return None
    if imported_entry(ctx, module_file, base) is None:
        return None
    if _rebound_in_module(ctx, module_file, base) or _assigned_in_caller(
        ctx, caller_file, base
    ):
        return None
    found = follow_reexports(ctx, module_file, base)
    if found is None:
        return None
    found_id, defining_file, name = found
    if name == base:
        return found_id, defining_file, None
    provenance = {
        "local": base,
        "name": name,
        "line": binding_line,
        "module": module_file,
    }
    return found_id, defining_file, provenance


def _module_binding(
    ctx: ResolverContext,
    caller_file: str,
    qualifier: str,
    caller_line: int,
    call_line: int,
) -> tuple[int, str] | None:
    """调用文件中 ``qualifier`` 绑定的模块文件 ``(导入行, 文件)``；不唯一时为 None。

    同一文件里同名的模块别名指向多个模块（各测试函数内各自 ``import … as owner``）
    时，取调用所在函数内、调用之前最近的那一行导入；找不到即不解析。
    """
    bindings = _bindings(ctx, caller_file, qualifier)
    if not bindings:
        return None
    if len({target for _line, target in bindings}) == 1:
        line, target = bindings[0]
        return (line, target) if target else None
    in_scope = [
        (line, target) for line, target in bindings if caller_line <= line <= call_line
    ]
    if not in_scope:
        return None
    line, target = max(in_scope)
    return (line, target) if target else None


def _bindings(
    ctx: ResolverContext, caller_file: str, qualifier: str
) -> list[tuple[int, str]]:
    """``qualifier`` 在调用文件中的每一次导入绑定；不是模块的绑定记为空文件名。"""
    from ._context import _local_name_as_submodule

    head = qualifier.split(".", 1)[0]
    found: list[tuple[int, str]] = []
    for entry in ctx.imports_by_file.get(caller_file, []):
        if entry.is_star:
            continue
        if "." in qualifier:
            # `import a.b.c` 绑定 `a`；`a.b.c.f()` 的接收者是完整的模块路径。
            if (
                entry.local_name == head
                and not entry.alias_of
                and not entry.is_relative
                and entry.module_path == qualifier
            ):
                found.append((entry.line, ctx.module_to_file.get(qualifier, "")))
            continue
        if entry.local_name != qualifier:
            continue
        if not entry.is_relative and entry.alias_of == entry.module_path:
            # `import a.b as q`
            target = ctx.module_to_file.get(entry.module_path, "")
        elif not entry.is_relative and not entry.alias_of:
            # `import q`
            target = (
                ctx.module_to_file.get(qualifier, "")
                if entry.module_path == qualifier
                else ""
            )
        else:
            # `from pkg import mod [as q]`；不是子模块时绑定的是别的对象。
            target = _local_name_as_submodule(
                entry.local_name,
                entry.alias_of,
                entry.module_path,
                caller_file,
                ctx.module_to_file,
                ctx.indexed_module_files,
            )
        found.append((entry.line, target))
    return found


def _rebound_in_module(ctx: ResolverContext, module_file: str, name: str) -> bool:
    """模块在导入之外重新绑定了 ``name``；读不到源码按“已重新绑定”处理。"""
    text = _source(ctx, module_file)
    if text is None:
        return True
    word = re.escape(name)
    other = r"[\w.]+[ \t]*"
    pattern = re.compile(
        rf"^[ \t]*(?:{other},[ \t]*)*{word}[ \t]*(?:,[ \t]*{other})*{_ASSIGN_OP}"
        rf"|^[ \t]*(?:global|nonlocal|del)[ \t][^\n]*(?<![\w$]){word}(?![\w$])",
        re.MULTILINE,
    )
    return pattern.search(text) is not None


def _assigned_in_caller(ctx: ResolverContext, caller_file: str, name: str) -> bool:
    """调用文件给属性 ``name`` 赋值或以字符串点名它；读不到源码按“已赋值”处理。"""
    text = _source(ctx, caller_file)
    if text is None:
        return True
    word = re.escape(name)
    pattern = re.compile(
        rf"\.[ \t]*{word}{_ASSIGN_OP}|\bdel[ \t][^\n]*\.{word}(?![\w$])"
        rf"|[\"']{word}[\"']"
    )
    return pattern.search(text) is not None


def _source(ctx: ResolverContext, rel_path: str) -> str | None:
    memo = ctx.text_memo
    if rel_path not in memo:
        try:
            with open(
                os.path.join(ctx.project_root, rel_path), encoding="utf-8"
            ) as handle:
                memo[rel_path] = handle.read()
        except (OSError, UnicodeDecodeError, TypeError):
            memo[rel_path] = None
    return memo[rel_path]


__all__ = ["resolve_module_attribute"]
