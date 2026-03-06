#!/usr/bin/env python3
"""
Plugin System for Multi-Language Code Analysis

This package provides a plugin-based architecture for extending
the tree-sitter analyzer with language-specific parsers and extractors.
"""

# Import base classes from base.py
from .base import (
    DefaultExtractor,
    DefaultLanguagePlugin,
    ElementExtractor,
    LanguagePlugin,
)

# Import new mixin classes for code reuse
from .extractor_mixin import (
    CacheManagementMixin,
    ElementExtractorBase,
    NodeTextExtractionMixin,
    NodeTraversalMixin,
)

__all__ = [
    # Base plugin classes
    "LanguagePlugin",
    "ElementExtractor",
    "DefaultExtractor",
    "DefaultLanguagePlugin",
    # Mixin classes for code reuse
    "CacheManagementMixin",
    "NodeTraversalMixin",
    "NodeTextExtractionMixin",
    "ElementExtractorBase",
]
