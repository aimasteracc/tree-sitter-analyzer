"""Import-light defaults shared by the search tools, their schemas and the CLI parser.

The CLI argument parser needs these values to render ``--help`` and to set
defaults. Importing them from ``symbol_search_tool`` pulled in the AST cache,
encoding detection, gitignore matching and asyncio (~1.2 s on Windows) just to
read three literals, and that cost landed on every ``--help`` and every argparse
error. Keep this module free of imports so the parser stays cheap.
"""

from __future__ import annotations

# Default result cap. 50 source-rich hits made symbol search ~8 KB/call; 15 is
# plenty to judge relevance. Shared by the CLI (`--symbol-search-limit`) and
# the tool schema — MCP/CLI parity (Codex P2 on #297).
DEFAULT_SYMBOL_SEARCH_LIMIT = 15

# Authoritative ``kind`` filter values. Must mirror exactly what
# ``_extract_symbols`` (tree_sitter_analyzer/_ast_extraction.py) writes into
# ``ast_symbol_rows`` — function/method/class/enum/variable/import/constant — plus
# the "any" no-filter default. Shared by the CLI (`--symbol-search-kind`
# choices) and the ``search`` facade public schema (#640).
SYMBOL_SEARCH_KINDS: tuple[str, ...] = (
    "function",
    "method",
    "class",
    "enum",
    "variable",
    "import",
    "constant",
    "any",
)

DEFAULT_TEXT_SEARCH_LIMIT = 100
MAX_TEXT_SEARCH_LIMIT = 1000
