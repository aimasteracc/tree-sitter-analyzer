"""Formatter interface definitions — no imports from other formatters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models import CodeElement


class IFormatter(ABC):
    """Interface for code element formatters."""

    @staticmethod
    @abstractmethod
    def get_format_name() -> str:
        """Return the format name this formatter supports."""

    @abstractmethod
    def format(self, elements: list[CodeElement]) -> str:
        """Format a list of CodeElements into a string representation."""


class IStructureFormatter(ABC):
    """Interface for structure-based formatters (legacy compatibility)."""

    @abstractmethod
    def format_structure(self, structure_data: dict[str, Any]) -> str:
        """Format structure data dictionary into a string representation."""
