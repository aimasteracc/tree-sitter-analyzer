"""
Test SummaryFormatter functionality.

Tests the summary formatter output format and edge cases.
"""


class TestSummaryFormatter:
    """Test SummaryFormatter class."""

    def test_formatter_can_be_imported(self) -> None:
        """Test that SummaryFormatter can be imported."""
        from tree_sitter_analyzer_v2.formatters.summary_formatter import SummaryFormatter

        assert SummaryFormatter is not None

    def test_formatter_initialization(self) -> None:
        """Test creating a SummaryFormatter instance."""
        from tree_sitter_analyzer_v2.formatters.summary_formatter import SummaryFormatter

        formatter = SummaryFormatter()
        assert formatter is not None

    def test_format_basic_result(self) -> None:
        """Test formatting a basic analysis result."""
        from tree_sitter_analyzer_v2.formatters.summary_formatter import SummaryFormatter

        formatter = SummaryFormatter()

        result = {
            "file_path": "test.py",
            "language": "python",
            "classes": [{"name": "MyClass", "methods": [{"name": "method1"}]}],
            "functions": [{"name": "my_function"}],
            "imports": [{"module": "os"}],
            "metadata": {
                "total_lines": 100,
                "code_lines": 70,
                "comment_lines": 20,
                "blank_lines": 10,
            },
        }

        output = formatter.format(result)

        # Verify required fields
        assert "File: test.py" in output
        assert "Language: python" in output
        assert "Lines: 100" in output
        assert "Classes: 1" in output
        assert "MyClass" in output
        assert "Functions: 1" in output
        assert "Methods: 1" in output
        assert "Imports: 1" in output

    def test_format_empty_file(self) -> None:
        """Test formatting an empty file result."""
        from tree_sitter_analyzer_v2.formatters.summary_formatter import SummaryFormatter

        formatter = SummaryFormatter()

        result = {
            "file_path": "empty.py",
            "language": "python",
            "classes": [],
            "functions": [],
            "imports": [],
            "metadata": {},
        }

        output = formatter.format(result)

        assert "File: empty.py" in output
        assert "Language: python" in output
        assert "Classes: 0" in output
        assert "Functions: 0" in output
        assert "Imports: 0" in output

    def test_format_with_multiple_classes(self) -> None:
        """Test formatting result with many classes."""
        from tree_sitter_analyzer_v2.formatters.summary_formatter import SummaryFormatter

        formatter = SummaryFormatter()

        result = {
            "file_path": "multi.py",
            "language": "python",
            "classes": [
                {"name": "Class1"},
                {"name": "Class2"},
                {"name": "Class3"},
                {"name": "Class4"},
                {"name": "Class5"},
            ],
            "functions": [],
            "imports": [],
            "metadata": {},
        }

        output = formatter.format(result)

        # Should show first 3 and indicate more
        assert "Classes: 5" in output
        assert "Class1" in output
        assert "Class2" in output
        assert "Class3" in output
        assert "... (+2 more)" in output

    def test_format_with_complexity(self) -> None:
        """Test formatting result with complexity data."""
        from tree_sitter_analyzer_v2.formatters.summary_formatter import SummaryFormatter

        formatter = SummaryFormatter()

        result = {
            "file_path": "complex.py",
            "language": "python",
            "classes": [
                {
                    "name": "MyClass",
                    "methods": [
                        {"name": "method1", "complexity": 2},
                        {"name": "method2", "complexity": 4},
                    ],
                }
            ],
            "functions": [{"name": "func1", "complexity": 3}],
            "imports": [],
            "metadata": {},
        }

        output = formatter.format(result)

        # Should show complexity
        assert "Complexity:" in output
        assert "avg 3.0" in output  # (2+4+3)/3 = 3.0

    def test_complexity_level_low(self) -> None:
        """Test low complexity level."""
        from tree_sitter_analyzer_v2.formatters.summary_formatter import SummaryFormatter

        formatter = SummaryFormatter()

        level = formatter._get_complexity_level(2.5)
        assert level == "Low"

    def test_complexity_level_medium(self) -> None:
        """Test medium complexity level."""
        from tree_sitter_analyzer_v2.formatters.summary_formatter import SummaryFormatter

        formatter = SummaryFormatter()

        level = formatter._get_complexity_level(5.0)
        assert level == "Medium"

    def test_complexity_level_high(self) -> None:
        """Test high complexity level."""
        from tree_sitter_analyzer_v2.formatters.summary_formatter import SummaryFormatter

        formatter = SummaryFormatter()

        level = formatter._get_complexity_level(8.0)
        assert level == "High"
