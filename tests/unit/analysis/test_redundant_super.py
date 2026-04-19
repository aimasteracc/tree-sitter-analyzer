"""Tests for RedundantSuperAnalyzer — Python, JS/TS, Java."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.redundant_super import (
    ISSUE_REDUNDANT_SUPER,
    RedundantSuperAnalyzer,
    RedundantSuperIssue,
)


@pytest.fixture
def analyzer() -> RedundantSuperAnalyzer:
    return RedundantSuperAnalyzer()


def _write(tmp_path: Path, name: str, code: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(code))
    return p


# ── Python Tests ──────────────────────────────────────────────


class TestPythonRedundantSuper:
    def test_redundant_super_init(self, analyzer: RedundantSuperAnalyzer, tmp_path: Path) -> None:
        code = """\
        class Foo:
            def __init__(self):
                super().__init__()
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert result.total_constructors == 1
        assert len(result.issues) == 1
        assert result.issues[0].issue_type == ISSUE_REDUNDANT_SUPER
        assert result.issues[0].function_name == "__init__"
        assert result.issues[0].line_number == 2

    def test_no_redundant_super_with_logic(self, analyzer: RedundantSuperAnalyzer, tmp_path: Path) -> None:
        code = """\
        class Foo:
            def __init__(self):
                super().__init__()
                self.x = 1
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert result.total_constructors == 1
        assert len(result.issues) == 0

    def test_no_init(self, analyzer: RedundantSuperAnalyzer, tmp_path: Path) -> None:
        code = """\
        class Foo:
            pass
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert result.total_constructors == 0
        assert len(result.issues) == 0

    def test_init_with_params_no_super(self, analyzer: RedundantSuperAnalyzer, tmp_path: Path) -> None:
        code = """\
        class Foo:
            def __init__(self, x):
                self.x = x
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert result.total_constructors == 1
        assert len(result.issues) == 0

    def test_redundant_super_with_args(self, analyzer: RedundantSuperAnalyzer, tmp_path: Path) -> None:
        code = """\
        class Foo(Bar):
            def __init__(self):
                super().__init__()
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert result.total_constructors == 1
        assert len(result.issues) == 1
        assert result.issues[0].issue_type == ISSUE_REDUNDANT_SUPER

    def test_multiple_classes(self, analyzer: RedundantSuperAnalyzer, tmp_path: Path) -> None:
        code = """\
        class A:
            def __init__(self):
                super().__init__()

        class B:
            def __init__(self):
                super().__init__()
                self.x = 1
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert result.total_constructors == 2
        assert len(result.issues) == 1

    def test_nested_class(self, analyzer: RedundantSuperAnalyzer, tmp_path: Path) -> None:
        code = """\
        class Outer:
            class Inner:
                def __init__(self):
                    super().__init__()
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert result.total_constructors == 1
        assert len(result.issues) == 1

    def test_empty_init(self, analyzer: RedundantSuperAnalyzer, tmp_path: Path) -> None:
        code = """\
        class Foo:
            def __init__(self):
                pass
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert result.total_constructors == 1
        assert len(result.issues) == 0

    def test_non_init_not_flagged(self, analyzer: RedundantSuperAnalyzer, tmp_path: Path) -> None:
        code = """\
        class Foo:
            def method(self):
                super().method()
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert result.total_constructors == 0
        assert len(result.issues) == 0

    def test_result_to_dict(self, analyzer: RedundantSuperAnalyzer, tmp_path: Path) -> None:
        code = """\
        class Foo:
            def __init__(self):
                super().__init__()
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        d = result.to_dict()
        assert "total_constructors" in d
        assert "issues" in d
        assert "file_path" in d
        assert d["issue_count"] == 1

    def test_issue_to_dict(self) -> None:
        issue = RedundantSuperIssue(
            line_number=5,
            issue_type=ISSUE_REDUNDANT_SUPER,
            severity="low",
            description="test",
            function_name="__init__",
        )
        d = issue.to_dict()
        assert d["line_number"] == 5
        assert d["issue_type"] == ISSUE_REDUNDANT_SUPER
        assert "suggestion" in d


# ── JavaScript/TypeScript Tests ──────────────────────────────


class TestJSRedundantSuper:
    def test_js_redundant_super(self, analyzer: RedundantSuperAnalyzer, tmp_path: Path) -> None:
        code = """\
        class Foo extends Bar {
            constructor() {
                super();
            }
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.js", code))
        assert result.total_constructors == 1
        assert len(result.issues) == 1
        assert result.issues[0].issue_type == ISSUE_REDUNDANT_SUPER
        assert result.issues[0].function_name == "constructor"

    def test_js_no_redundant_with_logic(self, analyzer: RedundantSuperAnalyzer, tmp_path: Path) -> None:
        code = """\
        class Foo extends Bar {
            constructor() {
                super();
                this.x = 1;
            }
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.js", code))
        assert result.total_constructors == 1
        assert len(result.issues) == 0

    def test_ts_redundant_super(self, analyzer: RedundantSuperAnalyzer, tmp_path: Path) -> None:
        code = """\
        class Foo extends Bar {
            constructor() {
                super();
            }
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.ts", code))
        assert result.total_constructors == 1
        assert len(result.issues) == 1

    def test_jsx_redundant_super(self, analyzer: RedundantSuperAnalyzer, tmp_path: Path) -> None:
        code = """\
        class Foo extends Bar {
            constructor() {
                super();
            }
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.jsx", code))
        assert result.total_constructors == 1
        assert len(result.issues) == 1

    def test_tsx_redundant_super(self, analyzer: RedundantSuperAnalyzer, tmp_path: Path) -> None:
        code = """\
        class Foo extends Bar {
            constructor() {
                super();
            }
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.tsx", code))
        assert result.total_constructors == 1
        assert len(result.issues) == 1

    def test_js_no_constructor(self, analyzer: RedundantSuperAnalyzer, tmp_path: Path) -> None:
        code = """\
        class Foo {
            method() {}
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.js", code))
        assert result.total_constructors == 0
        assert len(result.issues) == 0


# ── Java Tests ──────────────────────────────────────────────


class TestJavaRedundantSuper:
    def test_java_redundant_super(self, analyzer: RedundantSuperAnalyzer, tmp_path: Path) -> None:
        code = """\
        public class Foo extends Bar {
            public Foo() {
                super();
            }
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "Foo.java", code))
        assert result.total_constructors == 1
        assert len(result.issues) == 1
        assert result.issues[0].issue_type == ISSUE_REDUNDANT_SUPER

    def test_java_no_redundant_with_logic(self, analyzer: RedundantSuperAnalyzer, tmp_path: Path) -> None:
        code = """\
        public class Foo extends Bar {
            public Foo() {
                super();
                this.x = 1;
            }
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "Foo.java", code))
        assert result.total_constructors == 1
        assert len(result.issues) == 0

    def test_java_this_delegation(self, analyzer: RedundantSuperAnalyzer, tmp_path: Path) -> None:
        code = """\
        public class Foo {
            public Foo() {
                this(0);
            }
            public Foo(int x) {
                super();
            }
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "Foo.java", code))
        assert result.total_constructors == 2
        assert len(result.issues) == 1

    def test_java_no_constructor(self, analyzer: RedundantSuperAnalyzer, tmp_path: Path) -> None:
        code = """\
        public class Foo {
            public void bar() {}
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "Foo.java", code))
        assert result.total_constructors == 0
        assert len(result.issues) == 0


# ── Edge Cases ──────────────────────────────────────────────


class TestEdgeCases:
    def test_file_not_found(self, analyzer: RedundantSuperAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.total_constructors == 0
        assert len(result.issues) == 0

    def test_unsupported_extension(self, analyzer: RedundantSuperAnalyzer, tmp_path: Path) -> None:
        p = tmp_path / "a.rb"
        p.write_text("class Foo; def initialize; super; end; end")
        result = analyzer.analyze_file(p)
        assert result.total_constructors == 0
        assert len(result.issues) == 0

    def test_empty_file(self, analyzer: RedundantSuperAnalyzer, tmp_path: Path) -> None:
        p = tmp_path / "a.py"
        p.write_text("")
        result = analyzer.analyze_file(p)
        assert result.total_constructors == 0
        assert len(result.issues) == 0
