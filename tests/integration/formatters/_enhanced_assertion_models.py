"""Shared models for enhanced format assertions."""

from dataclasses import dataclass
from typing import Any


@dataclass
class AssertionResult:
    """Result of an assertion with detailed information"""

    passed: bool
    message: str
    details: dict[str, Any]
    severity: str = "error"  # error, warning, info
    location: tuple[int, int] | None = None  # line, column
    suggestion: str | None = None


@dataclass
class FormatElement:
    """Represents a format element with metadata"""

    element_type: str
    name: str
    content: str
    line_number: int
    column_number: int
    attributes: dict[str, Any]
