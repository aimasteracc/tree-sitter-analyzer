"""Shared fixtures for formatter tests."""

import pytest

from tree_sitter_analyzer.models import AnalysisResult, Class, Function, Variable


@pytest.fixture
def sample_elements():
    """Create a list of sample CodeElements for formatter testing."""
    return [
        Class(
            name="MyClass",
            line_number=1,
            end_line=20,
        ),
        Function(
            name="my_function",
            line_number=25,
            end_line=30,
        ),
        Variable(
            name="my_variable",
            line_number=35,
        ),
    ]


@pytest.fixture
def sample_analysis_result(sample_elements):
    """Create a sample AnalysisResult for formatter testing."""
    return AnalysisResult(
        file_path="test.py",
        language="python",
        elements=sample_elements,
    )


@pytest.fixture
def empty_analysis_result():
    """Create an empty AnalysisResult for testing edge cases."""
    return AnalysisResult(
        file_path="empty.py",
        language="python",
        elements=[],
    )
