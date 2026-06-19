"""Formatter interface definitions — no imports from other formatters."""

from __future__ import annotations

from abc import ABC, abstractmethod

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
