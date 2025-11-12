"""
Test fixtures package.

This package provides reusable test utilities, helpers, and data generators
for comprehensive testing of the tree-sitter-analyzer codebase.

Modules:
    coverage_helpers: Utilities for measuring and improving test coverage
    data_generators: Generators for creating realistic test data
    assertion_helpers: Custom assertion functions for complex validations

Usage:
    from tests.fixtures import coverage_helpers, data_generators, assertion_helpers
    
    # Create mock data
    node = coverage_helpers.create_mock_node("function_definition")
    
    # Generate test code
    code = data_generators.generate_python_function("my_func")
    
    # Use custom assertions
    assertion_helpers.assert_analysis_result_valid(result)
"""

from __future__ import annotations

# Import submodules for easier access
from . import assertion_helpers, coverage_helpers, data_generators

__all__ = [
    "assertion_helpers",
    "coverage_helpers",
    "data_generators",
]
