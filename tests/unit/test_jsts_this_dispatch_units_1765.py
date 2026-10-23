"""#1765：JS/TS ``this.m()`` 分派与 ``extends`` 链定位的单元行为（不建索引）。"""

from __future__ import annotations

import sqlite3
from collections import defaultdict

import pytest

from tree_sitter_analyzer.cached_edge_resolution import CachedEdgeResolver, EdgeTargets
from tree_sitter_analyzer.call_graph import FunctionRef
from tree_sitter_analyzer.call_graph_self_dispatch import SubclassIndex


class _Cache:
    def __init__(self, extends: list[tuple[str, str]], classes: list[str]) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE edges (source_node_id TEXT, target_node_id TEXT, kind TEXT)"
        )
        self.conn.execute("CREATE TABLE ast_symbol_rows (name TEXT, kind TEXT)")
        self.conn.executemany("INSERT INTO edges VALUES (?, ?, 'extends')", extends)
        self.conn.executemany(
            "INSERT INTO ast_symbol_rows VALUES (?, 'class')", [(c,) for c in classes]
        )

    def get_conn(self) -> sqlite3.Connection:
        return self.conn


class _Broken:
    def get_conn(self):
        raise RuntimeError("no index")


def _ref(file: str, cls: str | None, name: str, line: int) -> FunctionRef:
    return FunctionRef(file, name, line, "typescript", receiver=cls, end_line=line)


def _resolver(refs, subclasses, imports=None) -> CachedEdgeResolver:
    by_name, by_file = defaultdict(list), defaultdict(list)
    for ref in refs:
        by_name[ref.name].append(ref)
        by_file[ref.file_path].append(ref)
    return CachedEdgeResolver(
        functions_by_name=dict(by_name),
        functions_by_file=dict(by_file),
        file_import_map={},
        subclasses=subclasses,
        jsts_imports=imports or {},
    )


def _this(resolver, caller_file, caller_class, targets=EdgeTargets()):
    return resolver._jsts_this_targets(targets, "m", caller_class, caller_file)  # noqa: SLF001


def test_caller_outside_a_class_keeps_synapse_binding() -> None:
    a = _ref("a.ts", "A", "m", 2)
    b = _ref("b.ts", "B", "m", 2)
    resolver = _resolver([a, b], SubclassIndex(_Cache([], ["A", "B"])))

    result = _this(resolver, "a.ts", None, EdgeTargets(certain=[a]))

    assert (result.certain, result.possible) == ([a], [b])


def test_class_without_heritage_makes_every_same_named_method_possible() -> None:
    a = _ref("a.ts", "A", "m", 2)
    caller = _ref("c.ts", "C", "go", 2)
    resolver = _resolver([a, caller], SubclassIndex(_Cache([], ["A", "C"])))

    result = _this(resolver, "c.ts", "C")

    assert (result.certain, result.possible) == ([], [a])


def test_chain_walks_through_a_base_without_the_method() -> None:
    # C extends B (same file, no `m`) extends A (unique project class with `m`).
    a = _ref("a.ts", "A", "m", 2)
    b_other = _ref("c.ts", "B", "other", 5)
    extends = [("c.ts:C:1", "class:B"), ("c.ts:B:4", "class:A")]
    resolver = _resolver([a, b_other], SubclassIndex(_Cache(extends, ["A", "B", "C"])))

    result = _this(resolver, "c.ts", "C")

    assert (result.certain, result.possible) == ([a], [])


def test_two_bases_or_an_unknown_base_is_not_certain() -> None:
    a = _ref("a.ts", "A", "m", 2)
    two = [("c.ts:C:1", "class:A"), ("c.ts:C:1", "class:Z")]
    resolver = _resolver([a], SubclassIndex(_Cache(two, ["A", "Z", "C"])))
    assert _this(resolver, "c.ts", "C").certain == []

    external = [("c.ts:D:1", "class:Error")]
    resolver = _resolver([a], SubclassIndex(_Cache(external, ["D"])))
    result = _this(resolver, "c.ts", "D")
    assert (result.certain, result.possible) == ([], [])


def test_import_picks_the_base_among_duplicate_class_names() -> None:
    v3 = _ref("v3/types.ts", "ZodType", "m", 2)
    v4 = _ref("v4/types.ts", "ZodType", "m", 2)
    extends = [("v3/string.ts:ZodString:2", "class:ZodType")]
    subclasses = SubclassIndex(_Cache(extends, ["ZodType", "ZodType", "ZodString"]))
    imports = {"v3/string.ts": {"ZodType": "v3/types.ts"}}

    resolved = _this(
        _resolver([v3, v4], subclasses, imports), "v3/string.ts", "ZodString"
    )
    unresolved = _this(_resolver([v3, v4], subclasses), "v3/string.ts", "ZodString")

    assert resolved.certain == [v3]
    assert (unresolved.certain, sorted(r.file_path for r in unresolved.possible)) == (
        [],
        ["v3/types.ts", "v4/types.ts"],
    )


def test_unreadable_index_has_no_class_evidence() -> None:
    subclasses = SubclassIndex(_Broken())

    assert subclasses.unique_class("A") is False
    assert subclasses.ancestors("A") is None
    assert subclasses.parents_of("A") == set()


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("const X = class extends B {}\n", "X"),
        (
            "const X = class Named extends B {}\n",
            None,
        ),  # 自己有名字：按 class 声明处理。
        ("const [X] = [class {}]\n", None),
    ],
)
def test_class_expression_name(source: str, expected: str | None) -> None:
    import tree_sitter
    import tree_sitter_typescript

    from tree_sitter_analyzer.cache._symbol_syntax import jsts_class_expression_name

    grammar = tree_sitter.Language(tree_sitter_typescript.language_typescript())
    root = tree_sitter.Parser(grammar).parse(source.encode()).root_node

    def first(node):
        if node.type == "class":
            return node
        return next(filter(None, (first(child) for child in node.children)), None)

    assert jsts_class_expression_name(first(root), source) == expected
