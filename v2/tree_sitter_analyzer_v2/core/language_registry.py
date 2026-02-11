"""
Unified Language Registry — single registry for parsers and call extractors.

Consolidates parser_registry and call_extractor_registry into one module,
eliminating the core→graph layer violation and reducing global mutable state.

Usage:
    from tree_sitter_analyzer_v2.core.language_registry import (
        get_parser,
        get_all_parsers,
        get_ext_lang_map,
        get_call_extractor,
        get_all_call_extractors,
    )
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Protocol

from tree_sitter_analyzer_v2.core.types import LanguageParseResult

logger = logging.getLogger(__name__)


# ── Protocols ──


class LanguageParser(Protocol):
    """Protocol that all language parsers must satisfy."""

    def parse(self, content: str, file_path: str = "") -> LanguageParseResult: ...


class CallExtractorProtocol(Protocol):
    """Protocol that all call extractors must satisfy."""

    def extract_calls(self, ast_node: Any) -> list[dict[str, Any]]: ...
    def get_call_node_types(self) -> list[str]: ...


# ── Unified Registry ──


class LanguageRegistry:
    """Unified registry for language parsers and call extractors.

    Thread-safe. Supports lazy auto-registration on first access.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._parsers: dict[str, LanguageParser] = {}
        self._ext_lang_map: dict[str, str] = {}
        self._call_extractors: dict[str, CallExtractorProtocol] = {}
        self._parsers_loaded = False
        self._extractors_loaded = False

    # ── Parser registration ──

    def register_parser(
        self,
        language: str,
        parser: LanguageParser,
        extensions: list[str] | None = None,
    ) -> None:
        """Register a language parser."""
        with self._lock:
            self._parsers[language] = parser
            logger.debug(
                "Registered parser for '%s'%s",
                language,
                f" (extensions: {extensions})" if extensions else "",
            )
            if extensions:
                for ext in extensions:
                    self._ext_lang_map[ext.lower()] = language

    def get_parser(self, language: str) -> LanguageParser | None:
        """Get a registered parser by language name."""
        self._ensure_parsers_loaded()
        return self._parsers.get(language)

    def get_all_parsers(self) -> dict[str, LanguageParser]:
        """Get all registered parsers."""
        self._ensure_parsers_loaded()
        return dict(self._parsers)

    def get_ext_lang_map(self) -> dict[str, str]:
        """Get extension → language mapping from all registered parsers."""
        self._ensure_parsers_loaded()
        return dict(self._ext_lang_map)

    # ── Call extractor registration ──

    def register_call_extractor(
        self,
        language: str,
        extractor: CallExtractorProtocol,
    ) -> None:
        """Register a call extractor for a language."""
        with self._lock:
            self._call_extractors[language] = extractor
            logger.debug("Registered call extractor for '%s'", language)

    def get_call_extractor(self, language: str) -> CallExtractorProtocol | None:
        """Get a registered call extractor by language name."""
        self._ensure_extractors_loaded()
        return self._call_extractors.get(language)

    def get_all_call_extractors(self) -> dict[str, CallExtractorProtocol]:
        """Get all registered call extractors."""
        self._ensure_extractors_loaded()
        return dict(self._call_extractors)

    # ── Lazy loading ──

    def _ensure_parsers_loaded(self) -> None:
        """Lazy-load built-in parsers on first access (thread-safe)."""
        if self._parsers_loaded:
            return
        with self._lock:
            if self._parsers_loaded:
                return
            self._parsers_loaded = True
            self._register_builtin_parsers()

    def _ensure_extractors_loaded(self) -> None:
        """Lazy-load built-in call extractors on first access (thread-safe)."""
        if self._extractors_loaded:
            return
        with self._lock:
            if self._extractors_loaded:
                return
            self._extractors_loaded = True
            self._register_builtin_extractors()

    def _register_builtin_parsers(self) -> None:
        """Register all built-in language parsers."""
        try:
            from tree_sitter_analyzer_v2.languages.python_parser import PythonParser
            self._parsers["python"] = PythonParser()
            for ext in [".py", ".pyw"]:
                self._ext_lang_map[ext] = "python"
        except ImportError:
            pass

        try:
            from tree_sitter_analyzer_v2.languages.java_parser import JavaParser
            self._parsers["java"] = JavaParser()
            self._ext_lang_map[".java"] = "java"
        except ImportError:
            pass

        try:
            from tree_sitter_analyzer_v2.languages.typescript_parser import TypeScriptParser
            ts_parser = TypeScriptParser()
            self._parsers["typescript"] = ts_parser
            self._parsers["javascript"] = ts_parser
            for ext in [".ts", ".tsx"]:
                self._ext_lang_map[ext] = "typescript"
            for ext in [".js", ".jsx", ".mjs", ".cjs"]:
                self._ext_lang_map[ext] = "javascript"
        except ImportError:
            pass

        # Register profile-driven languages (Go, Rust, C, C++)
        self._register_profile_languages()

    def _register_profile_languages(self) -> None:
        """Register languages using the data-driven LanguageProfile system."""
        try:
            from tree_sitter_analyzer_v2.languages.generic_parser import GenericLanguageParser
            from tree_sitter_analyzer_v2.languages.profiles import ALL_PROFILES

            for lang_name, profile in ALL_PROFILES.items():
                try:
                    parser = GenericLanguageParser(profile)
                    self._parsers[lang_name] = parser
                    for ext in profile.extensions:
                        self._ext_lang_map[ext] = lang_name
                    logger.debug("Registered profile-driven parser: %s", lang_name)
                except Exception:
                    logger.debug("Failed to register %s (tree-sitter lib missing?)", lang_name)
        except ImportError:
            logger.debug("generic_parser or profiles not available")

    def _register_builtin_extractors(self) -> None:
        """Register all built-in call extractors.

        Uses the graph module's own registration entry-point to maintain
        proper dependency direction: graph → core (not core → graph).
        """
        try:
            from tree_sitter_analyzer_v2.graph.extractors import (
                JavaCallExtractor,
                PythonCallExtractor,
            )
            self._call_extractors["python"] = PythonCallExtractor()
            self._call_extractors["java"] = JavaCallExtractor()
        except ImportError:
            logger.debug("graph module not available; no call extractors registered")


# ── Module-level singleton ──

_registry: LanguageRegistry | None = None
_singleton_lock = threading.Lock()


def _get_registry() -> LanguageRegistry:
    """Get (or create) the module-level singleton registry."""
    global _registry
    if _registry is None:
        with _singleton_lock:
            if _registry is None:
                _registry = LanguageRegistry()
    return _registry


# ── Public API (backward-compatible free functions) ──


def register_parser(
    language: str,
    parser: LanguageParser,
    extensions: list[str] | None = None,
) -> None:
    """Register a language parser."""
    _get_registry().register_parser(language, parser, extensions)


def get_parser(language: str) -> LanguageParser | None:
    """Get a registered parser by language name."""
    return _get_registry().get_parser(language)


def get_all_parsers() -> dict[str, LanguageParser]:
    """Get all registered parsers."""
    return _get_registry().get_all_parsers()


def get_ext_lang_map() -> dict[str, str]:
    """Get extension → language mapping."""
    return _get_registry().get_ext_lang_map()


def register_call_extractor(
    language: str,
    extractor: CallExtractorProtocol,
) -> None:
    """Register a call extractor for a language."""
    _get_registry().register_call_extractor(language, extractor)


def get_call_extractor(language: str) -> CallExtractorProtocol | None:
    """Get a registered call extractor by language name."""
    return _get_registry().get_call_extractor(language)


def get_all_call_extractors() -> dict[str, CallExtractorProtocol]:
    """Get all registered call extractors."""
    return _get_registry().get_all_call_extractors()
