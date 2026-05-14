#!/usr/bin/env python3
"""Markdown Language Plugin — wrapper class and query definitions."""

from typing import TYPE_CHECKING, Optional

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
from ...utils.tree_sitter_compat import TreeSitterQueryCompat
from .extractor import MarkdownElementExtractor


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

    def get_language(self) -> str:
        """Get the language name for Markdown (legacy compatibility)"""
        return "markdown"

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[CodeElement]:
        """Extract functions from the tree (legacy compatibility)"""
        extractor = self.get_extractor()
        functions = extractor.extract_functions(tree, source_code)
        return [
            CodeElement(
                name=f.name,
                start_line=f.start_line,
                end_line=f.end_line,
                raw_text=f.raw_text,
                language=f.language,
            )
            for f in functions
        ]

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[CodeElement]:
        """Extract classes from the tree (legacy compatibility)"""
        extractor = self.get_extractor()
        classes = extractor.extract_classes(tree, source_code)
        return [
            CodeElement(
                name=c.name,
                start_line=c.start_line,
                end_line=c.end_line,
                raw_text=c.raw_text,
                language=c.language,
            )
            for c in classes
        ]

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[CodeElement]:
        """Extract variables from the tree (legacy compatibility)"""
        extractor = self.get_extractor()
        variables = extractor.extract_variables(tree, source_code)
        return [
            CodeElement(
                name=v.name,
                start_line=v.start_line,
                end_line=v.end_line,
                raw_text=v.raw_text,
                language=v.language,
            )
            for v in variables
        ]

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[CodeElement]:
        """Extract imports from the tree (legacy compatibility)"""
        extractor = self.get_extractor()
        imports = extractor.extract_imports(tree, source_code)
        return [
            CodeElement(
                name=i.name,
                start_line=i.start_line,
                end_line=i.end_line,
                raw_text=i.raw_text,
                language=i.language,
            )
            for i in imports
        ]

    def get_tree_sitter_language(self) -> Optional["tree_sitter.Language"]:
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
        """Analyze a Markdown file and return the analysis results."""
        if not TREE_SITTER_AVAILABLE:
            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                success=False,
                error_message="Tree-sitter library not available.",
            )

        language = self.get_tree_sitter_language()
        if not language:
            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                success=False,
                error_message="Could not load Markdown language for parsing.",
            )

        try:
            from ...encoding_utils import read_file_safe

            source_code, _ = read_file_safe(file_path)

            parser = tree_sitter.Parser()
            parser.language = language
            tree = parser.parse(source_code.encode("utf-8"))

            extractor = self.create_extractor()
            extractor.current_file = file_path  # Set current file for context

            elements: list[CodeElement] = []

            # Extract all element types using the markdown-specific extractor
            if isinstance(extractor, MarkdownElementExtractor):
                headers = extractor.extract_headers(tree, source_code)
                code_blocks = extractor.extract_code_blocks(tree, source_code)
                links = extractor.extract_links(tree, source_code)
                images = extractor.extract_images(tree, source_code)
                references = extractor.extract_references(tree, source_code)
                lists = extractor.extract_lists(tree, source_code)
                tables = extractor.extract_tables(tree, source_code)

                # Extract new element types
                blockquotes = extractor.extract_blockquotes(tree, source_code)
                horizontal_rules = extractor.extract_horizontal_rules(tree, source_code)
                html_elements = extractor.extract_html_elements(tree, source_code)
                text_formatting = extractor.extract_text_formatting(tree, source_code)
                footnotes = extractor.extract_footnotes(tree, source_code)
            else:
                # Fallback for base ElementExtractor
                headers = []
                code_blocks = []
                links = []
                images = []
                references = []
                lists = []
                tables = []
                blockquotes = []
                horizontal_rules = []
                html_elements = []
                text_formatting = []
                footnotes = []

            elements.extend(headers)
            elements.extend(code_blocks)
            elements.extend(links)
            elements.extend(images)
            elements.extend(references)
            elements.extend(lists)
            elements.extend(tables)
            elements.extend(blockquotes)
            elements.extend(horizontal_rules)
            elements.extend(html_elements)
            elements.extend(text_formatting)
            elements.extend(footnotes)

            def count_nodes(node: "tree_sitter.Node") -> int:
                count = 1
                for child in node.children:
                    count += count_nodes(child)
                return count

            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                success=True,
                elements=elements,
                line_count=len(source_code.splitlines()),
                node_count=count_nodes(tree.root_node),
            )
        except Exception as e:
            log_error(f"Error analyzing Markdown file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                success=False,
                error_message=str(e),
            )

    def execute_query(self, tree: "tree_sitter.Tree", query_name: str) -> dict:
        """Execute a specific query on the tree"""
        try:
            language = self.get_tree_sitter_language()
            if not language:
                return {"error": "Language not available"}

            # Import query definitions
            from ...queries.markdown import get_query

            try:
                query_string = get_query(query_name)
            except KeyError:
                return {"error": f"Unknown query: {query_name}"}

            # Use tree-sitter API with modern handling
            captures = TreeSitterQueryCompat.safe_execute_query(
                language, query_string, tree.root_node, fallback_result=[]
            )
            return {
                "captures": captures,
                "query": query_string,
                "matches": len(captures),
            }

        except Exception as e:
            log_error(f"Query execution failed: {e}")
            return {"error": str(e)}

    def extract_elements(self, tree: "tree_sitter.Tree", source_code: str) -> list:
        """Extract elements from source code using tree-sitter AST"""
        # CRITICAL: Always create a NEW extractor to avoid state pollution between calls
        extractor = self.create_extractor()
        elements = []

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

                # Sort by line number and element type for fully deterministic output
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

        return elements

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
        """Get Markdown element categories mapping query_key to node_types"""
        return {
            # Header categories (function-like)
            "function": ["atx_heading", "setext_heading"],
            "headers": ["atx_heading", "setext_heading"],
            "heading": ["atx_heading", "setext_heading"],
            # Code block categories (class-like)
            "class": ["fenced_code_block", "indented_code_block"],
            "code_blocks": ["fenced_code_block", "indented_code_block"],
            "code_block": ["fenced_code_block", "indented_code_block"],
            # Link and image categories (variable-like)
            "variable": [
                "inline",  # Contains links and images
                "link",
                "autolink",
                "reference_link",
                "image",
            ],
            "links": [
                "inline",  # Contains inline links
                "link",
                "autolink",
                "reference_link",
            ],
            "link": ["inline", "link", "autolink", "reference_link"],
            "images": [
                "inline",  # Contains inline images
                "image",
            ],
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
            "html_blocks": [
                "html_block",
                "inline",  # Contains inline HTML
            ],
            "html_block": ["html_block", "inline"],
            "html": ["html_block", "inline"],
            # Text formatting categories
            "emphasis": ["inline"],  # Contains emphasis elements
            "formatting": ["inline"],
            "text_formatting": ["inline"],
            "inline_code": ["inline"],
            "strikethrough": ["inline"],
            # Footnote categories
            "footnotes": [
                "inline",  # Contains footnote references
                "paragraph",  # Contains footnote definitions
            ],
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
