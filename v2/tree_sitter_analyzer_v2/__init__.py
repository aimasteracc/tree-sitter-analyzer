"""
Tree-Sitter Analyzer v2 - Enterprise-grade code analysis for the AI era.

This is a complete rewrite of tree-sitter-analyzer focusing on:
- Simplicity: Clean architecture, no over-engineering
- Performance: Fast analysis with fd/ripgrep integration
- Token efficiency: TOON format for 70-80% reduction
- AI-first: Built for AI assistants (Claude, GPT, etc.)

Key Features:
- 17 language support
- MCP server integration
- CLI + API + MCP interfaces
- TOON + Markdown output formats
- Fast search with fd and ripgrep
"""

__version__ = "2.0.0-alpha.1"
__author__ = "aisheng.yu"

# Public API exports will be added as modules are implemented
__all__ = [
    "__version__",
    "__author__",
]
