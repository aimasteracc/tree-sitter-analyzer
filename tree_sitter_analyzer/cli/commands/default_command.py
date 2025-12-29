#!/usr/bin/env python3
"""
Default Command

Handles default analysis when no specific command is specified.
"""

from ...output_manager import output_error, output_info
from .base_command import BaseCommand


class DefaultCommand(BaseCommand):
    """Default command that shows error when no specific command is given."""

    async def execute_async(self, language: str) -> int:
        """Execute default command - show error for missing options."""
        output_error("Please specify a query or --advanced option")
        output_info("")
        output_info("Usage examples:")
        output_info("  --query-key class        Extract class definitions")
        output_info("  --query-key method       Extract method definitions")
        output_info("  --advanced               Perform advanced analysis")
        output_info("  --table full             Output in table format")
        output_info("  --structure              Output detailed structure")
        output_info("  --summary                Display summary")
        output_info("")
        output_info("Examples:")
        output_info("  tree-sitter-analyzer file.java --query-key class --format json")
        output_info("  tree-sitter-analyzer file.java --advanced --format json")
        output_info("  tree-sitter-analyzer file.java --table json")
        return 1
