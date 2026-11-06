"""#1926: the implicit-receiver scope of Kotlin bare calls, and how the graph binds it."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.call_graph import FunctionRef
from tree_sitter_analyzer.call_graph_kotlin_bare import (
    KotlinSite,
    kotlin_site,
    kotlin_targets,
)
from tree_sitter_analyzer.function_extraction import walk_tree
from tree_sitter_analyzer.language_loader import create_parser_safely


def _scopes(source: str) -> dict[tuple[int, str], str | None]:
    """``(line, full_name) -> kotlin_scope`` of every call in ``source``."""
    parser = create_parser_safely("kotlin")
    assert parser is not None
    tree = parser.parse(source.encode("utf-8"))
    _definitions, calls = walk_tree(tree.root_node, source, "kotlin")
    return {
        (call["line"], call["full_name"]): call.get("kotlin_scope") for call in calls
    }


@pytest.mark.parametrize(
    ("source", "line", "expected"),
    [
        ("class A {\n    fun r() = make()\n}\n", 2, "member"),
        ("class A {\n    fun r() = this.make()\n}\n", 2, "member"),
        ("fun top() = make()\n", 1, "top"),
        ("class A {\n    init {\n        make()\n    }\n}\n", 3, "member"),
        ("class A {\n    val x = make()\n}\n", 2, "member"),
        ("object O {\n    fun s() = make()\n}\n", 2, "member"),
        ("val o = object : I {\n    fun q() = make()\n}\n", 2, "member"),
        # Extension function / property: the receiver is implicit.
        ("fun Box.ext() = make()\n", 1, "receiver"),
        ("val Box.p: String get() = make()\n", 1, "receiver"),
        # Lambdas whose receiver is unknown or present.
        ("class A {\n    fun r(b: B) = b.apply { make() }\n}\n", 2, "receiver"),
        ("class A {\n    fun r(b: B) = with(b) { make() }\n}\n", 2, "receiver"),
        ("class A {\n    fun r(b: B) = b.run { make() }\n}\n", 2, "receiver"),
        ("class A {\n    fun r() = html { body { make() } }\n}\n", 2, "receiver"),
        ("class A {\n    fun r() = foo({ make() })\n}\n", 2, "receiver"),
        (
            "class A {\n    fun r() {\n        val f: B.() -> Unit = { make() }\n    }\n}\n",
            3,
            "receiver",
        ),
        (
            "class A {\n    fun r() {\n        val g = fun B.() { make() }\n    }\n}\n",
            3,
            "receiver",
        ),
        # A class inside a receiver lambda still sees the lambda's receiver.
        (
            "fun t(b: B) = b.apply {\n    object : I {\n        fun q() = make()\n    }\n}\n",
            3,
            "receiver",
        ),
        # ``apply`` / ``run`` on the implicit ``this``: the receiver is that ``this``.
        ("class A {\n    fun r(): A = apply { make() }\n}\n", 2, "member:this.apply"),
        ("class A {\n    fun r() = this.run { make() }\n}\n", 2, "member:this.run"),
        ("class A {\n    fun r() = this@A.apply { make() }\n}\n", 2, "receiver"),
        ("class A {\n    fun r() = with(this) { make() }\n}\n", 2, "receiver"),
        # Standard-library lambdas without a receiver keep the scope, naming the host.
        ("class A {\n    fun r(b: B) = b.let { make() }\n}\n", 2, "member:let"),
        ("class A {\n    fun r(b: B) = b.also { make() }\n}\n", 2, "member:also"),
        (
            "class A {\n    fun r(x: List<Int>) = x.map { y -> x.forEach { make() } }\n}\n",
            2,
            "member:forEach,map",
        ),
        ("fun t(x: List<Int>) = x.forEach { make() }\n", 1, "top:forEach"),
        # An anonymous function without a receiver is a plain function scope.
        (
            "class A {\n    fun r(x: List<Int>) = x.forEach(fun(i: Int) { make() })\n}\n",
            2,
            "member",
        ),
    ],
)
def test_scope_of_a_bare_call(source: str, line: int, expected: str) -> None:
    scopes = _scopes(source)
    found = [
        scope
        for (at, name), scope in scopes.items()
        if at == line and name.endswith("make")
    ]
    assert found == [expected], scopes


def test_qualified_calls_carry_no_scope() -> None:
    scopes = _scopes("class A {\n    fun r(b: B) = b.make()\n}\n")
    assert scopes[(2, "b.make")] is None


def test_a_parse_error_opens_the_site() -> None:
    scopes = _scopes("class A {\n    fun r() { make() }\n    ) \n}\n")
    assert [s for (_, name), s in scopes.items() if name == "make"] == ["receiver"]


def test_scope_is_written_to_the_edge_metadata(tmp_path) -> None:
    from tree_sitter_analyzer.cache.call_edges import extract_call_edges

    parser = create_parser_safely("kotlin")
    assert parser is not None
    source = "class A {\n    fun r() = make()\n}\n"
    edges = extract_call_edges(parser.parse(source.encode()), source, "kotlin")
    assert [edge.get("kotlin_scope") for edge in edges] == ["member"]


# --- graph side ------------------------------------------------------------


def _ref(name: str, receiver: str | None, file: str = "p/A.kt", line: int = 1):
    return FunctionRef(file, name, line, "kotlin", receiver=receiver)


class _Resolver:
    """Stands in for ``CachedEdgeResolver`` (own method + overrides)."""

    def __init__(self, own: FunctionRef | None, overrides: list[FunctionRef]):
        self.own = own
        self.overrides = overrides

    def _own_method(self, caller_file, caller_class, base_name):
        return self.own

    def _with_overrides(self, certain, possible, base_name, qualifier, caller_class):
        return [*possible, *self.overrides]


def test_site_is_read_only_for_kotlin_bare_and_this_calls() -> None:
    edge = {"language": "kotlin", "kotlin_scope": "member:let,map"}
    assert kotlin_site(edge, "", "p/A.kt") == KotlinSite("member", ("let", "map"))
    assert kotlin_site(edge, "this", "p/A.kt") == KotlinSite("member", ("let", "map"))
    assert kotlin_site(edge, "box", "p/A.kt") is None
    assert kotlin_site({"language": "java"}, "", "p/A.java") is None
    # An index before #1926 has no scope: the site is open.
    assert kotlin_site({"language": "kotlin"}, "", "p/A.kt") == KotlinSite(None)
    assert kotlin_site({}, "", "p/A.kts") == KotlinSite(None)


def test_member_site_binds_the_own_method_and_offers_overrides() -> None:
    own, override = _ref("make", "A"), _ref("make", "B", "p/B.kt")
    picked = kotlin_targets(
        _Resolver(own, [override]),
        {"make": [own, override]},
        [own],
        KotlinSite("member"),
        "make",
        "",
        "A",
        "p/A.kt",
    )
    assert picked == ([own], [override])


@pytest.mark.parametrize(
    "site",
    [
        KotlinSite(None),
        KotlinSite("receiver"),
        # The project defines ``let``: it may take a receiver lambda.
        KotlinSite("member", ("let",)),
    ],
)
def test_open_sites_make_every_method_possible(site: KotlinSite) -> None:
    own, other = _ref("make", "A"), _ref("make", "C", "p/C.kt")
    let = _ref("let", None, "p/L.kt")
    picked = kotlin_targets(
        _Resolver(own, []),
        {"make": [own, other], "let": [let]},
        [own],
        site,
        "make",
        "",
        "A",
        "p/A.kt",
    )
    assert picked == ([], [own, other])


def test_shadowing_function_opens_a_bare_member_site() -> None:
    own, top = _ref("make", "A"), _ref("make", None, "p/A.kt", 20)
    elsewhere = _ref("make", None, "p/T.kt")
    # A function in another file cannot outrank the member.
    assert kotlin_targets(
        _Resolver(own, []),
        {"make": [own, elsewhere]},
        [elsewhere],
        KotlinSite("member"),
        "make",
        "",
        "A",
        "p/A.kt",
    ) == ([own], [elsewhere])
    functions = {"make": [own, top]}
    bare = kotlin_targets(
        _Resolver(own, []),
        functions,
        [top],
        KotlinSite("member"),
        "make",
        "",
        "A",
        "p/A.kt",
    )
    assert bare == ([], [top, own])
    # ``this.make()`` names the member: the function cannot shadow it.
    this = kotlin_targets(
        _Resolver(own, []),
        functions,
        [],
        KotlinSite("member"),
        "make",
        "this",
        "A",
        "p/A.kt",
    )
    assert this == ([own], [])


def test_member_site_without_an_own_method_is_open() -> None:
    inherited = _ref("make", "Base", "p/Base.kt")
    picked = kotlin_targets(
        _Resolver(None, []),
        {"make": [inherited]},
        [],
        KotlinSite("member"),
        "make",
        "",
        None,
        "p/A.kt",
    )
    assert picked == ([], [inherited])


def test_sites_left_unchanged() -> None:
    top = _ref("helper", None)
    method = _ref("make", "A")
    # Top-level code has no implicit receiver.
    assert (
        kotlin_targets(
            _Resolver(None, []),
            {"make": [method]},
            [],
            KotlinSite("top"),
            "make",
            "",
            None,
            "p/A.kt",
        )
        is None
    )
    # No project method of that name: only functions can answer.
    assert (
        kotlin_targets(
            _Resolver(None, []),
            {"helper": [top]},
            [top],
            KotlinSite("receiver"),
            "helper",
            "",
            "A",
            "p/A.kt",
        )
        is None
    )


class _Subclasses:
    def __init__(self, ancestors: dict[str, set[str]]):
        self._ancestors = ancestors

    def ancestors(self, name: str):
        return self._ancestors.get(name)


@pytest.mark.parametrize(
    ("apply_defs", "caller_class", "ancestors", "opened"),
    [
        # Another class's ``apply`` (a JUnit rule) does not replace ``this.apply``.
        ([_ref("apply", "Rule", "p/R.kt")], "A", {}, False),
        # The caller's class or a supertype declares ``apply``: it is the member.
        ([_ref("apply", "A", "p/A.kt", 9)], "A", {}, True),
        ([_ref("apply", "Base", "p/Base.kt")], "A", {"A": {"Base"}}, True),
        # An extension / top-level ``apply`` may be imported over the standard one.
        ([_ref("apply", None, "p/X.kt")], "A", {}, True),
        # The caller's class is unknown: any method ``apply`` may be the member.
        ([_ref("apply", "Rule", "p/R.kt")], None, {}, True),
        ([], "A", {}, False),
    ],
)
def test_apply_on_this_opens_only_for_a_replacing_definition(
    apply_defs, caller_class, ancestors, opened
) -> None:
    own, other = _ref("make", "A"), _ref("make", "C", "p/C.kt")
    resolver = _Resolver(own, [])
    resolver._subclasses = _Subclasses(ancestors)
    picked = kotlin_targets(
        resolver,
        {"make": [own, other], "apply": apply_defs},
        [own],
        KotlinSite("member", ("this.apply",)),
        "make",
        "",
        caller_class,
        "p/A.kt",
    )
    if opened:
        assert picked == ([], [own, other])
    elif caller_class:
        assert picked == ([own], [])


def test_open_site_offers_extensions_too() -> None:
    method, extension = _ref("make", "A"), _ref("make", None, "p/Ext.kt")
    picked = kotlin_targets(
        _Resolver(None, []),
        {"make": [method, extension]},
        [],
        KotlinSite("receiver"),
        "make",
        "",
        "A",
        "p/A.kt",
    )
    # ``fun Box.make()`` is indexed without a receiver; a receiver lambda reaches it.
    assert picked == ([], [method, extension])
