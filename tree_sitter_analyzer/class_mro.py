"""#1677：``self.m()`` 在外围类没有 ``m`` 时，按 MRO 找最近的继承定义。

索引里的 ``extends`` 边给出每个类的基类：已解析的基类是 ``file:Class:line`` 节点，
未解析的是 ``class:Name`` 占位。基类的顺序取自 ``symbols_json`` 的 ``parents``。

判定（只会更保守）：

* 祖先链上的每个基类都解析到项目类，或是外部基类且运行时确认它没有 ``m``
  （``ABC`` / ``Protocol`` / ``Exception`` 等标准库类：外部类不可能继承项目类，
  因此去掉它不改变项目类在 MRO 中的相对顺序）——MRO 完全已知，按 C3 线性化取
  第一个定义 ``m`` 的类，它是确定目标；
* 任何一个基类未解析且无法确认（第三方库类、动态基类），或 C3 线性化不一致——
  MRO 未知，找到的定义只是可能目标。
"""

from __future__ import annotations

import builtins
import importlib
import json
import sqlite3
from collections import defaultdict
from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Any

from .synapse_resolver._constants import STDLIB_NAMES_PY

#: 线性化最多访问的类数，防止异常索引拖慢解析。
_MAX_CLASSES = 64
#: 运行时可直接取到、用来确认“外部基类没有该方法”的模块。
_RUNTIME_MODULES = ("typing", "abc", "enum", "collections", "dataclasses")

_CLASS_ROWS_SQL = (
    "SELECT ast_index.file_path, json_extract(value, '$.name'), "
    "json_extract(value, '$.line'), json_extract(value, '$.parents') "
    "FROM ast_index, json_each(json_extract(ast_index.symbols_json, '$.symbols')) "
    "WHERE ast_index.language = 'python' AND json_extract(value, '$.kind') = 'class'"
)
_METHOD_ROWS_SQL = (
    "SELECT ast_index.file_path, json_extract(value, '$.class'), "
    "json_extract(value, '$.name'), json_extract(value, '$.line') "
    "FROM ast_index, json_each(json_extract(ast_index.symbols_json, '$.symbols')) "
    "WHERE ast_index.language = 'python' "
    "AND json_extract(value, '$.kind') IN ('function', 'method') "
    "AND json_extract(value, '$.class') IS NOT NULL"
)
_EXTENDS_SQL = "SELECT source_node_id, target_node_id FROM edges WHERE kind = 'extends'"


@dataclass(frozen=True)
class ClassKey:
    """项目类的身份：定义文件与类名。"""

    file: str
    name: str


@dataclass
class Hierarchy:
    """按类给出有序基类（项目类为 ``ClassKey``，未解析为基类文本）与方法表。"""

    parents: dict[ClassKey, list[ClassKey | str]] = field(default_factory=dict)
    methods: dict[ClassKey, dict[str, int]] = field(default_factory=dict)
    #: 项目类名（惰性建立；``parents`` 填充完成后才会被读取）。
    _names: frozenset[str] | None = field(default=None, repr=False, compare=False)

    def _external(self, base_text: str, name: str) -> bool:
        """未解析的基类确认是外部类且没有 ``name``。

        #1834：名字与项目类相同的未解析基类是第二遍解析定不下来的歧义基类
        （同名类不止一个），不是外部类——即使标准库里恰有同名类也不能确认。
        """
        if self._names is None:
            self._names = frozenset(key.name for key in self.parents)
        simple = base_text.split("[", 1)[0].strip().rsplit(".", 1)[-1]
        return simple not in self._names and external_lacks(base_text, name)

    def nearest(self, owner: ClassKey, name: str) -> tuple[ClassKey | None, bool]:
        """``owner`` 的 MRO 中第一个定义 ``name`` 的类，以及 MRO 是否完全已知。"""
        order, known = self._linearize(owner, name, ())
        for klass in order:
            if name in self.methods.get(klass, {}):
                return klass, known
        return None, known

    def after(self, owner: ClassKey, name: str) -> tuple[ClassKey | None, bool]:
        """#1699：``super().name()``——``owner`` 之后的 MRO 中第一个定义 ``name`` 的类。"""
        order, known = self._linearize(owner, name, ())
        for klass in order[1:]:
            if name in self.methods.get(klass, {}):
                return klass, known
        return None, known

    def classes_named(self, name: str) -> list[ClassKey]:
        """项目中名为 ``name`` 的类（同名类可能不止一个）。"""
        return [key for key in self.parents if key.name == name]

    def _linearize(
        self, klass: ClassKey, name: str, stack: tuple[ClassKey, ...]
    ) -> tuple[list[ClassKey], bool]:
        if klass in stack or len(stack) > _MAX_CLASSES:
            return [klass], False
        known = True
        sequences: list[list[ClassKey]] = []
        direct: list[ClassKey] = []
        for parent in self.parents.get(klass, []):
            if isinstance(parent, str):
                known = known and self._external(parent, name)
                continue
            order, parent_known = self._linearize(parent, name, (*stack, klass))
            known = known and parent_known
            sequences.append(order)
            direct.append(parent)
        merged = _c3_merge([*sequences, direct])
        if merged is None:
            return [klass, *direct], False
        return [klass, *merged], known


def _c3_merge(sequences: list[list[ClassKey]]) -> list[ClassKey] | None:
    """C3 合并；不一致（Python 会拒绝的类定义）时返回 None。"""
    pending = [list(seq) for seq in sequences if seq]
    result: list[ClassKey] = []
    while pending:
        for seq in pending:
            head = seq[0]
            if not any(head in other[1:] for other in pending):
                break
        else:
            return None
        result.append(head)
        pending = [[c for c in seq if c != head] for seq in pending]
        pending = [seq for seq in pending if seq]
    return result


def external_lacks(base_text: str, name: str) -> bool:
    """未解析的基类是可在运行时取到的标准库类，且它（含其基类）没有 ``name``。"""
    runtime = _runtime_class(base_text.split("[", 1)[0].strip())
    return runtime is not None and not hasattr(runtime, name)


def _runtime_class(text: str) -> type | None:
    if not text:
        return None
    if "." not in text:
        found = getattr(builtins, text, None)
        for module_name in _RUNTIME_MODULES:
            if found is not None:
                break
            found = getattr(importlib.import_module(module_name), text, None)
        return found if isinstance(found, type) else None
    module_name, _, attr = text.rpartition(".")
    if module_name.split(".", 1)[0] not in STDLIB_NAMES_PY:
        return None
    try:
        module = importlib.import_module(module_name)
    except Exception:  # nosec B110 — 取不到即“无法确认”，MRO 视为未知。
        return None
    found = getattr(module, attr, None)
    return found if isinstance(found, type) else None


def load_hierarchy(conn: sqlite3.Connection) -> Hierarchy:
    """从索引读取 Python 类的有序基类与方法；读库失败时返回空层级（没有证据）。"""
    try:
        classes = conn.execute(_CLASS_ROWS_SQL).fetchall()
        method_rows = conn.execute(_METHOD_ROWS_SQL).fetchall()
        extends = conn.execute(_EXTENDS_SQL).fetchall()
    except sqlite3.Error:
        return Hierarchy()
    return _hierarchy_from_rows(classes, method_rows, extends)


def load_hierarchy_update(
    conn: sqlite3.Connection, base: Hierarchy, files: Collection[str]
) -> Hierarchy:
    """#1723：在 ``base`` 上只重新读取 ``files`` 中的类与方法（其余文件的条目沿用）。

    刷新的解析范围给出 ``files``（改动文件与其依赖文件）；范围外文件的类行、方法行
    与继承边都与上一轮相同，因此结果与全量 :func:`load_hierarchy` 相同。读库失败
    退回全量读取。
    """
    wanted = sorted(set(files))
    if not wanted:
        return base
    classes: list[Any] = []
    method_rows: list[Any] = []
    try:
        for start in range(0, len(wanted), 500):
            chunk = wanted[start : start + 500]
            marks = ",".join("?" * len(chunk))
            scope = f" AND ast_index.file_path IN ({marks})"
            classes += conn.execute(_CLASS_ROWS_SQL + scope, chunk).fetchall()  # nosec B608
            method_rows += conn.execute(_METHOD_ROWS_SQL + scope, chunk).fetchall()  # nosec B608
        extends = conn.execute(_EXTENDS_SQL).fetchall()
    except sqlite3.Error:
        return load_hierarchy(conn)
    part = _hierarchy_from_rows(classes, method_rows, extends)
    keep = set(wanted)
    updated = Hierarchy()
    updated.parents = {k: v for k, v in base.parents.items() if k.file not in keep}
    updated.parents.update(part.parents)
    updated.methods = {k: v for k, v in base.methods.items() if k.file not in keep}
    updated.methods.update(part.methods)
    return updated


def _hierarchy_from_rows(
    classes: list[Any], method_rows: list[Any], extends: list[Any]
) -> Hierarchy:
    resolved: dict[tuple[str, str, int], list[ClassKey]] = defaultdict(list)
    for source, target in extends:
        child, parent = _node(source), _node(target)
        if child is not None and parent is not None:
            resolved[child].append(ClassKey(parent[0], parent[1]))
    hierarchy = Hierarchy()
    for file_path, class_name, line, parents_json in classes:
        if not class_name:
            continue
        key = ClassKey(str(file_path), str(class_name))
        targets = resolved.get((str(file_path), str(class_name), int(line or 0)), [])
        hierarchy.parents[key] = _ordered_parents(parents_json, targets)
    for file_path, class_name, method, line in method_rows:
        key = ClassKey(str(file_path), str(class_name))
        hierarchy.methods.setdefault(key, {})[str(method)] = int(line or 0)
    return hierarchy


def _ordered_parents(
    parents_json: Any, targets: list[ClassKey]
) -> list[ClassKey | str]:
    """按 ``parents`` 文本的顺序，把每个基类换成已解析的项目类，否则保留文本。"""
    try:
        texts = [str(text) for text in json.loads(parents_json or "[]")]
    except (TypeError, ValueError):
        texts = []
    remaining = list(targets)
    ordered: list[ClassKey | str] = []
    for text in texts:
        simple = text.split("[", 1)[0].strip().rsplit(".", 1)[-1]
        match = next((key for key in remaining if key.name == simple), None)
        if match is None:
            ordered.append(text)
        else:
            remaining.remove(match)
            ordered.append(match)
    # 文本里没有对应项的已解析边（解析器的别名等）：无法定序，记为未知基类。
    ordered.extend(f"<unordered {key.name}>" for key in remaining)
    return ordered


def _node(node_id: Any) -> tuple[str, str, int] | None:
    """``path:Class:line`` 节点；``class:Name`` 占位与无法解析的 id 返回 None。"""
    parts = str(node_id).rsplit(":", 2)
    if len(parts) != 3 or not parts[0] or not parts[1] or parts[0] == "class":
        return None
    try:
        return parts[0], parts[1], int(parts[2])
    except ValueError:
        return None


__all__ = ["ClassKey", "Hierarchy", "external_lacks", "load_hierarchy"]
