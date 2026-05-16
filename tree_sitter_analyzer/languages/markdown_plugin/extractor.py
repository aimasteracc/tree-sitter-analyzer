#!/usr/bin/env python3
"""
Markdown Language Plugin

Enhanced Markdown-specific parsing and element extraction functionality.
Provides comprehensive support for Markdown elements including headers,
links, code blocks, lists, tables, and other structural elements.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

try:
    import tree_sitter

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from ...encoding_utils import extract_text_slice, safe_encode
from ...models import Class as ModelClass
from ...models import CodeElement
from ...models import Function as ModelFunction
from ...models import Import as ModelImport
from ...models import Variable as ModelVariable
from ...plugins.base import ElementExtractor
from ...utils import log_debug, log_error
from . import misc_extractor as _misc
from .link_image_extractor import (
    extract_md_images as _extract_md_images_standalone,
)
from .link_image_extractor import (
    extract_md_link_reference_definitions as _extract_md_link_refs_standalone,
)
from .link_image_extractor import (
    extract_md_links as _extract_md_links_standalone,
)


# Section: imports and module configuration
# Section: main class definition
# Section: helper functions
# Section: data processing methods
# Section: output formatting methods
# Section: validation and error handling
# Section: module imports and setup
# Section: class definitions
# Section: public API methods
# Section: internal helper methods
# Section: data processing pipeline
# Section: output formatting
# Section: error handling
class MarkdownElement(CodeElement):
    """Markdown-specific code element"""

    def __init__(
        self,
        name: str,
        start_line: int,
        end_line: int,
        raw_text: str,
        language: str = "markdown",
        element_type: str = "markdown",
        level: int | None = None,
        url: str | None = None,
        alt_text: str | None = None,
        title: str | None = None,
        language_info: str | None = None,
        is_checked: bool | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language=language,
            **kwargs,
        )
        self.element_type = element_type
        self.level = level  # For headers (1-6)
        self.url = url  # For links and images
        self.alt_text = alt_text  # For images
        self.title = title  # For links and images
        self.language_info = language_info  # For code blocks
        self.is_checked = is_checked  # For task list items

        # Additional attributes used by formatters
        self.text: str | None = None  # Text content
        self.type: str | None = None  # Element type for formatters
        self.line_count: int | None = None  # For code blocks
        self.alt: str | None = None  # Alternative text for images
        self.list_type: str | None = None  # For lists (ordered/unordered/task)
        self.item_count: int | None = None  # For lists
        self.row_count: int | None = None  # For tables
        self.column_count: int | None = None  # For tables


class MarkdownElementExtractor(ElementExtractor):
    """Markdown-specific element extractor with comprehensive feature support"""

    def __init__(self) -> None:
        """Initialize the Markdown element extractor."""
        self.current_file: str = ""
        self.source_code: str = ""
        self.content_lines: list[str] = []

        # Performance optimization caches - cleared for each extraction
        # Use position-based keys (start_byte, end_byte) for deterministic caching
        self._node_text_cache: dict[tuple[int, int], str] = {}
        self._processed_nodes: set[tuple[int, int]] = set()
        self._element_cache: dict[tuple[tuple[int, int], str], Any] = {}
        self._file_encoding: str | None = None

        # Extraction tracking - must be reset for each file
        self._extracted_links: set[str] = set()
        self._extracted_images: set[tuple[str, str]] = set()

    # Extract elements from AST: extract_functions
    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelFunction]:
        """Extract Markdown elements (headers act as 'functions')"""
        headers = self.extract_headers(tree, source_code)
        functions = []
        for header in headers:
            func = ModelFunction(
                name=header.name,
                start_line=header.start_line,
                end_line=header.end_line,
                raw_text=header.raw_text,
                language=header.language,
            )
            functions.append(func)
        return functions

    # Extract elements from AST: extract_classes
    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelClass]:
        """Extract Markdown sections (code blocks act as 'classes')"""
        code_blocks = self.extract_code_blocks(tree, source_code)
        classes = []
        for block in code_blocks:
            cls = ModelClass(
                name=block.name,
                start_line=block.start_line,
                end_line=block.end_line,
                raw_text=block.raw_text,
                language=block.language,
            )
            classes.append(cls)
        return classes

    # Extract elements from AST: extract_variables
    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelVariable]:
        """Extract Markdown links and images (act as 'variables')"""
        elements = []
        elements.extend(self.extract_links(tree, source_code))
        elements.extend(self.extract_images(tree, source_code))

        variables = []
        for element in elements:
            var = ModelVariable(
                name=element.name,
                start_line=element.start_line,
                end_line=element.end_line,
                raw_text=element.raw_text,
                language=element.language,
            )
            variables.append(var)
        return variables

    # Extract elements from AST: extract_imports
    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelImport]:
        """Extract Markdown references and definitions"""
        references = self.extract_references(tree, source_code)
        imports = []
        for ref in references:
            imp = ModelImport(
                name=ref.name,
                start_line=ref.start_line,
                end_line=ref.end_line,
                raw_text=ref.raw_text,
                language=ref.language,
            )
            imports.append(imp)
        return imports

    # Extract elements from AST: extract_headers
    def extract_headers(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown headers (H1-H6)"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        headers: list[MarkdownElement] = []

        if tree is not None and tree.root_node is not None:
            try:
                # Extract ATX headers (# ## ### etc.)
                self._extract_atx_headers(tree.root_node, headers)
                # Extract Setext headers (underlined)
                self._extract_setext_headers(tree.root_node, headers)
            except Exception as e:
                log_debug(f"Error during header extraction: {e}")

        log_debug(f"Extracted {len(headers)} Markdown headers")
        return headers

    # Extract elements from AST: extract_code_blocks
    def extract_code_blocks(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown code blocks"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        code_blocks: list[MarkdownElement] = []

        if tree is not None and tree.root_node is not None:
            try:
                self._extract_fenced_code_blocks(tree.root_node, code_blocks)
                self._extract_indented_code_blocks(tree.root_node, code_blocks)
            except Exception as e:
                log_debug(f"Error during code block extraction: {e}")

        log_debug(f"Extracted {len(code_blocks)} Markdown code blocks")
        return code_blocks

    # Extract elements from AST: extract_links
    def extract_links(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown links"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        links: list[MarkdownElement] = []

        if tree is not None and tree.root_node is not None:
            try:
                all_links = _extract_md_links_standalone(
                    tree.root_node,
                    self._get_node_text_optimized,
                    self._traverse_nodes,
                    getattr(self, "_extracted_links", None),
                )
                links.extend(all_links)
            except Exception as e:
                log_debug(f"Error during link extraction: {e}")

        # Deduplicate
        seen: set[tuple[str, str]] = set()
        unique_links: list[MarkdownElement] = []
        for link in links:
            key = (getattr(link, "text", "") or "", getattr(link, "url", "") or "")
            if key not in seen:
                seen.add(key)
                unique_links.append(link)

        log_debug(f"Extracted {len(unique_links)} Markdown links")
        # Return result
        return unique_links

    # Extract elements from AST: extract_images
    def extract_images(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown images"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        images: list[MarkdownElement] = []

        # Check: tree is not None and tree.root_node is n
        if tree is not None and tree.root_node is not None:
            try:
                all_images = _extract_md_images_standalone(
                    tree.root_node,
                    self._get_node_text_optimized,
                    self._traverse_nodes,
                )
                images.extend(all_images)
            except Exception as e:
                log_debug(f"Error during image extraction: {e}")

        # Deduplicate
        seen: set[tuple[str, str]] = set()
        unique_images: list[MarkdownElement] = []
        # Iterate over img
        for img in images:
            key = (img.alt_text or "", img.url or "")
            # Check: key not in seen
            if key not in seen:
                seen.add(key)
                unique_images.append(img)

        log_debug(f"Extracted {len(unique_images)} Markdown images")
        # Return result
        return unique_images

    # Extract elements from AST: extract_references
    def extract_references(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown reference definitions"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        references: list[MarkdownElement] = []

        # Check: tree is not None and tree.root_node is n
        if tree is not None and tree.root_node is not None:
            try:
                refs = _extract_md_link_refs_standalone(
                    tree.root_node,
                    self._get_node_text_optimized,
                    self._traverse_nodes,
                )
                references.extend(refs)
            except Exception as e:
                log_debug(f"Error during reference extraction: {e}")

        log_debug(f"Extracted {len(references)} Markdown references")
        # Return result
        return references

    # Extract elements from AST: extract_blockquotes
    def extract_blockquotes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown blockquotes"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        blockquotes: list[MarkdownElement] = []

        # Check: tree is not None and tree.root_node is n
        if tree is not None and tree.root_node is not None:
            try:
                self._extract_block_quotes(tree.root_node, blockquotes)
            except Exception as e:
                log_debug(f"Error during blockquote extraction: {e}")

        log_debug(f"Extracted {len(blockquotes)} Markdown blockquotes")
        # Return result
        return blockquotes

    # Extract elements from AST: extract_horizontal_rules
    def extract_horizontal_rules(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown horizontal rules"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        horizontal_rules: list[MarkdownElement] = []

        # Check: tree is not None and tree.root_node is n
        if tree is not None and tree.root_node is not None:
            try:
                self._extract_thematic_breaks(tree.root_node, horizontal_rules)
            except Exception as e:
                log_debug(f"Error during horizontal rule extraction: {e}")

        log_debug(f"Extracted {len(horizontal_rules)} Markdown horizontal rules")
        # Return result
        return horizontal_rules

    # Extract elements from AST: extract_html_elements
    def extract_html_elements(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract HTML elements"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        html_elements: list[MarkdownElement] = []

        # Check: tree is not None and tree.root_node is n
        if tree is not None and tree.root_node is not None:
            try:
                self._extract_html_blocks(tree.root_node, html_elements)
                # Disable regex-based inline HTML extraction that causes instability
                # self._extract_inline_html(tree.root_node, html_elements)
            except Exception as e:
                log_debug(f"Error during HTML element extraction: {e}")

        log_debug(f"Extracted {len(html_elements)} HTML elements")
        # Return result
        return html_elements

    # Format data for output: extract_text_formatting
    def extract_text_formatting(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract text formatting elements (bold, italic, strikethrough, inline code)"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        formatting_elements: list[MarkdownElement] = []

        # Check: tree is not None and tree.root_node is n
        if tree is not None and tree.root_node is not None:
            try:
                self._extract_emphasis_elements(tree.root_node, formatting_elements)
                self._extract_inline_code_spans(tree.root_node, formatting_elements)
                self._extract_strikethrough_elements(
                    tree.root_node, formatting_elements
                )
            except Exception as e:
                log_debug(f"Error during text formatting extraction: {e}")

        log_debug(f"Extracted {len(formatting_elements)} text formatting elements")
        # Return result
        return formatting_elements

    # Extract elements from AST: extract_footnotes
    def extract_footnotes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract footnotes"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        footnotes: list[MarkdownElement] = []

        # Check: tree is not None and tree.root_node is n
        if tree is not None and tree.root_node is not None:
            try:
                self._extract_footnote_elements(tree.root_node, footnotes)
            except Exception as e:
                log_debug(f"Error during footnote extraction: {e}")

        log_debug(f"Extracted {len(footnotes)} footnotes")
        # Return result
        return footnotes

    # Extract elements from AST: extract_lists
    def extract_lists(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown lists"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        lists: list[MarkdownElement] = []

        # Check: tree is not None and tree.root_node is n
        if tree is not None and tree.root_node is not None:
            try:
                self._extract_list_items(tree.root_node, lists)
            except Exception as e:
                log_debug(f"Error during list extraction: {e}")

        log_debug(f"Extracted {len(lists)} Markdown list items")
        # Return result
        return lists

    # Extract elements from AST: extract_tables
    def extract_tables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown tables"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        tables: list[MarkdownElement] = []

        # Check: tree is not None and tree.root_node is n
        if tree is not None and tree.root_node is not None:
            try:
                self._extract_pipe_tables(tree.root_node, tables)
            except Exception as e:
                log_debug(f"Error during table extraction: {e}")

        log_debug(f"Extracted {len(tables)} Markdown tables")
        # Return result
        return tables

    # Process: _reset_caches
    def _reset_caches(self) -> None:
        """Reset performance caches AND extraction tracking sets"""
        self._node_text_cache.clear()
        self._processed_nodes.clear()
        self._element_cache.clear()
        # Critical: Reset extraction tracking to prevent cross-call pollution
        if hasattr(self, "_extracted_links"):
            self._extracted_links.clear()
        # Check: hasattr(self, "_extracted_images")
        if hasattr(self, "_extracted_images"):
            self._extracted_images.clear()

    # Process: _get_node_text_optimized
    def _get_node_text_optimized(self, node: "tree_sitter.Node") -> str:
        """Get node text with optimized caching using position-based keys"""
        # Use position-based cache key for deterministic behavior
        cache_key = (node.start_byte, node.end_byte)

        # Check: cache_key in self._node_text_cache
        if cache_key in self._node_text_cache:
            # Return result
            return self._node_text_cache[cache_key]

        try:
            start_byte = node.start_byte
            end_byte = node.end_byte

            encoding = self._file_encoding or "utf-8"
            content_bytes = safe_encode("\n".join(self.content_lines), encoding)
            text = extract_text_slice(content_bytes, start_byte, end_byte, encoding)

            # Check: text
            if text:
                self._node_text_cache[cache_key] = text
                # Return result
                return text
        except Exception as e:
            log_error(f"Error in _get_node_text_optimized: {e}")

        # Fallback to simple text extraction
        try:
            start_point = node.start_point
            end_point = node.end_point

            # Check: start_point[0] < 0 or start_point[0] >= 
            if start_point[0] < 0 or start_point[0] >= len(self.content_lines):
                # Return result
                return ""

            # Check: end_point[0] < 0 or end_point[0] >= len(
            if end_point[0] < 0 or end_point[0] >= len(self.content_lines):
                # Return result
                return ""

            # Check: start_point[0] == end_point[0]
            if start_point[0] == end_point[0]:
                line = self.content_lines[start_point[0]]
                start_col = max(0, min(start_point[1], len(line)))
                end_col = max(start_col, min(end_point[1], len(line)))
                result: str = line[start_col:end_col]
                self._node_text_cache[cache_key] = result
                # Return result
                return result
            else:
                lines = []
                for i in range(
                    start_point[0], min(end_point[0] + 1, len(self.content_lines))
                ):
                    # Check: i < len(self.content_lines)
                    if i < len(self.content_lines):
                        line = self.content_lines[i]
                        # Check: i == start_point[0] and i == end_point[0
                        if i == start_point[0] and i == end_point[0]:
                            # Single line case
                            start_col = max(0, min(start_point[1], len(line)))
                            end_col = max(start_col, min(end_point[1], len(line)))
                            lines.append(line[start_col:end_col])
                        elif i == start_point[0]:
                            start_col = max(0, min(start_point[1], len(line)))
                            lines.append(line[start_col:])
                        elif i == end_point[0]:
                            end_col = max(0, min(end_point[1], len(line)))
                            lines.append(line[:end_col])
                        else:
                            lines.append(line)
                result = "\n".join(lines)
                self._node_text_cache[cache_key] = result
                # Return result
                return result
        except Exception as fallback_error:
            log_error(f"Fallback text extraction also failed: {fallback_error}")
            # Return result
            return ""

    # Extract elements from AST: _extract_atx_headers
    def _extract_atx_headers(
        self, root_node: "tree_sitter.Node", headers: list[MarkdownElement]
    ) -> None:
        """Extract ATX-style headers (# ## ### etc.)"""
        # Iterate over node
        for node in self._traverse_nodes(root_node):
            # Check: node.type == "atx_heading"
            if node.type == "atx_heading":
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = self._get_node_text_optimized(node)

                    # Extract header level and content
                    level = 1
                    content = raw_text.strip()

                    # Count # symbols to determine level
                    if content.startswith("#"):
                        level = len(content) - len(content.lstrip("#"))
                        content = content.lstrip("# ").rstrip()

                    header = MarkdownElement(
                        name=content or f"Header Level {level}",
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=raw_text,
                        element_type="heading",
                        level=level,
                    )
                    # Add additional attributes for formatter
                    header.text = content or f"Header Level {level}"
                    header.type = "heading"
                    headers.append(header)
                except Exception as e:
                    log_debug(f"Failed to extract ATX header: {e}")

    # Extract elements from AST: _extract_setext_headers
    def _extract_setext_headers(
        self, root_node: "tree_sitter.Node", headers: list[MarkdownElement]
    ) -> None:
        """Extract Setext-style headers (underlined)"""
        # Iterate over node
        for node in self._traverse_nodes(root_node):
            # Check: node.type == "setext_heading"
            if node.type == "setext_heading":
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = self._get_node_text_optimized(node)

                    # Determine level based on underline character
                    level = 2  # Default to H2
                    lines = raw_text.strip().split("\n")
                    # Check: len(lines) >= 2
                    if len(lines) >= 2:
                        underline = lines[1].strip()
                        # Check: underline.startswith("=")
                        if underline.startswith("="):
                            level = 1  # H1
                        elif underline.startswith("-"):
                            level = 2  # H2
                        content = lines[0].strip()
                    else:
                        content = raw_text.strip()

                    header = MarkdownElement(
                        name=content or f"Header Level {level}",
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=raw_text,
                        element_type="heading",
                        level=level,
                    )
                    # Add additional attributes for formatter
                    header.text = content or f"Header Level {level}"
                    header.type = "heading"
                    headers.append(header)
                except Exception as e:
                    log_debug(f"Failed to extract Setext header: {e}")

    # Extract elements from AST: _extract_fenced_code_blocks
    def _extract_fenced_code_blocks(
        self, root_node: "tree_sitter.Node", code_blocks: list[MarkdownElement]
    ) -> None:
        """Extract fenced code blocks"""
        # Iterate over node
        for node in self._traverse_nodes(root_node):
            # Check: node.type == "fenced_code_block"
            if node.type == "fenced_code_block":
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = self._get_node_text_optimized(node)

                    # Extract language info
                    language_info = None
                    lines = raw_text.strip().split("\n")
                    # Check: lines and lines[0].startswith("```")
                    if lines and lines[0].startswith("```"):
                        language_info = lines[0][3:].strip()

                    # Extract content (excluding fence markers)
                    content_lines = []
                    in_content = False
                    # Iterate over line
                    for line in lines:
                        # Check: line.startswith("```")
                        if line.startswith("```"):
                            # Check: not in_content
                            if not in_content:
                                in_content = True
                                continue
                            else:
                                break
                        # Check: in_content
                        if in_content:
                            content_lines.append(line)

                    name = f"Code Block ({language_info or 'unknown'})"

                    code_block = MarkdownElement(
                        name=name,
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=raw_text,
                        element_type="code_block",
                        language_info=language_info,
                    )
                    # Add additional attributes for formatter
                    code_block.language = language_info or "text"
                    code_block.line_count = len(content_lines)
                    code_block.type = "code_block"
                    code_blocks.append(code_block)
                except Exception as e:
                    log_debug(f"Failed to extract fenced code block: {e}")

    # Extract elements from AST: _extract_indented_code_blocks
    def _extract_indented_code_blocks(
        self, root_node: "tree_sitter.Node", code_blocks: list[MarkdownElement]
    ) -> None:
        """Extract indented code blocks"""
        # Iterate over node
        for node in self._traverse_nodes(root_node):
            # Check: node.type == "indented_code_block"
            if node.type == "indented_code_block":
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = self._get_node_text_optimized(node)

                    code_block = MarkdownElement(
                        name="Indented Code Block",
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=raw_text,
                        element_type="code_block",
                        language_info="indented",
                    )
                    # Add additional attributes for formatter
                    code_block.language = "text"
                    code_block.line_count = end_line - start_line + 1
                    code_block.type = "code_block"
                    code_blocks.append(code_block)
                except Exception as e:
                    log_debug(f"Failed to extract indented code block: {e}")

    # Extract elements from AST: _extract_inline_links
    def _extract_inline_links(
        self, root_node: "tree_sitter.Node", links: list[MarkdownElement]
    ) -> None:
        from .link_image_extractor import _extract_inline_links as _impl

        _impl(
            root_node,
            links,
            self._get_node_text_optimized,
            self._traverse_nodes,
            getattr(self, "_extracted_links", None),
        )

    # Extract elements from AST: _extract_reference_links
    def _extract_reference_links(
        self, root_node: "tree_sitter.Node", links: list[MarkdownElement]
    ) -> None:
        from .link_image_extractor import _extract_reference_links as _impl

        _impl(root_node, links, self._get_node_text_optimized, self._traverse_nodes)

    # Extract elements from AST: _extract_autolinks
    def _extract_autolinks(
        self, root_node: "tree_sitter.Node", links: list[MarkdownElement]
    ) -> None:
        from .link_image_extractor import _extract_autolinks as _impl

        _impl(
            root_node,
            links,
            self._get_node_text_optimized,
            self._traverse_nodes,
            getattr(self, "_extracted_links", None),
        )

    # Extract elements from AST: _extract_inline_images
    def _extract_inline_images(
        self, root_node: "tree_sitter.Node", images: list[MarkdownElement]
    ) -> None:
        from .link_image_extractor import _extract_inline_images as _impl

        _impl(root_node, images, self._get_node_text_optimized, self._traverse_nodes)

    # Extract elements from AST: _extract_reference_images
    def _extract_reference_images(
        self, root_node: "tree_sitter.Node", images: list[MarkdownElement]
    ) -> None:
        from .link_image_extractor import _extract_reference_images as _impl

        _impl(root_node, images, self._get_node_text_optimized, self._traverse_nodes)

    # Extract elements from AST: _extract_image_reference_definitions
    def _extract_image_reference_definitions(
        self, root_node: "tree_sitter.Node", images: list[MarkdownElement]
    ) -> None:
        from .link_image_extractor import _extract_image_reference_definitions as _impl

        _impl(root_node, images, self._get_node_text_optimized, self._traverse_nodes)

    # Extract elements from AST: _extract_link_reference_definitions
    def _extract_link_reference_definitions(
        self, root_node: "tree_sitter.Node", references: list[MarkdownElement]
    ) -> None:
        refs = _extract_md_link_refs_standalone(
            root_node, self._get_node_text_optimized, self._traverse_nodes
        )
        references.extend(refs)

    # Extract elements from AST: _extract_list_items
    def _extract_list_items(
        self, root_node: "tree_sitter.Node", lists: list[MarkdownElement]
    ) -> None:
        """Extract lists (not individual items)"""
        # Iterate over node
        for node in self._traverse_nodes(root_node):
            # Check: node.type == "list"
            if node.type == "list":
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = self._get_node_text_optimized(node)

                    # Count list items in this list
                    item_count = 0
                    is_task_list = False
                    is_ordered = False

                    # Iterate over child
                    for child in node.children:
                        # Check: child.type == "list_item"
                        if child.type == "list_item":
                            item_count += 1
                            item_text = self._get_node_text_optimized(child)

                            # Check if it's a task list item
                            if (
                                "[ ]" in item_text
                                or "[x]" in item_text
                                or "[X]" in item_text
                            ):
                                is_task_list = True

                            # Check if it's an ordered list (starts with number)
                            if item_text.strip() and item_text.strip()[0].isdigit():
                                is_ordered = True

                    # Determine list type
                    if is_task_list:
                        list_type = "task"
                        element_type = "task_list"
                    elif is_ordered:
                        list_type = "ordered"
                        element_type = "list"
                    else:
                        list_type = "unordered"
                        element_type = "list"

                    name = f"{list_type.title()} List ({item_count} items)"

                    list_element = MarkdownElement(
                        name=name,
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=raw_text,
                        element_type=element_type,
                    )
                    # Add additional attributes for formatter
                    list_element.list_type = list_type
                    list_element.item_count = item_count
                    list_element.type = list_type
                    lists.append(list_element)
                except Exception as e:
                    log_debug(f"Failed to extract list: {e}")

    # Extract elements from AST: _extract_pipe_tables
    def _extract_pipe_tables(
        self, root_node: "tree_sitter.Node", tables: list[MarkdownElement]
    ) -> None:
        """Extract pipe tables"""
        # Iterate over node
        for node in self._traverse_nodes(root_node):
            # Check: node.type == "pipe_table"
            if node.type == "pipe_table":
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = self._get_node_text_optimized(node)

                    # Count rows and columns
                    lines = raw_text.strip().split("\n")
                    row_count = len(
                        [
                            line
                            for line in lines
                            if line.strip() and not line.strip().startswith("|---")
                        ]
                    )

                    # Count columns from first row
                    column_count = 0
                    # Check: lines
                    if lines:
                        first_row = lines[0]
                        column_count = len(
                            [col for col in first_row.split("|") if col.strip()]
                        )

                    table = MarkdownElement(
                        name=f"Table ({row_count} rows, {column_count} columns)",
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=raw_text,
                        element_type="table",
                    )
                    # Add additional attributes for formatter
                    table.row_count = row_count
                    table.column_count = column_count
                    table.type = "table"
                    tables.append(table)
                except Exception as e:
                    log_debug(f"Failed to extract pipe table: {e}")

    # Extract elements from AST: _extract_block_quotes
    def _extract_block_quotes(
        self, root_node: "tree_sitter.Node", blockquotes: list[MarkdownElement]
    ) -> None:
        _misc.extract_block_quotes(
            root_node, blockquotes, self._get_node_text_optimized, self._traverse_nodes
        )

    # Extract elements from AST: _extract_thematic_breaks
    def _extract_thematic_breaks(
        self, root_node: "tree_sitter.Node", horizontal_rules: list[MarkdownElement]
    ) -> None:
        _misc.extract_thematic_breaks(
            root_node,
            horizontal_rules,
            self._get_node_text_optimized,
            self._traverse_nodes,
        )

    # Extract elements from AST: _extract_html_blocks
    def _extract_html_blocks(
        self, root_node: "tree_sitter.Node", html_elements: list[MarkdownElement]
    ) -> None:
        _misc.extract_html_blocks(
            root_node,
            html_elements,
            self._get_node_text_optimized,
            self._traverse_nodes,
        )

    # Extract elements from AST: _extract_inline_html
    def _extract_inline_html(
        self, root_node: "tree_sitter.Node", html_elements: list[MarkdownElement]
    ) -> None:
        _misc.extract_inline_html(
            root_node,
            html_elements,
            self._get_node_text_optimized,
            self._traverse_nodes,
        )

    # Extract elements from AST: _extract_emphasis_elements
    def _extract_emphasis_elements(
        self, root_node: "tree_sitter.Node", formatting_elements: list[MarkdownElement]
    ) -> None:
        _misc.extract_emphasis_elements(
            root_node,
            formatting_elements,
            self._get_node_text_optimized,
            self._traverse_nodes,
        )

    # Extract elements from AST: _extract_inline_code_spans
    def _extract_inline_code_spans(
        self, root_node: "tree_sitter.Node", formatting_elements: list[MarkdownElement]
    ) -> None:
        _misc.extract_inline_code_spans(
            root_node,
            formatting_elements,
            self._get_node_text_optimized,
            self._traverse_nodes,
        )

    # Extract elements from AST: _extract_strikethrough_elements
    def _extract_strikethrough_elements(
        self, root_node: "tree_sitter.Node", formatting_elements: list[MarkdownElement]
    ) -> None:
        _misc.extract_strikethrough_elements(
            root_node,
            formatting_elements,
            self._get_node_text_optimized,
            self._traverse_nodes,
        )

    # Extract elements from AST: _extract_footnote_elements
    def _extract_footnote_elements(
        self, root_node: "tree_sitter.Node", footnotes: list[MarkdownElement]
    ) -> None:
        _misc.extract_footnote_elements(
            root_node, footnotes, self._get_node_text_optimized, self._traverse_nodes
        )

    # Process: _traverse_nodes
    def _traverse_nodes(self, node: "tree_sitter.Node") -> Any:
        """Traverse all nodes in the tree"""
        yield node
        # Iterate over child
        for child in node.children:
            yield from self._traverse_nodes(child)

    # Parse input into structured data: _parse_link_components
    def _parse_link_components(self, raw_text: str) -> tuple[str, str, str]:
        """Parse link components from raw text"""
        import re

        # Pattern for [text](url "title")
        pattern = r'\[([^\]]*)\]\(([^)]*?)(?:\s+"([^"]*)")?\)'
        match = re.search(pattern, raw_text)

        # Check: match
        if match:
            text = match.group(1) or ""
            url = match.group(2) or ""
            title = match.group(3) or ""
            # Return result
            return text, url, title

        # Return result
        return "", "", ""

    # Parse input into structured data: _parse_image_components
    def _parse_image_components(self, raw_text: str) -> tuple[str, str, str]:
        """Parse image components from raw text"""
        import re

        # Pattern for ![alt](url "title")
        pattern = r'!\[([^\]]*)\]\(([^)]*?)(?:\s+"([^"]*)")?\)'
        match = re.search(pattern, raw_text)

        # Check: match
        if match:
            alt_text = match.group(1) or ""
            url = match.group(2) or ""
            title = match.group(3) or ""
            # Return result
            return alt_text, url, title

        # Return result
        return "", "", ""



