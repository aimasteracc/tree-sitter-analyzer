"""
Unit tests for refactoring_suggestions_tool MCP tool.
"""

from tree_sitter_analyzer.mcp.tools.refactoring_suggestions_tool import (
    RefactoringSuggestionsTool,
)


class TestRefactoringSuggestionsTool:
    """Tests for RefactoringSuggestionsTool class."""

    def test_tool_initialization(self) -> None:
        """Test tool initialization."""
        tool = RefactoringSuggestionsTool()

        assert tool.advisor is not None

    def test_get_tool_definition(self) -> None:
        """Test tool definition generation."""
        tool = RefactoringSuggestionsTool()
        definition = tool.get_tool_definition()

        assert definition["name"] == "refactoring_suggestions"
        assert "file_path" in definition["inputSchema"]["properties"]
        assert "content" in definition["inputSchema"]["properties"]
        assert "language" in definition["inputSchema"]["properties"]
        assert "min_severity" in definition["inputSchema"]["properties"]
        assert "output_format" in definition["inputSchema"]["properties"]

    def test_validate_arguments_valid(self) -> None:
        """Test argument validation with valid arguments."""
        tool = RefactoringSuggestionsTool()

        arguments = {
            "file_path": "test.py",
            "content": "def test(): pass",
            "language": "python",
            "min_severity": "low",
            "output_format": "toon",
        }

        assert tool.validate_arguments(arguments) is True

    def test_validate_arguments_invalid_language(self) -> None:
        """Test argument validation with invalid language."""
        tool = RefactoringSuggestionsTool()

        arguments = {
            "file_path": "test.py",
            "language": "invalid_language",
        }

        try:
            tool.validate_arguments(arguments)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "language" in str(e).lower()

    def test_validate_arguments_invalid_severity(self) -> None:
        """Test argument validation with invalid severity."""
        tool = RefactoringSuggestionsTool()

        arguments = {
            "file_path": "test.py",
            "min_severity": "invalid",
        }

        try:
            tool.validate_arguments(arguments)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "min_severity" in str(e)

    def test_validate_arguments_invalid_format(self) -> None:
        """Test argument validation with invalid format."""
        tool = RefactoringSuggestionsTool()

        arguments = {
            "file_path": "test.py",
            "output_format": "invalid",
        }

        try:
            tool.validate_arguments(arguments)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "output_format" in str(e)

    def test_format_summary_empty_report(self) -> None:
        """Test summary format with empty report."""
        tool = RefactoringSuggestionsTool()

        from tree_sitter_analyzer.analysis.refactoring_suggestions import (
            RefactoringReport,
        )

        report = RefactoringReport(file_path="empty.py")
        result = tool._format_summary(report)

        assert "No refactoring suggestions" in result
        assert "code looks good" in result

    def test_format_summary_with_suggestions(self) -> None:
        """Test summary format with suggestions."""
        tool = RefactoringSuggestionsTool()

        from tree_sitter_analyzer.analysis.refactoring_suggestions import (
            RefactoringReport,
            RefactoringSuggestion,
            RefactoringType,
            SeverityLevel,
        )

        report = RefactoringReport(file_path="test.py")
        suggestion = RefactoringSuggestion(
            type=RefactoringType.EXTRACT_METHOD,
            title="Extract Method",
            description="Method is too long",
            severity=SeverityLevel.MEDIUM,
            file_path="test.py",
            line_start=10,
            line_end=50,
            language="python",
        )
        report.add_suggestion(suggestion)

        result = tool._format_summary(report)

        assert "Suggestions" in result
        assert "Total suggestions: 1" in result

    def test_format_toon_empty_report(self) -> None:
        """Test TOON format with empty report."""
        tool = RefactoringSuggestionsTool()

        from tree_sitter_analyzer.analysis.refactoring_suggestions import (
            RefactoringReport,
        )

        report = RefactoringReport(file_path="empty.py")
        result = tool._format_toon(report, "python")

        assert "🔧" in result
        assert "No refactoring suggestions" in result

    def test_format_toon_with_suggestions(self) -> None:
        """Test TOON format with suggestions."""
        tool = RefactoringSuggestionsTool()

        from tree_sitter_analyzer.analysis.refactoring_suggestions import (
            RefactoringReport,
            RefactoringSuggestion,
            RefactoringType,
            SeverityLevel,
        )

        report = RefactoringReport(file_path="test.py")
        suggestion = RefactoringSuggestion(
            type=RefactoringType.EXTRACT_METHOD,
            title="Extract Method",
            description="Method is too long",
            severity=SeverityLevel.MEDIUM,
            file_path="test.py",
            line_start=10,
            line_end=50,
            language="python",
        )
        report.add_suggestion(suggestion)

        result = tool._format_toon(report, "python")

        assert "🔧" in result
        assert "💡" in result
        assert "Extract Method" in result

    def test_severity_emoji(self) -> None:
        """Test severity emoji mapping."""
        tool = RefactoringSuggestionsTool()

        assert tool._severity_emoji("critical") == "🔴"
        assert tool._severity_emoji("high") == "🟠"
        assert tool._severity_emoji("medium") == "🟡"
        assert tool._severity_emoji("low") == "🟢"
        assert tool._severity_emoji("info") == "🔵"
        assert tool._severity_emoji("unknown") == "⚪"
