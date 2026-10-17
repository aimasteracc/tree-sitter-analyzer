"""#1635：``self.m()`` 绑定规则的边界——每条分支都只会更保守。"""

from __future__ import annotations

import sqlite3

from tree_sitter_analyzer.cached_edge_resolution import CachedEdgeResolver
from tree_sitter_analyzer.call_graph import FunctionRef
from tree_sitter_analyzer.call_graph_self_dispatch import (
    SubclassIndex,
    override_candidates,
    own_class_target,
)

_BASE = FunctionRef("base.py", "hook", 5, "python", receiver="Base")
_SUB = FunctionRef("base.py", "hook", 10, "python", receiver="Sub")
_LEAF = FunctionRef("leaf.py", "hook", 5, "python", receiver="Leaf")
_OTHER = FunctionRef("other.py", "hook", 2, "python", receiver="Unrelated")


class _Rows:
    def __init__(self, rows: list[tuple[str, str]]) -> None:
        self._rows = rows

    def get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE edges (source_node_id, target_node_id, kind)")
        conn.executemany("INSERT INTO edges VALUES (?, ?, 'extends')", self._rows)
        return conn


class _Broken:
    def get_conn(self) -> sqlite3.Connection:
        raise sqlite3.OperationalError("no such table: edges")


_HIERARCHY = _Rows(
    [
        ("base.py:Sub:9", "base.py:Base:1"),
        ("leaf.py:Leaf:4", "base.py:Sub:9"),
        ("odd-node-id", "base.py:Base:1"),
    ]
)


def _by_name() -> dict[str, list[FunctionRef]]:
    return {"hook": [_BASE, _SUB, _LEAF, _OTHER]}


def test_own_class_target_requires_an_own_instance_receiver() -> None:
    assert own_class_target([_BASE, _SUB], "self", "Base") == _BASE
    assert own_class_target([_BASE, _SUB], "obj", "Base") is None
    assert own_class_target([_BASE, _SUB], "self", None) is None
    # 同类同名的两个定义无法区分：不绑定。
    twin = FunctionRef("base.py", "hook", 20, "python", receiver="Base")
    assert own_class_target([_BASE, twin], "self", "Base") is None


def test_subclasses_are_transitive_and_skip_unparsable_ids() -> None:
    assert SubclassIndex(_HIERARCHY).subclasses("Base") == {"Sub", "Leaf"}
    assert SubclassIndex(_HIERARCHY).subclasses("Leaf") == set()


def test_unreadable_extends_edges_give_no_subclass_evidence() -> None:
    assert SubclassIndex(_Broken()).subclasses("Base") == set()


def test_override_candidates_are_subclass_methods_only() -> None:
    index = SubclassIndex(_HIERARCHY)

    assert override_candidates(index, _by_name(), "hook", "self", "Base") == [
        _SUB,
        _LEAF,
    ]
    assert override_candidates(index, _by_name(), "hook", "obj", "Base") == []
    assert override_candidates(index, _by_name(), "hook", "self", "Leaf") == []


def _resolver(subclasses: SubclassIndex | None) -> CachedEdgeResolver:
    return CachedEdgeResolver(
        functions_by_name=_by_name(),
        functions_by_file={
            "base.py": [_BASE, _SUB],
            "leaf.py": [_LEAF],
            "other.py": [_OTHER],
        },
        file_import_map={},
        subclasses=subclasses,
    )


def _edge(full: str) -> dict[str, str]:
    return {
        "callee_name": "hook",
        "callee_full": full,
        "callee_resolution": "local",
        "callee_resolved_file": "base.py",
    }


def test_self_call_binds_own_method_and_marks_overrides_possible() -> None:
    targets = _resolver(SubclassIndex(_HIERARCHY)).resolve(
        _edge("self.hook"), "base.py", "Base"
    )

    assert targets.certain == [_BASE]
    assert targets.possible == [_SUB, _LEAF]


def test_without_subclass_index_only_same_file_candidates_stay_possible() -> None:
    targets = _resolver(None).resolve(_edge("self.hook"), "base.py", "Base")

    assert (targets.certain, targets.possible) == ([_BASE], [_SUB])


def test_self_call_without_own_method_is_left_unbound() -> None:
    # 外围类没有自己的 `hook`（继承而来）：不猜，候选仍只是可能目标。
    targets = _resolver(None).resolve(_edge("self.hook"), "base.py", "Mixin")

    assert (targets.certain, targets.possible) == ([], [_BASE, _SUB])


def test_super_call_never_targets_the_callers_own_method() -> None:
    targets = _resolver(None).resolve(_edge("super().hook"), "base.py", "Sub")

    assert _SUB not in targets.certain + targets.possible


def test_other_receivers_and_module_callers_are_unchanged() -> None:
    resolver = _resolver(SubclassIndex(_HIERARCHY))

    assert resolver.resolve(_edge("obj.hook"), "base.py", "Base").certain == []
    assert resolver.resolve(_edge("self.hook"), "base.py", None).certain == []
