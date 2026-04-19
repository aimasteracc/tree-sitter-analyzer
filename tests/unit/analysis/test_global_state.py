"""Tests for Global State Analyzer."""
from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.global_state import (
    ISSUE_GLOBAL_KEYWORD,
    ISSUE_GLOBAL_STATE,
    ISSUE_NONLOCAL_KEYWORD,
    ISSUE_PACKAGE_VAR,
    ISSUE_STATIC_MUTABLE,
    GlobalStateAnalyzer,
    GlobalStateResult,
)


@pytest.fixture
def analyzer() -> GlobalStateAnalyzer:
    return GlobalStateAnalyzer()


def _write_tmp(content: str, suffix: str) -> Path:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, prefix="test_gs_", delete=False, dir="/tmp"
    )
    f.write(textwrap.dedent(content))
    f.close()
    return Path(f.name)


# --- Python: module-level mutable state ---


class TestPythonGlobalState:
    def test_detects_module_level_assignment(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            counter = 0
            cache = {}
        """, ".py")
        result = analyzer.analyze_file(str(path))
        types = [f.issue_type for f in result.findings]
        assert ISSUE_GLOBAL_STATE in types

    def test_ignores_upper_snake_constants(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            MAX_RETRIES = 3
            API_BASE_URL = "https://example.com"
        """, ".py")
        result = analyzer.analyze_file(str(path))
        names = [f.name for f in result.findings]
        assert "MAX_RETRIES" not in names
        assert "API_BASE_URL" not in names

    def test_ignores_function_local_vars(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            def foo():
                x = 10
                y = []
        """, ".py")
        result = analyzer.analyze_file(str(path))
        assert len(result.findings) == 0

    def test_ignores_class_body_assignments(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            class Config:
                debug = True
                items = []
        """, ".py")
        result = analyzer.analyze_file(str(path))
        assert len(result.findings) == 0

    def test_detects_mutable_collection_dict(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            cache = {}
        """, ".py")
        result = analyzer.analyze_file(str(path))
        names = [f.name for f in result.findings]
        assert "cache" in names

    def test_detects_mutable_collection_list(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            items = []
        """, ".py")
        result = analyzer.analyze_file(str(path))
        names = [f.name for f in result.findings]
        assert "items" in names
        path = _write_tmp("""
            seen = set()
        """, ".py")
        result = analyzer.analyze_file(str(path))
        assert any(f.name == "seen" for f in result.findings)

    def test_detects_dict_call_constructor(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            data = dict()
        """, ".py")
        result = analyzer.analyze_file(str(path))
        assert any(f.name == "data" for f in result.findings)

    def test_no_findings_for_clean_module(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            MAX_VAL = 100

            def helper():
                return MAX_VAL
        """, ".py")
        result = analyzer.analyze_file(str(path))
        assert len(result.findings) == 0


# --- Python: global keyword ---


class TestPythonGlobalKeyword:
    def test_detects_global_keyword(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            counter = 0

            def increment():
                global counter
                counter += 1
        """, ".py")
        result = analyzer.analyze_file(str(path))
        types = [f.issue_type for f in result.findings]
        assert ISSUE_GLOBAL_KEYWORD in types

    def test_detects_multiple_global_vars(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            def func():
                global x, y
                x = 1
                y = 2
        """, ".py")
        result = analyzer.analyze_file(str(path))
        global_findings = [f for f in result.findings if f.issue_type == ISSUE_GLOBAL_KEYWORD]
        names = {f.name for f in global_findings}
        assert "x" in names
        assert "y" in names

    def test_no_global_keyword_in_normal_func(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            def func():
                x = 10
                return x
        """, ".py")
        result = analyzer.analyze_file(str(path))
        assert not any(f.issue_type == ISSUE_GLOBAL_KEYWORD for f in result.findings)


# --- Python: nonlocal keyword ---


class TestPythonNonlocalKeyword:
    def test_detects_nonlocal_keyword(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            def outer():
                x = 10
                def inner():
                    nonlocal x
                    x = 20
        """, ".py")
        result = analyzer.analyze_file(str(path))
        types = [f.issue_type for f in result.findings]
        assert ISSUE_NONLOCAL_KEYWORD in types

    def test_detects_multiple_nonlocal_vars(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            def outer():
                a = 1
                b = 2
                def inner():
                    nonlocal a, b
                    a = 10
                    b = 20
        """, ".py")
        result = analyzer.analyze_file(str(path))
        nonlocal_findings = [f for f in result.findings if f.issue_type == ISSUE_NONLOCAL_KEYWORD]
        names = {f.name for f in nonlocal_findings}
        assert "a" in names
        assert "b" in names

    def test_no_nonlocal_in_simple_func(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            def simple():
                x = 1
                return x
        """, ".py")
        result = analyzer.analyze_file(str(path))
        assert not any(f.issue_type == ISSUE_NONLOCAL_KEYWORD for f in result.findings)


# --- JavaScript/TypeScript ---


class TestJSTSGlobalState:
    def test_detects_var_at_top_level(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            var counter = 0;
            var items = [];
        """, ".js")
        result = analyzer.analyze_file(str(path))
        assert len(result.findings) >= 1

    def test_detects_let_at_top_level(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            let counter = 0;
        """, ".js")
        result = analyzer.analyze_file(str(path))
        names = [f.name for f in result.findings]
        assert "counter" in names

    def test_ignores_const_at_top_level(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            const MAX = 100;
        """, ".js")
        result = analyzer.analyze_file(str(path))
        assert len(result.findings) == 0

    def test_ignores_function_scoped_vars(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            function foo() {
                var x = 10;
                let y = 20;
            }
        """, ".js")
        result = analyzer.analyze_file(str(path))
        assert len(result.findings) == 0

    def test_ignores_class_methods(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            class Foo {
                bar() {
                    let x = 1;
                }
            }
        """, ".js")
        result = analyzer.analyze_file(str(path))
        assert len(result.findings) == 0

    def test_detects_top_level_assignment_no_decl(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            counter = 0;
        """, ".js")
        result = analyzer.analyze_file(str(path))
        assert any(f.name == "counter" for f in result.findings)

    def test_typescript_let_detection(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            let state: string = "init";
        """, ".ts")
        result = analyzer.analyze_file(str(path))
        assert any(f.name == "state" for f in result.findings)

    def test_tsx_detection(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            let isOpen = false;
        """, ".tsx")
        result = analyzer.analyze_file(str(path))
        assert any(f.name == "isOpen" for f in result.findings)


# --- Java ---


class TestJavaStaticMutable:
    def test_detects_static_non_final_field(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            public class Config {
                private static int counter = 0;
            }
        """, ".java")
        result = analyzer.analyze_file(str(path))
        types = [f.issue_type for f in result.findings]
        assert ISSUE_STATIC_MUTABLE in types

    def test_ignores_static_final_field(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            public class Config {
                private static final int MAX = 100;
            }
        """, ".java")
        result = analyzer.analyze_file(str(path))
        assert len(result.findings) == 0

    def test_ignores_instance_fields(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            public class Foo {
                private int count = 0;
            }
        """, ".java")
        result = analyzer.analyze_file(str(path))
        assert len(result.findings) == 0

    def test_detects_multiple_static_non_final(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            public class Cache {
                private static Map<String, Object> store = new HashMap<>();
                private static List<String> keys = new ArrayList<>();
            }
        """, ".java")
        result = analyzer.analyze_file(str(path))
        names = [f.name for f in result.findings]
        assert "store" in names
        assert "keys" in names

    def test_ignores_final_only(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            public class Constants {
                public final String name = "test";
            }
        """, ".java")
        result = analyzer.analyze_file(str(path))
        assert len(result.findings) == 0


# --- Go ---


class TestGoPackageVars:
    def test_detects_package_var(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            package main

            var counter int
        """, ".go")
        result = analyzer.analyze_file(str(path))
        types = [f.issue_type for f in result.findings]
        assert ISSUE_PACKAGE_VAR in types

    def test_detects_short_var_at_package_level(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            package main

            items := []string{}
        """, ".go")
        result = analyzer.analyze_file(str(path))
        assert any(f.name == "items" for f in result.findings)

    def test_ignores_func_vars(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            package main

            func main() {
                x := 10
                var y int
            }
        """, ".go")
        result = analyzer.analyze_file(str(path))
        assert len(result.findings) == 0

    def test_detects_multiple_package_vars(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            package main

            var (
                count int
                name  string
            )
        """, ".go")
        result = analyzer.analyze_file(str(path))
        names = [f.name for f in result.findings]
        assert "count" in names
        assert "name" in names

    def test_ignores_type_declarations(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            package main

            type Config struct {
                Debug bool
            }
        """, ".go")
        result = analyzer.analyze_file(str(path))
        assert len(result.findings) == 0


# --- Result structure ---


class TestGlobalStateResult:
    def test_to_dict_structure(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            counter = 0
            def inc():
                global counter
                counter += 1
        """, ".py")
        result = analyzer.analyze_file(str(path))
        d = result.to_dict()
        assert "file_path" in d
        assert "total_findings" in d
        assert "high_severity" in d
        assert "findings" in d
        assert d["total_findings"] >= 1

    def test_high_severity_count(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            def f():
                global x
                nonlocal y
        """, ".py")
        result = analyzer.analyze_file(str(path))
        d = result.to_dict()
        assert d["high_severity"] >= 2

    def test_nonexistent_file(self, analyzer: GlobalStateAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert len(result.findings) == 0

    def test_unsupported_extension(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("x = 1", ".rb")
        result = analyzer.analyze_file(str(path))
        assert len(result.findings) == 0


# --- Edge cases ---


class TestEdgeCases:
    def test_nested_function_global(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            def outer():
                def inner():
                    global z
                    z = 1
        """, ".py")
        result = analyzer.analyze_file(str(path))
        assert any(f.issue_type == ISSUE_GLOBAL_KEYWORD for f in result.findings)

    def test_lambda_does_not_create_scope_for_assignments(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            f = lambda x: x + 1
        """, ".py")
        result = analyzer.analyze_file(str(path))
        assert len(result.findings) == 0

    def test_arrow_func_not_top_level(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            const handler = () => {
                let x = 1;
            };
        """, ".js")
        result = analyzer.analyze_file(str(path))
        # handler is const, so not flagged; x inside arrow, not flagged
        assert len(result.findings) == 0

    def test_java_final_static_order(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            public class C {
                static final int A = 1;
                final static int B = 2;
            }
        """, ".java")
        result = analyzer.analyze_file(str(path))
        assert len(result.findings) == 0

    def test_go_method_var_not_flagged(self, analyzer: GlobalStateAnalyzer) -> None:
        path = _write_tmp("""
            package main

            type T struct{}

            func (t T) Method() {
                var x int
            }
        """, ".go")
        result = analyzer.analyze_file(str(path))
        assert len(result.findings) == 0
