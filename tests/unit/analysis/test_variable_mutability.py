"""Unit tests for Variable Mutability Analyzer."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.variable_mutability import (
    MUTABILITY_LOOP_MUTATION,
    MUTABILITY_REASSIGNED_CONST,
    MUTABILITY_SHADOW,
    MUTABILITY_UNUSED,
    VariableMutabilityAnalyzer,
    _compute_score,
    _empty_result,
)


@pytest.fixture
def analyzer() -> VariableMutabilityAnalyzer:
    return VariableMutabilityAnalyzer()


def _write_py(tmp_path: Path, code: str, name: str = "sample.py") -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(code))
    return p


def _write_js(tmp_path: Path, code: str, name: str = "sample.js") -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(code))
    return p


def _write_java(tmp_path: Path, code: str, name: str = "Sample.java") -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(code))
    return p


def _write_go(tmp_path: Path, code: str, name: str = "sample.go") -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(code))
    return p


# --- Core ---

class TestVariableMutabilityCore:
    def test_empty_file(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        p = _write_py(tmp_path, "")
        result = analyzer.analyze_file(p)
        assert result.total_issues == 0
        assert result.quality_score == 100.0

    def test_nonexistent_file(self, analyzer: VariableMutabilityAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.total_issues == 0

    def test_unsupported_extension(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        p = tmp_path / "file.rb"
        p.write_text("x = 1")
        result = analyzer.analyze_file(p)
        assert result.total_issues == 0

    def test_clean_code_no_issues(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        def clean():
            x = 1
            return x
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        assert result.total_issues == 0
        assert result.quality_score == 100.0

    def test_empty_result_factory(self) -> None:
        result = _empty_result("/fake.py")
        assert result.total_issues == 0
        assert result.quality_score == 100.0
        assert result.file_path == "/fake.py"

    def test_compute_score_no_issues(self) -> None:
        assert _compute_score(0, []) == 100.0

    def test_compute_score_with_issues(self) -> None:
        from tree_sitter_analyzer.analysis.variable_mutability import MutabilityIssue
        issues = [
            MutabilityIssue(
                issue_type=MUTABILITY_SHADOW,
                line=1, column=0, variable_name="x",
                severity="medium", description="test", suggestion="test",
            ),
        ]
        score = _compute_score(1, issues)
        assert score == 90.0

    def test_issue_types_in_result(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        def outer():
            x = 1
            def inner():
                x = 2
                y = 99
                return x
            return inner()
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        types = {i.issue_type for i in result.issues}
        assert MUTABILITY_SHADOW in types or MUTABILITY_UNUSED in types


# --- Python Shadow Variable ---

class TestPythonShadowVariable:
    def test_shadow_in_nested_function(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        def outer():
            x = 1
            def inner():
                x = 2
                return x
            return inner()
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        shadows = [i for i in result.issues if i.issue_type == MUTABILITY_SHADOW]
        assert len(shadows) >= 1
        assert shadows[0].variable_name == "x"

    def test_no_shadow_different_names(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        def outer():
            x = 1
            def inner():
                y = 2
                return y
            return inner()
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        shadows = [i for i in result.issues if i.issue_type == MUTABILITY_SHADOW]
        assert len(shadows) == 0

    def test_shadow_in_for_loop_nested(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        def outer():
            x = 1
            def inner():
                for x in range(10):
                    pass
                return x
            return inner()
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        shadows = [i for i in result.issues if i.issue_type == MUTABILITY_SHADOW]
        assert len(shadows) >= 1


# --- Python Unused Assignment ---

class TestPythonUnusedAssignment:
    def test_unused_variable(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        def func():
            x = 42
            return 1
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        unused = [i for i in result.issues if i.issue_type == MUTABILITY_UNUSED]
        assert len(unused) >= 1
        assert unused[0].variable_name == "x"

    def test_used_variable_no_issue(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        def func():
            x = 42
            return x
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        unused = [i for i in result.issues if i.issue_type == MUTABILITY_UNUSED]
        assert len(unused) == 0

    def test_underscore_prefix_not_flagged(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        def func():
            _unused = 42
            return 1
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        unused = [i for i in result.issues if i.issue_type == MUTABILITY_UNUSED and i.variable_name == "_unused"]
        assert len(unused) == 0


# --- Python Reassigned Constant ---

class TestPythonReassignedConstant:
    def test_upper_snake_reassigned(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        def func():
            MAX_RETRIES = 3
            MAX_RETRIES = 5
            return MAX_RETRIES
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        consts = [i for i in result.issues if i.issue_type == MUTABILITY_REASSIGNED_CONST]
        assert len(consts) >= 1
        assert consts[0].variable_name == "MAX_RETRIES"

    def test_lowercase_reassigned_not_flagged(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        def func():
            count = 0
            count = 1
            return count
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        consts = [i for i in result.issues if i.issue_type == MUTABILITY_REASSIGNED_CONST]
        assert len(consts) == 0


# --- Python Loop Mutation ---

class TestPythonLoopMutation:
    def test_augmented_assign_in_loop(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        def func():
            total = 0
            for i in range(10):
                total += 1
            return total
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        mutations = [i for i in result.issues if i.issue_type == MUTABILITY_LOOP_MUTATION]
        assert len(mutations) >= 1
        assert mutations[0].variable_name == "total"

    def test_new_var_in_loop_not_flagged(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        def func():
            result = []
            for i in range(10):
                x = i * 2
                result.append(x)
            return result
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        mutations = [i for i in result.issues if i.issue_type == MUTABILITY_LOOP_MUTATION and i.variable_name == "x"]
        assert len(mutations) == 0


# --- JavaScript ---

class TestJavaScriptShadowVariable:
    def test_shadow_in_nested_function(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        function outer() {
            let x = 1;
            function inner() {
                let x = 2;
                return x;
            }
            return inner();
        }
        """
        p = _write_js(tmp_path, code)
        result = analyzer.analyze_file(p)
        shadows = [i for i in result.issues if i.issue_type == MUTABILITY_SHADOW]
        assert len(shadows) >= 1

    def test_no_shadow_different_names(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        function outer() {
            let x = 1;
            function inner() {
                let y = 2;
                return y;
            }
            return inner();
        }
        """
        p = _write_js(tmp_path, code)
        result = analyzer.analyze_file(p)
        shadows = [i for i in result.issues if i.issue_type == MUTABILITY_SHADOW]
        assert len(shadows) == 0


class TestJavaScriptUnusedAssignment:
    def test_unused_var(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        function func() {
            let x = 42;
            return 1;
        }
        """
        p = _write_js(tmp_path, code)
        result = analyzer.analyze_file(p)
        unused = [i for i in result.issues if i.issue_type == MUTABILITY_UNUSED]
        assert len(unused) >= 1

    def test_used_var_no_issue(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        function func() {
            let x = 42;
            return x;
        }
        """
        p = _write_js(tmp_path, code)
        result = analyzer.analyze_file(p)
        unused = [i for i in result.issues if i.issue_type == MUTABILITY_UNUSED and i.variable_name == "x"]
        assert len(unused) == 0


class TestJavaScriptConstReassign:
    def test_const_reassignment(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        function func() {
            const x = 42;
            x = 99;
            return x;
        }
        """
        p = _write_js(tmp_path, code)
        result = analyzer.analyze_file(p)
        consts = [i for i in result.issues if i.issue_type == MUTABILITY_REASSIGNED_CONST]
        assert len(consts) >= 1

    def test_let_reassignment_not_flagged(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        function func() {
            let x = 42;
            x = 99;
            return x;
        }
        """
        p = _write_js(tmp_path, code)
        result = analyzer.analyze_file(p)
        consts = [i for i in result.issues if i.issue_type == MUTABILITY_REASSIGNED_CONST and i.variable_name == "x"]
        assert len(consts) == 0


class TestJavaScriptLoopMutation:
    def test_augmented_in_loop(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        function func() {
            let total = 0;
            for (let i = 0; i < 10; i++) {
                total += 1;
            }
            return total;
        }
        """
        p = _write_js(tmp_path, code)
        result = analyzer.analyze_file(p)
        mutations = [i for i in result.issues if i.issue_type == MUTABILITY_LOOP_MUTATION]
        assert len(mutations) >= 1


# --- Java ---

class TestJavaShadowVariable:
    def test_shadow_in_nested_scope(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        public class Sample {
            public void method() {
                int x = 1;
                for (int i = 0; i < 10; i++) {
                    int x = 2;
                }
            }
        }
        """
        p = _write_java(tmp_path, code)
        result = analyzer.analyze_file(p)
        shadows = [i for i in result.issues if i.issue_type == MUTABILITY_SHADOW]
        assert len(shadows) >= 1

    def test_no_shadow_different_names(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        public class Sample {
            public void method() {
                int x = 1;
                int y = 2;
                return;
            }
        }
        """
        p = _write_java(tmp_path, code)
        result = analyzer.analyze_file(p)
        shadows = [i for i in result.issues if i.issue_type == MUTABILITY_SHADOW]
        assert len(shadows) == 0


class TestJavaUnusedAssignment:
    def test_unused_var(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        public class Sample {
            public void method() {
                int x = 42;
            }
        }
        """
        p = _write_java(tmp_path, code)
        result = analyzer.analyze_file(p)
        unused = [i for i in result.issues if i.issue_type == MUTABILITY_UNUSED]
        assert len(unused) >= 1

    def test_used_var_no_issue(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        public class Sample {
            public int method() {
                int x = 42;
                return x;
            }
        }
        """
        p = _write_java(tmp_path, code)
        result = analyzer.analyze_file(p)
        unused = [i for i in result.issues if i.issue_type == MUTABILITY_UNUSED and i.variable_name == "x"]
        assert len(unused) == 0


class TestJavaFinalReassign:
    def test_upper_snake_reassigned(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        public class Sample {
            public void method() {
                int MAX_SIZE = 100;
                MAX_SIZE = 200;
            }
        }
        """
        p = _write_java(tmp_path, code)
        result = analyzer.analyze_file(p)
        consts = [i for i in result.issues if i.issue_type == MUTABILITY_REASSIGNED_CONST]
        assert len(consts) >= 1


# --- Go ---

class TestGoShadowVariable:
    def test_shadow_in_nested_scope(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        package main

        func outer() {
            x := 1
            if true {
                x := 2
                _ = x
            }
            _ = x
        }
        """
        p = _write_go(tmp_path, code)
        result = analyzer.analyze_file(p)
        shadows = [i for i in result.issues if i.issue_type == MUTABILITY_SHADOW]
        assert len(shadows) >= 1

    def test_no_shadow_different_names(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        package main

        func outer() {
            x := 1
            y := 2
            _ = x
            _ = y
        }
        """
        p = _write_go(tmp_path, code)
        result = analyzer.analyze_file(p)
        shadows = [i for i in result.issues if i.issue_type == MUTABILITY_SHADOW]
        assert len(shadows) == 0


class TestGoUnusedAssignment:
    def test_unused_var(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        package main

        func outer() {
            x := 42
        }
        """
        p = _write_go(tmp_path, code)
        result = analyzer.analyze_file(p)
        unused = [i for i in result.issues if i.issue_type == MUTABILITY_UNUSED]
        assert len(unused) >= 1

    def test_blank_identifier_not_flagged(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        package main

        func outer() {
            _ = 42
        }
        """
        p = _write_go(tmp_path, code)
        result = analyzer.analyze_file(p)
        unused = [i for i in result.issues if i.issue_type == MUTABILITY_UNUSED and i.variable_name == "_"]
        assert len(unused) == 0


class TestGoLoopMutation:
    def test_assign_in_loop(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        package main

        func outer() {
            total := 0
            for i := 0; i < 10; i++ {
                total = total + 1
            }
            _ = total
        }
        """
        p = _write_go(tmp_path, code)
        result = analyzer.analyze_file(p)
        mutations = [i for i in result.issues if i.issue_type == MUTABILITY_LOOP_MUTATION]
        assert len(mutations) >= 1


# --- TypeScript ---

class TestTypeScriptSupport:
    def test_typescript_shadow(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        function outer() {
            let x = 1;
            function inner() {
                let x = 2;
                return x;
            }
            return inner();
        }
        """
        p = tmp_path / "sample.ts"
        p.write_text(textwrap.dedent(code))
        result = analyzer.analyze_file(p)
        shadows = [i for i in result.issues if i.issue_type == MUTABILITY_SHADOW]
        assert len(shadows) >= 1

    def test_typescript_unused(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        function func() {
            let x = 42;
            return 1;
        }
        """
        p = tmp_path / "sample.ts"
        p.write_text(textwrap.dedent(code))
        result = analyzer.analyze_file(p)
        unused = [i for i in result.issues if i.issue_type == MUTABILITY_UNUSED]
        assert len(unused) >= 1


# --- Score and Counts ---

class TestScoreAndCounts:
    def test_issue_counts(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        def func():
            x = 1
            def inner():
                x = 2
                y = 99
                return x
            return inner()
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        assert isinstance(result.issue_counts, dict)
        if result.total_issues > 0:
            assert sum(result.issue_counts.values()) == result.total_issues

    def test_score_decreases_with_issues(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code_clean = """\
        def func():
            x = 1
            return x
        """
        code_dirty = """\
        def func():
            x = 42
            return 1
        """
        p_clean = _write_py(tmp_path, code_clean, "clean.py")
        p_dirty = _write_py(tmp_path, code_dirty, "dirty.py")

        clean_result = analyzer.analyze_file(p_clean)
        dirty_result = analyzer.analyze_file(p_dirty)

        if dirty_result.total_issues > 0:
            assert dirty_result.quality_score < clean_result.quality_score

    def test_quality_score_non_negative(self, analyzer: VariableMutabilityAnalyzer, tmp_path: Path) -> None:
        code = """\
        def func():
            A = 1
            A = 2
            B = 3
            B = 4
            C = 5
            C = 6
            return A + B + C
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        assert result.quality_score >= 0.0
