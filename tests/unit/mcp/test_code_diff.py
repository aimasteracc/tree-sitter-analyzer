#!/usr/bin/env python3
"""
Unit tests for Code Diff Analysis Tool.
"""

import pytest

from tree_sitter_analyzer.mcp.tools.code_diff_tool import (
    ChangeSeverity,
    ChangeType,
    CodeDiffResult,
    CodeDiffTool,
    ElementDiff,
)


class TestElementDiff:
    """Tests for ElementDiff dataclass."""

    def test_create_element_diff(self) -> None:
        """Test creating an ElementDiff."""
        diff = ElementDiff(
            element_type="function",
            name="process_data",
            change_type=ChangeType.MODIFIED,
            severity=ChangeSeverity.NON_BREAKING,
            details="Parameters changed",
        )

        assert diff.element_type == "function"
        assert diff.name == "process_data"
        assert diff.change_type == ChangeType.MODIFIED
        assert diff.severity == ChangeSeverity.NON_BREAKING
        assert diff.details == "Parameters changed"

    def test_to_dict(self) -> None:
        """Test ElementDiff.to_dict()."""
        diff = ElementDiff(
            element_type="class",
            name="Service",
            change_type=ChangeType.ADDED,
            severity=ChangeSeverity.NON_BREAKING,
        )

        result = diff.to_dict()

        assert result == {
            "type": "class",
            "name": "Service",
            "change": "added",
            "severity": "non_breaking",
            "details": "",
        }


class TestCodeDiffResult:
    """Tests for CodeDiffResult dataclass."""

    def test_create_diff_result(self) -> None:
        """Test creating a CodeDiffResult."""
        diffs = [
            ElementDiff(
                element_type="function",
                name="foo",
                change_type=ChangeType.ADDED,
                severity=ChangeSeverity.NON_BREAKING,
            )
        ]

        result = CodeDiffResult(
            file_path="test.py",
            old_content_hash="abc123",
            new_content_hash="def456",
            elements=diffs,
            summary={"total": 1, "added": 1, "removed": 0, "modified": 0, "breaking": 0},
        )

        assert result.file_path == "test.py"
        assert len(result.elements) == 1
        assert result.summary["total"] == 1

    def test_to_dict(self) -> None:
        """Test CodeDiffResult.to_dict()."""
        diffs = [
            ElementDiff(
                element_type="function",
                name="bar",
                change_type=ChangeType.REMOVED,
                severity=ChangeSeverity.BREAKING,
            )
        ]

        result = CodeDiffResult(
            file_path="service.py",
            old_content_hash="old_hash",
            new_content_hash="new_hash",
            elements=diffs,
            summary={"total": 1, "added": 0, "removed": 1, "modified": 0, "breaking": 1},
        )

        dict_result = result.to_dict()

        assert dict_result["file"] == "service.py"
        assert dict_result["old_hash"] == "old_hash"
        assert dict_result["new_hash"] == "new_hash"
        assert len(dict_result["changes"]) == 1
        assert dict_result["changes"][0]["name"] == "bar"
        assert dict_result["summary"]["breaking"] == 1


class TestCodeDiffTool:
    """Tests for CodeDiffTool."""

    @pytest.fixture
    def tool(self) -> CodeDiffTool:
        """Create a CodeDiffTool instance."""
        return CodeDiffTool()

    def test_get_tool_definition(self, tool: CodeDiffTool) -> None:
        """Test tool definition."""
        definition = tool.get_tool_definition()

        assert definition["name"] == "code_diff"
        assert "diff" in definition["description"].lower()
        assert "inputSchema" in definition

    def test_get_content_hash(self, tool: CodeDiffTool) -> None:
        """Test content hashing."""
        content = "def hello(): pass"
        hash1 = tool._get_content_hash(content)
        hash2 = tool._get_content_hash(content)
        hash3 = tool._get_content_hash("different content")

        assert len(hash1) == 16
        assert hash1 == hash2  # Same content produces same hash
        assert hash1 != hash3  # Different content produces different hash

    def test_detect_language_python(self, tool: CodeDiffTool) -> None:
        """Test Python language detection."""
        content = "import os\ndef foo(): pass"
        language = tool._detect_language("test.py", content)

        assert language == "python"

    def test_detect_language_java(self, tool: CodeDiffTool) -> None:
        """Test Java language detection."""
        content = "public class Test { }"
        language = tool._detect_language("Test.java", content)

        assert language == "java"

    def test_detect_language_from_extension(self, tool: CodeDiffTool) -> None:
        """Test language detection from file extension."""
        assert tool._detect_language("test.go", "") == "go"
        assert tool._detect_language("test.rs", "") == "rust"
        assert tool._detect_language("test.ts", "") == "typescript"
        assert tool._detect_language("test.js", "") == "javascript"

    def test_is_public_api_public_function(self, tool: CodeDiffTool) -> None:
        """Test public API detection for public functions."""
        from tree_sitter_analyzer.models import Function

        func = Function(name="public_method", start_line=1, end_line=5, is_public=True)
        assert tool._is_public_api(func) is True

    def test_is_public_api_private_function(self, tool: CodeDiffTool) -> None:
        """Test public API detection for private functions."""
        from tree_sitter_analyzer.models import Function

        func = Function(name="_private_method", start_line=1, end_line=5, is_private=True)
        assert tool._is_public_api(func) is False

    def test_is_public_api_private_class(self, tool: CodeDiffTool) -> None:
        """Test public API detection for private classes."""
        from tree_sitter_analyzer.models import Class

        cls = Class(name="_InternalClass", start_line=1, end_line=10)
        assert tool._is_public_api(cls) is False

    def test_validate_arguments_valid_paths(self, tool: CodeDiffTool) -> None:
        """Test argument validation with valid paths."""
        arguments = {
            "old_path": "/path/to/old.py",
            "new_path": "/path/to/new.py",
        }

        assert tool.validate_arguments(arguments) is True

    def test_validate_arguments_valid_content(self, tool: CodeDiffTool) -> None:
        """Test argument validation with valid content."""
        arguments = {
            "old_content": "def old(): pass",
            "new_content": "def new(): pass",
        }

        assert tool.validate_arguments(arguments) is True

    def test_validate_arguments_missing_old(self, tool: CodeDiffTool) -> None:
        """Test argument validation with missing old version."""
        arguments = {
            "new_content": "def new(): pass",
        }

        with pytest.raises(ValueError, match="Must provide"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_missing_new(self, tool: CodeDiffTool) -> None:
        """Test argument validation with missing new version."""
        arguments = {
            "old_content": "def old(): pass",
        }

        with pytest.raises(ValueError, match="Must provide"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_output_format(self, tool: CodeDiffTool) -> None:
        """Test argument validation with invalid output format."""
        arguments = {
            "old_content": "old",
            "new_content": "new",
            "output_format": "invalid",
        }

        with pytest.raises(ValueError, match="output_format"):
            tool.validate_arguments(arguments)

    def test_get_element_key_function(self, tool: CodeDiffTool) -> None:
        """Test element key generation for functions."""
        from tree_sitter_analyzer.models import Function

        func = Function(name="method", start_line=1, end_line=5)
        key = tool._get_element_key(func)

        assert key == "function:method"

    def test_get_element_key_class(self, tool: CodeDiffTool) -> None:
        """Test element key generation for classes."""
        from tree_sitter_analyzer.models import Class

        cls = Class(name="MyClass", start_line=1, end_line=10)
        key = tool._get_element_key(cls)

        assert key == "class:MyClass"

    def test_compare_elements_added(self, tool: CodeDiffTool) -> None:
        """Test element comparison with added elements."""
        from tree_sitter_analyzer.models import Function

        new_func = Function(name="new_method", start_line=1, end_line=5)

        diffs = tool._compare_elements([], [new_func])

        assert len(diffs) == 1
        assert diffs[0].change_type == ChangeType.ADDED
        assert diffs[0].name == "new_method"

    def test_compare_elements_removed(self, tool: CodeDiffTool) -> None:
        """Test element comparison with removed elements."""
        from tree_sitter_analyzer.models import Function

        old_func = Function(name="old_method", start_line=1, end_line=5)

        diffs = tool._compare_elements([old_func], [])

        assert len(diffs) == 1
        assert diffs[0].change_type == ChangeType.REMOVED
        assert diffs[0].name == "old_method"

    def test_compare_elements_unchanged(self, tool: CodeDiffTool) -> None:
        """Test element comparison with unchanged elements."""
        from tree_sitter_analyzer.models import Function

        func = Function(name="same_method", start_line=1, end_line=5)

        diffs = tool._compare_elements([func], [func])

        assert len(diffs) == 0  # No changes detected

    def test_compare_elements_removed_public_breaking(self, tool: CodeDiffTool) -> None:
        """Test that removing public API is marked as breaking."""
        from tree_sitter_analyzer.models import Function

        public_func = Function(name="public_api", start_line=1, end_line=5)

        diffs = tool._compare_elements([public_func], [])

        assert len(diffs) == 1
        assert diffs[0].severity == ChangeSeverity.BREAKING

    def test_compare_elements_removed_private_non_breaking(
        self, tool: CodeDiffTool
    ) -> None:
        """Test that removing private API is marked as non-breaking."""
        from tree_sitter_analyzer.models import Function

        private_func = Function(name="_private", start_line=1, end_line=5)

        diffs = tool._compare_elements([private_func], [])

        assert len(diffs) == 1
        assert diffs[0].severity == ChangeSeverity.NON_BREAKING
