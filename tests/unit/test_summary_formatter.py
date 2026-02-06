"""Tests for SummaryFormatter."""

import pytest

from tree_sitter_analyzer_v2.formatters.summary_formatter import SummaryFormatter


class TestSummaryFormatter:
    """Tests for SummaryFormatter class."""

    def test_format_basic(self) -> None:
        """Test basic formatting."""
        formatter = SummaryFormatter()
        result = {
            "file_path": "/path/to/test.py",
            "language": "python",
            "classes": [],
            "functions": [],
            "imports": [],
        }
        output = formatter.format(result)
        
        assert "File: test.py" in output
        assert "Language: python" in output
        assert "Classes: 0" in output
        assert "Functions: 0" in output

    def test_format_with_classes(self) -> None:
        """Test formatting with classes."""
        formatter = SummaryFormatter()
        result = {
            "file_path": "test.py",
            "language": "python",
            "classes": [
                {"name": "ClassA", "methods": [{"name": "method1"}]},
                {"name": "ClassB", "methods": []},
            ],
            "functions": [],
            "imports": [],
        }
        output = formatter.format(result)
        
        assert "Classes: 2" in output
        assert "ClassA" in output
        assert "ClassB" in output
        assert "Methods: 1" in output

    def test_format_with_many_classes(self) -> None:
        """Test formatting with more than 3 classes."""
        formatter = SummaryFormatter()
        result = {
            "file_path": "test.py",
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
        }
        output = formatter.format(result)
        
        assert "Classes: 5" in output
        assert "+2 more" in output

    def test_format_with_functions(self) -> None:
        """Test formatting with functions."""
        formatter = SummaryFormatter()
        result = {
            "file_path": "test.py",
            "language": "python",
            "classes": [],
            "functions": [{"name": "func1"}, {"name": "func2"}],
            "imports": [],
        }
        output = formatter.format(result)
        
        assert "Functions: 2" in output

    def test_format_with_imports(self) -> None:
        """Test formatting with imports."""
        formatter = SummaryFormatter()
        result = {
            "file_path": "test.py",
            "language": "python",
            "classes": [],
            "functions": [],
            "imports": [{"module": "os"}, {"module": "sys"}],
        }
        output = formatter.format(result)
        
        assert "Imports: 2" in output

    def test_format_with_metadata(self) -> None:
        """Test formatting with line count metadata."""
        formatter = SummaryFormatter()
        result = {
            "file_path": "test.py",
            "language": "python",
            "classes": [],
            "functions": [],
            "imports": [],
            "metadata": {
                "total_lines": 100,
                "code_lines": 70,
                "comment_lines": 20,
                "blank_lines": 10,
            },
        }
        output = formatter.format(result)
        
        assert "Lines: 100" in output
        assert "Code: 70" in output
        assert "Comments: 20" in output
        assert "Blank: 10" in output

    def test_format_with_complexity(self) -> None:
        """Test formatting with complexity info."""
        formatter = SummaryFormatter()
        result = {
            "file_path": "test.py",
            "language": "python",
            "classes": [],
            "functions": [
                {"name": "func1", "complexity": 2},
                {"name": "func2", "complexity": 4},
            ],
            "imports": [],
        }
        output = formatter.format(result)
        
        assert "Complexity:" in output
        assert "avg" in output

    def test_format_with_method_complexity(self) -> None:
        """Test formatting with method complexity."""
        formatter = SummaryFormatter()
        result = {
            "file_path": "test.py",
            "language": "python",
            "classes": [
                {
                    "name": "MyClass",
                    "methods": [
                        {"name": "method1", "complexity": 10},
                        {"name": "method2", "complexity": 8},
                    ],
                }
            ],
            "functions": [],
            "imports": [],
        }
        output = formatter.format(result)
        
        assert "Complexity: High" in output

    def test_format_unknown_file_path(self) -> None:
        """Test formatting with missing file path."""
        formatter = SummaryFormatter()
        result = {
            "classes": [],
            "functions": [],
            "imports": [],
        }
        output = formatter.format(result)
        
        assert "File: unknown" in output

    def test_format_no_metadata_lines(self) -> None:
        """Test formatting without line count metadata."""
        formatter = SummaryFormatter()
        result = {
            "file_path": "test.py",
            "language": "python",
            "classes": [],
            "functions": [],
            "imports": [],
            "metadata": {"total_lines": 0},
        }
        output = formatter.format(result)
        
        # Should not include line count when total is 0
        assert "Lines:" not in output

    def test_format_no_complexity(self) -> None:
        """Test formatting without complexity info."""
        formatter = SummaryFormatter()
        result = {
            "file_path": "test.py",
            "language": "python",
            "classes": [],
            "functions": [{"name": "func1"}],  # No complexity
            "imports": [],
        }
        output = formatter.format(result)
        
        assert "Complexity: N/A" in output


class TestComplexityLevel:
    """Tests for complexity level calculation."""

    def test_low_complexity(self) -> None:
        """Test low complexity level."""
        formatter = SummaryFormatter()
        assert formatter._get_complexity_level(1.0) == "Low"
        assert formatter._get_complexity_level(2.0) == "Low"
        assert formatter._get_complexity_level(2.9) == "Low"

    def test_medium_complexity(self) -> None:
        """Test medium complexity level."""
        formatter = SummaryFormatter()
        assert formatter._get_complexity_level(3.0) == "Medium"
        assert formatter._get_complexity_level(5.0) == "Medium"
        assert formatter._get_complexity_level(6.9) == "Medium"

    def test_high_complexity(self) -> None:
        """Test high complexity level."""
        formatter = SummaryFormatter()
        assert formatter._get_complexity_level(7.0) == "High"
        assert formatter._get_complexity_level(10.0) == "High"
        assert formatter._get_complexity_level(20.0) == "High"
