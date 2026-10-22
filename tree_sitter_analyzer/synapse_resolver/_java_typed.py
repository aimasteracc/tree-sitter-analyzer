"""#1743：按接收者的声明类型绑定 Java 调用 ``x.m()``（虚分派的静态目标）。

提取器给 ``x`` 记下声明类型（``java_receiver_hints.py``）。这里：

1. 在调用文件的 Java 上下文里把类型名解析为项目类：同文件（含嵌套类）、单类型导入、
   同包、按需导入（``import a.b.*``），以及 ``Outer.Inner`` 限定名；
2. 在该类上找 ``m``；没有就沿项目祖先（``extends`` / ``implements``，深度优先）找，
   恰有一个定义时绑定。

结果是 RFC-0038 的 ``annotated_receiver`` 绑定：声明类型上的定义是确定目标，其子类型
中的覆写由调用图记为可能目标（``NAME_ONLY_INBOUND``），从不省略。

以下情形不绑定（返回 None，回到原有级联）：类型解析不到项目类（JDK / 第三方 /
类型变量）；``m`` 在该类上有多个重载；祖先链上有解析不到的基类型而类本身没有
声明 ``m``；不同祖先分支各有一个 ``m``。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..cached_annotated_binding import ANNOTATED_RECEIVER

if TYPE_CHECKING:
    from . import ResolvedCallee
    from ._context import ResolverContext
    from ._java_context import JavaResolverContext

#: 与 Python 注解绑定相同的置信度（声明类型同样不保证运行时类型）。
JAVA_TYPED_CONFIDENCE = 0.8
_MAX_DEPTH = 8

ClassKey = tuple[str, str]  # (文件, 类名)


@dataclass
class JavaTypeIndex:
    """Java 类、基类型与方法定义（每个解析上下文构建一次）。"""

    #: 文件 -> 类名 -> 基类型名（``extends`` 与 ``implements``，源码中的写法）。
    classes: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    #: (文件, 类) -> 方法名 -> [(定义行, 符号 id)]
    methods: dict[ClassKey, dict[str, list[tuple[int, int]]]] = field(default_factory=dict)


def java_type_index(ctx: ResolverContext) -> JavaTypeIndex:
    cached = getattr(ctx, "_java_type_index", None)
    if isinstance(cached, JavaTypeIndex):
        return cached
    index = JavaTypeIndex()
    cache = getattr(ctx, "cache", None)
    if cache is not None:
        try:
            _load(cache.get_conn(), index)
        except Exception:  # nosec B110 — 缺表：没有类型证据，不绑定。
            index = JavaTypeIndex()
    ctx._java_type_index = index  # type: ignore[attr-defined]  # noqa: SLF001
    return index


def _load(conn: Any, index: JavaTypeIndex) -> None:
    by_position: dict[tuple[str, str, int], int] = {}
    for row in conn.execute(
        "SELECT id, name, file_path, line FROM ast_symbol_rows WHERE kind IN ('method', 'function')"
    ):
        by_position[(str(row[2]), str(row[1]), int(row[3] or 0))] = int(row[0])
    for file_path, symbols_json in conn.execute(
        "SELECT file_path, symbols_json FROM ast_index WHERE language = 'java'"
    ):
        try:
            symbols = json.loads(symbols_json).get("symbols", [])
        except (TypeError, ValueError, AttributeError):
            continue
        for symbol in symbols:
            kind = symbol.get("kind")
            name = str(symbol.get("name") or "")
            if kind == "class" and name:
                index.classes.setdefault(file_path, {})[name] = [
                    str(parent) for parent in symbol.get("parents") or []
                ]
            elif kind in ("method", "function") and name and symbol.get("class"):
                line = int(symbol.get("line") or 0)
                sym_id = by_position.get((file_path, name, line))
                if sym_id is None:
                    continue
                key = (file_path, str(symbol["class"]))
                index.methods.setdefault(key, {}).setdefault(name, []).append((line, sym_id))


def resolve_type(
    name: str, file_path: str, jctx: JavaResolverContext, index: JavaTypeIndex
) -> ClassKey | None:
    """Java 类型名在 ``file_path`` 中指向的项目类；不是项目类时为 None。"""
    name = name.split("<", 1)[0].strip()
    if not name:
        return None
    if "." in name:
        target = jctx.fqn_to_file.get(name)
        simple = name.rsplit(".", 1)[1]
        if target and simple in index.classes.get(target, {}):
            return (target, simple)
        head, _, rest = name.partition(".")
        outer = resolve_type(head, file_path, jctx, index)
        if outer is None or "." in rest:
            return None
        return (outer[0], rest) if rest in index.classes.get(outer[0], {}) else None
    if name in index.classes.get(file_path, {}):
        return (file_path, name)
    imported = jctx.simple_to_fqn_by_file.get(file_path, {}).get(name)
    if imported:
        target = jctx.fqn_to_file.get(imported)
        if target and name in index.classes.get(target, {}):
            return (target, name)
        return None  # 导入的是项目外的类型
    package = jctx.file_package.get(file_path, "")
    candidates = []
    if package:
        candidates.append(f"{package}.{name}")
    candidates += [f"{pkg}.{name}" for pkg in jctx.wildcard_pkgs_by_file.get(file_path, [])]
    found = {
        (target, name)
        for fqn in candidates
        if (target := jctx.fqn_to_file.get(fqn)) and name in index.classes.get(target, {})
    }
    return found.pop() if len(found) == 1 else None


def find_method(
    cls: ClassKey,
    method: str,
    jctx: JavaResolverContext,
    index: JavaTypeIndex,
    depth: int = 0,
) -> tuple[str, int, str, int] | None:
    """``(定义文件, 符号 id, 所属类, 定义行)``；无法唯一确定时为 None。"""
    if depth > _MAX_DEPTH:
        return None
    own = index.methods.get(cls, {}).get(method)
    if own is not None:
        if len(own) != 1:
            return None  # 重载：调用的是哪一个取决于实参类型
        line, sym_id = own[0]
        return (cls[0], sym_id, cls[1], line)
    found: set[tuple[str, int, str, int]] = set()
    for parent in index.classes.get(cls[0], {}).get(cls[1], []):
        resolved = resolve_type(parent, cls[0], jctx, index)
        if resolved is None:
            return None  # 基类型在项目外：方法可能来自它
        hit = find_method(resolved, method, jctx, index, depth + 1)
        if hit is not None:
            found.add(hit)
        elif _declares_anywhere(resolved, method, jctx, index, depth + 1):
            return None  # 祖先里有该名字但无法唯一确定（重载 / 外部基类型）
    return found.pop() if len(found) == 1 else None


def _declares_anywhere(
    cls: ClassKey, method: str, jctx: JavaResolverContext, index: JavaTypeIndex, depth: int
) -> bool:
    if depth > _MAX_DEPTH:
        return True
    if method in index.methods.get(cls, {}):
        return True
    for parent in index.classes.get(cls[0], {}).get(cls[1], []):
        resolved = resolve_type(parent, cls[0], jctx, index)
        if resolved is None or _declares_anywhere(resolved, method, jctx, index, depth + 1):
            return True
    return False


def resolve_java_typed_receiver(
    hint: dict[str, Any] | None,
    method: str,
    caller_file: str,
    ctx: ResolverContext,
) -> ResolvedCallee | None:
    """按声明类型绑定 ``x.method()``；无法判定时为 None。"""
    if not hint or not method or not hint.get("type"):
        return None
    jctx = ctx.lang_context("java")
    if jctx is None:
        return None
    from . import ResolvedCallee

    index = java_type_index(ctx)
    cls = resolve_type(str(hint["type"]), caller_file, jctx, index)
    if cls is None:
        return None
    bound = find_method(cls, method, jctx, index)
    if bound is None:
        return None
    def_file, sym_id, owner, line = bound
    binding = {
        "source": str(hint.get("source") or ""),
        "type": cls[1],
        "type_file": cls[0],
        "owner": owner,
        "line": line,
        "confidence": JAVA_TYPED_CONFIDENCE,
    }
    return ResolvedCallee(sym_id, ANNOTATED_RECEIVER, def_file, binding=binding)


__all__ = ["JavaTypeIndex", "find_method", "java_type_index", "resolve_java_typed_receiver", "resolve_type"]
