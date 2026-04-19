"""Tests for Contract Compliance Analyzer."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.contract_compliance import (
    ISSUE_BOOLEAN_TRAP,
    ISSUE_RETURN_VIOLATION,
    ContractComplianceAnalyzer,
)

ANALYZER = ContractComplianceAnalyzer()


class TestPythonContract:
    def test_return_type_violation(self, tmp_path: Path) -> None:
        code = (
            "def get_name() -> str:\n"
            "    return None\n"
        )
        f = tmp_path / "violation.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_RETURN_VIOLATION for i in result.issues)

    def test_boolean_trap(self, tmp_path: Path) -> None:
        code = (
            "def is_valid() -> bool:\n"
            "    return 1\n"
        )
        f = tmp_path / "booltrap.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_BOOLEAN_TRAP for i in result.issues)

    def test_clean_code(self, tmp_path: Path) -> None:
        code = (
            "def get_name() -> str:\n"
            "    return 'hello'\n"
        )
        f = tmp_path / "clean.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0

    def test_no_annotation(self, tmp_path: Path) -> None:
        code = (
            "def greet(name):\n"
            "    return f'Hello {name}'\n"
        )
        f = tmp_path / "noannot.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0

    def test_nonexistent_file(self) -> None:
        result = ANALYZER.analyze_file("/nonexistent/file.py")
        assert result.total_issues == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("")
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0


class TestJavaContract:
    def test_return_violation_java(self, tmp_path: Path) -> None:
        code = (
            "public class Foo {\n"
            "  public String getName() {\n"
            "    return;\n"
            "  }\n"
            "}\n"
        )
        f = tmp_path / "Foo.java"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_RETURN_VIOLATION for i in result.issues)
