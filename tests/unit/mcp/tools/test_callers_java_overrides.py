"""PR-2: ``@Override`` is closed in the project only when every supertype resolves
to a project type and no call edge may dispatch to the target through one."""

from __future__ import annotations

import json
import sqlite3

import pytest

from tree_sitter_analyzer.mcp.tools.callers_java_overrides import (
    OverrideProof,
    override_hint,
    override_proof,
)


class _Cache:
    """A minimal index: class / method rows and call edges."""

    def __init__(self, classes=(), methods=(), edges=()) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE ast_symbol_rows (name TEXT, kind TEXT, file_path TEXT, "
            "language TEXT, line INTEGER)"
        )
        self.conn.execute(
            "CREATE TABLE edges (kind TEXT, callee_name TEXT, file_path TEXT, line "
            "INTEGER, callee_resolution TEXT, callee_resolved_file TEXT, metadata TEXT)"
        )
        for name, file in classes:
            self.conn.execute(
                "INSERT INTO ast_symbol_rows VALUES (?, 'class', ?, 'java', 1)",
                (name, file),
            )
        for name, file in methods:
            self.conn.execute(
                "INSERT INTO ast_symbol_rows VALUES (?, 'method', ?, 'java', 1)",
                (name, file),
            )
        for row in edges:
            self.conn.execute(
                "INSERT INTO edges VALUES ('calls', ?, ?, ?, ?, ?, ?)", row
            )

    def get_conn(self):
        return self.conn


_BASE = "package p;\n\npublic abstract class Base {\n  abstract void hook();\n}\n"
_IMPL = "package p;\n\nclass Impl extends Base {\n  @Override\n  void hook() {}\n}\n"


def _write(tmp_path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _proof(tmp_path, cache, file: str, line: int, bare: str) -> OverrideProof:
    text = (tmp_path / file).read_text(encoding="utf-8")
    return override_proof(cache, str(tmp_path), file, text, line, bare)


def _base_cache(**extra) -> _Cache:
    return _Cache(
        classes=[("Base", "p/Base.java"), ("Impl", "p/Impl.java")],
        methods=[("hook", "p/Base.java"), ("hook", "p/Impl.java")],
        **extra,
    )


def test_same_package_supertype_is_closed(tmp_path) -> None:
    _write(tmp_path, {"p/Base.java": _BASE, "p/Impl.java": _IMPL})

    assert _proof(tmp_path, _base_cache(), "p/Impl.java", 4, "hook").proved is True


@pytest.mark.parametrize(
    ("resolution", "resolved", "metadata", "proved"),
    [
        ("external", "", None, True),
        ("stdlib", "", None, True),
        ("local", "p/Impl.java", None, True),
        ("project", "p/Base.java", None, False),
        ("unknown", "", None, False),
        ("annotated_receiver", "p/Impl.java", {"owner": "Impl", "line": 4}, True),
        ("annotated_receiver", "p/Impl.java", {"owner": "Other", "line": 4}, False),
        ("annotated_receiver", "p/Impl.java", "not json", False),
        ("annotated_receiver", "p/Base.java", {"owner": "Base", "line": 4}, False),
        ("weird", "p/Impl.java", None, False),
    ],
)
def test_call_edges_named_like_the_method(
    tmp_path, resolution, resolved, metadata, proved
) -> None:
    _write(tmp_path, {"p/Base.java": _BASE, "p/Impl.java": _IMPL})
    if isinstance(metadata, dict):
        metadata = json.dumps({"receiver_binding": metadata})
    cache = _base_cache(
        edges=[("hook", "p/Run.java", 7, resolution, resolved, metadata)]
    )

    proof = _proof(tmp_path, cache, "p/Impl.java", 4, "hook")

    assert proof.proved is proved
    if not proved:
        assert proof.sites == ({"file": "p/Run.java", "line": 7},)
        assert "p/Run.java:7" in proof.detail


def test_two_methods_of_the_name_in_the_file_need_a_typed_binding(tmp_path) -> None:
    _write(tmp_path, {"p/Base.java": _BASE, "p/Impl.java": _IMPL})
    cache = _base_cache(edges=[("hook", "p/Run.java", 7, "local", "p/Impl.java", None)])
    cache.conn.execute(
        "INSERT INTO ast_symbol_rows VALUES ('hook', 'method', 'p/Impl.java', 'java', 9)"
    )

    assert _proof(tmp_path, cache, "p/Impl.java", 4, "hook").proved is False


def test_many_dispatch_sites_are_counted_in_the_detail(tmp_path) -> None:
    _write(tmp_path, {"p/Base.java": _BASE, "p/Impl.java": _IMPL})
    edges = [("hook", "p/Run.java", line, "unknown", "", None) for line in range(1, 6)]

    proof = _proof(tmp_path, _base_cache(edges=edges), "p/Impl.java", 4, "hook")

    assert proof.detail.endswith("p/Run.java:3; and 2 more")


def test_imported_supertype_resolves_by_its_package(tmp_path) -> None:
    impl = _IMPL.replace("package p;\n", "package q;\n\nimport p.Base;\n")
    _write(tmp_path, {"p/Base.java": _BASE, "q/Impl.java": impl})
    cache = _Cache(classes=[("Base", "p/Base.java")])

    assert _proof(tmp_path, cache, "q/Impl.java", 6, "hook").proved is True


def test_static_member_type_import_shadows_the_same_package(tmp_path) -> None:
    impl = _IMPL.replace(
        "package p;\n", "package p;\n\nimport static lib.Outer.Base;\n"
    )
    _write(tmp_path, {"p/Base.java": _BASE, "p/Impl.java": impl})

    proof = _proof(tmp_path, _base_cache(), "p/Impl.java", 6, "hook")

    assert (proof.proved, proof.detail) == (
        False,
        "its supertype `Base` is outside the project",
    )


def test_supertype_in_another_package_without_import_is_not_resolved(tmp_path) -> None:
    impl = _IMPL.replace("package p;", "package q;")
    _write(tmp_path, {"p/Base.java": _BASE, "q/Impl.java": impl})
    cache = _Cache(classes=[("Base", "p/Base.java")])

    proof = _proof(tmp_path, cache, "q/Impl.java", 4, "hook")

    assert (proof.proved, proof.detail) == (
        False,
        "its supertype `Base` is outside the project",
    )


def test_ambiguous_same_package_supertype_is_not_resolved(tmp_path) -> None:
    _write(
        tmp_path,
        {"p/Base.java": _BASE, "t/p/Base.java": _BASE, "p/Impl.java": _IMPL},
    )
    cache = _Cache(classes=[("Base", "p/Base.java"), ("Base", "t/p/Base.java")])

    proof = _proof(tmp_path, cache, "p/Impl.java", 4, "hook")

    assert proof.detail == "its supertype `Base` is ambiguous in the project"


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (
            "class Impl extends java.util.AbstractList {",
            "`java.util.AbstractList` is not a simple",
        ),
        (
            "class Impl extends Base implements EventListener {",
            "`EventListener` is outside the project",
        ),
    ],
)
def test_unresolvable_supertypes_fail(tmp_path, header: str, expected: str) -> None:
    _write(
        tmp_path,
        {
            "p/Base.java": _BASE,
            "p/Impl.java": _IMPL.replace("class Impl extends Base {", header),
        },
    )

    proof = _proof(tmp_path, _base_cache(), "p/Impl.java", 4, "hook")

    assert proof.proved is False
    assert expected in proof.detail


def test_nested_supertype_in_scope_and_enclosing_type_checked(tmp_path) -> None:
    text = (
        "package p;\n"
        "\n"
        "class Outer extends Missing {\n"
        "  abstract static class Inner { abstract void hook(); }\n"
        "  static class Leaf extends Inner {\n"
        "    @Override\n"
        "    void hook() {}\n"
        "  }\n"
        "}\n"
    )
    _write(tmp_path, {"p/Outer.java": text})

    proof = _proof(tmp_path, _Cache(), "p/Outer.java", 6, "hook")

    # Inner resolves (same file, in scope), but Outer's supertype is unknown and its
    # inherited member types are in Leaf's scope.
    assert (
        proof.detail == "an enclosing type's supertype `Missing` is outside the project"
    )


def test_nested_type_out_of_scope_is_not_used(tmp_path) -> None:
    text = (
        "package p;\n"
        "\n"
        "class Holder { abstract static class Inner { abstract void hook(); } }\n"
        "class Leaf extends Inner {\n"
        "  @Override\n"
        "  void hook() {}\n"
        "}\n"
    )
    _write(tmp_path, {"p/Leaf.java": text})

    proof = _proof(tmp_path, _Cache(), "p/Leaf.java", 5, "hook")

    assert proof.detail == "its supertype `Inner` is outside the project"


def test_duplicate_in_scope_names_fail(tmp_path) -> None:
    text = (
        "package p;\n"
        "\n"
        "class Base { void hook() {} }\n"
        "class Base { void hook() {} }\n"
        "class Leaf extends Base {\n"
        "  @Override\n"
        "  void hook() {}\n"
        "}\n"
    )
    _write(tmp_path, {"p/Leaf.java": text})

    proof = _proof(tmp_path, _Cache(), "p/Leaf.java", 6, "hook")

    assert (
        proof.detail == "its supertype `Base` is declared more than once in p/Leaf.java"
    )


def test_anonymous_class_and_interface_chain(tmp_path) -> None:
    text = (
        "package p;\n"
        "\n"
        "interface Root { void hook(); }\n"
        "interface Mid<T> extends Root {}\n"
        "class Host {\n"
        "  Object make() {\n"
        "    return new Mid<String>() {\n"
        "      @Override\n"
        "      public void hook() {}\n"
        "    };\n"
        "  }\n"
        "}\n"
    )
    _write(tmp_path, {"p/Host.java": text})

    assert _proof(tmp_path, _Cache(), "p/Host.java", 8, "hook").proved is True


def test_enum_constant_body_overrides_its_enum(tmp_path) -> None:
    text = (
        "package p;\n"
        "\n"
        "enum Mode {\n"
        "  FAST {\n"
        "    @Override\n"
        "    void hook() {}\n"
        "  };\n"
        "  void hook() {}\n"
        "}\n"
    )
    _write(tmp_path, {"p/Mode.java": text})

    assert _proof(tmp_path, _Cache(), "p/Mode.java", 5, "hook").proved is True


@pytest.mark.parametrize(
    ("text", "line", "expected"),
    [
        # No supertype declares the method.
        (
            "package p;\nclass A extends B { @Override void hook() {} }\nclass B {}\n",
            2,
            "no supertype in the project declares it",
        ),
        # A record's accessors and implicit supertype are not modelled.
        (
            "package p;\nrecord R(int x) { @Override public int x() { return x; } }\n",
            2,
            "its declaring type is not a class, interface or enum",
        ),
        # Syntax error: cannot prove anything.
        (
            "package p;\nclass A extends B { @Override void hook( {} }\n",
            2,
            "its declaring file could not be parsed",
        ),
        # The declaration line holds no method of that name.
        (
            "package p;\nclass A { void other() {} }\n",
            2,
            "its declaration could not be located",
        ),
    ],
)
def test_unprovable_shapes(tmp_path, text: str, line: int, expected: str) -> None:
    _write(tmp_path, {"p/A.java": text})

    proof = _proof(
        tmp_path, _Cache(), "p/A.java", line, "hook" if "hook" in text else "x"
    )

    assert (proof.proved, proof.detail) == (False, expected)


def test_object_methods_and_missing_index_fail_closed(tmp_path) -> None:
    _write(tmp_path, {"p/Base.java": _BASE, "p/Impl.java": _IMPL})

    assert (
        "java.lang.Object.equals"
        in _proof(tmp_path, _Cache(), "p/Impl.java", 4, "equals").detail
    )
    assert _proof(tmp_path, None, "p/Impl.java", 4, "hook").detail == (
        "the project index could not be read to resolve its supertypes"
    )


def test_unreadable_index_fails_closed(tmp_path) -> None:
    _write(tmp_path, {"p/Base.java": _BASE, "p/Impl.java": _IMPL})

    class _Broken:
        def get_conn(self):
            raise sqlite3.OperationalError("gone")

    assert _proof(tmp_path, _Broken(), "p/Impl.java", 4, "hook").proved is False


def test_unreadable_candidate_file_fails_closed(tmp_path) -> None:
    _write(tmp_path, {"p/Impl.java": _IMPL})
    # The index names p/Base.java, but the file is gone.
    proof = _proof(tmp_path, _base_cache(), "p/Impl.java", 4, "hook")

    assert proof.detail == "a candidate supertype file could not be parsed"


def test_hint_wraps_the_detail() -> None:
    assert override_hint("A.hook", "its supertype `X` is outside the project") == (
        "No resolved caller for 'A.hook', but it carries `@Override` and its supertype "
        "`X` is outside the project, so a caller through the supertype would leave no "
        "call edge naming it; this is not evidence of absence."
    )
