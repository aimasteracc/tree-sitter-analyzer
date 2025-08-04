#!/usr/bin/env python3
"""
Default Command

Handles default analysis when no specific command is specified.
"""

from ...output_manager import output_error
from .base_command import BaseCommand


class DefaultCommand(BaseCommand):
    """Default command that shows error when no specific command is given."""

    async def execute_async(self, language: str) -> int:
        """Execute default command - show error for missing options."""
        output_error("Please specify a query or --advanced option")
        return 1
