"""
Call Extractor Registry — Thin backward-compatible proxy.

Delegates to the unified LanguageRegistry. Existing code that imports from
this module will continue to work without changes.

Usage:
    from tree_sitter_analyzer_v2.core.call_extractor_registry import (
        get_call_extractor,
    )
"""

from __future__ import annotations

# Re-export everything from the unified registry
from tree_sitter_analyzer_v2.core.language_registry import (
    CallExtractorProtocol as CallExtractorProtocol,
    get_all_call_extractors as get_all_call_extractors,
    get_call_extractor as get_call_extractor,
    register_call_extractor as register_call_extractor,
)

__all__ = [
    "CallExtractorProtocol",
    "register_call_extractor",
    "get_call_extractor",
    "get_all_call_extractors",
]
