#!/usr/bin/env python3
"""Markdown Language Plugin — wrapper class and query definitions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

    from ...core.analysis_engine import AnalysisRequest
    from ...models import AnalysisResult

try:
    import tree_sitter

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from ...models import AnalysisResult, CodeElement
from ...plugins.base import ElementExtractor, LanguagePlugin
from ...utils import log_error
from .extractor import MarkdownElementExtractor

# Canonical query-key → node-types mapping for Markdown.
#
# r37et (dogfood): lifted from ``MarkdownPlugin.get_element_categories`` so the
# 89-line literal isn't re-created on every call and so an audit of the
# supported query keys reads as plain data. The method now returns a defensive
# copy of this dict (callers that mutate must not poison the next call).
#
# Categories are grouped by "shape" alignment with the cross-language
# vocabulary used by AnalysisResult — ``function`` = headings, ``class`` =
# code blocks, ``variable`` = links/images, ``import`` = link reference
# definitions. The plural / singular / domain aliases (``headers`` /
# ``heading``, ``code_blocks`` / ``code_block``, etc.) keep CLI/MCP callers
# from having to remember the canonical spelling.
_MARKDOWN_ELEMENT_CATEGORIES: dict[str, list[str]] = {
    # Header categories (function-like)
    "function": ["atx_heading", "setext_heading"],
    "headers": ["atx_heading", "setext_heading"],
    "heading": ["atx_heading", "setext_heading"],
    # Code block categories (class-like)
    "class": ["fenced_code_block", "indented_code_block"],
    "code_blocks": ["fenced_code_block", "indented_code_block"],
    "code_block": ["fenced_code_block", "indented_code_block"],
    # Link and image categories (variable-like)
    "variable": ["inline", "link", "autolink", "reference_link", "image"],
    "links": ["inline", "link", "autolink", "reference_link"],
    "link": ["inline", "link", "autolink", "reference_link"],
    "images": ["inline", "image"],
    "image": ["inline", "image"],
    # Reference categories (import-like)
    "import": ["link_reference_definition"],
    "references": ["link_reference_definition"],
    "reference": ["link_reference_definition"],
    # List categories
    "lists": ["list", "list_item"],
    "list": ["list", "list_item"],
    "task_lists": ["list", "list_item"],
    # Table categories
    "tables": ["pipe_table", "table"],
    "table": ["pipe_table", "table"],
    # Content structure categories
    "blockquotes": ["block_quote"],
    "blockquote": ["block_quote"],
    "horizontal_rules": ["thematic_break"],
    "horizontal_rule": ["thematic_break"],
    # HTML categories
    "html_blocks": ["html_block", "inline"],
    "html_block": ["html_block", "inline"],
    "html": ["html_block", "inline"],
    # Text formatting categories
    "emphasis": ["inline"],
    "formatting": ["inline"],
    "text_formatting": ["inline"],
    "inline_code": ["inline"],
    "strikethrough": ["inline"],
    # Footnote categories
    "footnotes": ["inline", "paragraph"],
    "footnote": ["inline", "paragraph"],
    # Comprehensive categories
    "all_elements": [
        "atx_heading",
        "setext_heading",
        "fenced_code_block",
        "indented_code_block",
        "inline",
        "link",
        "autolink",
        "reference_link",
        "image",
        "link_reference_definition",
        "list",
        "list_item",
        "pipe_table",
        "table",
        "block_quote",
        "thematic_break",
        "html_block",
        "paragraph",
    ],
    "text_content": ["atx_heading", "setext_heading", "inline", "paragraph"],
}


class MarkdownPlugin(LanguagePlugin):
    """Markdown language plugin for the tree-sitter analyzer"""

    def __init__(self) -> None:
        """Initialize the Markdown plugin"""
        super().__init__()
        self._language_cache: tree_sitter.Language | None = None
        self._extractor: MarkdownElementExtractor = MarkdownElementExtractor()

        # Legacy compatibility attributes for tests
        self.language = "markdown"
        self.extractor = self._extractor

    def get_language_name(self) -> str:
        """Return the name of the programming language this plugin supports"""
        return "markdown"

    def get_file_extensions(self) -> list[str]:
        """Return list of file extensions this plugin supports"""
        return [".md", ".markdown", ".mdown", ".mkd", ".mkdn", ".mdx"]

    def create_extractor(self) -> ElementExtractor:
        """Create and return a NEW element extractor for this language (avoid state pollution)"""
        return MarkdownElementExtractor()

    def get_extractor(self) -> ElementExtractor:
        """Get the cached extractor instance, creating it if necessary"""
        return self._extractor

    def get_tree_sitter_language(self) -> tree_sitter.Language | None:
        """Get the Tree-sitter language object for Markdown"""
        if self._language_cache is None:
            try:
                # Import markdown bindings first so a failure there doesn't require importing
                # the core tree_sitter module (helps avoid unraisable finalizer issues in tests).
                import tree_sitter_markdown as tsmarkdown

                language_capsule = tsmarkdown.language()

                import tree_sitter

                self._language_cache = tree_sitter.Language(language_capsule)
            except ImportError:
                log_error("tree-sitter-markdown not available")
                return None
            except Exception as e:
                log_error(f"Failed to load Markdown language: {e}")
                return None
        return self._language_cache

    def get_supported_queries(self) -> list[str]:
        """Get list of supported query names for this language"""
        return [
            "headers",
            "code_blocks",
            "links",
            "images",
            "lists",
            "tables",
            "blockquotes",
            "emphasis",
            "inline_code",
            "references",
            "task_lists",
            "horizontal_rules",
            "html_blocks",
            "strikethrough",
            "footnotes",
            "text_content",
            "all_elements",
        ]

    def is_applicable(self, file_path: str) -> bool:
        """Check if this plugin is applicable for the given file"""
        return any(
            file_path.lower().endswith(ext.lower())
            for ext in self.get_file_extensions()
        )

    def get_plugin_info(self) -> dict:
        """Get information about this plugin"""
        return {
            "name": "Markdown Plugin",
            "language": self.get_language_name(),
            "extensions": self.get_file_extensions(),
            "version": "1.0.0",
            "supported_queries": self.get_supported_queries(),
            "features": [
                "ATX headers (# ## ###)",
                "Setext headers (underlined)",
                "Fenced code blocks",
                "Indented code blocks",
                "Inline code spans",
                "Inline links",
                "Reference links",
                "Autolinks",
                "Email autolinks",
                "Images (inline and reference)",
                "Lists (ordered and unordered)",
                "Task lists (checkboxes)",
                "Blockquotes",
                "Tables",
                "Emphasis and strong emphasis",
                "Strikethrough text",
                "Horizontal rules",
                "HTML blocks and inline HTML",
                "Footnotes (references and definitions)",
                "Reference definitions",
                "Text formatting extraction",
                "CommonMark compliance",
            ],
        }

    async def analyze_file(
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        """Analyze a Markdown file and return the analysis results.

        r37da (dogfood): 101 lines → ~30 lines of phase dispatch.
        Sub-helpers ``_check_markdown_runtime``, ``_collect_markdown_elements``
        own the precondition gating and the per-category extraction batch.
        Output ``AnalysisResult`` shape is preserved byte-for-byte.
        """
        precheck_error = self._check_markdown_runtime(file_path)
        if precheck_error is not None:
            return precheck_error

        language = self.get_tree_sitter_language()
        if language is None:
            # _check_markdown_runtime above should have caught this, but
            # narrow for mypy + defence-in-depth.
            return AnalysisResult(
                file_path=file_path,
                language="markdown",
                elements=[],
                line_count=0,
                source_code="",
                node_count=0,
                query_results={},
            )
        try:
            from ...encoding_utils import read_file_safe

            source_code, _ = read_file_safe(file_path)
            parser = tree_sitter.Parser()
            parser.language = language
            tree = parser.parse(source_code.encode("utf-8"))

            extractor = self.create_extractor()
            extractor.current_file = file_path  # Set current file for context
            elements = self._collect_markdown_elements(extractor, tree, source_code)

            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                success=True,
                elements=elements,
                line_count=len(source_code.splitlines()),
                node_count=_count_markdown_nodes(tree.root_node),
            )
        except Exception as e:
            log_error(f"Error analyzing Markdown file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                success=False,
                error_message=str(e),
            )

    def _check_markdown_runtime(self, file_path: str) -> AnalysisResult | None:
        """Return a failure result when tree-sitter / language is unavailable.

        Returns ``None`` on the happy path so the caller can proceed with
        parsing. Splitting this out keeps ``analyze_file`` focused on the
        success flow.
        """
        if not TREE_SITTER_AVAILABLE:
            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                success=False,
                error_message="Tree-sitter library not available.",
            )
        if not self.get_tree_sitter_language():
            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                success=False,
                error_message="Could not load Markdown language for parsing.",
            )
        return None

    @staticmethod
    def _collect_markdown_elements(
        extractor: Any,
        tree: tree_sitter.Tree,
        source_code: str,
    ) -> list[CodeElement]:
        """Run every markdown-specific extractor and concatenate results.

        The list order matches the prior in-line block so existing
        consumers that index by position keep working: headers,
        code_blocks, links, images, references, lists, tables,
        blockquotes, horizontal_rules, html_elements, text_formatting,
        footnotes.
        """
        if not isinstance(extractor, MarkdownElementExtractor):
            return []
        elements: list[CodeElement] = []
        elements.extend(extractor.extract_headers(tree, source_code))
        elements.extend(extractor.extract_code_blocks(tree, source_code))
        elements.extend(extractor.extract_links(tree, source_code))
        elements.extend(extractor.extract_images(tree, source_code))
        elements.extend(extractor.extract_references(tree, source_code))
        elements.extend(extractor.extract_lists(tree, source_code))
        elements.extend(extractor.extract_tables(tree, source_code))
        elements.extend(extractor.extract_blockquotes(tree, source_code))
        elements.extend(extractor.extract_horizontal_rules(tree, source_code))
        elements.extend(extractor.extract_html_elements(tree, source_code))
        elements.extend(extractor.extract_text_formatting(tree, source_code))
        elements.extend(extractor.extract_footnotes(tree, source_code))
        return elements

    def extract_elements(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> dict[str, list[Any]]:
        extractor = self.create_extractor()
        elements: list[Any] = []

        try:
            if isinstance(extractor, MarkdownElementExtractor):
                elements.extend(extractor.extract_headers(tree, source_code))
                elements.extend(extractor.extract_code_blocks(tree, source_code))
                elements.extend(extractor.extract_links(tree, source_code))
                elements.extend(extractor.extract_images(tree, source_code))
                elements.extend(extractor.extract_references(tree, source_code))
                elements.extend(extractor.extract_lists(tree, source_code))
                elements.extend(extractor.extract_tables(tree, source_code))
                elements.extend(extractor.extract_blockquotes(tree, source_code))
                elements.extend(extractor.extract_horizontal_rules(tree, source_code))
                elements.extend(extractor.extract_html_elements(tree, source_code))
                elements.extend(extractor.extract_text_formatting(tree, source_code))
                elements.extend(extractor.extract_footnotes(tree, source_code))

                elements.sort(
                    key=lambda e: (
                        getattr(e, "start_line", 0),
                        getattr(e, "end_line", 0),
                        getattr(e, "element_type", ""),
                        getattr(e, "name", ""),
                    )
                )
        except Exception as e:
            log_error(f"Failed to extract elements: {e}")

        return {"elements": elements}

    def execute_query_strategy(
        self, query_key: str | None, language: str
    ) -> str | None:
        """Execute query strategy for Markdown language"""
        if not query_key:
            return None

        # Use markdown-specific element categories instead of base queries
        element_categories = self.get_element_categories()
        if query_key in element_categories:
            # Return a simple query string for the category
            node_types = element_categories[query_key]
            if node_types:
                # Create a basic query for the first node type
                return f"({node_types[0]}) @{query_key}"

        # Fallback to base implementation
        queries = self.get_queries()
        return queries.get(query_key) if queries else None

    def get_element_categories(self) -> dict[str, list[str]]:
        """Get Markdown element categories mapping query_key to node_types.

        r37et (dogfood): the 89-line literal moved to module-level
        ``_MARKDOWN_ELEMENT_CATEGORIES``. Each call now returns a defensive
        copy so callers that mutate the result don't poison the next call.
        """
        return {k: list(v) for k, v in _MARKDOWN_ELEMENT_CATEGORIES.items()}


def _count_markdown_nodes(node: tree_sitter.Node) -> int:
    """Return the total number of AST nodes under ``node`` (inclusive).

    r37da (dogfood): lifted from a closure inside ``analyze_file`` so the
    method itself stays a thin phase dispatcher. Recursion is iterative-
    friendly (each call counts the node plus its subtree), matching the
    original semantics.
    """
    count = 1
    for child in node.children:
        count += _count_markdown_nodes(child)
    return count
