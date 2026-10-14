"""cached_reexport_binding：沿包再导出与基类绑定方法定义（#1578）。

公开路径（nav callers）的端到端用例在 ``tests/unit/mcp/tools/test_nav_not_found_contract.py``；
这里固定证据不足时"不绑定"的边界行为。
"""

from __future__ import annotations

import sqlite3

from tree_sitter_analyzer.cached_reexport_binding import (
    PackageReexportBinder,
    _BindingIndex,
    _class_node,
    _locate_class,
    _method_in_bases,
    _Reexport,
)
from tree_sitter_analyzer.call_graph import FunctionRef


def _index(**overrides) -> _BindingIndex:
    base = {
        "module_to_file": {"a": "a/__init__.py", "b": "b/__init__.py"},
        "reexports": {},
        "classes": set(),
        "bases": {},
    }
    base.update(overrides)
    return _BindingIndex(**base)


def _method(path: str, cls: str, line: int) -> FunctionRef:
    return FunctionRef(path, "run", line, "python", end_line=line + 1, receiver=cls)


def test_unresolved_parent_node_is_not_a_class() -> None:
    # #1578：未解析的基类以 ``class:Name`` 记录，不能当作项目内的类。
    assert _class_node("class:Exception") is None


def test_reexport_to_missing_module_does_not_bind() -> None:
    # #1578：再导出指向索引外的模块时没有证据，返回 None 而不是猜测。
    index = _index(reexports={("a/__init__.py", "Thing"): _Reexport(".gone", True, "")})
    assert _locate_class(index, "a/__init__.py", "Thing") is None


def test_cyclic_reexport_terminates_without_binding() -> None:
    # #1578：两个包互相再导出同名对象时，跳数上限保证终止。
    index = _index(
        reexports={
            ("a/__init__.py", "Thing"): _Reexport("b", False, ""),
            ("b/__init__.py", "Thing"): _Reexport("a", False, ""),
        }
    )
    assert _locate_class(index, "a/__init__.py", "Thing") is None


def test_diamond_bases_resolve_to_the_first_declared_definition() -> None:
    # #1578：菱形继承中公共基类只访问一次，按声明顺序取第一个定义。
    child, left, right, root = (
        ("c.py", "Child"),
        ("l.py", "Left"),
        ("r.py", "Right"),
        ("o.py", "Root"),
    )
    index = _index(bases={child: [left, right], left: [root], right: [root]})
    functions = {"o.py": [_method("o.py", "Root", 3)]}
    assert _method_in_bases(index, child, "run", functions) == [
        _method("o.py", "Root", 3)
    ]


class _UnreadableCache:
    def get_conn(self) -> sqlite3.Connection:
        raise sqlite3.OperationalError("no such table: ast_imports")


def test_unreadable_cache_never_binds() -> None:
    # #1578：旧索引缺表时不绑定，边保持 possible（由完整性如实报告）。
    binder = PackageReexportBinder(_UnreadableCache())
    assert binder.bind("pkg/__init__.py", "Thing", "run", {}) == []
