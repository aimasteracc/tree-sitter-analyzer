#!/usr/bin/env python3
"""
Dead Code Detection Module.

Identifies unused code elements:
- Unused functions/methods
- Unused classes
- Unused imports
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DeadCodeType(Enum):
    """Type of dead code issue."""

    UNUSED_FUNCTION = "unused_function"
    UNUSED_CLASS = "unused_class"
    UNUSED_IMPORT = "unused_import"


@dataclass(frozen=True)
class DeadCodeIssue:
    """A dead code issue."""

    name: str
    type: DeadCodeType
    file: str
    line: int
    confidence: float  # 0.0 to 1.0
    reason: str = ""

    def __str__(self) -> str:
        return f"{self.type.value}:{self.name}@{self.file}:{self.line}"


@dataclass
class DeadCodeReport:
    """Report of dead code analysis."""

    issues: list[DeadCodeIssue] = field(default_factory=list)
    files_scanned: int = 0
    total_definitions: int = 0
    total_references: int = 0

    @property
    def dead_count(self) -> int:
        return len(self.issues)

    @property
    def unused_functions(self) -> list[DeadCodeIssue]:
        return [i for i in self.issues if i.type == DeadCodeType.UNUSED_FUNCTION]

    @property
    def unused_classes(self) -> list[DeadCodeIssue]:
        return [i for i in self.issues if i.type == DeadCodeType.UNUSED_CLASS]

    @property
    def unused_imports(self) -> list[DeadCodeIssue]:
        return [i for i in self.issues if i.type == DeadCodeType.UNUSED_IMPORT]

    def add_issue(self, issue: DeadCodeIssue) -> None:
        self.issues.append(issue)


# Entry point patterns (symbols that should never be flagged as dead)
ENTRY_POINT_PATTERNS: list[str] = [
    "main",
    "test_",
    "Test",
    "setup",
    "teardown",
    "pytest_",
    "unittest_",
]

# Public API patterns (symbols that are part of public API)
PUBLIC_API_PATTERNS: list[str] = [
    "__all__",
]


def is_entry_point(symbol_name: str, file_path: str | None = None) -> bool:
    """Check if a symbol is an entry point that should not be flagged as dead."""
    name_lower = symbol_name.lower()

    # Check against entry point patterns
    for pattern in ENTRY_POINT_PATTERNS:
        if pattern.lower() in name_lower:
            return True

    # Check file path for test files
    if file_path:
        path_lower = file_path.lower()
        if "test" in path_lower or "tests" in path_lower:
            return True

    return False


def is_public_api(symbol_name: str) -> bool:
    """Check if a symbol is part of public API."""
    # Check against known public API patterns first (handles __all__)
    for pattern in PUBLIC_API_PATTERNS:
        if pattern in symbol_name:
            return True

    # Public symbols typically don't start with underscore (except dunder methods)
    if symbol_name.startswith("_") and not (
        symbol_name.startswith("__") and symbol_name.endswith("__")
    ):
        return False

    return True


def is_excluded_method(
    symbol_name: str,
    decorators: list[str] | None = None,
    is_abstract: bool = False,
) -> bool:
    """Check if a method should be excluded from dead code analysis.

    Args:
        symbol_name: Name of the method/function
        decorators: List of decorators applied to the method
        is_abstract: Whether the method is abstract

    Returns:
        True if the method should be excluded (not flagged as dead)
    """
    if decorators is None:
        decorators = []

    # Abstract methods must be implemented by subclasses
    if is_abstract:
        return True

    # Common decorators that indicate external use or test code
    excluded_decorators = [
        "@abstractmethod",
        "@staticmethod",
        "@classmethod",
        "@property",
        "@setter",
        "@deleter",
        "@pytest.fixture",
        "@pytest.mark",
        "@unittest.mock",
        "@app.route",  # Flask routes
        "@api.",  # FastAPI decorators
        "@command",  # Click commands
        "@test",
        "@Test",
    ]

    for decorator in decorators:
        for excluded in excluded_decorators:
            if excluded.lower() in decorator.lower():
                return True

    return False


def is_exported_symbol(symbol_name: str, exports: list[str] | None = None) -> bool:
    """Check if a symbol is explicitly exported.

    Args:
        symbol_name: Name of the symbol
        exports: List of exported symbols (e.g., from __all__ or export statements)

    Returns:
        True if the symbol is in the exports list
    """
    if exports is None:
        return False

    return symbol_name in exports


def is_test_file(file_path: str) -> bool:
    """Check if a file is a test file.

    Args:
        file_path: Path to the file

    Returns:
        True if the file appears to be a test file
    """
    path_lower = file_path.lower()
    test_indicators = [
        "/test/",
        "/tests/",
        "\\test\\",
        "\\tests\\",
        "test_",
        "_test.",
        "conftest.py",
    ]
    return any(indicator in path_lower for indicator in test_indicators)
