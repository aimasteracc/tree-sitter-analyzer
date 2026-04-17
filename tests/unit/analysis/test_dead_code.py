#!/usr/bin/env python3
"""
Unit tests for Dead Code Detection module.
"""

import pytest

from tree_sitter_analyzer.analysis.dead_code import (
    DeadCodeIssue,
    DeadCodeReport,
    DeadCodeType,
    is_entry_point,
    is_public_api,
)


class TestDeadCodeType:
    """Tests for DeadCodeType enum."""

    def test_enum_values(self) -> None:
        """Test that DeadCodeType has expected values."""
        assert DeadCodeType.UNUSED_FUNCTION.value == "unused_function"
        assert DeadCodeType.UNUSED_CLASS.value == "unused_class"
        assert DeadCodeType.UNUSED_IMPORT.value == "unused_import"


class TestDeadCodeIssue:
    """Tests for DeadCodeIssue dataclass."""

    def test_create_issue(self) -> None:
        """Test creating a dead code issue."""
        issue = DeadCodeIssue(
            name="unused_func",
            type=DeadCodeType.UNUSED_FUNCTION,
            file="test.py",
            line=10,
            confidence=0.9,
        )
        assert issue.name == "unused_func"
        assert issue.type == DeadCodeType.UNUSED_FUNCTION
        assert issue.file == "test.py"
        assert issue.line == 10
        assert issue.confidence == 0.9

    def test_issue_is_frozen(self) -> None:
        """Test that DeadCodeIssue is frozen (immutable)."""
        issue = DeadCodeIssue(
            name="unused_func",
            type=DeadCodeType.UNUSED_FUNCTION,
            file="test.py",
            line=10,
            confidence=0.9,
        )
        with pytest.raises((TypeError, AttributeError)):  # Frozen dataclass raises these
            issue.name = "new_name"  # type: ignore

    def test_issue_str_representation(self) -> None:
        """Test string representation of issue."""
        issue = DeadCodeIssue(
            name="unused_func",
            type=DeadCodeType.UNUSED_FUNCTION,
            file="test.py",
            line=10,
            confidence=0.9,
        )
        assert str(issue) == "unused_function:unused_func@test.py:10"

    def test_issue_with_reason(self) -> None:
        """Test issue with reason."""
        issue = DeadCodeIssue(
            name="unused_func",
            type=DeadCodeType.UNUSED_FUNCTION,
            file="test.py",
            line=10,
            confidence=0.9,
            reason="No references found",
        )
        assert issue.reason == "No references found"


class TestDeadCodeReport:
    """Tests for DeadCodeReport dataclass."""

    def test_empty_report(self) -> None:
        """Test creating an empty report."""
        report = DeadCodeReport()
        assert report.dead_count == 0
        assert report.files_scanned == 0
        assert report.total_definitions == 0
        assert report.total_references == 0

    def test_add_issue(self) -> None:
        """Test adding an issue to report."""
        report = DeadCodeReport()
        issue = DeadCodeIssue(
            name="unused_func",
            type=DeadCodeType.UNUSED_FUNCTION,
            file="test.py",
            line=10,
            confidence=0.9,
        )
        report.add_issue(issue)
        assert report.dead_count == 1
        assert report.issues == [issue]

    def test_unused_functions_filter(self) -> None:
        """Test filtering unused functions."""
        report = DeadCodeReport()
        report.add_issue(
            DeadCodeIssue(
                name="func1",
                type=DeadCodeType.UNUSED_FUNCTION,
                file="a.py",
                line=1,
                confidence=0.9,
            )
        )
        report.add_issue(
            DeadCodeIssue(
                name="Class1",
                type=DeadCodeType.UNUSED_CLASS,
                file="a.py",
                line=5,
                confidence=0.9,
            )
        )
        assert len(report.unused_functions) == 1
        assert report.unused_functions[0].name == "func1"

    def test_unused_classes_filter(self) -> None:
        """Test filtering unused classes."""
        report = DeadCodeReport()
        report.add_issue(
            DeadCodeIssue(
                name="func1",
                type=DeadCodeType.UNUSED_FUNCTION,
                file="a.py",
                line=1,
                confidence=0.9,
            )
        )
        report.add_issue(
            DeadCodeIssue(
                name="Class1",
                type=DeadCodeType.UNUSED_CLASS,
                file="a.py",
                line=5,
                confidence=0.9,
            )
        )
        assert len(report.unused_classes) == 1
        assert report.unused_classes[0].name == "Class1"

    def test_unused_imports_filter(self) -> None:
        """Test filtering unused imports."""
        report = DeadCodeReport()
        report.add_issue(
            DeadCodeIssue(
                name="os",
                type=DeadCodeType.UNUSED_IMPORT,
                file="a.py",
                line=1,
                confidence=0.9,
            )
        )
        report.add_issue(
            DeadCodeIssue(
                name="func1",
                type=DeadCodeType.UNUSED_FUNCTION,
                file="a.py",
                line=10,
                confidence=0.9,
            )
        )
        assert len(report.unused_imports) == 1
        assert report.unused_imports[0].name == "os"


class TestIsEntryPoint:
    """Tests for is_entry_point function."""

    def test_main_is_entry_point(self) -> None:
        """Test that 'main' is recognized as entry point."""
        assert is_entry_point("main") is True
        assert is_entry_point("Main") is True
        assert is_entry_point("my_main") is True

    def test_test_function_is_entry_point(self) -> None:
        """Test that test functions are recognized as entry points."""
        assert is_entry_point("test_something") is True
        assert is_entry_point("TestSomething") is True
        assert is_entry_point("pytest_something") is True
        assert is_entry_point("unittest_something") is True

    def test_setup_teardown_are_entry_points(self) -> None:
        """Test that setup and teardown are entry points."""
        assert is_entry_point("setup") is True
        assert is_entry_point("teardown") is True
        assert is_entry_point("setUp") is True
        assert is_entry_point("tearDown") is True

    def test_regular_function_is_not_entry_point(self) -> None:
        """Test that regular functions are not entry points."""
        assert is_entry_point("calculate") is False
        assert is_entry_point("process_data") is False

    def test_test_file_path(self) -> None:
        """Test that symbols in test files are considered entry points."""
        assert is_entry_point("helper", "test_module.py") is True
        assert is_entry_point("helper", "tests/test_case.py") is True
        assert is_entry_point("helper", "src/module.py") is False

    def test_case_insensitive_pattern_matching(self) -> None:
        """Test that pattern matching is case-insensitive."""
        assert is_entry_point("MAIN") is True
        assert is_entry_point("TestFunc") is True
        assert is_entry_point("SETUP") is True


class TestIsPublicApi:
    """Tests for is_public_api function."""

    def test_underscore_prefix_is_private(self) -> None:
        """Test that symbols starting with underscore are private."""
        assert is_public_api("_private_func") is False
        assert is_public_api("__dunder") is False
        assert is_public_api("_internal") is False

    def test_regular_name_is_public(self) -> None:
        """Test that regular names are public."""
        assert is_public_api("public_func") is True
        assert is_public_api("MyClass") is True
        assert is_public_api("CONSTANT") is True

    def test_dunder_all_is_public_api(self) -> None:
        """Test that __all__ is recognized as public API marker."""
        assert is_public_api("__all__") is True

    def test_dunder_methods_are_public(self) -> None:
        """Test that dunder methods are considered public."""
        assert is_public_api("__init__") is True
        assert is_public_api("__str__") is True
        assert is_public_api("__repr__") is True

    def test_single_underscore_is_private(self) -> None:
        """Test that single underscore prefix is private."""
        assert is_public_api("_private") is False
        assert is_public_api("_internal_func") is False
