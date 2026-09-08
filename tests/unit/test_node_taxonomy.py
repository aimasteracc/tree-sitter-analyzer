"""Bind the node-type registry to the grammars it claims to describe.

The registry replaced flat cross-language frozensets that were, in effect,
a human's recollection of grammar node names. Nine entries in those sets
(``class_method``, ``member_function``, ``enum``, ``require_statement``,
``extern_crate_item``, ``include_directive`` and friends) matched no
installed grammar at all — dead weight that read as coverage.

The test that matters here is :func:`test_every_declared_node_type_exists`.
It makes a typo or an upstream grammar rename fail CI, which is the property
the old design lacked: previously a wrong node-type string was
indistinguishable from a construct the language simply does not have, and
the difference only showed up as missing rows months later.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.cache import node_taxonomy as nt


@pytest.mark.parametrize(
    ("language", "category", "source"),
    [
        ("python", "function_like", "def demo():\n    pass\n"),
        ("python", "class_like", "class Demo:\n    pass\n"),
        ("python", "import_like", "import os\n"),
        ("javascript", "var_decl_like", "const demo = 1;"),
        ("rust", "const_like", "const DEMO: i32 = 1;"),
        ("python", "const_like", "DEMO = 1\n"),
        ("java", "enum_like", "enum Demo { ONE }"),
        ("python", "scope_body", "def demo():\n    LOCAL = 1\n"),
        ("scala", "deferred_class_like", "def f(): Int = { object Demo {}; 1 }"),
    ],
)
def test_registry_changes_control_real_extraction(
    monkeypatch, language: str, category: str, source: str
) -> None:
    """2026-09-08 审查：注册表必须实际驱动提取，而不是仅供测试检查。"""
    from tree_sitter_analyzer.cache.extraction import _extract_symbols
    from tree_sitter_analyzer.core.parser import Parser

    parsed = Parser().parse_code(source, language)
    assert parsed.success
    before = _extract_symbols(parsed.tree, source, language)["symbols"]
    monkeypatch.setitem(nt.LANGUAGE_NODES[language], category, frozenset())
    after = _extract_symbols(parsed.tree, source, language)["symbols"]
    assert after != before, f"{language}.{category} 未控制真实提取路径"


@pytest.mark.parametrize("language", ["javascript", "typescript"])
def test_named_javascript_function_expression_is_extracted(language: str) -> None:
    """2026-09-08 审查：具名函数表达式及其嵌套函数均应进入索引。"""
    from tree_sitter_analyzer.cache.extraction import _extract_symbols
    from tree_sitter_analyzer.core.parser import Parser

    source = (
        "class A { field = function named() { function nested() {} }; method() {} }"
    )
    parsed = Parser().parse_code(source, language)
    symbols = _extract_symbols(parsed.tree, source, language)["symbols"]
    assert {s["name"]: (s["kind"], s.get("class")) for s in symbols} == {
        "A": ("class", None),
        "named": ("function", None),
        "nested": ("function", None),
        "method": ("method", "A"),
    }


def test_scala_local_deferred_type_does_not_fall_through_to_class_branch() -> None:
    """延迟类型受局部作用域限制，不能再落入普通类分支。"""
    from tree_sitter_analyzer.cache.extraction import _extract_symbols
    from tree_sitter_analyzer.core.parser import Parser

    source = "object Outer { def f(): Int = { object Local {}; 1 } }"
    parsed = Parser().parse_code(source, "scala")
    symbols = _extract_symbols(parsed.tree, source, "scala")["symbols"]
    assert [s["name"] for s in symbols] == ["Outer", "f"]


def test_typescript_ambient_module_is_not_a_phantom_class() -> None:
    """2026-09-08 语料对比：模块字符串不是类，内部接口仍可提取。"""
    from tree_sitter_analyzer.cache.extraction import _extract_symbols
    from tree_sitter_analyzer.core.parser import Parser

    source = 'declare module "pkg" { interface Widget {} }'
    parsed = Parser().parse_code(source, "typescript")
    symbols = _extract_symbols(parsed.tree, source, "typescript")["symbols"]
    assert [(s["name"], s["kind"]) for s in symbols] == [("Widget", "class")]


def test_tsx_alias_uses_typescript_local_variable_scope() -> None:
    """别名归一化必须同时作用于分类和局部变量过滤。"""
    from tree_sitter_analyzer.cache.extraction import _extract_symbols
    from tree_sitter_analyzer.core.parser import Parser

    source = "const globalValue = 1; function f() { const localValue = 2; }"
    parsed = Parser().parse_code(source, "typescript")
    symbols = _extract_symbols(parsed.tree, source, "tsx")["symbols"]
    assert [(s["name"], s["language"]) for s in symbols] == [
        ("globalValue", "typescript"),
        ("f", "typescript"),
    ]


def test_unknown_language_does_not_reuse_another_grammar_categories() -> None:
    """未知语言不会通过共享节点名称意外产生函数。"""
    from tree_sitter_analyzer.cache.extraction import _extract_symbols
    from tree_sitter_analyzer.core.parser import Parser

    source = "def f():\n    pass\n"
    parsed = Parser().parse_code(source, "python")
    assert _extract_symbols(parsed.tree, source, "unknown")["symbols"] == []


# Grammar module + factory for each declared language. Kept beside the
# registry rather than derived so an unlisted language fails loudly.
_GRAMMARS: dict[str, tuple[str, str]] = {
    "python": ("tree_sitter_python", "language"),
    "javascript": ("tree_sitter_javascript", "language"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "java": ("tree_sitter_java", "language"),
    "go": ("tree_sitter_go", "language"),
    "rust": ("tree_sitter_rust", "language"),
    "c": ("tree_sitter_c", "language"),
    "cpp": ("tree_sitter_cpp", "language"),
    "csharp": ("tree_sitter_c_sharp", "language"),
    "ruby": ("tree_sitter_ruby", "language"),
    "kotlin": ("tree_sitter_kotlin", "language"),
    "php": ("tree_sitter_php", "language_php"),
    "scala": ("tree_sitter_scala", "language"),
    "swift": ("tree_sitter_swift", "language"),
    "bash": ("tree_sitter_bash", "language"),
    "lua": ("tree_sitter_lua", "language"),
}

# tree-sitter's error-recovery pseudo-node is not a grammar rule but is a
# legitimate scope-body marker.
_PSEUDO_NODES = frozenset({"ERROR"})


def _grammar_node_kinds(language: str) -> frozenset[str]:
    module_name, factory = _GRAMMARS[language]
    try:
        module = __import__(module_name)
        from tree_sitter import Language
    except ImportError as exc:  # pragma: no cover
        pytest.skip(f"tracked: optional grammar for {language} unavailable: {exc}")
    lang_obj = Language(getattr(module, factory)())
    kinds = set()
    for index in range(lang_obj.node_kind_count):
        name = lang_obj.node_kind_for_id(index)
        if name and lang_obj.node_kind_is_named(index):
            kinds.add(name)
    return frozenset(kinds)


# ---------------------------------------------------------------------------
# The binding to reality
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("language", sorted(nt.LANGUAGE_NODES))
def test_every_declared_node_type_exists(language: str) -> None:
    """Every node type declared must be a real named kind in that grammar.

    A failure means one of: a typo, a node type copied from another
    language, or an upstream grammar rename. All three used to be silent.
    """
    kinds = _grammar_node_kinds(language)
    bogus: dict[str, list[str]] = {}
    for category, types in nt.LANGUAGE_NODES[language].items():
        missing = sorted(t for t in types if t not in kinds and t not in _PSEUDO_NODES)
        if missing:
            bogus[category] = missing
    assert not bogus, (
        f"{language}: node types declared but absent from the grammar: {bogus}"
    )


@pytest.mark.parametrize("language", sorted(nt.LANGUAGE_NODES))
def test_declared_categories_are_known(language: str) -> None:
    unknown = set(nt.LANGUAGE_NODES[language]) - set(nt.CATEGORIES)
    assert not unknown, f"{language}: unknown categories {sorted(unknown)}"


@pytest.mark.parametrize("language", sorted(nt.LANGUAGE_NODES))
def test_enum_like_is_a_subset_of_class_like(language: str) -> None:
    """Enums are reported through the class branch, so they must be classes."""
    enums = nt.nodes_for(language, "enum_like")
    classes = nt.nodes_for(language, "class_like")
    assert enums <= classes, (
        f"{language}: enum_like not contained in class_like: {sorted(enums - classes)}"
    )


@pytest.mark.parametrize("language", sorted(nt.LANGUAGE_NODES))
def test_deferred_class_like_is_a_subset_of_class_like(language: str) -> None:
    """The deferred branch reports types, so its nodes must be class-like."""
    deferred = nt.nodes_for(language, "deferred_class_like")
    classes = nt.nodes_for(language, "class_like")
    assert deferred <= classes, (
        f"{language}: deferred_class_like escapes class_like: "
        f"{sorted(deferred - classes)}"
    )


def test_scala_deferred_excludes_plain_classes() -> None:
    """A Scala ``class`` takes the ordinary branch, not the deferred one.

    Only object/trait/enum/given/type are deferred; folding
    ``class_definition`` in would report Scala classes twice.
    """
    deferred = nt.nodes_for("scala", "deferred_class_like")
    assert "class_definition" not in deferred
    assert "object_definition" in deferred
    assert "given_definition" in deferred


@pytest.mark.parametrize("language", sorted(nt.LANGUAGE_NODES))
def test_no_category_is_declared_empty(language: str) -> None:
    """An empty set is indistinguishable from an absent one — omit instead."""
    empty = [c for c, types in nt.LANGUAGE_NODES[language].items() if not types]
    assert not empty, f"{language}: declared but empty categories {empty}"


# ---------------------------------------------------------------------------
# Lookup contract
# ---------------------------------------------------------------------------


def test_nodes_for_unknown_language_is_empty_not_an_error() -> None:
    """An unexpected file type must degrade to "no symbols", not a crash."""
    assert nt.nodes_for("cobol", "function_like") == frozenset()


def test_nodes_for_unknown_category_is_empty() -> None:
    assert nt.nodes_for("python", "nonexistent_category") == frozenset()


def test_is_a_matches_nodes_for() -> None:
    assert nt.is_a("python", "function_like", "function_definition")
    assert not nt.is_a("python", "function_like", "method_declaration")


def test_tsx_and_jsx_fold_onto_their_base_language() -> None:
    assert nt.normalize_language("tsx") == "typescript"
    assert nt.normalize_language("jsx") == "javascript"
    assert nt.nodes_for("tsx", "function_like") == nt.nodes_for(
        "typescript", "function_like"
    )
    assert nt.nodes_for("jsx", "class_like") == nt.nodes_for("javascript", "class_like")


def test_normalize_leaves_plain_languages_alone() -> None:
    for language in nt.LANGUAGE_NODES:
        assert nt.normalize_language(language) == language


# ---------------------------------------------------------------------------
# Language scoping — the property the flat sets could not express
# ---------------------------------------------------------------------------


def test_node_types_do_not_leak_across_languages() -> None:
    """Ruby's ``method`` must not make Python's walker see a function."""
    assert nt.is_a("ruby", "function_like", "method")
    assert not nt.is_a("python", "function_like", "method")

    assert nt.is_a("rust", "function_like", "function_item")
    assert not nt.is_a("go", "function_like", "function_item")


def test_python_root_module_is_not_a_class() -> None:
    """``module`` is Python's root node, not a type declaration.

    The flat ``_CLASS_LIKE`` contained ``module`` for Ruby's sake, so every
    Python file's root node matched the class branch. It produced no symbol
    only because the root has no ``name`` field — a coincidence, not a
    design. Scoping per language removes the hazard outright.
    """
    assert not nt.is_a("python", "class_like", "module")
    assert nt.is_a("ruby", "class_like", "module")


def test_block_opens_a_scope_in_rust_but_not_in_python() -> None:
    """The collision that forced eight parallel scope sets in the old design."""
    assert nt.is_a("rust", "scope_body", "block")
    assert not nt.is_a("python", "scope_body", "block")


def test_type_definition_is_scala_only_here() -> None:
    """``type_definition`` is also a C/C++ typedef; scoping keeps them apart."""
    assert nt.is_a("scala", "class_like", "type_definition")
    assert not nt.is_a("c", "class_like", "type_definition")
    assert not nt.is_a("cpp", "class_like", "type_definition")


# ---------------------------------------------------------------------------
# The dead entries that used to look like coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "node_type",
    [
        "class_method",
        "member_function",
        "enum",
        "require_statement",
        "extern_crate_item",
        "include_directive",
    ],
)
def test_dead_node_types_are_gone(node_type: str) -> None:
    """These matched no grammar; carrying them implied coverage that never existed."""
    for language, categories in nt.LANGUAGE_NODES.items():
        for category, types in categories.items():
            assert node_type not in types, (
                f"{node_type!r} reintroduced under {language}.{category}"
            )


def test_lua_function_admission_survives_taxonomy_migration():
    """2026-09-08：Lua 具名函数不能因遗漏语言分类而退出缓存提取。"""
    from tree_sitter import Language, Parser

    from tree_sitter_analyzer.cache.extraction import _extract_symbols

    grammar = pytest.importorskip(
        "tree_sitter_lua", reason="tracked: optional Lua grammar"
    )
    source = "function greet(name) return name end\n"
    tree = Parser(Language(grammar.language())).parse(source.encode())
    symbols = _extract_symbols(tree, source, "lua")["symbols"]
    assert [(symbol["name"], symbol["kind"]) for symbol in symbols] == [
        ("greet", "function")
    ]
