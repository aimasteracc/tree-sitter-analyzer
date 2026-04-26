#!/usr/bin/env python3
"""Tests for Documentation Coverage Analyzer."""

from __future__ import annotations

import textwrap
from pathlib import Path

from tree_sitter_analyzer.analysis.doc_coverage import (
    DocCoverageAnalyzer,
    DocCoverageResult,
    DocElement,
)


def _write_tmp_file(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# --- Python tests ---


class TestPythonDocCoverage:
    def test_documented_function(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "a.py", '''\
            def foo():
                """Hello."""
                pass
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        funcs = [e for e in result.elements if e.element_type == "function"]
        assert len(funcs) == 1
        assert funcs[0].has_doc is True

    def test_undocumented_function(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "a.py", '''\
            def foo():
                pass
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        funcs = [e for e in result.elements if e.element_type == "function"]
        assert len(funcs) == 1
        assert funcs[0].has_doc is False

    def test_documented_class(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "a.py", '''\
            class Foo:
                """A class."""
                pass
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        classes = [e for e in result.elements if e.element_type == "class"]
        assert len(classes) == 1
        assert classes[0].has_doc is True

    def test_class_with_documented_method(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "a.py", '''\
            class Foo:
                """A class."""
                def bar(self):
                    """A method."""
                    pass
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        code_elements = [e for e in result.elements if e.element_type != "module"]
        assert len(code_elements) == 2
        assert all(e.has_doc for e in code_elements)

    def test_class_with_undocumented_method(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "a.py", '''\
            class Foo:
                """A class."""
                def bar(self):
                    pass
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        code_elements = [e for e in result.elements if e.element_type != "module"]
        assert len(code_elements) == 2
        docs = [e.has_doc for e in code_elements]
        assert docs == [True, False]

    def test_undocumented_class_with_method(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "a.py", '''\
            class Foo:
                def bar(self):
                    """A method."""
                    pass
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        code_elements = [e for e in result.elements if e.element_type != "module"]
        assert len(code_elements) == 2
        docs = [e.has_doc for e in code_elements]
        assert docs == [False, True]

    def test_module_docstring(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "a.py", '''\
            """Module docstring."""

            def foo():
                pass
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        mod = [e for e in result.elements if e.element_type == "module"]
        assert len(mod) == 1
        assert mod[0].has_doc is True

    def test_no_module_docstring(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "a.py", '''\
            def foo():
                pass
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        mod = [e for e in result.elements if e.element_type == "module"]
        assert len(mod) == 1
        assert mod[0].has_doc is False

    def test_multiline_docstring(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "a.py", '''\
            def foo():
                \"\"\"
                Multi-line
                docstring.
                \"\"\"
                pass
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        funcs = [e for e in result.elements if e.element_type == "function"]
        assert len(funcs) == 1
        assert funcs[0].has_doc is True

    def test_nested_function(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "a.py", '''\
            def outer():
                """Outer."""
                def inner():
                    pass
                return inner
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        funcs = [e for e in result.elements if e.element_type == "function"]
        assert len(funcs) == 2
        assert funcs[0].has_doc is True
        assert funcs[1].has_doc is False

    def test_async_function(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "a.py", '''\
            async def fetch():
                """Fetch data."""
                pass
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        funcs = [e for e in result.elements if e.element_type == "function"]
        assert len(funcs) == 1
        assert funcs[0].has_doc is True

    def test_coverage_percent(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "a.py", '''\
            def a():
                """Doc."""
                pass

            def b():
                pass

            def c():
                """Doc."""
                pass
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        code_elements = [e for e in result.elements if e.element_type != "module"]
        assert len(code_elements) == 3
        documented = sum(1 for e in code_elements if e.has_doc)
        assert documented == 2

    def test_get_missing_docs(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "a.py", '''\
            def a():
                """Doc."""
                pass

            def b():
                pass
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        missing = [e for e in result.get_missing_docs() if e.element_type != "module"]
        assert len(missing) == 1
        assert missing[0].name == "b"

    def test_static_method(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "a.py", '''\
            class Foo:
                @staticmethod
                def bar():
                    """Static."""
                    pass
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        methods = [e for e in result.elements if e.element_type == "method"]
        assert len(methods) == 1
        assert methods[0].has_doc is True


# --- JavaScript/TypeScript tests ---


class TestJSDocCoverage:
    def test_documented_js_function(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "a.js", '''\
            /**
             * Add two numbers.
             */
            function add(a, b) {
                return a + b;
            }
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        assert len(result.elements) >= 1
        funcs = [e for e in result.elements if e.name == "add"]
        assert len(funcs) == 1
        assert funcs[0].has_doc is True

    def test_undocumented_js_function(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "a.js", '''\
            function add(a, b) {
                return a + b;
            }
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        funcs = [e for e in result.elements if e.name == "add"]
        assert len(funcs) == 1
        assert funcs[0].has_doc is False

    def test_documented_js_class(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "a.js", '''\
            /** My class. */
            class Foo {
                constructor() {}
            }
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        classes = [e for e in result.elements if e.element_type == "class"]
        assert len(classes) == 1
        assert classes[0].has_doc is True

    def test_documented_ts_method(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "a.ts", '''\
            class Foo {
                /** Do something. */
                bar(): void {}
            }
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        methods = [e for e in result.elements if e.element_type == "method"]
        assert len(methods) == 1
        assert methods[0].has_doc is True

    def test_arrow_function_not_tracked(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "a.js", '''\
            const add = (a, b) => a + b;
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        assert result is not None


# --- Java tests ---


class TestJavaDocCoverage:
    def test_documented_java_class(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "A.java", '''\
            /**
             * A simple class.
             */
            public class A {
            }
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        classes = [e for e in result.elements if e.element_type == "class"]
        assert len(classes) == 1
        assert classes[0].has_doc is True

    def test_undocumented_java_class(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "A.java", '''\
            public class A {
            }
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        classes = [e for e in result.elements if e.element_type == "class"]
        assert len(classes) == 1
        assert classes[0].has_doc is False

    def test_documented_java_method(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "A.java", '''\
            public class A {
                /**
                 * Do something.
                 */
                public void foo() {}
            }
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        methods = [e for e in result.elements if e.element_type == "method"]
        assert len(methods) == 1
        assert methods[0].has_doc is True

    def test_java_interface(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "I.java", '''\
            /**
             * An interface.
             */
            public interface I {
                void run();
            }
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        interfaces = [e for e in result.elements if e.element_type == "interface"]
        assert len(interfaces) == 1
        assert interfaces[0].has_doc is True


# --- Go tests ---


class TestGoDocCoverage:
    def test_documented_go_function(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "a.go", '''\
            package main

            // Add adds two numbers.
            func Add(a, b int) int {
                return a + b
            }
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        funcs = [e for e in result.elements if e.name == "Add"]
        assert len(funcs) == 1
        assert funcs[0].has_doc is True

    def test_undocumented_go_function(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "a.go", '''\
            package main

            func Add(a, b int) int {
                return a + b
            }
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        funcs = [e for e in result.elements if e.name == "Add"]
        assert len(funcs) == 1
        assert funcs[0].has_doc is False

    def test_documented_go_type(self, tmp_path: Path) -> None:
        p = _write_tmp_file(tmp_path, "a.go", '''\
            package main

            // Server is a web server.
            type Server struct {
                Addr string
            }
        ''')
        result = DocCoverageAnalyzer().analyze_file(p)
        types = [e for e in result.elements if e.name == "Server"]
        assert len(types) == 1
        assert types[0].has_doc is True


# --- Directory analysis ---


class TestDirectoryAnalysis:
    def test_analyze_directory(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text(
            'def foo():\n    """Doc."""\n    pass\n', encoding="utf-8"
        )
        (tmp_path / "b.py").write_text(
            "def bar():\n    pass\n", encoding="utf-8"
        )
        result = DocCoverageAnalyzer().analyze_directory(tmp_path)
        funcs = [e for e in result.elements if e.element_type == "function"]
        assert len(funcs) == 2
        assert result.documented_count >= 1

    def test_unsupported_extension_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "readme.txt").write_text("hello", encoding="utf-8")
        (tmp_path / "a.py").write_text(
            'def foo():\n    """Doc."""\n    pass\n', encoding="utf-8"
        )
        result = DocCoverageAnalyzer().analyze_directory(tmp_path)
        assert all(
            e.file_path.endswith(".py") or e.file_path.endswith(".txt") is False
            for e in result.elements
            if e.element_type != "module"
        )


# --- Data structure tests ---


class TestDataStructures:
    def test_doc_element_creation(self) -> None:
        elem = DocElement(
            name="foo",
            element_type="function",
            file_path="/test/a.py",
            line_number=5,
            has_doc=True,
            doc_content="Hello.",
        )
        assert elem.name == "foo"
        assert elem.has_doc is True

    def test_coverage_result_stats(self) -> None:
        elements = [
            DocElement("a", "function", "/t.py", 1, True, "doc"),
            DocElement("b", "function", "/t.py", 5, False, None),
        ]
        result = DocCoverageResult(
            elements=elements,
            total_elements=2,
            documented_count=1,
            coverage_percent=50.0,
        )
        assert result.coverage_percent == 50.0
        assert len(result.get_missing_docs()) == 1
        assert result.get_missing_docs()[0].name == "b"

    def test_empty_result(self) -> None:
        result = DocCoverageResult(
            elements=[], total_elements=0, documented_count=0, coverage_percent=100.0
        )
        assert result.coverage_percent == 100.0
        assert len(result.get_missing_docs()) == 0
