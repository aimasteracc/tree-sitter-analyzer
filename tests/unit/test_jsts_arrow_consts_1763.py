"""#1763：JS/TS 以常量定义的函数（``export const f = (...) => {}``）是函数定义。

ts1 dogfood（hono）：``export const cors = (options?) => { ... return async function
cors(c, next) {...} }`` 与 ``export const getCookie: GetCookie = (c, key?) => {...}``
没有被索引为函数：

* ``getCookie`` 没有定义行，``nav callers`` 无法定位；
* 函数体内的调用没有调用方（hono 94% 的 TS 调用边 caller 为空）；
* 测试里 16 处 ``cors()`` 被绑定到内层同名的 ``function cors``——全部是假调用方。
"""

from __future__ import annotations

from pathlib import Path

import pytest

_CORS_TS = (
    "export const cors = (options?: string): number => {\n"
    "  helper()\n"
    "  return async function cors(c: number) {\n"
    "    return inner(c)\n"
    "  }\n"
    "}\n"
    "export const getCookie: (k: string) => string = (key) => {\n"
    "  return helper2(key)\n"
    "}\n"
    "const verify = async function (t: string) {\n"
    "  return helper()\n"
    "}\n"
    "const wrapped = ((x: number) => helper())\n"
    "export function helper() { return [1].map(x => inner(x)) }\n"
    "function helper2(k: string) { return k }\n"
    "function inner(v: number) { return v }\n"
)
_CORS_TEST_TS = (
    "import { cors, getCookie } from './cors'\n"
    "export function useAll() {\n"
    "  cors()\n"
    "  cors('a')\n"
    "  return getCookie('k')\n"
    "}\n"
)


def _walk(source: str, language: str) -> tuple[list[dict], list[dict]]:
    import tree_sitter

    from tree_sitter_analyzer.function_extraction import walk_tree

    if language == "typescript":
        import tree_sitter_typescript

        grammar = tree_sitter_typescript.language_typescript()
    else:
        import tree_sitter_javascript

        grammar = tree_sitter_javascript.language()
    parser = tree_sitter.Parser(tree_sitter.Language(grammar))
    tree = parser.parse(source.encode("utf-8"))
    return walk_tree(tree.root_node, source, language)


def _js(source: str) -> str:
    """去掉 TS 类型注解，得到等价的 JS 源码。"""
    return (
        source.replace("(options?: string): number =>", "(options) =>")
        .replace("(c: number)", "(c)")
        .replace(": (k: string) => string =", " =")
        .replace("(t: string)", "(t)")
        .replace("(x: number)", "(x)")
        .replace("(k: string)", "(k)")
        .replace("(v: number)", "(v)")
    )


@pytest.mark.parametrize("language", ["typescript", "javascript"])
def test_arrow_and_function_expression_constants_are_definitions(
    language: str,
) -> None:
    source = _CORS_TS if language == "typescript" else _js(_CORS_TS)
    definitions, _calls = _walk(source, language)

    assert sorted((d["name"], d["start_line"]) for d in definitions) == [
        ("cors", 1),
        ("cors", 3),
        ("getCookie", 7),
        ("helper", 14),
        ("helper2", 15),
        ("inner", 16),
        ("verify", 10),
        ("wrapped", 13),
    ]


@pytest.mark.parametrize("language", ["typescript", "javascript"])
def test_calls_inside_constant_functions_have_that_caller(language: str) -> None:
    import tree_sitter

    from tree_sitter_analyzer.cache.call_edges import extract_call_edges

    source = _CORS_TS if language == "typescript" else _js(_CORS_TS)
    if language == "typescript":
        import tree_sitter_typescript

        grammar = tree_sitter_typescript.language_typescript()
    else:
        import tree_sitter_javascript

        grammar = tree_sitter_javascript.language()
    tree = tree_sitter.Parser(tree_sitter.Language(grammar)).parse(source.encode())
    edges = extract_call_edges(tree, source, language)

    assert [(e["callee_line"], e["callee_name"], e["caller_name"]) for e in edges] == [
        (2, "helper", "cors"),
        (4, "inner", "cors"),
        (8, "helper2", "getCookie"),
        (11, "helper", "verify"),
        (13, "helper", "wrapped"),
        (14, "map", "helper"),
        # 匿名回调 `x => inner(x)` 没有名字：调用归属外层的 `helper`，
        # 而不是以参数名 `x` 命名的“函数”。
        (14, "inner", "helper"),
    ]


@pytest.fixture
async def cors_root(tmp_path: Path) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "cors.ts").write_text(_CORS_TS, encoding="utf-8")
    (tmp_path / "src" / "use.ts").write_text(_CORS_TEST_TS, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert indexed["published"] is True
    return str(tmp_path)


def _graph(root: str):
    from tree_sitter_analyzer.call_graph import CachedCallGraph
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    cache = CodeGraphCallersTool(root)._try_get_cache()
    graph = CachedCallGraph(root, cache=cache, fallback=False)
    graph.build()
    return graph


@pytest.mark.asyncio
async def test_constant_functions_are_indexed_symbols(cors_root: str) -> None:
    import sqlite3

    db = next(Path(cors_root).rglob("index.db"))
    with sqlite3.connect(str(db)) as conn:
        rows = conn.execute(
            "SELECT name, line FROM ast_symbol_rows "
            "WHERE file_path = 'src/cors.ts' AND kind = 'function' ORDER BY line"
        ).fetchall()

    assert rows == [
        ("cors", 1),
        ("cors", 3),
        ("getCookie", 7),
        ("verify", 10),
        ("wrapped", 13),
        ("helper", 14),
        ("helper2", 15),
        ("inner", 16),
    ]


@pytest.mark.asyncio
async def test_imported_call_binds_the_module_level_constant(cors_root: str) -> None:
    # hono：`cors()` 调用的是模块级的箭头常量，不是内层的 `function cors`。
    callees = _graph(cors_root).callees_of("useAll", "src/use.ts")

    assert sorted((c["name"], c["line"]) for c in callees) == [
        ("cors", 1),
        ("getCookie", 7),
    ]


@pytest.mark.asyncio
async def test_calls_in_constant_bodies_are_graph_edges(cors_root: str) -> None:
    # `cors`（文件内指模块级的外层定义）调用 `helper`；内层 `function cors`
    # 的 `inner()` 归属内层。`getCookie` 调用 `helper2`。修复前这些调用都没有调用方。
    graph = _graph(cors_root)

    assert [
        (c["name"], c["line"]) for c in graph.callees_of("cors", "src/cors.ts")
    ] == [("helper", 14)]
    assert [
        (c["name"], c["line"]) for c in graph.callees_of("getCookie", "src/cors.ts")
    ] == [("helper2", 15)]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("const [a] = () => 1\n", None),  # 解构声明没有单一的名字。
        ("run(() => 1)\n", None),  # 回调实参。
        ("const f = (() => 1)\n", "f"),  # 括号包裹。
        ("const g = function named() {}\n", "named"),  # 命名函数表达式用自己的名字。
    ],
)
def test_function_value_name_shapes(source: str, expected: str | None) -> None:
    import tree_sitter
    import tree_sitter_typescript

    from tree_sitter_analyzer.jsts_function_names import function_value_name

    grammar = tree_sitter.Language(tree_sitter_typescript.language_typescript())
    root = tree_sitter.Parser(grammar).parse(source.encode()).root_node

    def first(node):
        if node.type in ("arrow_function", "function_expression"):
            return node
        return next(filter(None, (first(child) for child in node.children)), None)

    assert function_value_name(first(root)) == expected
    assert function_value_name(root) is None


def _resolver(refs, imports=None):
    from collections import defaultdict

    from tree_sitter_analyzer.cached_edge_resolution import CachedEdgeResolver

    by_name, by_file = defaultdict(list), defaultdict(list)
    for ref in refs:
        by_name[ref.name].append(ref)
        by_file[ref.file_path].append(ref)
    return CachedEdgeResolver(
        functions_by_name=dict(by_name),
        functions_by_file=dict(by_file),
        file_import_map=imports or {},
    )


def _edge(resolution: str = "unknown", resolved: str = "") -> dict:
    return {
        "callee_name": "g",
        "callee_full": "g",
        "callee_resolution": resolution,
        "callee_resolved_file": resolved,
    }


def test_nested_only_definition_is_possible_from_another_file() -> None:
    # `a.ts` 只有嵌套在 `f` 里的 `g`：别的文件按名字到达不了它。
    from tree_sitter_analyzer.call_graph import FunctionRef

    outer = FunctionRef("a.ts", "f", 1, "typescript", end_line=6)
    inner = FunctionRef("a.ts", "g", 3, "typescript", end_line=5)
    resolver = _resolver([outer, inner], {"b.ts": {"g": "a.ts"}})

    for edge in (_edge("project", "a.ts"), _edge()):
        targets = resolver.resolve(edge, "b.ts")
        assert (targets.certain, targets.possible) == ([], [inner])
    # 同一文件内的调用仍可到达嵌套定义。
    assert resolver.resolve(_edge("local", "a.ts"), "a.ts").certain == [inner]


def test_ambiguous_module_level_definitions_keep_nested_ones_possible() -> None:
    from tree_sitter_analyzer.call_graph import FunctionRef

    first = FunctionRef("a.ts", "g", 1, "typescript", end_line=6)
    nested = FunctionRef("a.ts", "g", 3, "typescript", end_line=5)
    other = FunctionRef("a.ts", "g", 8, "typescript", end_line=9)
    resolver = _resolver([first, nested, other], {"b.ts": {"g": "a.ts"}})

    targets = resolver.resolve(_edge(), "b.ts")

    assert targets.certain == []
    assert sorted(ref.start_line for ref in targets.possible) == [1, 3, 8]
