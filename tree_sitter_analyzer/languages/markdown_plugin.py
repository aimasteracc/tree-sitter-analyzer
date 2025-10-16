#!/usr/bin/env python3
"""
Markdown Language Plugin

Enhanced Markdown-specific parsing and element extraction functionality.
Provides comprehensive support for Markdown elements including headers,
links, code blocks, lists, tables, and other structural elements.
"""

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import tree_sitter

try:
    import tree_sitter

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from ..core.analysis_engine import AnalysisRequest
from ..encoding_utils import extract_text_slice, safe_encode
from ..models import AnalysisResult, CodeElement
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error, log_warning
from ..utils.tree_sitter_compat import TreeSitterQueryCompat


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
        **kwargs,
    ):
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


class MarkdownElementExtractor(ElementExtractor):
    """Markdown-specific element extractor with comprehensive feature support"""

    def __init__(self) -> None:
        """Initialize the Markdown element extractor."""
        self.current_file: str = ""
        self.source_code: str = ""
        self.content_lines: list[str] = []

        # Performance optimization caches
        self._node_text_cache: dict[int, str] = {}
        self._processed_nodes: set[int] = set()
        self._element_cache: dict[tuple[int, str], Any] = {}
        self._file_encoding: str | None = None

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[CodeElement]:
        """Extract Markdown elements (headers act as 'functions')"""
        return self.extract_headers(tree, source_code)

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[CodeElement]:
        """Extract Markdown sections (code blocks act as 'classes')"""
        return self.extract_code_blocks(tree, source_code)

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[CodeElement]:
        """Extract Markdown links and images (act as 'variables')"""
        elements = []
        elements.extend(self.extract_links(tree, source_code))
        elements.extend(self.extract_images(tree, source_code))
        return elements

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[CodeElement]:
        """Extract Markdown references and definitions"""
        return self.extract_references(tree, source_code)

    def extract_headers(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown headers (H1-H6)"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        headers: list[MarkdownElement] = []

        if tree is None or tree.root_node is None:
            log_debug("Tree or root_node is None, returning empty headers list")
            return headers

        try:
            # Extract ATX headers (# ## ### etc.)
            self._extract_atx_headers(tree.root_node, headers)
            # Extract Setext headers (underlined)
            self._extract_setext_headers(tree.root_node, headers)
        except Exception as e:
            log_debug(f"Error during header extraction: {e}")
            return []

        log_debug(f"Extracted {len(headers)} Markdown headers")
        return headers

    def extract_code_blocks(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown code blocks"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        code_blocks: list[MarkdownElement] = []

        if tree is None or tree.root_node is None:
            log_debug("Tree or root_node is None, returning empty code blocks list")
            return code_blocks

        try:
            self._extract_fenced_code_blocks(tree.root_node, code_blocks)
            self._extract_indented_code_blocks(tree.root_node, code_blocks)
        except Exception as e:
            log_debug(f"Error during code block extraction: {e}")
            return []

        log_debug(f"Extracted {len(code_blocks)} Markdown code blocks")
        return code_blocks

    def extract_links(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown links"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        links: list[MarkdownElement] = []

        if tree is None or tree.root_node is None:
            log_debug("Tree or root_node is None, returning empty links list")
            return links

        try:
            # Track extracted links to prevent global duplicates (ensure reset)
            self._extracted_links = set()

            self._extract_inline_links(tree.root_node, links)
            self._extract_reference_links(tree.root_node, links)
            self._extract_autolinks(tree.root_node, links)

            # Clean up after extraction is complete
            if hasattr(self, "_extracted_links"):
                delattr(self, "_extracted_links")

        except Exception as e:
            log_debug(f"Error during link extraction: {e}")
            return []

        # 重複除去: 同じtextとurlを持つ要素を除去
        seen = set()
        unique_links = []
        for link in links:
            key = (getattr(link, "text", "") or "", getattr(link, "url", "") or "")
            if key not in seen:
                seen.add(key)
                unique_links.append(link)

        links = unique_links

        log_debug(f"Extracted {len(links)} Markdown links")
        return links

    def extract_images(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown images"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        images: list[MarkdownElement] = []

        if tree is None or tree.root_node is None:
            log_debug("Tree or root_node is None, returning empty images list")
            return images

        try:
            self._extract_inline_images(tree.root_node, images)
            self._extract_reference_images(tree.root_node, images)
            self._extract_image_reference_definitions(tree.root_node, images)
        except Exception as e:
            log_debug(f"Error during image extraction: {e}")
            return []

        # 重複除去: 同じalt_textとurlを持つ要素を除去
        seen = set()
        unique_images = []
        for img in images:
            key = (img.alt_text or "", img.url or "")
            if key not in seen:
                seen.add(key)
                unique_images.append(img)

        images = unique_images

        log_debug(f"Extracted {len(images)} Markdown images")
        return images

    def extract_references(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown reference definitions"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        references: list[MarkdownElement] = []

        if tree is None or tree.root_node is None:
            log_debug("Tree or root_node is None, returning empty references list")
            return references

        try:
            self._extract_link_reference_definitions(tree.root_node, references)
        except Exception as e:
            log_debug(f"Error during reference extraction: {e}")
            return []

        log_debug(f"Extracted {len(references)} Markdown references")
        return references

    def extract_blockquotes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown blockquotes"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        blockquotes: list[MarkdownElement] = []

        if tree is None or tree.root_node is None:
            log_debug("Tree or root_node is None, returning empty blockquotes list")
            return blockquotes

        try:
            self._extract_block_quotes(tree.root_node, blockquotes)
        except Exception as e:
            log_debug(f"Error during blockquote extraction: {e}")
            return []

        log_debug(f"Extracted {len(blockquotes)} Markdown blockquotes")
        return blockquotes

    def extract_horizontal_rules(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown horizontal rules"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        horizontal_rules: list[MarkdownElement] = []

        if tree is None or tree.root_node is None:
            log_debug(
                "Tree or root_node is None, returning empty horizontal rules list"
            )
            return horizontal_rules

        try:
            self._extract_thematic_breaks(tree.root_node, horizontal_rules)
        except Exception as e:
            log_debug(f"Error during horizontal rule extraction: {e}")
            return []

        log_debug(f"Extracted {len(horizontal_rules)} Markdown horizontal rules")
        return horizontal_rules

    def extract_html_elements(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract HTML elements"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        html_elements: list[MarkdownElement] = []

        if tree is None or tree.root_node is None:
            log_debug("Tree or root_node is None, returning empty HTML elements list")
            return html_elements

        try:
            self._extract_html_blocks(tree.root_node, html_elements)
            self._extract_inline_html(tree.root_node, html_elements)
        except Exception as e:
            log_debug(f"Error during HTML element extraction: {e}")
            return []

        log_debug(f"Extracted {len(html_elements)} HTML elements")
        return html_elements

    def extract_text_formatting(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract text formatting elements (bold, italic, strikethrough, inline code)"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        formatting_elements: list[MarkdownElement] = []

        if tree is None or tree.root_node is None:
            log_debug(
                "Tree or root_node is None, returning empty formatting elements list"
            )
            return formatting_elements

        try:
            self._extract_emphasis_elements(tree.root_node, formatting_elements)
            self._extract_inline_code_spans(tree.root_node, formatting_elements)
            self._extract_strikethrough_elements(tree.root_node, formatting_elements)
        except Exception as e:
            log_debug(f"Error during text formatting extraction: {e}")
            return []

        log_debug(f"Extracted {len(formatting_elements)} text formatting elements")
        return formatting_elements

    def extract_footnotes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract footnotes"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        footnotes: list[MarkdownElement] = []

        if tree is None or tree.root_node is None:
            log_debug("Tree or root_node is None, returning empty footnotes list")
            return footnotes

        try:
            self._extract_footnote_elements(tree.root_node, footnotes)
        except Exception as e:
            log_debug(f"Error during footnote extraction: {e}")
            return []

        log_debug(f"Extracted {len(footnotes)} footnotes")
        return footnotes

    def extract_lists(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown lists"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        lists: list[MarkdownElement] = []

        if tree is None or tree.root_node is None:
            log_debug("Tree or root_node is None, returning empty lists list")
            return lists

        try:
            self._extract_list_items(tree.root_node, lists)
        except Exception as e:
            log_debug(f"Error during list extraction: {e}")
            return []

        log_debug(f"Extracted {len(lists)} Markdown list items")
        return lists

    def extract_tables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown tables"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        tables: list[MarkdownElement] = []

        if tree is None or tree.root_node is None:
            log_debug("Tree or root_node is None, returning empty tables list")
            return tables

        try:
            self._extract_pipe_tables(tree.root_node, tables)
        except Exception as e:
            log_debug(f"Error during table extraction: {e}")
            return []

        log_debug(f"Extracted {len(tables)} Markdown tables")
        return tables

    def _reset_caches(self) -> None:
        """Reset performance caches"""
        self._node_text_cache.clear()
        self._processed_nodes.clear()
        self._element_cache.clear()

    def _get_node_text_optimized(self, node: "tree_sitter.Node") -> str:
        """Get node text with optimized caching"""
        node_id = id(node)

        if node_id in self._node_text_cache:
            return self._node_text_cache[node_id]

        try:
            start_byte = node.start_byte
            end_byte = node.end_byte

            encoding = self._file_encoding or "utf-8"
            content_bytes = safe_encode("\n".join(self.content_lines), encoding)
            text = extract_text_slice(content_bytes, start_byte, end_byte, encoding)

            if text:
                self._node_text_cache[node_id] = text
                return text
        except Exception as e:
            log_error(f"Error in _get_node_text_optimized: {e}")

        # Fallback to simple text extraction
        try:
            start_point = node.start_point
            end_point = node.end_point

            if start_point[0] < 0 or start_point[0] >= len(self.content_lines):
                return ""

            if end_point[0] < 0 or end_point[0] >= len(self.content_lines):
                return ""

            if start_point[0] == end_point[0]:
                line = self.content_lines[start_point[0]]
                start_col = max(0, min(start_point[1], len(line)))
                end_col = max(start_col, min(end_point[1], len(line)))
                result = line[start_col:end_col]
                self._node_text_cache[node_id] = result
                return result
            else:
                lines = []
                for i in range(
                    start_point[0], min(end_point[0] + 1, len(self.content_lines))
                ):
                    if i < len(self.content_lines):
                        line = self.content_lines[i]
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
                self._node_text_cache[node_id] = result
                return result
        except Exception as fallback_error:
            log_error(f"Fallback text extraction also failed: {fallback_error}")
            return ""

    def _extract_atx_headers(
        self, root_node: "tree_sitter.Node", headers: list[MarkdownElement]
    ) -> None:
        """Extract ATX-style headers (# ## ### etc.)"""
        for node in self._traverse_nodes(root_node):
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

    def _extract_setext_headers(
        self, root_node: "tree_sitter.Node", headers: list[MarkdownElement]
    ) -> None:
        """Extract Setext-style headers (underlined)"""
        for node in self._traverse_nodes(root_node):
            if node.type == "setext_heading":
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = self._get_node_text_optimized(node)

                    # Determine level based on underline character
                    level = 2  # Default to H2
                    lines = raw_text.strip().split("\n")
                    if len(lines) >= 2:
                        underline = lines[1].strip()
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

    def _extract_fenced_code_blocks(
        self, root_node: "tree_sitter.Node", code_blocks: list[MarkdownElement]
    ) -> None:
        """Extract fenced code blocks"""
        for node in self._traverse_nodes(root_node):
            if node.type == "fenced_code_block":
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = self._get_node_text_optimized(node)

                    # Extract language info
                    language_info = None
                    lines = raw_text.strip().split("\n")
                    if lines and lines[0].startswith("```"):
                        language_info = lines[0][3:].strip()

                    # Extract content (excluding fence markers)
                    content_lines = []
                    in_content = False
                    for line in lines:
                        if line.startswith("```"):
                            if not in_content:
                                in_content = True
                                continue
                            else:
                                break
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

    def _extract_indented_code_blocks(
        self, root_node: "tree_sitter.Node", code_blocks: list[MarkdownElement]
    ) -> None:
        """Extract indented code blocks"""
        for node in self._traverse_nodes(root_node):
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

    def _extract_inline_links(
        self, root_node: "tree_sitter.Node", links: list[MarkdownElement]
    ) -> None:
        """Extract inline links"""
        import re

        # Extract links from text within inline nodes using regular expressions
        for node in self._traverse_nodes(root_node):
            if node.type == "inline":
                try:
                    raw_text = self._get_node_text_optimized(node)
                    if not raw_text:
                        continue

                    # Inline link pattern: [text](url "title") (excluding images)
                    inline_pattern = r'(?<!\!)\[([^\]]*)\]\(([^)]*?)(?:\s+"([^"]*)")?\)'
                    matches = re.finditer(inline_pattern, raw_text)

                    for match in matches:
                        text = match.group(1) or ""
                        url = match.group(2) or ""
                        title = match.group(3) or ""

                        # Global duplicate check: process same text and URL combination only once
                        link_signature = f"{text}|{url}"
                        if (
                            hasattr(self, "_extracted_links")
                            and link_signature in self._extracted_links
                        ):
                            continue

                        if hasattr(self, "_extracted_links"):
                            self._extracted_links.add(link_signature)

                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1

                        link = MarkdownElement(
                            name=text or "Link",
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=match.group(0),
                            element_type="link",
                            url=url,
                            title=title,
                        )
                        # Add additional attributes for formatter
                        link.text = text or "Link"
                        link.type = "link"
                        links.append(link)

                except Exception as e:
                    log_debug(f"Failed to extract inline link: {e}")

    def _extract_reference_links(
        self, root_node: "tree_sitter.Node", links: list[MarkdownElement]
    ) -> None:
        """Extract reference links"""
        import re

        # Reference links also need to be extracted from inline nodes
        # Track already processed reference links to avoid duplicates
        processed_ref_links = set()

        for node in self._traverse_nodes(root_node):
            if node.type == "inline":
                try:
                    raw_text = self._get_node_text_optimized(node)
                    if not raw_text:
                        continue

                    # Reference link pattern: [text][ref]
                    ref_pattern = r"\[([^\]]*)\]\[([^\]]*)\]"
                    matches = re.finditer(ref_pattern, raw_text)

                    for match in matches:
                        text = match.group(1) or ""
                        ref = match.group(2) or ""

                        # Skip image references (starting with !)
                        if match.start() > 0 and raw_text[match.start() - 1] == "!":
                            continue

                        # Duplicate check: process same text and reference combination only once
                        start_line = node.start_point[0] + 1
                        ref_link_key = (text, ref, start_line)

                        if ref_link_key in processed_ref_links:
                            continue
                        processed_ref_links.add(ref_link_key)

                        end_line = node.end_point[0] + 1

                        link = MarkdownElement(
                            name=text or "Reference Link",
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=match.group(0),
                            element_type="reference_link",
                        )
                        # Add additional attributes for formatter
                        link.text = text or "Reference Link"
                        link.type = "reference_link"
                        links.append(link)

                except Exception as e:
                    log_debug(f"Failed to extract reference link: {e}")

    def _extract_autolinks(
        self, root_node: "tree_sitter.Node", links: list[MarkdownElement]
    ) -> None:
        """Extract autolinks"""
        import re

        # Extract autolinks from text within inline nodes using regular expressions
        for node in self._traverse_nodes(root_node):
            if node.type == "inline":
                try:
                    raw_text = self._get_node_text_optimized(node)
                    if not raw_text:
                        continue

                    # Autolink pattern: <url> or <email>
                    autolink_pattern = (
                        r"<(https?://[^>]+|mailto:[^>]+|[^@\s]+@[^@\s]+\.[^@\s]+)>"
                    )
                    matches = re.finditer(autolink_pattern, raw_text)

                    for match in matches:
                        url = match.group(1) or ""
                        full_match = match.group(0)

                        # Global duplicate check: process same URL for autolinks only once
                        autolink_signature = f"autolink|{url}"
                        if (
                            hasattr(self, "_extracted_links")
                            and autolink_signature in self._extracted_links
                        ):
                            continue

                        if hasattr(self, "_extracted_links"):
                            self._extracted_links.add(autolink_signature)

                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1

                        link = MarkdownElement(
                            name=url or "Autolink",
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=full_match,
                            element_type="autolink",
                            url=url,
                        )
                        # Add additional attributes for formatter
                        link.text = url or "Autolink"
                        link.type = "autolink"
                        links.append(link)

                except Exception as e:
                    log_debug(f"Failed to extract autolink: {e}")

    def _extract_inline_images(
        self, root_node: "tree_sitter.Node", images: list[MarkdownElement]
    ) -> None:
        """Extract inline images"""
        import re

        # Extract images from text within inline nodes using regular expressions
        for node in self._traverse_nodes(root_node):
            if node.type == "inline":
                try:
                    raw_text = self._get_node_text_optimized(node)
                    if not raw_text:
                        continue

                    # Inline image pattern: ![alt](url "title")
                    image_pattern = r'!\[([^\]]*)\]\(([^)]*?)(?:\s+"([^"]*)")?\)'
                    matches = re.finditer(image_pattern, raw_text)

                    for match in matches:
                        alt_text = match.group(1) or ""
                        url = match.group(2) or ""
                        title = match.group(3) or ""

                        # Calculate line number from matched position
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1

                        image = MarkdownElement(
                            name=alt_text or "Image",
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=match.group(0),
                            element_type="image",
                            url=url,
                            alt_text=alt_text,
                            title=title,
                        )
                        # Add additional attributes for formatter
                        image.alt = alt_text or ""
                        image.type = "image"
                        images.append(image)

                except Exception as e:
                    log_debug(f"Failed to extract inline image: {e}")

    def _extract_reference_images(
        self, root_node: "tree_sitter.Node", images: list[MarkdownElement]
    ) -> None:
        """Extract reference images"""
        import re

        # Reference images also need to be extracted from inline nodes
        for node in self._traverse_nodes(root_node):
            if node.type == "inline":
                try:
                    raw_text = self._get_node_text_optimized(node)
                    if not raw_text:
                        continue

                    # Reference image pattern: ![alt][ref]
                    ref_image_pattern = r"!\[([^\]]*)\]\[([^\]]*)\]"
                    matches = re.finditer(ref_image_pattern, raw_text)

                    for match in matches:
                        alt_text = match.group(1) or ""
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1

                        image = MarkdownElement(
                            name=alt_text or "Reference Image",
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=match.group(0),
                            element_type="reference_image",
                        )
                        # Add additional attributes for formatter
                        image.alt = alt_text or ""
                        image.type = "reference_image"
                        images.append(image)

                except Exception as e:
                    log_debug(f"Failed to extract reference image: {e}")

    def _extract_image_reference_definitions(
        self, root_node: "tree_sitter.Node", images: list[MarkdownElement]
    ) -> None:
        """Extract image reference definitions"""
        import re

        # Extract all reference definitions that could be used for images
        # We check if the URL points to an image file or if it's used by an image reference

        # First, collect all image references used in the document
        image_refs_used = set()
        for node in self._traverse_nodes(root_node):
            if node.type == "inline":
                try:
                    raw_text = self._get_node_text_optimized(node)
                    if not raw_text:
                        continue

                    # Find image references: ![alt][ref]
                    ref_image_pattern = r"!\[([^\]]*)\]\[([^\]]*)\]"
                    matches = re.finditer(ref_image_pattern, raw_text)

                    for match in matches:
                        ref = match.group(2) or ""
                        if ref:
                            image_refs_used.add(ref.lower())

                except Exception as e:
                    log_debug(f"Failed to scan for image references: {e}")

        # Now extract reference definitions that are used by images OR point to image files
        for node in self._traverse_nodes(root_node):
            if node.type == "link_reference_definition":
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = self._get_node_text_optimized(node)

                    # Pattern: [label]: url "title"
                    ref_pattern = r'^\[([^\]]+)\]:\s*([^\s]+)(?:\s+"([^"]*)")?'
                    match = re.match(ref_pattern, raw_text.strip())

                    if match:
                        label = match.group(1) or ""
                        url = match.group(2) or ""
                        title = match.group(3) or ""

                        # Include if this reference is used by an image OR if URL looks like an image
                        is_used_by_image = label.lower() in image_refs_used
                        is_image_url = any(
                            url.lower().endswith(ext)
                            for ext in [
                                ".png",
                                ".jpg",
                                ".jpeg",
                                ".gif",
                                ".svg",
                                ".webp",
                                ".bmp",
                            ]
                        )

                        if is_used_by_image or is_image_url:
                            image_ref = MarkdownElement(
                                name=f"Image Reference Definition: {label}",
                                start_line=start_line,
                                end_line=end_line,
                                raw_text=raw_text,
                                element_type="image_reference_definition",
                                url=url,
                                alt_text=label,
                                title=title,
                            )
                            # Add additional attributes for formatter
                            image_ref.alt = label
                            image_ref.type = "image_reference_definition"
                            images.append(image_ref)

                except Exception as e:
                    log_debug(f"Failed to extract image reference definition: {e}")

    def _extract_link_reference_definitions(
        self, root_node: "tree_sitter.Node", references: list[MarkdownElement]
    ) -> None:
        """Extract link reference definitions"""
        for node in self._traverse_nodes(root_node):
            if node.type == "link_reference_definition":
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = self._get_node_text_optimized(node)

                    reference = MarkdownElement(
                        name=raw_text or "Reference Definition",
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=raw_text,
                        element_type="reference_definition",
                    )
                    references.append(reference)
                except Exception as e:
                    log_debug(f"Failed to extract reference definition: {e}")

    def _extract_list_items(
        self, root_node: "tree_sitter.Node", lists: list[MarkdownElement]
    ) -> None:
        """Extract lists (not individual items)"""
        for node in self._traverse_nodes(root_node):
            if node.type == "list":
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = self._get_node_text_optimized(node)

                    # Count list items in this list
                    item_count = 0
                    is_task_list = False
                    is_ordered = False

                    for child in node.children:
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

    def _extract_pipe_tables(
        self, root_node: "tree_sitter.Node", tables: list[MarkdownElement]
    ) -> None:
        """Extract pipe tables"""
        for node in self._traverse_nodes(root_node):
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

    def _extract_block_quotes(
        self, root_node: "tree_sitter.Node", blockquotes: list[MarkdownElement]
    ) -> None:
        """Extract blockquotes"""
        import re

        # Blockquotes are often represented as paragraphs starting with >
        for node in self._traverse_nodes(root_node):
            if node.type == "block_quote":
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = self._get_node_text_optimized(node)

                    # Extract content without > markers
                    lines = raw_text.strip().split("\n")
                    content_lines = []
                    for line in lines:
                        # Remove > marker and optional space
                        cleaned = re.sub(r"^>\s?", "", line)
                        content_lines.append(cleaned)
                    content = "\n".join(content_lines).strip()

                    blockquote = MarkdownElement(
                        name=f"Blockquote: {content[:50]}..."
                        if len(content) > 50
                        else f"Blockquote: {content}",
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=raw_text,
                        element_type="blockquote",
                    )
                    blockquote.type = "blockquote"
                    blockquote.text = content
                    blockquotes.append(blockquote)
                except Exception as e:
                    log_debug(f"Failed to extract blockquote: {e}")

    def _extract_thematic_breaks(
        self, root_node: "tree_sitter.Node", horizontal_rules: list[MarkdownElement]
    ) -> None:
        """Extract thematic breaks (horizontal rules)"""
        for node in self._traverse_nodes(root_node):
            if node.type == "thematic_break":
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = self._get_node_text_optimized(node)

                    hr = MarkdownElement(
                        name="Horizontal Rule",
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=raw_text,
                        element_type="horizontal_rule",
                    )
                    hr.type = "horizontal_rule"
                    horizontal_rules.append(hr)
                except Exception as e:
                    log_debug(f"Failed to extract horizontal rule: {e}")

    def _extract_html_blocks(
        self, root_node: "tree_sitter.Node", html_elements: list[MarkdownElement]
    ) -> None:
        """Extract HTML block elements"""
        for node in self._traverse_nodes(root_node):
            if node.type == "html_block":
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = self._get_node_text_optimized(node)

                    # Extract tag name if possible
                    import re

                    tag_match = re.search(r"<(\w+)", raw_text)
                    tag_name = tag_match.group(1) if tag_match else "HTML"

                    html_element = MarkdownElement(
                        name=f"HTML Block: {tag_name}",
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=raw_text,
                        element_type="html_block",
                    )
                    html_element.type = "html_block"
                    html_elements.append(html_element)
                except Exception as e:
                    log_debug(f"Failed to extract HTML block: {e}")

    def _extract_inline_html(
        self, root_node: "tree_sitter.Node", html_elements: list[MarkdownElement]
    ) -> None:
        """Extract inline HTML elements"""
        import re

        # Look for HTML tags in inline content
        for node in self._traverse_nodes(root_node):
            if node.type == "inline":
                try:
                    raw_text = self._get_node_text_optimized(node)
                    if not raw_text:
                        continue

                    # Pattern for HTML tags (excluding autolinks)
                    # Exclude autolink patterns: <url> or <email>
                    html_pattern = r"<(?!(?:https?://|mailto:|[^@\s]+@[^@\s]+\.[^@\s]+)[^>]*>)[^>]+>"
                    matches = re.finditer(html_pattern, raw_text)

                    for match in matches:
                        tag_text = match.group(0)

                        # Extract tag name
                        tag_match = re.search(r"<(\w+)", tag_text)
                        tag_name = tag_match.group(1) if tag_match else "HTML"

                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1

                        html_element = MarkdownElement(
                            name=f"HTML Tag: {tag_name}",
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=tag_text,
                            element_type="html_inline",
                        )
                        html_element.type = "html_inline"
                        html_element.name = tag_name  # Set name attribute for formatter
                        html_elements.append(html_element)

                except Exception as e:
                    log_debug(f"Failed to extract inline HTML: {e}")

    def _extract_emphasis_elements(
        self, root_node: "tree_sitter.Node", formatting_elements: list[MarkdownElement]
    ) -> None:
        """Extract emphasis and strong emphasis elements"""
        import re

        for node in self._traverse_nodes(root_node):
            if node.type == "inline":
                try:
                    raw_text = self._get_node_text_optimized(node)
                    if not raw_text:
                        continue

                    # Pattern for bold text: **text** or __text__
                    bold_pattern = r"\*\*([^*]+)\*\*|__([^_]+)__"
                    bold_matches = re.finditer(bold_pattern, raw_text)

                    for match in bold_matches:
                        content = match.group(1) or match.group(2) or ""
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1

                        bold_element = MarkdownElement(
                            name=f"Bold: {content}",
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=match.group(0),
                            element_type="strong_emphasis",
                        )
                        bold_element.type = "strong_emphasis"
                        bold_element.text = content
                        formatting_elements.append(bold_element)

                    # Pattern for italic text: *text* or _text_ (but not **text** or __text__)
                    italic_pattern = r"(?<!\*)\*([^*]+)\*(?!\*)|(?<!_)_([^_]+)_(?!_)"
                    italic_matches = re.finditer(italic_pattern, raw_text)

                    for match in italic_matches:
                        content = match.group(1) or match.group(2) or ""
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1

                        italic_element = MarkdownElement(
                            name=f"Italic: {content}",
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=match.group(0),
                            element_type="emphasis",
                        )
                        italic_element.type = "emphasis"
                        italic_element.text = content
                        formatting_elements.append(italic_element)

                except Exception as e:
                    log_debug(f"Failed to extract emphasis elements: {e}")

    def _extract_inline_code_spans(
        self, root_node: "tree_sitter.Node", formatting_elements: list[MarkdownElement]
    ) -> None:
        """Extract inline code spans"""
        import re

        for node in self._traverse_nodes(root_node):
            if node.type == "inline":
                try:
                    raw_text = self._get_node_text_optimized(node)
                    if not raw_text:
                        continue

                    # Pattern for inline code: `code`
                    code_pattern = r"`([^`]+)`"
                    matches = re.finditer(code_pattern, raw_text)

                    for match in matches:
                        content = match.group(1) or ""
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1

                        code_element = MarkdownElement(
                            name=f"Inline Code: {content}",
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=match.group(0),
                            element_type="inline_code",
                        )
                        code_element.type = "inline_code"
                        code_element.text = content
                        formatting_elements.append(code_element)

                except Exception as e:
                    log_debug(f"Failed to extract inline code: {e}")

    def _extract_strikethrough_elements(
        self, root_node: "tree_sitter.Node", formatting_elements: list[MarkdownElement]
    ) -> None:
        """Extract strikethrough elements"""
        import re

        for node in self._traverse_nodes(root_node):
            if node.type == "inline":
                try:
                    raw_text = self._get_node_text_optimized(node)
                    if not raw_text:
                        continue

                    # Pattern for strikethrough: ~~text~~
                    strike_pattern = r"~~([^~]+)~~"
                    matches = re.finditer(strike_pattern, raw_text)

                    for match in matches:
                        content = match.group(1) or ""
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1

                        strike_element = MarkdownElement(
                            name=f"Strikethrough: {content}",
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=match.group(0),
                            element_type="strikethrough",
                        )
                        strike_element.type = "strikethrough"
                        strike_element.text = content
                        formatting_elements.append(strike_element)

                except Exception as e:
                    log_debug(f"Failed to extract strikethrough: {e}")

    def _extract_footnote_elements(
        self, root_node: "tree_sitter.Node", footnotes: list[MarkdownElement]
    ) -> None:
        """Extract footnote elements"""
        import re

        for node in self._traverse_nodes(root_node):
            if node.type == "inline":
                try:
                    raw_text = self._get_node_text_optimized(node)
                    if not raw_text:
                        continue

                    # Pattern for footnote references: [^1]
                    footnote_ref_pattern = r"\[\^([^\]]+)\]"
                    matches = re.finditer(footnote_ref_pattern, raw_text)

                    for match in matches:
                        ref_id = match.group(1) or ""
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1

                        footnote_element = MarkdownElement(
                            name=f"Footnote Reference: {ref_id}",
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=match.group(0),
                            element_type="footnote_reference",
                        )
                        footnote_element.type = "footnote_reference"
                        footnote_element.text = ref_id
                        footnotes.append(footnote_element)

                except Exception as e:
                    log_debug(f"Failed to extract footnote reference: {e}")

            # Look for footnote definitions
            elif node.type == "paragraph":
                try:
                    raw_text = self._get_node_text_optimized(node)
                    if not raw_text:
                        continue

                    # Pattern for footnote definitions: [^1]: content
                    footnote_def_pattern = r"^\[\^([^\]]+)\]:\s*(.+)$"
                    match = re.match(
                        footnote_def_pattern, raw_text.strip(), re.MULTILINE
                    )

                    if match:
                        ref_id = match.group(1) or ""
                        content = match.group(2) or ""
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1

                        footnote_element = MarkdownElement(
                            name=f"Footnote Definition: {ref_id}",
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            element_type="footnote_definition",
                        )
                        footnote_element.type = "footnote_definition"
                        footnote_element.text = content
                        footnotes.append(footnote_element)

                except Exception as e:
                    log_debug(f"Failed to extract footnote definition: {e}")

    def _traverse_nodes(self, node: "tree_sitter.Node"):
        """Traverse all nodes in the tree"""
        yield node
        for child in node.children:
            yield from self._traverse_nodes(child)

    def _parse_link_components(self, raw_text: str) -> tuple[str, str, str]:
        """Parse link components from raw text"""
        import re

        # Pattern for [text](url "title")
        pattern = r'\[([^\]]*)\]\(([^)]*?)(?:\s+"([^"]*)")?\)'
        match = re.search(pattern, raw_text)

        if match:
            text = match.group(1) or ""
            url = match.group(2) or ""
            title = match.group(3) or ""
            return text, url, title

        return "", "", ""

    def _parse_image_components(self, raw_text: str) -> tuple[str, str, str]:
        """Parse image components from raw text"""
        import re

        # Pattern for ![alt](url "title")
        pattern = r'!\[([^\]]*)\]\(([^)]*?)(?:\s+"([^"]*)")?\)'
        match = re.search(pattern, raw_text)

        if match:
            alt_text = match.group(1) or ""
            url = match.group(2) or ""
            title = match.group(3) or ""
            return alt_text, url, title

        return "", "", ""


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
        """Create and return an element extractor for this language"""
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
        return extractor.extract_functions(tree, source_code)

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[CodeElement]:
        """Extract classes from the tree (legacy compatibility)"""
        extractor = self.get_extractor()
        return extractor.extract_classes(tree, source_code)

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[CodeElement]:
        """Extract variables from the tree (legacy compatibility)"""
        extractor = self.get_extractor()
        return extractor.extract_variables(tree, source_code)

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[CodeElement]:
        """Extract imports from the tree (legacy compatibility)"""
        extractor = self.get_extractor()
        return extractor.extract_imports(tree, source_code)

    def get_tree_sitter_language(self) -> Optional["tree_sitter.Language"]:
        """Get the Tree-sitter language object for Markdown"""
        if self._language_cache is None:
            try:
                import tree_sitter
                import tree_sitter_markdown as tsmarkdown

                # Use modern tree-sitter-markdown API
                language_capsule = tsmarkdown.language()
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
            with open(file_path, encoding="utf-8") as f:
                source_code = f.read()

            parser = tree_sitter.Parser()
            parser.language = language
            tree = parser.parse(bytes(source_code, "utf8"))

            extractor = self.create_extractor()
            extractor.current_file = file_path  # Set current file for context

            elements: list[CodeElement] = []

            # Extract all element types
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
            from ..queries.markdown import get_query

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
        extractor = self.get_extractor()
        elements = []

        try:
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
        except Exception as e:
            log_error(f"Failed to extract elements: {e}")

        return elements

    def execute_query_strategy(
        self, tree: "tree_sitter.Tree", source_code: str, query_key: str
    ) -> list[CodeElement]:
        """Execute Markdown-specific query strategy based on query_key"""
        if not tree or not source_code:
            return []

        # Initialize extractor with source code
        self._extractor.source_code = source_code
        self._extractor.content_lines = source_code.split("\n")
        self._extractor._reset_caches()

        # Map query_key to appropriate extraction method
        query_mapping = {
            # Header-related queries (mapped to functions)
            "function": lambda: self._extractor.extract_headers(tree, source_code),
            "headers": lambda: self._extractor.extract_headers(tree, source_code),
            "heading": lambda: self._extractor.extract_headers(tree, source_code),
            # Code block-related queries (mapped to classes)
            "class": lambda: self._extractor.extract_code_blocks(tree, source_code),
            "code_blocks": lambda: self._extractor.extract_code_blocks(
                tree, source_code
            ),
            "code_block": lambda: self._extractor.extract_code_blocks(
                tree, source_code
            ),
            # Link and image queries (mapped to variables)
            "variable": lambda: self._extractor.extract_links(tree, source_code)
            + self._extractor.extract_images(tree, source_code),
            "links": lambda: self._extractor.extract_links(tree, source_code),
            "link": lambda: self._extractor.extract_links(tree, source_code),
            "images": lambda: self._extractor.extract_images(tree, source_code),
            "image": lambda: self._extractor.extract_images(tree, source_code),
            # Reference queries (mapped to imports)
            "import": lambda: self._extractor.extract_references(tree, source_code),
            "references": lambda: self._extractor.extract_references(tree, source_code),
            "reference": lambda: self._extractor.extract_references(tree, source_code),
            # List and table queries
            "lists": lambda: self._extractor.extract_lists(tree, source_code),
            "list": lambda: self._extractor.extract_lists(tree, source_code),
            "task_lists": lambda: [
                lst
                for lst in self._extractor.extract_lists(tree, source_code)
                if getattr(lst, "element_type", "") == "task_list"
            ],
            "tables": lambda: self._extractor.extract_tables(tree, source_code),
            "table": lambda: self._extractor.extract_tables(tree, source_code),
            # Content structure queries
            "blockquotes": lambda: self._extractor.extract_blockquotes(
                tree, source_code
            ),
            "blockquote": lambda: self._extractor.extract_blockquotes(
                tree, source_code
            ),
            "horizontal_rules": lambda: self._extractor.extract_horizontal_rules(
                tree, source_code
            ),
            "horizontal_rule": lambda: self._extractor.extract_horizontal_rules(
                tree, source_code
            ),
            # HTML and formatting queries
            "html_blocks": lambda: self._extractor.extract_html_elements(
                tree, source_code
            ),
            "html_block": lambda: self._extractor.extract_html_elements(
                tree, source_code
            ),
            "html": lambda: self._extractor.extract_html_elements(tree, source_code),
            "emphasis": lambda: self._extractor.extract_text_formatting(
                tree, source_code
            ),
            "formatting": lambda: self._extractor.extract_text_formatting(
                tree, source_code
            ),
            "text_formatting": lambda: self._extractor.extract_text_formatting(
                tree, source_code
            ),
            "inline_code": lambda: [
                f
                for f in self._extractor.extract_text_formatting(tree, source_code)
                if getattr(f, "element_type", "") == "inline_code"
            ],
            "strikethrough": lambda: [
                f
                for f in self._extractor.extract_text_formatting(tree, source_code)
                if getattr(f, "element_type", "") == "strikethrough"
            ],
            # Footnote queries
            "footnotes": lambda: self._extractor.extract_footnotes(tree, source_code),
            "footnote": lambda: self._extractor.extract_footnotes(tree, source_code),
            # Comprehensive queries
            "all_elements": lambda: self.extract_elements(tree, source_code),
            "text_content": lambda: self._extractor.extract_headers(tree, source_code)
            + self._extractor.extract_text_formatting(tree, source_code),
        }

        # Execute the appropriate extraction method
        if query_key in query_mapping:
            try:
                return query_mapping[query_key]()
            except Exception as e:
                log_error(f"Error executing Markdown query '{query_key}': {e}")
                return []
        else:
            log_warning(f"Unsupported Markdown query key: {query_key}")
            return []

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
            "emphasis": [
                "inline"  # Contains emphasis elements
            ],
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
