"""PR-1：调用被下标的项目类（``Cls[T](...)``）只会构造实例。

声明文件守卫（RFC-0028 §1.2）把文本里带 ``[`` 的调用点都当作计算式分发——
``HANDLERS[k]()`` 取出的可以是任何可调用对象。但当 ``X`` 可证明就是本文件里
定义的普通类时，``X[T]`` 由 ``typing.Generic.__class_getitem__`` 产出别名，调用
别名只执行构造：``__new__``、``__init__``（数据类再经 ``__post_init__``），再给
实例设 ``__orig_class__``（``__setattr__``）。它不会到达类上的任意方法
（pydantic ``_Pipeline[Any, Any](...)`` 曾因此挡住 ``_Pipeline.str_upper``）。

只在能确认时排除，其余一律保留守卫：

* Python 源文件（``.py``）；调用文本恰为 ``名字[...]``；
* 该名字在本文件只有一处绑定：模块顶层的 ``class`` 语句（无 ``if``/``try``
  包裹，无重新赋值、参数、导入、``global`` 等同名绑定）；
* 类语句无关键字参数（无 ``metaclass=``）、类体及基类体都不定义
  ``__class_getitem__``；装饰器只允许 ``dataclasses.dataclass``；
* 每个基类是 ``object``、从 ``typing`` / ``typing_extensions`` 导入的
  ``Generic``，或本文件里同样满足上述条件的类——其余基类的元类无法确定；
* 本文件没有 ``globals()`` / ``vars()`` / ``exec`` / ``eval`` / ``setattr`` /
  ``__dict__`` 之类的动态改名，也没有以该类名为内容的字符串；其他被索引的
  Python 文件里没有 ``.X =`` 赋值或 ``"X"`` 字符串（可能从外部替换模块属性）；
* 目标不是构造相关方法，也不是该类或其本文件基类本身。

读取失败（源文件、索引）一律保留守卫。
"""

from __future__ import annotations

import ast
import hashlib
import os
import re
import threading
from collections import Counter, OrderedDict
from typing import Any

#: 排除原因码。
CLASS_CONSTRUCTION_REASON = "class_subscript_construction"
#: 调用 ``X[T](...)`` 时可能执行的方法（构造、别名设 ``__orig_class__``）。
CONSTRUCTION_METHODS = frozenset(
    {
        "__init__",
        "__new__",
        "__call__",
        "__init_subclass__",
        "__class_getitem__",
        "__post_init__",
        "__setattr__",
    }
)
#: 运行时按名改绑模块属性的构造：出现即保留守卫。
_DYNAMIC_CALLS = frozenset(
    {"globals", "vars", "exec", "eval", "setattr", "delattr", "__import__"}
)
_TYPING_MODULES = frozenset({"typing", "typing_extensions"})
_SUFFIX = ".py"

#: :func:`_chain_for` 的结果，以源文本摘要与类名为键（纯函数，有界）。
_CHAINS: OrderedDict[tuple[bytes, str], frozenset[str] | None] = OrderedDict()
_CHAINS_MAX = 256
_CHAINS_LOCK = threading.Lock()


def clear_chains() -> None:
    """Forget the memoized class chains (tests)."""
    with _CHAINS_LOCK:
        _CHAINS.clear()


def subscripted_name(callee: str) -> str | None:
    """调用文本恰为 ``名字[...]`` 时的名字；其余形状为 None。"""
    text = (callee or "").strip()
    if not text or "[" not in text:
        return None
    try:
        node = ast.parse(f"({text})", mode="eval").body
    except (SyntaxError, ValueError, RecursionError):
        return None
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        return node.value.id
    return None


def constructs_only(text: str, name: str) -> bool:
    """Python 源 ``text`` 里调用 ``name[...]`` 是否可证明只构造 ``name`` 的实例。"""
    return _chain_for(text, name) is not None


def _chain_for(text: str, name: str) -> frozenset[str] | None:
    """``name`` 及其本文件祖先类（含 ``Generic`` 的本地名）；不能确认时为 None。"""
    key = (
        hashlib.blake2b(text.encode("utf-8", "surrogatepass"), digest_size=20).digest(),
        name,
    )
    with _CHAINS_LOCK:
        if key in _CHAINS:
            _CHAINS.move_to_end(key)
            return _CHAINS[key]
    chain = _analyze(text, name)
    with _CHAINS_LOCK:
        _CHAINS[key] = chain
        while len(_CHAINS) > _CHAINS_MAX:
            _CHAINS.popitem(last=False)
    return chain


class _Module:
    """一个模块的绑定计数、导入来源与顶层类。"""

    def __init__(self, tree: ast.Module) -> None:
        self.tree = tree
        self.bindings: Counter[str] = Counter()
        self.from_imports: dict[str, tuple[str, str]] = {}
        self.imports: dict[str, str] = {}
        self.star = False
        self.classes = {
            node.name: node for node in tree.body if isinstance(node, ast.ClassDef)
        }
        for node in ast.walk(tree):
            self._bind(node)

    def _bind(self, node: ast.AST) -> None:
        names: list[str] = []
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store | ast.Del):
            names.append(node.id)
        elif isinstance(node, ast.arg):
            names.append(node.arg)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.append(node.name)
        elif isinstance(node, ast.Global | ast.Nonlocal):
            names.extend(node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.append(node.name)
        elif isinstance(node, ast.MatchAs | ast.MatchStar) and node.name:
            names.append(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            names.append(node.rest)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".", 1)[0]
                names.append(local)
                if alias.asname or "." not in alias.name:
                    self.imports[local] = alias.name
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    self.star = True
                    continue
                local = alias.asname or alias.name
                names.append(local)
                if not node.level and node.module:
                    self.from_imports[local] = (node.module, alias.name)
        else:
            type_param_name = getattr(node, "name", None)
            if type(node).__name__ in {"TypeVar", "ParamSpec", "TypeVarTuple"} and (
                isinstance(type_param_name, str)
            ):
                names.append(type_param_name)
        for item in names:
            self.bindings[item] += 1

    def bound_once(self, name: str) -> bool:
        return self.bindings[name] == 1

    def is_from(self, name: str, modules: frozenset[str], attr: str) -> bool:
        source = self.from_imports.get(name)
        return (
            self.bound_once(name)
            and source is not None
            and source[0] in modules
            and source[1] == attr
        )

    def is_module(self, name: str, modules: frozenset[str]) -> bool:
        return self.bound_once(name) and self.imports.get(name) in modules


def _analyze(text: str, name: str) -> frozenset[str] | None:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return None
    if _has_dynamic_rebinding(tree):
        return None
    module = _Module(tree)
    if module.star:
        return None
    chain: set[str] = set()
    if not _plain_class(module, name, chain, set()):
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value in chain:
            return None
    return frozenset(chain)


def _has_dynamic_rebinding(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _DYNAMIC_CALLS
        ):
            return True
        if isinstance(node, ast.Attribute) and node.attr == "__dict__":
            return True
        if isinstance(node, ast.Name) and node.id in _DYNAMIC_CALLS:
            # Aliased (`g = globals`) or passed on: cannot follow it.
            return True
    return False


def _plain_class(module: _Module, name: str, chain: set[str], seen: set[str]) -> bool:
    """``name`` 是本文件顶层、只绑定一次、无元类与 ``__class_getitem__`` 的类。"""
    if name in seen:
        return False
    seen.add(name)
    node = module.classes.get(name)
    if node is None or not module.bound_once(name) or node.keywords:
        return False
    if not all(_dataclass_decorator(module, d) for d in node.decorator_list):
        return False
    if _defines_class_getitem(node):
        return False
    chain.add(name)
    return all(_plain_base(module, base, chain, seen) for base in node.bases)


def _defines_class_getitem(node: ast.ClassDef) -> bool:
    for item in ast.walk(node):
        if (
            isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
            and item.name == "__class_getitem__"
        ):
            return True
        if isinstance(item, ast.Name) and item.id == "__class_getitem__":
            return True
        if isinstance(item, ast.Attribute) and item.attr == "__class_getitem__":
            return True
    return False


def _dataclass_decorator(module: _Module, node: ast.expr) -> bool:
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Name):
        return module.is_from(target.id, frozenset({"dataclasses"}), "dataclass")
    return (
        isinstance(target, ast.Attribute)
        and target.attr == "dataclass"
        and isinstance(target.value, ast.Name)
        and module.is_module(target.value.id, frozenset({"dataclasses"}))
    )


def _plain_base(
    module: _Module, base: ast.expr, chain: set[str], seen: set[str]
) -> bool:
    if isinstance(base, ast.Subscript):
        base = base.value
    if isinstance(base, ast.Name):
        if base.id == "object" and module.bindings[base.id] == 0:
            return True
        if module.is_from(base.id, _TYPING_MODULES, "Generic"):
            chain.add(base.id)
            return True
        return _plain_class(module, base.id, chain, seen)
    return (
        isinstance(base, ast.Attribute)
        and base.attr == "Generic"
        and isinstance(base.value, ast.Name)
        and module.is_module(base.value.id, _TYPING_MODULES)
    )


class _Sources:
    """一次查询内按文件记忆的源码与被索引的 Python 文件列表。"""

    def __init__(self, cache: Any, project_root: str) -> None:
        self._cache = cache
        self._root = project_root
        self._text: dict[str, str | None] = {}
        self._paths: list[str] | None = None
        self._paths_read = False
        self._elsewhere: dict[tuple[str, str], bool] = {}

    def text(self, file_path: str) -> str | None:
        if file_path not in self._text:
            value: str | None = None
            try:
                with open(
                    os.path.join(self._root, file_path), encoding="utf-8"
                ) as handle:
                    value = handle.read()
            except (OSError, UnicodeDecodeError, TypeError, ValueError):
                value = None
            self._text[file_path] = value
        return self._text[file_path]

    def python_paths(self) -> list[str] | None:
        if not self._paths_read:
            self._paths_read = True
            try:
                rows = (
                    self._cache.get_conn()
                    .execute(
                        "SELECT file_path FROM ast_index WHERE language = 'python'"
                    )
                    .fetchall()
                )
                self._paths = [str(row[0]) for row in rows]
            except Exception:  # noqa: BLE001 — unreadable: keep the guard
                self._paths = None
        return self._paths

    def rebound_elsewhere(self, file_path: str, name: str) -> bool:
        """另一个被索引的 Python 文件可能替换 ``name``；无法读取按“可能”处理。"""
        key = (file_path, name)
        if key not in self._elsewhere:
            self._elsewhere[key] = self._scan(file_path, name)
        return self._elsewhere[key]

    def _scan(self, file_path: str, name: str) -> bool:
        paths = self.python_paths()
        if paths is None:
            return True
        word = re.escape(name)
        pattern = re.compile(rf"\.\s*{word}\s*(?::[^=\n]*)?=(?!=)|([\"']){word}\1")
        own = file_path.replace("\\", "/")
        for other in paths:
            if other.replace("\\", "/") == own:
                continue
            text = self.text(other)
            if text is None:
                return True
            if name in text and pattern.search(text):
                return True
        return False


def _excludes(sources: _Sources, site: dict[str, Any], target: str) -> bool:
    file_path = str(site.get("file") or "")
    if not file_path.lower().endswith(_SUFFIX):
        return False
    name = subscripted_name(str(site.get("callee") or ""))
    if name is None:
        return False
    text = sources.text(file_path)
    if text is None:
        return False
    chain = _chain_for(text, name)
    if chain is None or target in chain:
        return False
    return not sources.rebound_elsewhere(file_path, name)


def drop_class_constructions(
    cache: Any,
    project_root: str | None,
    unresolved: list[dict[str, Any]] | None,
    excluded: list[dict[str, Any]] | None,
    target: str,
) -> tuple[list[dict[str, Any]] | None, list[dict[str, Any]] | None]:
    """把只构造项目类实例的 ``X[T](...)`` 调用点移到已排除；读取失败时原样返回。"""
    if unresolved is None or excluded is None or cache is None or not project_root:
        return unresolved, excluded
    if target in CONSTRUCTION_METHODS:
        return unresolved, excluded
    sources = _Sources(cache, project_root)
    kept: list[dict[str, Any]] = []
    moved: list[dict[str, Any]] = []
    for site in unresolved:
        if _excludes(sources, site, target):
            moved.append(
                {
                    **site,
                    "classification": "excluded",
                    "reason_code": CLASS_CONSTRUCTION_REASON,
                }
            )
        else:
            kept.append(site)
    if not moved:
        return unresolved, excluded
    merged = sorted([*excluded, *moved], key=lambda s: (s["file"], s["line"]))
    return kept, merged


__all__ = [
    "CLASS_CONSTRUCTION_REASON",
    "CONSTRUCTION_METHODS",
    "clear_chains",
    "constructs_only",
    "drop_class_constructions",
    "subscripted_name",
]
