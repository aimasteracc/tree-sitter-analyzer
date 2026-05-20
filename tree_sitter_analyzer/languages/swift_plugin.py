#!/usr/bin/env python3
"""
Swift Language Plugin

Provides Swift-specific parsing and element extraction functionality.
Supports imports, classes, structs, enums, protocols, extensions, functions,
initializers, and let/var properties.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..encoding_utils import read_file_safe
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_error
from ._swift_plugin_extractor import SwiftElementExtractor

if TYPE_CHECKING:
    from ..core.analysis_engine import AnalysisRequest
    from ..models import AnalysisResult


class SwiftPlugin(LanguagePlugin):
    """Swift language plugin implementation."""

    def __init__(self) -> None:
        """Initialize the Swift language plugin."""
        super().__init__()
        self.language = "swift"
        self.supported_extensions = self.get_file_extensions()
        self._cached_language: Any | None = None

    def get_language_name(self) -> str:
        """Get the language name."""
        return "swift"

    def get_file_extensions(self) -> list[str]:
        """Get supported file extensions."""
        return [".swift"]

    def create_extractor(self) -> ElementExtractor:
        """Create a new element extractor instance."""
        return SwiftElementExtractor()

    async def analyze_file(
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        try:
            from ..models import AnalysisResult as _AR

            file_content, _detected_encoding = read_file_safe(file_path)
            language = self.get_tree_sitter_language()
            if language is None:
                return _empty_analysis_result(file_path, file_content)

            tree = _parse_swift_source(language, file_content)
            extractor = self.create_extractor()
            elements: list[Any] = []
            elements.extend(extractor.extract_functions(tree, file_content))
            elements.extend(extractor.extract_classes(tree, file_content))
            elements.extend(extractor.extract_variables(tree, file_content))
            elements.extend(extractor.extract_imports(tree, file_content))
            return _AR(
                file_path=file_path,
                language="swift",
                line_count=len(file_content.splitlines()),
                elements=elements,
                node_count=_count_tree_nodes(tree.root_node),
                source_code=file_content,
            )
        except Exception as e:
            log_error(f"Error analyzing Swift file {file_path}: {e}")
            return _analysis_error_result(file_path, str(e))

    def get_tree_sitter_language(self) -> Any | None:
        """Get the tree-sitter language for Swift."""
        if self._cached_language is not None:
            return self._cached_language

        try:
            import tree_sitter
            import tree_sitter_swift

            caps_or_lang = tree_sitter_swift.language()
            if "Language" in str(type(caps_or_lang)):
                self._cached_language = caps_or_lang
            else:
                self._cached_language = tree_sitter.Language(caps_or_lang)
            return self._cached_language
        except ImportError as e:
            log_error(f"tree-sitter-swift not available: {e}")
            return None
        except Exception as e:
            log_error(f"Failed to load tree-sitter language for Swift: {e}")
            return None

    def extract_elements(self, tree: Any | None, source_code: str) -> dict[str, Any]:
        """Extract all supported Swift elements."""
        if tree is None:
            return _empty_elements()
        try:
            extractor = self.create_extractor()
            return {
                "functions": extractor.extract_functions(tree, source_code),
                "classes": extractor.extract_classes(tree, source_code),
                "variables": extractor.extract_variables(tree, source_code),
                "imports": extractor.extract_imports(tree, source_code),
            }
        except Exception as e:
            log_error(f"Error extracting Swift elements: {e}")
            return _empty_elements()

    def supports_file(self, file_path: str) -> bool:
        """Check if this plugin supports the given file."""
        return self.is_applicable(file_path)


def _empty_elements() -> dict[str, list[Any]]:
    return {"functions": [], "classes": [], "variables": [], "imports": []}


def _flatten_elements(elements: dict[str, list[Any]]) -> list[Any]:
    flattened: list[Any] = []
    for key in ("functions", "classes", "variables", "imports"):
        flattened.extend(elements.get(key, []))
    return flattened


def _empty_analysis_result(file_path: str, file_content: str) -> AnalysisResult:
    from ..models import AnalysisResult

    return AnalysisResult(
        file_path=file_path,
        language="swift",
        line_count=len(file_content.splitlines()),
        elements=[],
        source_code=file_content,
    )


def _parse_swift_source(language: Any, file_content: str) -> Any:
    import tree_sitter

    parser = tree_sitter.Parser()
    if hasattr(parser, "set_language"):
        parser.set_language(language)
    elif hasattr(parser, "language"):
        parser.language = language
    else:
        parser = tree_sitter.Parser(language)
    return parser.parse(file_content.encode("utf-8"))


def _analysis_result(
    file_path: str,
    file_content: str,
    tree: Any,
    elements_dict: dict[str, list[Any]],
) -> AnalysisResult:
    from ..models import AnalysisResult

    return AnalysisResult(
        file_path=file_path,
        language="swift",
        line_count=len(file_content.splitlines()),
        elements=_flatten_elements(elements_dict),
        node_count=_count_tree_nodes(tree.root_node),
        source_code=file_content,
    )


def _analysis_error_result(file_path: str, message: str) -> AnalysisResult:
    from ..models import AnalysisResult

    return AnalysisResult(
        file_path=file_path,
        language="swift",
        line_count=0,
        elements=[],
        source_code="",
        error_message=message,
        success=False,
    )


def _count_tree_nodes(node: Any) -> int:
    count = 1
    for child in getattr(node, "children", []):
        count += _count_tree_nodes(child)
    return count
