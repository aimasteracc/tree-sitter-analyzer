"""#1699：经单例 / 构造 / 注解 / ``super()`` / 闭包接收者调用继承来的方法时，归属到 MRO 中最近的定义。

经公开的 ``nav callers``（``CodeGraphCallersTool``）在已索引的夹具上验证。
``Sub(Mixin, Base)``：``Mixin.fmt`` 与 ``Base.fmt`` 同名，C3 顺序下 ``Mixin.fmt`` 最近；
``Base.shared`` 只在基类上定义。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_BASE = (
    "class Base:\n"
    "    def shared(self):\n"
    "        return 0\n\n"
    "    def fmt(self):\n"
    "        return 0\n\n\n"
    "class Mixin:\n"
    "    def fmt(self):\n"
    "        return 1\n"
)
_SUB = (
    "from base import Base, Mixin\n\n\n"
    "class Sub(Mixin, Base):\n"
    "    def run(self):\n"
    "        return super().shared()\n\n"
    "    def again(self):\n"
    "        return super().fmt()\n"
)
_USE = (
    "from sub import Sub\n\n"
    "FMT = Sub()\n\n\n"
    "def via_singleton():\n"
    "    return FMT.fmt()\n\n\n"
    "def via_ctor():\n"
    "    s = Sub()\n"
    "    return s.fmt()\n\n\n"
    "def via_param(s: Sub):\n"
    "    return s.fmt()\n\n\n"
    "def outer():\n"
    "    s = Sub()\n\n"
    "    def inner():\n"
    "        return s.shared()\n\n"
    "    return inner()\n\n\n"
    "def shadowed():\n"
    "    s = Sub()\n\n"
    "    def inner2(s):\n"
    "        return s.shared()\n\n"
    "    return inner2(object())\n"
)


@pytest.fixture
async def shapes_root(tmp_path: Path) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "base.py").write_text(_BASE, encoding="utf-8")
    (tmp_path / "sub.py").write_text(_SUB, encoding="utf-8")
    (tmp_path / "use.py").write_text(_USE, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert indexed["published"] is True
    return str(tmp_path)


async def _callers(root: str, name: str) -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "file_path": "base.py", "include_bodies": False}
    )


def _names(result: dict) -> set[str]:
    return {entry["name"] for entry in result["callers"]}


@pytest.mark.asyncio
async def test_nearest_definition_in_the_mro_wins(shapes_root: str) -> None:
    result = await _callers(shapes_root, "Mixin.fmt")

    # 单例、构造得到的局部变量、参数注解与 super()：都到达 C3 顺序中最近的 Mixin.fmt。
    assert _names(result) == {"via_singleton", "via_ctor", "via_param", "again"}


@pytest.mark.asyncio
async def test_the_shadowed_base_definition_gains_no_caller(shapes_root: str) -> None:
    result = await _callers(shapes_root, "Base.fmt")

    assert result["caller_count"] == 0


@pytest.mark.asyncio
async def test_super_and_closure_receivers_reach_the_base(shapes_root: str) -> None:
    result = await _callers(shapes_root, "Base.shared")

    # `inner2(s)` 的参数 `s` 遮蔽了闭包变量：不是调用方。
    assert _names(result) == {"run", "inner"}


def test_extractor_version_is_bumped_for_receiver_shapes() -> None:
    from tree_sitter_analyzer import ast_cache
    from tree_sitter_analyzer.cache import indexer

    assert (
        ast_cache._AST_CACHE_EXTRACTOR_VERSION,
        indexer._AST_CACHE_EXTRACTOR_VERSION,
    ) == (53, 53)


def _shape_context():
    from tree_sitter_analyzer.synapse_resolver._annotated import AnnotationIndex
    from tree_sitter_analyzer.synapse_resolver._context import ResolverContext

    ctx = ResolverContext(
        "/repo",
        None,
        file_symbols={
            "m.py": [
                ("Base", "class", 1),
                ("Mixin", "class", 2),
                ("Sub", "class", 3),
                ("Bad", "class", 4),
                ("Loop", "class", 5),
            ],
            "other.py": [("Lone", "class", 6), ("only", "method", 30)],
        },
        file_class_methods={
            "m.py": {
                "Base": {"fmt": 10, "shared": 11},
                "Mixin": {"fmt": 20},
                "Sub": {"run": 30},
                "Bad": {"bad_m": 40},
            },
            "other.py": {"Lone": {"only": 30}},
        },
        name_to_source={},
        imports_by_file={},
        file_languages={"m.py": "python", "other.py": "python"},
    )
    ctx._annotation_index = AnnotationIndex(  # type: ignore[attr-defined]
        classes={
            "m.py": {
                "Base": ["object"],
                "Mixin": [],
                "Sub": ["Mixin", "Base", "Generic[T]", "external.Thing"],
                # Bad(Base, Sub)：Sub 已经在 Base 之前，C3 不一致。
                "Bad": ["Base", "Sub"],
                "Loop": ["Loop"],
            }
        }
    )
    return ctx


def test_c3_lookup_rules() -> None:
    from tree_sitter_analyzer.synapse_resolver._annotated import find_method, linearize

    ctx = _shape_context()
    assert linearize(("m.py", "Sub"), ctx) == [
        ("m.py", "Sub"),
        ("m.py", "Mixin"),
        ("m.py", "Base"),
    ]
    assert find_method(("m.py", "Sub"), "fmt", ctx) == ("m.py", 20, "Mixin")
    assert linearize(("m.py", "Bad"), ctx) is None
    assert find_method(("m.py", "Bad"), "fmt", ctx) is None
    assert linearize(("m.py", "Loop"), ctx) is None
    assert find_method(("m.py", "Sub"), "absent", ctx) is None


def test_proven_class_receiver_uses_the_mro_then_the_unique_name() -> None:
    from tree_sitter_analyzer.synapse_resolver import _try_inherited_class_method

    ctx = _shape_context()
    nearest = _try_inherited_class_method("fmt", "Sub", "m.py", ctx)
    constructed = _try_inherited_class_method("fmt", "Sub()", "m.py", ctx)
    absent = _try_inherited_class_method("absent", "Sub", "m.py", ctx)
    # 调用方文件里解析不出 `Lone`：退回项目里唯一的方法名。
    unique = _try_inherited_class_method("only", "Lone", "m.py", ctx)

    assert (nearest.callee_symbol_id, nearest.resolved_file) == (20, "m.py")
    assert constructed.callee_symbol_id == 20
    assert absent is None
    assert unique.callee_symbol_id == 30
    assert _try_inherited_class_method("fmt", "notaclass", "m.py", ctx) is None


def test_super_resolution_at_index_time() -> None:
    import sqlite3

    from tree_sitter_analyzer.cache.synapse import _owner_class, _resolve_super

    ctx = _shape_context()
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_symbol_rows (id INTEGER, name TEXT, kind TEXT, "
        "file_path TEXT, line INTEGER)"
    )
    conn.execute("INSERT INTO ast_symbol_rows VALUES (30, 'run', 'method', 'm.py', 7)")
    conn.execute("INSERT INTO ast_symbol_rows VALUES (31, 'dup', 'method', 'm.py', 8)")
    conn.execute("INSERT INTO ast_symbol_rows VALUES (32, 'dup', 'method', 'm.py', 8)")

    def row(caller: str, line: int, name: str) -> dict:
        return {
            "caller_file": "m.py",
            "caller_name": caller,
            "caller_line": line,
            "callee_name": name,
        }

    resolved = _resolve_super(conn, row("run", 7, "fmt"), ctx)
    assert (resolved.callee_symbol_id, resolved.resolution) == (20, "project")
    assert _resolve_super(conn, row("run", 7, "absent"), ctx) is None
    assert _owner_class(conn, row("dup", 8, "fmt"), ctx) is None
    assert _resolve_super(conn, row("dup", 8, "fmt"), ctx) is None
    conn.execute(
        "INSERT INTO ast_symbol_rows VALUES (40, 'bad_m', 'method', 'm.py', 9)"
    )
    # Bad 的 C3 线性化不一致：不解析。
    assert _resolve_super(conn, row("bad_m", 9, "fmt"), ctx) is None

    from tree_sitter_analyzer.cache.synapse import _resolve_indexed_callee

    fallback = object()

    def via(caller: str, line: int, full: str, name: str) -> object:
        edge = {**row(caller, line, name), "callee_full": full, "metadata": None}
        return _resolve_indexed_callee(conn, edge, ctx, lambda *_args: fallback)

    # 外围类无法唯一确定 / super() 找不到定义：交回原有级联。
    assert via("dup", 8, "self.fmt", "fmt") is fallback
    assert via("run", 7, "super().absent", "absent") is fallback
    assert via("run", 7, "super().fmt", "fmt").callee_symbol_id == 20


def test_graph_mro_targets_for_class_and_super_receivers() -> None:
    from tree_sitter_analyzer.cached_edge_resolution import CachedEdgeResolver
    from tree_sitter_analyzer.call_graph import FunctionRef
    from tree_sitter_analyzer.class_mro import ClassKey, Hierarchy

    def ref(name: str, cls: str, line: int) -> FunctionRef:
        return FunctionRef(
            file_path="m.py",
            name=name,
            start_line=line,
            language="python",
            receiver=cls,
        )

    base_fmt, mixin_fmt, run = (
        ref("fmt", "Base", 4),
        ref("fmt", "Mixin", 9),
        ref("run", "Sub", 14),
    )
    base, mixin, sub = (ClassKey("m.py", n) for n in ("Base", "Mixin", "Sub"))
    hierarchy = Hierarchy(
        parents={base: [], mixin: [], sub: [mixin, base]},
        methods={base: {"fmt": 4}, mixin: {"fmt": 9}, sub: {"run": 14}},
    )
    resolver = CachedEdgeResolver(
        functions_by_name={"fmt": [base_fmt, mixin_fmt], "run": [run]},
        functions_by_file={"m.py": [base_fmt, mixin_fmt, run]},
        file_import_map={},
        hierarchy=lambda: hierarchy,
    )
    project = {"callee_resolution": "project", "callee_resolved_file": "m.py"}

    by_class = resolver.resolve(
        {**project, "callee_name": "fmt", "callee_full": "Sub.fmt"}, "u.py"
    )
    by_super = resolver.resolve(
        {**project, "callee_name": "fmt", "callee_full": "super().fmt"}, "m.py", "Sub"
    )
    assert (by_class.certain, by_class.possible) == ([mixin_fmt], [base_fmt])
    assert by_super.certain == [mixin_fmt]

    no_hierarchy = CachedEdgeResolver(
        functions_by_name={"fmt": [base_fmt, mixin_fmt]},
        functions_by_file={"m.py": [base_fmt, mixin_fmt]},
        file_import_map={},
    )
    plain = no_hierarchy.resolve(
        {**project, "callee_name": "fmt", "callee_full": "super().fmt"}, "m.py", "Sub"
    )
    assert plain.certain == []
    unknown = Hierarchy(parents={sub: ["thirdparty.Base"]}, methods={})
    assert resolver._super_target("", "Sub", "fmt") is None
    assert resolver._super_target("m.py", "Sub", "absent") is None
    assert (
        CachedEdgeResolver(
            functions_by_name={},
            functions_by_file={},
            file_import_map={},
            hierarchy=lambda: unknown,
        )._class_receiver_target([base_fmt], "fmt", "Sub")
        is None
    )
    assert hierarchy.after(sub, "absent") == (None, True)
    assert hierarchy.classes_named("Nope") == []


def test_closure_rebinding_names() -> None:
    import tree_sitter
    import tree_sitter_python

    from tree_sitter_analyzer.function_extraction import _bound_names

    source = (
        "def inner(a, b=1):\n"
        "    nonlocal c\n"
        "    d = 1\n"
        "    e += 1\n"
        "    for f in g:\n"
        "        pass\n"
        "    with h() as i:\n"
        "        pass\n"
        "    k = [m for m in n]\n"
        "    return lambda o: o\n"
    )
    parser = tree_sitter.Parser(tree_sitter.Language(tree_sitter_python.language()))
    func = parser.parse(source.encode()).root_node.children[0]

    names = _bound_names(func, source)
    assert names == {"a", "b", "c", "d", "e", "f", "i", "k", "m", "o"}
