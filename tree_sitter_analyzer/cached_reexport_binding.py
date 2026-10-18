"""沿包再导出与基类，把持久化解析补全到真正的方法定义（#1578）。

写入期解析把 ``extractor._extract_import_info()``（``extractor: PythonElementExtractor``）
记为 ``callee_resolved_file = python_plugin/__init__.py``：类型名来自包的再导出，
而方法定义在基类 ``PythonImportPackageMixin`` 所在的文件中。``__init__.py`` 里没有
同名函数，于是这条边无法绑定，限定名查询回答 NOT_FOUND。

本模块只使用索引中的**静态**证据：

1. ``ast_imports``：包 ``__init__.py`` 的 ``from .x import Name`` 再导出链；
2. ``ast_symbol_rows``：类定义所在的文件；
3. ``edges`` 中已解析的 ``extends`` 边：类的基类（按声明顺序广度优先）。

任何一步缺证据（惰性 ``__getattr__`` 导出、星号导入、未解析的基类）都返回空，
由调用方把这条边留作 ``possible``，而不是猜测。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .synapse_resolver._context import _build_module_to_file, _resolve_module_to_file

if TYPE_CHECKING:
    from .call_graph import FunctionRef

#: 再导出链的最大跳数，防止环状再导出无限循环。
_MAX_REEXPORT_HOPS = 8
#: 继承图中最多访问的类数，防止异常索引拖慢构图。
_MAX_MRO_CLASSES = 64


@dataclass(frozen=True)
class _Reexport:
    module_path: str
    is_relative: bool
    alias_of: str


@dataclass
class _BindingIndex:
    module_to_file: dict[str, str]
    reexports: dict[tuple[str, str], _Reexport]
    classes: set[tuple[str, str]]
    bases: dict[tuple[str, str], list[tuple[str, str]]]


def _class_node(node_id: str) -> tuple[str, str] | None:
    """把 ``path:Class:line`` 形式的节点 id 拆成 ``(path, Class)``。"""
    parts = str(node_id).rsplit(":", 2)
    if len(parts) != 3 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


def _load_index(conn: Any) -> _BindingIndex:
    files = [row[0] for row in conn.execute("SELECT file_path FROM ast_index")]
    reexports: dict[tuple[str, str], _Reexport] = {}
    for row in conn.execute(
        "SELECT file_path, module_path, local_name, alias_of, is_relative "
        "FROM ast_imports WHERE is_star = 0 AND file_path LIKE '%__init__.py'"
    ):
        reexports[(row[0], row[2])] = _Reexport(row[1], bool(row[4]), row[3] or "")
    classes = {
        (row[0], row[1])
        for row in conn.execute(
            "SELECT file_path, name FROM ast_symbol_rows WHERE kind = 'class'"
        )
    }
    bases: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for row in conn.execute(
        "SELECT source_node_id, target_node_id FROM edges WHERE kind = 'extends'"
    ):
        child, parent = _class_node(row[0]), _class_node(row[1])
        if child is not None and parent is not None:
            bases.setdefault(child, []).append(parent)
    return _BindingIndex(_build_module_to_file(files), reexports, classes, bases)


class PackageReexportBinder:
    """惰性加载绑定证据；第一次需要时才读库，读库失败则永远不绑定。"""

    def __init__(self, cache: Any) -> None:
        self._cache = cache
        self._index: _BindingIndex | None = None
        self._loaded = False

    def _get_index(self) -> _BindingIndex | None:
        if not self._loaded:
            self._loaded = True
            try:
                self._index = _load_index(self._cache.get_conn())
            except Exception:  # nosec B110 — 缺表 / 旧索引：不绑定，交给 possible。
                self._index = None
        return self._index

    def evidence(self) -> _BindingIndex | None:
        """#1657：构图实际使用的绑定证据（读库失败时为 None），供输入摘要使用。"""
        return self._get_index()

    def bind(
        self,
        resolved_file: str,
        receiver: str,
        base_name: str,
        functions_by_file: dict[str, list[FunctionRef]],
    ) -> list[FunctionRef]:
        """返回 ``receiver.base_name`` 在静态证据下的定义；无法确定时返回空。"""
        index = self._get_index()
        if index is None:
            return []
        located = _locate_class(index, resolved_file, receiver)
        if located is None:
            return []
        return _method_in_bases(index, located, base_name, functions_by_file)


def _locate_class(
    index: _BindingIndex, file_path: str, name: str
) -> tuple[str, str] | None:
    """从 ``file_path`` 出发沿包再导出找到类 ``name`` 的定义。"""
    for _ in range(_MAX_REEXPORT_HOPS):
        if (file_path, name) in index.classes:
            return file_path, name
        reexport = index.reexports.get((file_path, name))
        if reexport is None:
            return None
        target = _resolve_module_to_file(
            reexport.module_path, reexport.is_relative, file_path, index.module_to_file
        )
        if not target:
            return None
        file_path, name = target, reexport.alias_of or name
    return None


def _method_in_bases(
    index: _BindingIndex,
    start: tuple[str, str],
    base_name: str,
    functions_by_file: dict[str, list[FunctionRef]],
) -> list[FunctionRef]:
    """在类及其基类（声明顺序、广度优先）中找第一个定义 ``base_name`` 的类。"""
    queue = deque([start])
    seen: set[tuple[str, str]] = set()
    while queue and len(seen) < _MAX_MRO_CLASSES:
        file_path, class_name = queue.popleft()
        if (file_path, class_name) in seen:
            continue
        seen.add((file_path, class_name))
        hits = [
            ref
            for ref in functions_by_file.get(file_path, [])
            if ref.name == base_name and ref.receiver == class_name
        ]
        if hits:
            return hits
        queue.extend(index.bases.get((file_path, class_name), []))
    return []
