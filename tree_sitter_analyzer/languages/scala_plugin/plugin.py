"""Scala Language Plugin — dispatch, parsing, and AnalysisResult assembly."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...core.request import AnalysisRequest
    from ...models import AnalysisResult

from ...plugins.base import ElementExtractor, LanguagePlugin
from ...utils import log_error
from ...utils.tree_sitter_compat import count_nodes_iterative
from .extractor import ScalaElementExtractor

__all__ = ["ScalaPlugin"]

_SCALA_ELEMENT_KEYS: tuple[str, ...] = (
    "functions",
    "classes",
    "variables",
    "imports",
    "packages",
    "comments",
    "annotations",
)


def _scala_empty_result(file_path: str, file_content: str) -> AnalysisResult:
    """Build an empty ``AnalysisResult`` when the tree-sitter language is missing."""
    from ...models import AnalysisResult

    return AnalysisResult(
        file_path=file_path,
        language="scala",
        # P1: splitlines() matches wc -l (split("\n") over-counts by 1
        # when file ends with trailing \n)
        line_count=len(file_content.splitlines()),
        elements=[],
        source_code=file_content,
    )


def _scala_error_result(file_path: str, exc: Exception) -> AnalysisResult:
    """Build the failure-path ``AnalysisResult`` used by the ``except`` arm."""
    from ...models import AnalysisResult

    return AnalysisResult(
        file_path=file_path,
        language="scala",
        line_count=0,
        elements=[],
        source_code="",
        error_message=str(exc),
        success=False,
    )


def _make_scala_parser(language: Any) -> Any:
    """Construct a ``tree_sitter.Parser`` bound to ``language`` across API shapes.

    Tree-sitter 0.20 used ``parser.set_language(lang)``; 0.21 added the
    ``parser.language`` property setter; 0.23 made the constructor accept
    the language directly. Probe each in order; fall back to the
    constructor form if neither attribute exists.
    """
    import tree_sitter

    parser = tree_sitter.Parser()
    if hasattr(parser, "set_language"):
        parser.set_language(language)
        return parser
    if hasattr(parser, "language"):
        parser.language = language
        return parser
    return tree_sitter.Parser(language)


def _flatten_scala_elements(elements_dict: dict[str, list[Any]]) -> list[Any]:
    """Concatenate per-kind element lists in the canonical Scala order."""
    flat: list[Any] = []
    for key in _SCALA_ELEMENT_KEYS:
        flat.extend(elements_dict.get(key, []))
    return flat


def _build_scala_elements_dict(
    extractor: ElementExtractor, tree: Any, source_code: str
) -> dict[str, Any]:
    """Delegate to ``extractor.extract_xxx`` for each element kind.

    Shared by ``ScalaPlugin.extract_elements`` (public API) and
    ``ScalaPlugin.analyze_file`` so neither has to call the other —
    ``analyze_file`` calling ``self.extract_elements()`` was flagged as
    hidden coupling by the plugin-architecture contract test.
    """
    return {
        "functions": extractor.extract_functions(tree, source_code),
        "classes": extractor.extract_classes(tree, source_code),
        "variables": extractor.extract_variables(tree, source_code),
        "imports": extractor.extract_imports(tree, source_code),
        "packages": extractor.extract_packages(tree, source_code),
        "comments": extractor.extract_comments(tree, source_code),  # type: ignore[attr-defined]
        "annotations": extractor.extract_annotations(tree, source_code),
    }


class ScalaPlugin(LanguagePlugin):
    """Scala language plugin implementation"""

    def __init__(self) -> None:
        """Initialize the Scala language plugin."""
        super().__init__()
        self.extractor = ScalaElementExtractor()
        self.language = "scala"
        self.supported_extensions = self.get_file_extensions()
        self._cached_language: Any | None = None

    def get_language_name(self) -> str:
        """Get the language name."""
        return "scala"

    def get_file_extensions(self) -> list[str]:
        """Get supported file extensions."""
        return [".scala", ".sc"]

    def create_extractor(self) -> ElementExtractor:
        """Create a new element extractor instance."""
        return ScalaElementExtractor()

    async def analyze_file(
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        """Analyze Scala code and return structured results.

        r37ed (dogfood): 85 lines → ~15 of orchestration. Per-phase helpers
        (``_scala_empty_result`` / ``_make_scala_parser`` / ``_build_scala_elements_dict``
        / ``_flatten_scala_elements`` / ``_scala_analysis_result`` / ``_scala_error_result``)
        own the individual steps; this body is just dispatch.
        """

        try:
            from ...encoding_utils import read_file_safe

            file_content, _detected_encoding = read_file_safe(file_path)

            language = self.get_tree_sitter_language()
            if language is None:
                return _scala_empty_result(file_path, file_content)

            parser = _make_scala_parser(language)
            tree = parser.parse(file_content.encode("utf-8"))
            extractor = self.create_extractor()
            try:
                elements_dict = _build_scala_elements_dict(
                    extractor, tree, file_content
                )
            except Exception as e:
                # Preserve extract_elements()'s graceful-degradation contract:
                # a failure inside one extract_xxx() call must still return a
                # successful, empty-elements AnalysisResult (correct
                # source_code/line_count), not the outer except's
                # success=False/empty-source error result (Codex #1158).
                log_error(f"Error extracting elements: {e}")
                elements_dict = {k: [] for k in _SCALA_ELEMENT_KEYS}
            return self._scala_analysis_result(
                file_path, file_content, tree, elements_dict
            )
        except Exception as e:
            log_error(f"Error analyzing Scala file {file_path}: {e}")
            return _scala_error_result(file_path, e)

    def _scala_analysis_result(
        self,
        file_path: str,
        file_content: str,
        tree: Any,
        elements_dict: dict[str, list[Any]],
    ) -> AnalysisResult:
        """Build the success-path ``AnalysisResult`` from parsed tree + elements."""
        from ...models import AnalysisResult

        all_elements = _flatten_scala_elements(elements_dict)
        node_count = (
            count_nodes_iterative(tree.root_node) if tree and tree.root_node else 0
        )
        packages = elements_dict.get("packages", [])
        package = packages[0] if packages else None
        return AnalysisResult(
            file_path=file_path,
            language="scala",
            # P1: splitlines() matches wc -l (split("\n") over-counts by 1
            # when file ends with trailing \n)
            line_count=len(file_content.splitlines()),
            elements=all_elements,
            node_count=node_count,
            source_code=file_content,
            package=package,
        )

    def _count_tree_nodes(self, node: Any) -> int:
        """Count all nodes in the subtree. Delegates to count_nodes_iterative."""
        if node is None:
            return 0
        return count_nodes_iterative(node)

    def get_tree_sitter_language(self) -> Any | None:
        """Get the tree-sitter language for Scala."""
        if self._cached_language is not None:
            return self._cached_language

        try:
            import tree_sitter
            import tree_sitter_scala

            caps_or_lang = tree_sitter_scala.language()

            if hasattr(caps_or_lang, "__class__") and "Language" in str(
                type(caps_or_lang)
            ):
                self._cached_language = caps_or_lang
                return self._cached_language

            try:
                self._cached_language = tree_sitter.Language(caps_or_lang)
            except Exception as e:
                log_error(f"Failed to create Language object: {e}")
                return None

            return self._cached_language
        except ImportError as e:
            log_error(f"tree-sitter-scala not available: {e}")
            return None
        except Exception as e:
            log_error(f"Failed to load tree-sitter language for Scala: {e}")
            return None

    def extract_elements(self, tree: Any | None, source_code: str) -> dict[str, Any]:
        """Extract all elements."""
        _empty: dict[str, Any] = {k: [] for k in _SCALA_ELEMENT_KEYS}
        if tree is None:
            return _empty
        try:
            extractor = self.create_extractor()
            return _build_scala_elements_dict(extractor, tree, source_code)
        except Exception as e:
            log_error(f"Error extracting elements: {e}")
            return _empty
