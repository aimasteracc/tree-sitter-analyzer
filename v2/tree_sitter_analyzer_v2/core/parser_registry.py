"""
Parser Registry — Thin backward-compatible proxy.

Delegates to the unified LanguageRegistry. Existing code that imports from
this module will continue to work without changes.

Usage:
    from tree_sitter_analyzer_v2.core.parser_registry import get_parser, get_all_parsers
"""

from __future__ import annotations

# Re-export everything from the unified registry
from tree_sitter_analyzer_v2.core.language_registry import (
    CallExtractorProtocol as CallExtractorProtocol,
    LanguageParser as LanguageParser,
    get_all_parsers as get_all_parsers,
    get_ext_lang_map as get_ext_lang_map,
    get_parser as get_parser,
    register_parser as register_parser,
)

__all__ = [
    "LanguageParser",
    "register_parser",
    "get_parser",
    "get_all_parsers",
    "get_ext_lang_map",
]
