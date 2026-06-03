"""Unit tests for synapse_resolver/_java.py — Java import parsing + cascade.

These lock in the B3 behaviour: Java imports become structured rows and
the 10-stage cascade resolves local / project / external / unknown with
``external`` as a terminal (non-rescan) resolution.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.synapse_resolver._imports import ImportEntry
from tree_sitter_analyzer.synapse_resolver._java import (
    JavaResolverContext,
    build_java_context,
    parse_java_imports,
    resolve_java_callee,
)

# ---------------------------------------------------------------------------
# parse_java_imports
# ---------------------------------------------------------------------------


class TestParseJavaImports:
    def test_package_declaration(self) -> None:
        rows = parse_java_imports("package a.b.c;", "Foo.java", 1)
        assert len(rows) == 1
        assert rows[0].module_path == "a.b.c"
        assert rows[0].local_name == "\x00package"

    def test_single_type_import(self) -> None:
        rows = parse_java_imports("import a.b.C;", "Foo.java", 2)
        assert rows == [
            ImportEntry(
                file_path="Foo.java",
                language="java",
                module_path="a.b.C",
                local_name="C",
                is_relative=False,
                is_star=False,
                alias_of="",
                line=2,
            )
        ]

    def test_wildcard_import(self) -> None:
        rows = parse_java_imports("import a.b.*;", "Foo.java", 3)
        assert len(rows) == 1
        assert rows[0].module_path == "a.b"
        assert rows[0].is_star is True
        assert rows[0].local_name == ""

    def test_static_member_import(self) -> None:
        rows = parse_java_imports("import static a.b.C.m;", "Foo.java", 4)
        assert len(rows) == 1
        assert rows[0].module_path == "a.b.C.m"
        assert rows[0].local_name == "m"

    def test_static_wildcard_import(self) -> None:
        rows = parse_java_imports("import static a.b.C.*;", "Foo.java", 5)
        assert len(rows) == 1
        assert rows[0].module_path == "a.b.C"
        assert rows[0].is_star is True

    @pytest.mark.parametrize("text", ["", "   ", "// comment", "class Foo {"])
    def test_non_import_returns_empty(self, text: str) -> None:
        assert parse_java_imports(text, "Foo.java", 0) == []


# ---------------------------------------------------------------------------
# resolve_java_callee cascade
# ---------------------------------------------------------------------------


def _build_two_file_ctx() -> JavaResolverContext:
    """Service.java (pkg com.acme.svc) imports Helper from com.acme.util."""
    helper = "Helper.java"
    service = "Service.java"
    imports_by_file = {
        helper: parse_java_imports("package com.acme.util;", helper, 1),
        service: (
            parse_java_imports("package com.acme.svc;", service, 1)
            + parse_java_imports("import com.acme.util.Helper;", service, 2)
            + parse_java_imports("import java.util.List;", service, 3)
        ),
    }
    file_symbols = {
        helper: [("Helper", "class", 1), ("greet", "function", 2)],
        service: [
            ("Service", "class", 1),
            ("run", "function", 2),
            ("localMethod", "function", 9),
        ],
    }
    file_class_methods = {
        service: {"Service": {"run": 20, "localMethod": 21}},
    }
    global_name_table = {
        "Helper": [(helper, 10)],
        "greet": [(helper, 11)],
        "Service": [(service, 20)],
        "run": [(service, 21)],
        "localMethod": [(service, 22)],
        "uniqueThing": [(helper, 99)],
    }
    return build_java_context(
        imports_by_file=imports_by_file,
        file_symbols=file_symbols,
        file_class_methods=file_class_methods,
        global_name_table=global_name_table,
    )


class TestResolveJavaCallee:
    def test_local_implicit_this(self) -> None:
        ctx = _build_two_file_ctx()
        sym, res, f = resolve_java_callee(
            "localMethod", "localMethod", "Service.java", ctx
        )
        assert res == "local"
        assert f == "Service.java"

    def test_this_qualified(self) -> None:
        ctx = _build_two_file_ctx()
        _sym, res, f = resolve_java_callee(
            "localMethod", "this.localMethod", "Service.java", ctx
        )
        assert res == "local"
        assert f == "Service.java"

    def test_type_import_cross_file(self) -> None:
        ctx = _build_two_file_ctx()
        _sym, res, f = resolve_java_callee("greet", "Helper.greet", "Service.java", ctx)
        assert res == "project"
        assert f == "Helper.java"

    def test_jdk_receiver_is_external(self) -> None:
        ctx = _build_two_file_ctx()
        _sym, res, f = resolve_java_callee(
            "println", "System.out.println", "Service.java", ctx
        )
        assert res == "external"
        assert f == ""

    def test_java_lang_simple_type_external(self) -> None:
        ctx = _build_two_file_ctx()
        _sym, res, _f = resolve_java_callee(
            "valueOf", "Integer.valueOf", "Service.java", ctx
        )
        assert res == "external"

    def test_single_global_unqualified(self) -> None:
        ctx = _build_two_file_ctx()
        _sym, res, f = resolve_java_callee(
            "uniqueThing", "uniqueThing", "Service.java", ctx
        )
        assert res == "project"
        assert f == "Helper.java"

    def test_unknown_instance_receiver(self) -> None:
        ctx = _build_two_file_ctx()
        # ``helper.compute()`` — receiver is a field/var, not a type.
        _sym, res, _f = resolve_java_callee(
            "compute", "helper.compute", "Service.java", ctx
        )
        assert res == "unknown"

    def test_same_package_resolution(self) -> None:
        helper = "Helper.java"
        sibling = "Sibling.java"
        imports_by_file = {
            helper: parse_java_imports("package com.acme.util;", helper, 1),
            sibling: parse_java_imports("package com.acme.util;", sibling, 1),
        }
        file_symbols = {
            helper: [("Helper", "class", 1), ("greet", "function", 2)],
            sibling: [("Sibling", "class", 1)],
        }
        ctx = build_java_context(
            imports_by_file=imports_by_file,
            file_symbols=file_symbols,
            file_class_methods={},
            global_name_table={},
        )
        # Sibling calls Helper.greet() without importing (same package).
        _sym, res, f = resolve_java_callee("greet", "Helper.greet", "Sibling.java", ctx)
        assert res == "project"
        assert f == "Helper.java"
