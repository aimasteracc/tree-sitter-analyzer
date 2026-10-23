"""#1759：由项目外函数产出的可调用对象，不经点名无法到达项目内的目标。

声明文件守卫（RFC-0028 §1.2）把计算式调用点（``f(x)(…)``、``ns.T[…](…)``）都算作
“可能指向目标”。当产出可调用对象的头部是**从项目外模块导入**的名字时——
``wrap_app_handling_exceptions(app, request)(scope, receive, send)``（starlette）、
``anyio.create_memory_object_stream[bytes](…)``——它返回的对象要成为项目里的某个
方法，只能把那个方法交给它：要么按名传入（非调用引用门会看见），要么经 ``getattr``
等动态取名（文本里可见，此处保留守卫）。因此这类调用点从守卫中排除，原因码为
``produced_by_external_call``。

只在能确认时排除：Python / JavaScript 的调用点；头部是导入绑定且该文件没有重新赋值
它；模块不是项目内模块（相对导入、或顶层包是项目里的目录 / 模块，都视为项目内）。
"""

from __future__ import annotations

import ast
import os
import re
from typing import Any

#: 排除原因码。
EXTERNAL_PRODUCER_REASON = "produced_by_external_call"
#: 排除原因码：模块级、从不修改的容器字面量里取出的可调用对象（值都写在字面量里）。
LITERAL_CONTAINER_REASON = "literal_container_dispatch"
#: 修改容器内容的方法名。
_MUTATORS = frozenset(
    {
        "update",
        "setdefault",
        "__setitem__",
        "append",
        "extend",
        "insert",
        "add",
        "clear",
        "pop",
        "popitem",
        "remove",
    }
)


def _first_target(tree: ast.Module, name: str) -> ast.Name | None:
    """模块级第一次给 ``name`` 赋值的目标节点。"""
    for node in tree.body:
        targets = (
            node.targets
            if isinstance(node, ast.Assign)
            else [node.target]
            if isinstance(node, ast.AnnAssign)
            else []
        )
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                return target
    return None


#: 运行时按名取值的构造：出现即保留守卫（与 ``callers_dispatch`` 一致）。
_DYNAMIC_MARKERS = (
    "getattr(",
    "setattr(",
    "hasattr(",
    "globals(",
    "locals(",
    "vars(",
    "eval(",
    "exec(",
    "__getattribute__",
    "attrgetter(",
    "methodcaller(",
    "Reflect.",
    "Function(",
)
#: 头部标识符，后面紧跟调用 / 取属性 / 下标。
_HEAD = re.compile(r"^([A-Za-z_$][\w$]*)\s*[(.\[]")
#: 适用的语言（其余语言保留守卫）。
_LANGUAGES = ("python", "javascript", "jsx", "typescript", "tsx")


def _produced_shape(text: str) -> bool:
    """调用的是产出值：``f(...)``、``f(...)(...)``、``m.f(...)[...]``、``m.T[...]``。"""
    return "(" in text or "[" in text


class ExternalProducers:
    """按文件记忆导入绑定、项目顶层名与源码；一次查询内使用。"""

    def __init__(self, cache: Any, project_root: str | None) -> None:
        self._cache = cache
        self._root = project_root
        self._imports: dict[str, dict[str, tuple[str, bool]]] = {}
        self._text: dict[str, str | None] = {}
        self._tops: set[str] | None = None
        self._languages: dict[str, str] | None = None

    def excludes(self, site: dict[str, Any]) -> str | None:
        """排除原因码；不能排除时为 None。"""
        file_path = str(site.get("file") or "")
        text = str(site.get("callee") or "").strip()
        if not file_path or not text or any(m in text for m in _DYNAMIC_MARKERS):
            return None
        if self._language(file_path) not in _LANGUAGES or not _produced_shape(text):
            return None
        head = _HEAD.match(text)
        if head is None:
            return None
        name = head.group(1)
        if text[len(name) :].lstrip().startswith("[") and self._literal_container(
            file_path, name
        ):
            return LITERAL_CONTAINER_REASON
        return EXTERNAL_PRODUCER_REASON if self._external(file_path, name) else None

    def _literal_container(self, file_path: str, name: str) -> bool:
        """``name`` 是模块级只赋值一次、从不修改的容器字面量（Python），且不含动态取名。"""
        if self._language(file_path) != "python":
            return False
        text = self._source(file_path)
        if text is None:
            return False
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            return False
        literal = None
        assigned = 0
        for node in tree.body:
            targets: list[ast.expr] = []
            value = None
            if isinstance(node, ast.Assign):
                targets, value = list(node.targets), node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets, value = [node.target], node.value
            if any(isinstance(t, ast.Name) and t.id == name for t in targets):
                assigned += 1
                literal = value
        if assigned != 1 or not isinstance(
            literal, ast.Dict | ast.List | ast.Tuple | ast.Set
        ):
            return False
        # An empty literal is a registry meant to be filled at runtime; keep the guard.
        if not (literal.keys if isinstance(literal, ast.Dict) else literal.elts):
            return False
        if any(marker in ast.unparse(literal) for marker in _DYNAMIC_MARKERS):
            return False
        # Another module may fill it (`registry.TABLE.update(vars(plugins))`).
        if self._named_elsewhere(file_path, name):
            return False
        for item in ast.walk(tree):
            if isinstance(item, ast.Global | ast.Nonlocal) and name in item.names:
                return False
            if (
                isinstance(item, ast.Subscript)
                and isinstance(item.ctx, ast.Store | ast.Del)
                and isinstance(item.value, ast.Name)
                and item.value.id == name
            ):
                return False
            if (
                isinstance(item, ast.Attribute)
                and isinstance(item.value, ast.Name)
                and item.value.id == name
                and item.attr in _MUTATORS
            ):
                return False
            if (
                isinstance(item, ast.Name)
                and item.id == name
                and isinstance(item.ctx, ast.Store | ast.Del)
            ):
                if item is not _first_target(tree, name):
                    return False
        return True

    def _named_elsewhere(self, file_path: str, name: str) -> bool:
        """Another indexed source file contains ``name`` as a word; unreadable counts as yes."""
        try:
            rows = self._conn().execute("SELECT file_path FROM ast_index").fetchall()
        except Exception:  # noqa: BLE001 — unreadable: assume it is referenced
            return True
        word = re.compile(rf"(?<![\w$]){re.escape(name)}(?![\w$])")
        for (other,) in rows:
            other_path = str(other)
            if other_path == file_path:
                continue
            text = self._source(other_path)
            if text is None or (name in text and word.search(text)):
                return True
        return False

    def _external(self, file_path: str, name: str) -> bool:
        binding = self._bindings(file_path).get(name)
        if binding is None:
            return False
        module, relative = binding
        if relative or self._is_project_module(module, file_path):
            return False
        return not self._rebound(file_path, name)

    def _source(self, file_path: str) -> str | None:
        if file_path not in self._text:
            value: str | None = None
            try:
                with open(
                    os.path.join(str(self._root), file_path), encoding="utf-8"
                ) as handle:
                    value = handle.read()
            except (OSError, UnicodeDecodeError, TypeError, ValueError):
                value = None
            self._text[file_path] = value
        return self._text[file_path]

    # ----------------------------------------------------------------- facts
    def _conn(self) -> Any:
        return self._cache.get_conn()

    def _language(self, file_path: str) -> str:
        if self._languages is None:
            try:
                rows = (
                    self._conn()
                    .execute("SELECT file_path, language FROM ast_index")
                    .fetchall()
                )
                self._languages = {str(r[0]): str(r[1] or "") for r in rows}
            except Exception:  # noqa: BLE001 — unreadable: keep the guard
                self._languages = {}
        return self._languages.get(file_path, "")

    def _bindings(self, file_path: str) -> dict[str, tuple[str, bool]]:
        if file_path not in self._imports:
            found: dict[str, tuple[str, bool]] = {}
            try:
                rows = (
                    self._conn()
                    .execute(
                        "SELECT local_name, module_path, is_relative, is_star FROM ast_imports "
                        "WHERE file_path = ?",
                        (file_path,),
                    )
                    .fetchall()
                )
            except Exception:  # noqa: BLE001 — unreadable: no binding, keep the guard
                rows = []
            for local, module, relative, star in rows:
                if star or not local:
                    continue
                key = str(local)
                value = (str(module or ""), bool(relative))
                # 同名导入两次且来源不同：无法确定，不作为外部绑定。
                if key in found and found[key] != value:
                    found[key] = ("", True)
                else:
                    found[key] = value
            self._imports[file_path] = found
        return self._imports[file_path]

    def _is_project_module(self, module: str, file_path: str) -> bool:
        if not module:
            return True
        language = self._language(file_path)
        if language != "python":
            # JS/TS：非相对说明符是包；相对说明符已在上面判为项目内。
            return module.startswith((".", "/"))
        return module.split(".", 1)[0] in self._project_tops()

    def _project_tops(self) -> set[str]:
        if self._tops is None:
            tops: set[str] = set()
            try:
                rows = (
                    self._conn()
                    .execute(
                        "SELECT file_path FROM ast_index WHERE language = 'python'"
                    )
                    .fetchall()
                )
            except Exception:  # noqa: BLE001 — unreadable: treat every module as project
                rows = []
                tops.add("")
            for (path,) in rows:
                parts = str(path).replace("\\", "/").split("/")
                for part in parts:
                    # 每一级目录名与模块名都可能是导入的顶层名（src 布局、嵌套包）。
                    tops.add(part[:-3] if part.endswith(".py") else part)
            self._tops = tops
        if "" in self._tops:
            return {""} | self._tops
        return self._tops

    def _rebound(self, file_path: str, name: str) -> bool:
        text = self._source(file_path)
        if text is None:
            return True
        word = re.escape(name)
        pattern = (
            rf"(?m)^[ \t]*(?:(?:const|let|var|global)[ \t]+)?{word}[ \t]*(?::[^=\n]*)?=(?!=)"
            rf"|^[ \t]*(?:def|class|function)[ \t]+{word}\b"
        )
        return re.search(pattern, text) is not None


def drop_external_producers(
    cache: Any,
    project_root: str | None,
    unresolved: list[dict[str, Any]] | None,
    excluded: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]] | None, list[dict[str, Any]] | None]:
    """把由项目外函数产出可调用对象的调用点移到已排除；读取失败时原样返回。"""
    if unresolved is None or excluded is None or cache is None or not project_root:
        return unresolved, excluded
    producers = ExternalProducers(cache, project_root)
    kept: list[dict[str, Any]] = []
    moved: list[dict[str, Any]] = []
    for site in unresolved:
        reason = producers.excludes(site)
        if reason:
            moved.append({**site, "classification": "excluded", "reason_code": reason})
        else:
            kept.append(site)
    if not moved:
        return unresolved, excluded
    merged = sorted([*excluded, *moved], key=lambda s: (s["file"], s["line"]))
    return kept, merged


__all__ = ["EXTERNAL_PRODUCER_REASON", "ExternalProducers", "drop_external_producers"]
