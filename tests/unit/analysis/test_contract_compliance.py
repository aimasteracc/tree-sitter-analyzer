"""Tests for Contract Compliance Analyzer."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.contract_compliance import (
    ISSUE_BOOLEAN_TRAP,
    ISSUE_RETURN_VIOLATION,
    ISSUE_TYPE_CONTRADICTION,
    SEVERITY_HIGH,
    ContractComplianceAnalyzer,
)


@pytest.fixture
def analyzer() -> ContractComplianceAnalyzer:
    return ContractComplianceAnalyzer()


def _write_tmp(content: str, suffix: str) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return Path(f.name)


class TestPythonReturnViolation:
    def test_return_none_when_str_expected(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''def get_name() -> str:
    if True:
        return None
    return "hello"
'''
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert result.total_issues >= 1
        violations = [i for i in result.issues if i.issue_type == ISSUE_RETURN_VIOLATION]
        assert len(violations) >= 1
        assert violations[0].severity == SEVERITY_HIGH

    def test_return_none_when_int_expected(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''def get_count() -> int:
    return None
'''
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        violations = [i for i in result.issues if i.issue_type == ISSUE_RETURN_VIOLATION]
        assert len(violations) >= 1

    def test_no_return_type_annotation(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''def get_name():
    return None
'''
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert result.total_issues == 0

    def test_optional_return_none_ok(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''from typing import Optional
def get_name() -> Optional[str]:
    return None
'''
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        violations = [i for i in result.issues if i.issue_type == ISSUE_RETURN_VIOLATION]
        assert len(violations) == 0

    def test_union_return_none_ok(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''def get_name() -> str | None:
    return None
'''
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        violations = [i for i in result.issues if i.issue_type == ISSUE_RETURN_VIOLATION]
        assert len(violations) == 0

    def test_none_return_type_ok(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''def do_nothing() -> None:
    return None
'''
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        violations = [i for i in result.issues if i.issue_type == ISSUE_RETURN_VIOLATION]
        assert len(violations) == 0

    def test_correct_return_type_no_issues(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''def get_name() -> str:
    return "hello"
'''
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert result.total_issues == 0

    def test_bare_return_violation(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''def get_name() -> str:
    return
'''
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        violations = [i for i in result.issues if i.issue_type == ISSUE_RETURN_VIOLATION]
        assert len(violations) >= 1


class TestPythonBooleanTrap:
    def test_bool_annotation_non_bool_return(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''def is_valid() -> bool:
    return 1
'''
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        bool_issues = [i for i in result.issues if i.issue_type == ISSUE_BOOLEAN_TRAP]
        assert len(bool_issues) >= 1

    def test_bool_annotation_true_ok(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''def is_valid() -> bool:
    return True
'''
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        bool_issues = [i for i in result.issues if i.issue_type == ISSUE_BOOLEAN_TRAP]
        assert len(bool_issues) == 0

    def test_bool_annotation_false_ok(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''def is_valid() -> bool:
    return False
'''
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert result.total_issues == 0


class TestPythonTypeContradiction:
    def test_str_param_multiplied(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''def greet(name: str) -> str:
    return name * 3
'''
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        contradictions = [i for i in result.issues if i.issue_type == ISSUE_TYPE_CONTRADICTION]
        assert len(contradictions) >= 1

    def test_int_param_string_method(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''def process(count: int) -> str:
    return count.upper()
'''
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        contradictions = [i for i in result.issues if i.issue_type == ISSUE_TYPE_CONTRADICTION]
        assert len(contradictions) >= 1

    def test_no_annotation_no_check(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''def greet(name):
    return name * 3
'''
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert result.total_issues == 0


class TestPythonEdgeCases:
    def test_nested_function_not_analyzed_for_returns(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''def outer() -> str:
    def inner():
        return None
    return "hello"
'''
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert result.total_issues == 0

    def test_file_not_found(self, analyzer: ContractComplianceAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.total_issues == 0

    def test_unsupported_extension(self, analyzer: ContractComplianceAnalyzer) -> None:
        path = _write_tmp("fn main() {}", ".rs")
        result = analyzer.analyze_file(path)
        assert result.total_issues == 0

    def test_empty_file(self, analyzer: ContractComplianceAnalyzer) -> None:
        path = _write_tmp("", ".py")
        result = analyzer.analyze_file(path)
        assert result.total_issues == 0

    def test_result_to_dict(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''def get_name() -> str:
    return None
'''
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        d = result.to_dict()
        assert "issues" in d
        assert "total_issues" in d
        assert d["language"] == "python"


class TestJavaScriptReturnViolation:
    def test_js_return_violation(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''function getName(): string {
    return;
}
'''
        path = _write_tmp(code, ".ts")
        result = analyzer.analyze_file(path)
        violations = [i for i in result.issues if i.issue_type == ISSUE_RETURN_VIOLATION]
        assert len(violations) >= 1

    def test_js_correct_return(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''function getName(): string {
    return "hello";
}
'''
        path = _write_tmp(code, ".ts")
        result = analyzer.analyze_file(path)
        assert result.total_issues == 0

    def test_js_boolean_trap(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''function isValid(): boolean {
    return 1;
}
'''
        path = _write_tmp(code, ".ts")
        result = analyzer.analyze_file(path)
        bool_issues = [i for i in result.issues if i.issue_type == ISSUE_BOOLEAN_TRAP]
        assert len(bool_issues) >= 1

    def test_js_no_annotation(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''function getName() {
    return;
}
'''
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert result.total_issues == 0

    def test_jsx_file_no_type_annotations(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''function getName() {
    return "hello";
}
'''
        path = _write_tmp(code, ".jsx")
        result = analyzer.analyze_file(path)
        assert result.total_issues == 0

    def test_tsx_file(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''function getName(): string {
    return;
}
'''
        path = _write_tmp(code, ".tsx")
        result = analyzer.analyze_file(path)
        assert result.total_issues >= 1


class TestJavaReturnViolation:
    def test_java_return_violation(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''public class Foo {
    public String getName() {
        return;
    }
}
'''
        path = _write_tmp(code, ".java")
        result = analyzer.analyze_file(path)
        violations = [i for i in result.issues if i.issue_type == ISSUE_RETURN_VIOLATION]
        assert len(violations) >= 1

    def test_java_void_return_ok(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''public class Foo {
    public void doNothing() {
        return;
    }
}
'''
        path = _write_tmp(code, ".java")
        result = analyzer.analyze_file(path)
        violations = [i for i in result.issues if i.issue_type == ISSUE_RETURN_VIOLATION]
        assert len(violations) == 0

    def test_java_boolean_trap(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''public class Foo {
    public boolean isValid() {
        return 1;
    }
}
'''
        path = _write_tmp(code, ".java")
        result = analyzer.analyze_file(path)
        bool_issues = [i for i in result.issues if i.issue_type == ISSUE_BOOLEAN_TRAP]
        assert len(bool_issues) >= 1

    def test_java_correct_return(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''public class Foo {
    public String getName() {
        return "hello";
    }
}
'''
        path = _write_tmp(code, ".java")
        result = analyzer.analyze_file(path)
        assert result.total_issues == 0


class TestGoReturnViolation:
    def test_go_nil_return_violation(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''func getName() string {
    return nil
}
'''
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        violations = [i for i in result.issues if i.issue_type == ISSUE_RETURN_VIOLATION]
        assert len(violations) >= 1

    def test_go_error_nil_ok(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''func doSomething() error {
    return nil
}
'''
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        violations = [i for i in result.issues if i.issue_type == ISSUE_RETURN_VIOLATION]
        assert len(violations) == 0

    def test_go_boolean_trap(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''func isValid() bool {
    return 1
}
'''
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        bool_issues = [i for i in result.issues if i.issue_type == ISSUE_BOOLEAN_TRAP]
        assert len(bool_issues) >= 1

    def test_go_no_result_type(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''func doSomething() {
    return
}
'''
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        assert result.total_issues == 0

    def test_go_method(self, analyzer: ContractComplianceAnalyzer) -> None:
        code = '''func (f Foo) getName() string {
    return nil
}
'''
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        violations = [i for i in result.issues if i.issue_type == ISSUE_RETURN_VIOLATION]
        assert len(violations) >= 1


class TestDirectoryAnalysis:
    def test_analyze_directory(self, analyzer: ContractComplianceAnalyzer, tmp_path: Path) -> None:
        py_file = tmp_path / "test.py"
        py_file.write_text("def get_name() -> str:\n    return None\n")

        js_file = tmp_path / "test.ts"
        js_file.write_text("function getName(): string { return; }\n")

        result = analyzer.analyze_directory(tmp_path)
        assert result.total_issues >= 2
        assert result.language == "mixed"

    def test_directory_skips_git(self, analyzer: ContractComplianceAnalyzer, tmp_path: Path) -> None:
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        git_file = git_dir / "test.py"
        git_file.write_text("def get_name() -> str:\n    return None\n")

        result = analyzer.analyze_directory(tmp_path)
        assert result.total_issues == 0
