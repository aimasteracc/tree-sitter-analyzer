"""RFC-0038 unit contracts: type resolution, method lookup, binding and glue.

The indexed-fixture tests in ``test_annotated_receivers_1618.py`` exercise the
public ``nav callers`` path; these pin the decision rules in-process, including
the branches that keep the rule conservative (``None`` = fall back to the old
cascade).
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.cached_annotated_binding import (
    bound_definition,
    dispatch_alternatives,
    parse_binding,
)
from tree_sitter_analyzer.call_graph import FunctionRef
from tree_sitter_analyzer.mcp.tools.callers_annotated import (
    annotated_provenance,
    drop_bound_sites,
    graph_bound_targets,
    name_bound_targets,
)
from tree_sitter_analyzer.synapse_resolver._annotated import (
    AnnotationIndex,
    find_method,
    receiver_hint_from_metadata,
    resolve_annotated_receiver,
    resolve_class,
)
from tree_sitter_analyzer.synapse_resolver._context import ResolverContext
from tree_sitter_analyzer.synapse_resolver._imports import ImportEntry


def _entry(file_path: str, module: str, local: str, alias_of: str = "") -> ImportEntry:
    return ImportEntry(
        file_path=file_path,
        language="python",
        module_path=module,
        local_name=local,
        is_relative=False,
        is_star=False,
        alias_of=alias_of,
        line=1,
    )


def _context() -> ResolverContext:
    """A small project: re-exported Store, a diamond, a factory module."""
    ctx = ResolverContext(
        project_root=".",
        cache=None,
        file_symbols={
            "store.py": [("Store", "class", 1), ("publish", "method", 2)],
            "base.py": [
                ("Left", "class", 10),
                ("Right", "class", 11),
                ("go", "method", 12),
                ("go", "method", 13),
                ("Child", "class", 14),
                ("Solo", "class", 15),
            ],
            "factory.py": [
                ("make", "function", 20),
                ("Builder", "class", 21),
                ("create", "method", 22),
                ("Store", "class", 1),
            ],
            "app.py": [("Owner", "class", 30), ("run", "method", 31)],
            "lower.py": [("thing", "class", 40), ("publish", "method", 41)],
        },
        name_to_source={
            "pkg/__init__.py": {"Store": "store.py"},
            "app.py": {
                "GS": "pkg/__init__.py",
                "make": "factory.py",
                "Builder": "factory.py",
                "thing": "lower.py",
            },
        },
        file_class_methods={
            "store.py": {"Store": {"publish": 2}},
            "base.py": {"Left": {"go": 12}, "Right": {"go": 13}},
            "factory.py": {"Builder": {"create": 22}},
            "app.py": {"Owner": {"run": 31}},
            "lower.py": {"thing": {"publish": 41}},
        },
        import_alias_target={"app.py": {"st": "store.py"}},
        imports_by_file={
            "pkg/__init__.py": [_entry("pkg/__init__.py", "store", "Store")],
            "app.py": [
                _entry("app.py", "pkg", "GS", alias_of="Store"),
                _entry("app.py", "factory", "make"),
                _entry("app.py", "factory", "Builder"),
                _entry("app.py", "lower", "thing"),
                _entry("app.py", "os", "path_like"),
            ],
        },
        file_languages=dict.fromkeys(
            ("store.py", "base.py", "factory.py", "app.py", "lower.py"), "python"
        ),
    )
    ctx._annotation_index = AnnotationIndex(  # type: ignore[attr-defined]
        classes={
            "store.py": {"Store": []},
            "base.py": {
                "Left": [],
                "Right": [],
                "Child": ["Left", "Right"],
                "Solo": ["object", "Left"],
            },
            "factory.py": {"Builder": []},
            "app.py": {"Owner": []},
            "lower.py": {"thing": []},
        },
        returns={
            20: ("'GS | None'", "app.py", None),
            22: ("Self", "factory.py", "Builder"),
        },
        kinds={
            1: "class",
            2: "method",
            20: "function",
            21: "class",
            22: "method",
            40: "class",
        },
        lines={2: 2, 12: 5, 13: 9, 22: 3, 41: 2},
        module_types={"store.py": {"SHARED": {"source": "module", "type": "Store"}}},
    )
    return ctx


def test_resolve_class_follows_alias_reexport_and_module_attribute() -> None:
    ctx = _context()
    assert resolve_class("GS", "app.py", ctx) == ("store.py", "Store")
    assert resolve_class("st.Store", "app.py", ctx) == ("store.py", "Store")
    assert resolve_class("st.deep.Store", "app.py", ctx) is None
    assert resolve_class("Missing", "app.py", ctx) is None
    assert resolve_class("path_like", "app.py", ctx) is None  # external module


def test_find_method_walks_bases_and_rejects_diamond_ambiguity() -> None:
    ctx = _context()
    assert find_method(("base.py", "Solo"), "go", ctx) == ("base.py", 12, "Left")
    # #1699：两个基类分支都定义 `go` 时按 C3 MRO 取最近的定义（Python 的分派规则）。
    assert find_method(("base.py", "Child"), "go", ctx) == ("base.py", 12, "Left")
    assert find_method(("store.py", "Store"), "absent", ctx) is None


@pytest.mark.parametrize(
    ("hint", "expected"),
    [
        ({"source": "param", "type": "GS"}, ("store.py", 2, "Store", "param")),
        ({"source": "local", "returns_of": "make"}, ("store.py", 2, "Store", "return")),
        (
            {"source": "module", "module_attr": "st.SHARED"},
            ("store.py", 2, "Store", "module"),
        ),
        (
            {"source": "local", "returns_of": "thing"},
            ("lower.py", 41, "thing", "return"),
        ),
    ],
)
def test_resolve_annotated_receiver_sources(hint: dict, expected: tuple) -> None:
    resolved = resolve_annotated_receiver(hint, "publish", "app.py", "", _context())

    assert resolved is not None
    assert (
        resolved.resolved_file,
        resolved.callee_symbol_id,
        resolved.binding["owner"],
        resolved.binding["source"],
    ) == expected
    assert (resolved.resolution, resolved.binding["confidence"]) == (
        "annotated_receiver",
        0.8,
    )


def test_self_return_binds_the_declaring_class() -> None:
    hint = {"source": "local", "returns_of": "Builder.create"}
    resolved = resolve_annotated_receiver(hint, "create", "app.py", "", _context())

    assert resolved is not None
    assert (resolved.binding["type"], resolved.binding["line"]) == ("Builder", 3)


@pytest.mark.parametrize(
    "hint",
    [
        None,
        {},
        {"source": "param", "type": "Self"},
        {"source": "param", "type": "GS | Other"},
        {"source": "local", "returns_of": "unknown_factory"},
        {"source": "local", "returns_of": "self.run"},
        {"source": "module", "imported": "nothing_here"},
        {"source": "module", "module_attr": "st.NOT_A_VARIABLE"},
    ],
)
def test_undecidable_hints_fall_back(hint: dict | None) -> None:
    assert (
        resolve_annotated_receiver(hint, "publish", "app.py", "run", _context()) is None
    )


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        (None, None),
        ("", None),
        ("not json", None),
        ('["list"]', None),
        ('{"receiver_hint": "text"}', None),
        (
            '{"receiver_hint": {"source": "param", "type": "T"}}',
            {"source": "param", "type": "T"},
        ),
        (
            {"receiver_hint": {"source": "local", "type": "T"}},
            {"source": "local", "type": "T"},
        ),
    ],
)
def test_receiver_hint_from_metadata(metadata: object, expected: dict | None) -> None:
    assert receiver_hint_from_metadata(metadata) == expected


def test_parse_binding_and_bound_definition() -> None:
    target = FunctionRef("store.py", "publish", 2, "python", receiver="Store")
    other = FunctionRef("store.py", "publish", 9, "python", receiver="Other")
    by_file = {"store.py": [target, other]}

    assert parse_binding('{"line": 2, "owner": "Store"}') == {
        "line": 2,
        "owner": "Store",
    }
    assert parse_binding({"line": 2}) == {"line": 2}
    assert parse_binding("{broken") is None
    assert parse_binding("[1]") is None
    assert parse_binding(None) is None
    assert (
        bound_definition(by_file, "store.py", "publish", {"line": 2, "owner": "Store"})
        is target
    )
    assert (
        bound_definition(by_file, "store.py", "publish", {"line": 2, "owner": "Other"})
        is None
    )
    assert bound_definition(by_file, "gone.py", "publish", {"line": 2}) is None


def test_dispatch_alternatives_lists_subclass_overrides_only() -> None:
    class _Subclasses:
        def subclasses(self, name: str) -> set[str]:
            return {"Fake"} if name == "Store" else set()

    target = FunctionRef("store.py", "publish", 2, "python", receiver="Store")
    fake = FunctionRef("fake.py", "publish", 4, "python", receiver="Fake")
    unrelated = FunctionRef("x.py", "publish", 1, "python", receiver="Other")
    by_name = {"publish": [target, fake, unrelated]}
    binding = {"type": "Store", "owner": "Store"}

    assert dispatch_alternatives(
        _Subclasses(), by_name, "publish", binding, target
    ) == [fake]
    assert dispatch_alternatives(None, by_name, "publish", binding, target) == []


def test_callers_glue_helpers() -> None:
    class _Graph:
        def resolve_targets(
            self, name: str, file_path: str | None
        ) -> list[FunctionRef]:
            return [FunctionRef("a.py", "m", 3, "python")]

    class _Broken:
        def resolve_targets(
            self, name: str, file_path: str | None
        ) -> list[FunctionRef]:
            raise RuntimeError("boom")

        def symbol_definitions(self, name: str) -> list[tuple[str, int]]:
            raise RuntimeError("boom")

    class _Cache:
        def symbol_definitions(self, name: str) -> list[tuple[str, int]]:
            return [("a.py", 3), ("b.py", 7)]

    assert graph_bound_targets(_Graph(), "m", None) == frozenset({("a.py", 3)})
    assert graph_bound_targets(_Broken(), "m", None) == frozenset()
    assert name_bound_targets(_Cache(), "m", None) == frozenset(
        {("a.py", 3), ("b.py", 7)}
    )
    assert name_bound_targets(_Cache(), "m", "b.py") == frozenset({("b.py", 7)})
    assert name_bound_targets(_Broken(), "m", None) == frozenset()
    assert name_bound_targets(object(), "m", None) == frozenset()

    sites = [
        {"file": "a.py", "line": 9, "bound_to": {"file": "a.py", "line": 3}},
        {"file": "a.py", "line": 12},
    ]
    assert drop_bound_sites(sites, frozenset({("a.py", 3)})) == [sites[1]]
    assert drop_bound_sites(sites, frozenset()) is sites
    assert drop_bound_sites(None, frozenset({("a.py", 3)})) is None
    assert annotated_provenance(None) == {}
    assert annotated_provenance(
        {"type": "T", "source": "param", "confidence": 0.8}
    ) == {
        "resolution_kind": "annotated_receiver",
        "receiver_type": "T",
        "type_source": "param",
        "confidence": 0.8,
    }


def _parse(source: str):
    import tree_sitter
    import tree_sitter_python

    parser = tree_sitter.Parser(tree_sitter.Language(tree_sitter_python.language()))
    return parser.parse(source.encode("utf-8"))


def test_class_attribute_hints_rules() -> None:
    from tree_sitter_analyzer.receiver_hints import class_attribute_hints

    tree = _parse(
        "class Owner:\n"
        "    declared: Store\n"
        "    default = None\n"
        "    counter = 0\n"
        "    def __init__(self, store: Store, *rest, plain=None, **kw):\n"
        "        self.a = store\n"
        "        self.b = Builder()\n"
        "        self.c = make()\n"
        "        self.d = None\n"
        "        self.d = Store()\n"
        "        self.e, self.f = 1, 2\n"
        "        self.g = Store()\n"
        "        self.g = Other()\n"
        "        self.h = Store()\n"
        "        self.h += 1\n"
        "        self.default = Store()\n"
        "        self.counter = Store()\n"
        "        self.typed: Store = plain\n"
        "        self.typed: Other = plain\n"
        "        other.x = Store()\n"
        "    @staticmethod\n"
        "    def helper():\n"
        "        pass\n"
        "    @property\n"
        "    def view(self) -> 'Store':\n"
        "        return self.a\n"
        "    @property\n"
        "    def untyped(self):\n"
        "        return 1\n"
        "    class Inner:\n"
        "        def __init__(self):\n"
        "            self.z = Store()\n"
    )

    hints = class_attribute_hints(tree.root_node)

    assert hints["Owner"] == {
        "declared": {"source": "attribute", "type": "Store"},
        "a": {"source": "attribute", "type": "Store"},
        "b": {"source": "attribute", "type": "Builder"},
        "c": {"source": "attribute", "returns_of": "make"},
        "d": {"source": "attribute", "type": "Store"},
        "default": {"source": "attribute", "type": "Store"},
        "view": {"source": "attribute", "type": "'Store'"},
    }
    assert hints["Inner"] == {"z": {"source": "attribute", "type": "Store"}}


def test_walk_tree_attaches_receiver_hints_to_python_calls() -> None:
    from tree_sitter_analyzer.function_extraction import walk_tree

    source = (
        "import pkg.owner as owner\n"
        "REG = Registry()\n"
        "REG.publish(0)\n"
        "class Service:\n"
        "    def __init__(self, store: Store):\n"
        "        self._store = store\n"
        "    def run(self, other: Other):\n"
        "        self._store.publish(1)\n"
        "        other.publish(2)\n"
        "        made = Made()\n"
        "        made.publish(3)\n"
        "        REG.publish(4)\n"
        "        owner.REGISTRY.publish(5)\n"
        "        def nested(REG):\n"
        "            REG.publish(6)\n"
        "        return nested\n"
    )
    _defs, calls = walk_tree(_parse(source).root_node, source, "python")
    hints = {c["full_name"] + f"@{c['line']}": c.get("receiver_hint") for c in calls}

    assert hints["REG.publish@3"] == {"source": "module", "type": "Registry"}
    assert hints["self._store.publish@8"] == {"source": "attribute", "type": "Store"}
    assert hints["other.publish@9"] == {"source": "param", "type": "Other"}
    assert hints["Made.publish@11"] is None  # RFC-0002 constructor path
    assert hints["REG.publish@12"] == {"source": "module", "type": "Registry"}
    assert hints["owner.REGISTRY.publish@13"] == {
        "source": "module",
        "module_attr": "owner.REGISTRY",
    }
    assert hints["REG.publish@15"] is None  # shadowed by the nested parameter


def test_non_python_calls_carry_no_receiver_hint() -> None:
    import tree_sitter
    import tree_sitter_javascript

    from tree_sitter_analyzer.function_extraction import walk_tree

    source = "function f(store) { store.publish(1); }\n"
    parser = tree_sitter.Parser(tree_sitter.Language(tree_sitter_javascript.language()))
    _defs, calls = walk_tree(
        parser.parse(source.encode()).root_node, source, "javascript"
    )
    assert calls
    assert all("receiver_hint" not in call for call in calls)


def test_extraction_persists_module_types_for_python_only() -> None:
    from tree_sitter_analyzer.cache.extraction import _extract_call_edges

    source = "REG = Registry()\n\ndef use():\n    REG.publish()\n"
    symbols: dict = {"symbols": []}
    edges = _extract_call_edges(_parse(source), source, "python", symbols)

    assert symbols["module_types"] == {"REG": {"source": "module", "type": "Registry"}}
    assert [e.get("receiver_hint") for e in edges if e["callee_name"] == "publish"] == [
        {"source": "module", "type": "Registry"}
    ]
    empty: dict = {"symbols": []}
    _extract_call_edges(_parse("x = 1\n"), "x = 1\n", "python", empty)
    assert "module_types" not in empty


def test_cached_edge_resolver_binds_annotated_edge_and_keeps_alternatives() -> None:
    from tree_sitter_analyzer.cached_edge_resolution import CachedEdgeResolver

    target = FunctionRef("store.py", "publish", 2, "python", receiver="Store")
    other = FunctionRef("other.py", "publish", 2, "python", receiver="Other")
    caller = FunctionRef("app.py", "run", 1, "python")
    resolver = CachedEdgeResolver(
        functions_by_name={"publish": [target, other], "run": [caller]},
        functions_by_file={
            "store.py": [target],
            "other.py": [other],
            "app.py": [caller],
        },
        file_import_map={},
    )
    edge = {
        "callee_name": "publish",
        "callee_full": "store.publish",
        "callee_resolution": "annotated_receiver",
        "callee_resolved_file": "store.py",
        "receiver_binding": '{"line": 2, "owner": "Store", "type": "Store"}',
    }

    targets = resolver.resolve(edge, "app.py")
    assert (targets.certain, targets.possible) == ([target], [other])
    assert targets.binding == {"line": 2, "owner": "Store", "type": "Store"}

    stale = {**edge, "receiver_binding": '{"line": 99, "owner": "Store"}'}
    assert resolver.resolve(stale, "app.py").certain == []
    missing = {**edge, "receiver_binding": None}
    assert resolver.resolve(missing, "app.py").binding is None


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # chained assignment and a call whose callee is not a dotted name
        (
            "def f():\n    x = y = make()\n    z = items[0]()\n",
            {
                "x": {"source": "local", "returns_of": "make"},
                "y": {"source": "local", "returns_of": "make"},
            },
        ),
        # augmented assignment, walrus and a for target make the name untyped
        (
            "def f():\n    a = make()\n    a += 1\n    if (b := make()):\n        pass\n",
            {},
        ),
        # conflicting annotations
        ("def f(x: A):\n    x: B = g()\n", {}),
        # typed default, typed splat and a lambda body
        (
            "def f(x: A = None, *xs: B, **kw: C):\n    pass\n",
            {"x": {"source": "param", "type": "A"}},
        ),
        # local `from m import name as alias` binds an import, not a typed name
        ("def f():\n    from m import thing as alias\n    alias.go()\n", {}),
    ],
)
def test_function_receiver_hint_edge_cases(source: str, expected: dict) -> None:
    from tree_sitter_analyzer.receiver_hints import function_receiver_hints

    func = next(
        c for c in _parse(source).root_node.children if c.type == "function_definition"
    )
    assert function_receiver_hints(func) == expected


def test_function_local_import_aliases_are_reported() -> None:
    from tree_sitter_analyzer.receiver_hints import function_scope_hints

    func = _parse(
        "def f():\n    import a.b as owner\n    import plain\n    from m import x as y\n"
    ).root_node.children[0]
    _hints, bound, local_imports = function_scope_hints(func)

    assert local_imports == {
        "owner": ("module", "a.b"),
        "plain": ("module", "plain"),
        "y": ("name", "m"),
    }
    assert not bound & set(local_imports)


def test_call_receiver_hint_ignores_deep_and_foreign_attributes() -> None:
    from tree_sitter_analyzer.receiver_hints import call_receiver_hint

    attributes = {"Owner": {"store": {"source": "attribute", "type": "Store"}}}
    assert call_receiver_hint(None, {}, attributes, "Owner") is None
    assert call_receiver_hint("self.store.inner", {}, attributes, "Owner") is None
    assert call_receiver_hint("self.store", {}, attributes, None) is None
    assert call_receiver_hint("self.store", {}, attributes, "Owner") == {
        "source": "attribute",
        "type": "Store",
    }
