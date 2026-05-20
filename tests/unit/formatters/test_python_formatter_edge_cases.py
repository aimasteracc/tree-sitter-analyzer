"""
Edge case and error handling tests for Python table formatter.
Tests cover error conditions, boundary cases, and robustness scenarios.

Re-export aggregator — tests live in:
  - test_python_formatter_error_handling.py
  - test_python_formatter_format_methods.py
"""

from test_python_formatter_error_handling import (  # noqa: F401
    TestPythonFormatterBoundaryConditions,
    TestPythonFormatterDecoratorHandling,
    TestPythonFormatterDocstringHandling,
    TestPythonFormatterErrorHandling,
    TestPythonFormatterPerformanceEdgeCases,
    TestPythonFormatterSpecialCharacters,
    TestPythonFormatterTypeHandling,
)
from test_python_formatter_format_methods import (  # noqa: F401
    TestPythonFormatterClassMethodRow,
    TestPythonFormatterCompactTable,
    TestPythonFormatterCreateCompactSignature,
    TestPythonFormatterDecoratorsEdge,
    TestPythonFormatterFormatAdvanced,
    TestPythonFormatterFormatJsonError,
    TestPythonFormatterFormatPythonSignature,
    TestPythonFormatterFormatSummary,
    TestPythonFormatterFormatTableMethod,
    TestPythonFormatterFullTable,
    TestPythonFormatterSignatureCompact,
    TestPythonFormatterVisibilitySymbol,
)
