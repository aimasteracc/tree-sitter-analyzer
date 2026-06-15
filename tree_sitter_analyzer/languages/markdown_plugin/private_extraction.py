"""Private extraction helpers for the Markdown element extractor."""

from typing import TYPE_CHECKING, Any

from ...utils import log_debug, log_error
from . import misc_extractor as _misc
from .elements import (
    MarkdownElement,
    _build_markdown_code_block_element,
    _build_markdown_heading_element,
    _build_markdown_list_element,
    _classify_markdown_list,
    _is_pipe_table_separator,
    _summarize_fenced_code_block,
    _summarize_markdown_list,
    _summarize_setext_header,
)
from .link_image_extractor import (
    extract_md_link_reference_definitions as _extract_md_link_refs_standalone,
)
from .node_text import _extract_node_text_by_bytes, _extract_node_text_by_points

if TYPE_CHECKING:
    import tree_sitter


def _count_pipe_table_rows(lines: list[str]) -> int:
    """Count non-separator rows in a Markdown pipe table."""
    return len(
        [line for line in lines if line.strip() and not _is_pipe_table_separator(line)]
    )


def _count_pipe_table_columns(lines: list[str]) -> int:
    """Count columns from the first Markdown pipe table row."""
    if not lines:
        return 0
    first_row = lines[0]
    return len([col for col in first_row.split("|") if col.strip()])


class MarkdownExtractorStateMixin:
    """Shared state and traversal helpers for Markdown extraction."""

    def _reset_caches(self) -> None:
        """Reset performance caches and extraction tracking sets."""
        self._node_text_cache.clear()
        self._processed_nodes.clear()
        self._element_cache.clear()
        if hasattr(self, "_extracted_links"):
            self._extracted_links.clear()
        if hasattr(self, "_extracted_images"):
            self._extracted_images.clear()

    # Public alias for public_extraction.py companion module
    reset_caches = _reset_caches

    def _get_node_text_optimized(self, node: "tree_sitter.Node") -> str:
        """Get node text with optimized caching using position-based keys."""
        cache_key = (node.start_byte, node.end_byte)

        if cache_key in self._node_text_cache:
            return self._node_text_cache[cache_key]

        try:
            encoding = self._file_encoding or "utf-8"
            text = _extract_node_text_by_bytes(node, self.content_lines, encoding)
            if text:
                self._node_text_cache[cache_key] = text
                return text
        except Exception as e:
            log_error(f"Error in _get_node_text_optimized: {e}")

        try:
            result = _extract_node_text_by_points(node, self.content_lines)
            if result:
                self._node_text_cache[cache_key] = result
            return result
        except Exception as fallback_error:
            log_error(f"Fallback text extraction also failed: {fallback_error}")
            return ""

    def _traverse_nodes(self, node: "tree_sitter.Node") -> Any:
        """Traverse all nodes in the tree."""
        yield node
        for child in node.children:
            yield from self._traverse_nodes(child)


class MarkdownBlockPrivateExtractionMixin:
    """Private extraction helpers for Markdown block elements."""

    def _extract_atx_headers(
        self, root_node: "tree_sitter.Node", headers: list[MarkdownElement]
    ) -> None:
        """Extract ATX-style headers (# ## ### etc.)."""
        for node in self._traverse_nodes(root_node):
            if node.type != "atx_heading":
                continue
            try:
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                raw_text = self._get_node_text_optimized(node)

                level = 1
                content = raw_text.strip()

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
                header.text = content or f"Header Level {level}"
                header.type = "heading"
                headers.append(header)
            except Exception as e:
                log_debug(f"Failed to extract ATX header: {e}")

    def _extract_setext_headers(
        self, root_node: "tree_sitter.Node", headers: list[MarkdownElement]
    ) -> None:
        """Extract Setext-style headers."""
        for node in self._traverse_nodes(root_node):
            if node.type != "setext_heading":
                continue
            try:
                raw_text = self._get_node_text_optimized(node)
                content, level = _summarize_setext_header(raw_text)
                headers.append(
                    _build_markdown_heading_element(node, raw_text, content, level)
                )
            except Exception as e:
                log_debug(f"Failed to extract Setext header: {e}")

    def _extract_fenced_code_blocks(
        self, root_node: "tree_sitter.Node", code_blocks: list[MarkdownElement]
    ) -> None:
        """Extract fenced code blocks."""
        for node in self._traverse_nodes(root_node):
            if node.type != "fenced_code_block":
                continue
            try:
                raw_text = self._get_node_text_optimized(node)
                language_info, line_count = _summarize_fenced_code_block(raw_text)
                code_blocks.append(
                    _build_markdown_code_block_element(
                        node,
                        raw_text,
                        language_info,
                        line_count,
                    )
                )
            except Exception as e:
                log_debug(f"Failed to extract fenced code block: {e}")

    def _extract_indented_code_blocks(
        self, root_node: "tree_sitter.Node", code_blocks: list[MarkdownElement]
    ) -> None:
        """Extract indented code blocks."""
        for node in self._traverse_nodes(root_node):
            if node.type != "indented_code_block":
                continue
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
                code_block.language = "text"
                # line_count is computed from start_line/end_line (CodeElement property)
                code_block.type = "code_block"
                code_blocks.append(code_block)
            except Exception as e:
                log_debug(f"Failed to extract indented code block: {e}")

    def _extract_list_items(
        self, root_node: "tree_sitter.Node", lists: list[MarkdownElement]
    ) -> None:
        """Extract lists."""
        for node in self._traverse_nodes(root_node):
            if node.type != "list":
                continue
            try:
                raw_text = self._get_node_text_optimized(node)
                item_count, is_task_list, is_ordered = _summarize_markdown_list(
                    node,
                    self._get_node_text_optimized,
                )
                list_type, element_type = _classify_markdown_list(
                    is_task_list,
                    is_ordered,
                )
                lists.append(
                    _build_markdown_list_element(
                        node,
                        raw_text,
                        item_count,
                        list_type,
                        element_type,
                    )
                )
            except Exception as e:
                log_debug(f"Failed to extract list: {e}")

    def _extract_pipe_tables(
        self, root_node: "tree_sitter.Node", tables: list[MarkdownElement]
    ) -> None:
        """Extract pipe tables."""
        for node in self._traverse_nodes(root_node):
            if node.type != "pipe_table":
                continue
            try:
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                raw_text = self._get_node_text_optimized(node)

                lines = raw_text.strip().split("\n")
                row_count = _count_pipe_table_rows(lines)
                column_count = _count_pipe_table_columns(lines)

                table = MarkdownElement(
                    name=f"Table ({row_count} rows, {column_count} columns)",
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    element_type="table",
                )
                table.row_count = row_count
                table.column_count = column_count
                table.type = "table"
                tables.append(table)
            except Exception as e:
                log_debug(f"Failed to extract pipe table: {e}")


class MarkdownLinkImagePrivateExtractionMixin:
    """Private extraction adapters for Markdown links and images."""

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

    def _extract_reference_links(
        self, root_node: "tree_sitter.Node", links: list[MarkdownElement]
    ) -> None:
        from .link_image_extractor import _extract_reference_links as _impl

        _impl(root_node, links, self._get_node_text_optimized, self._traverse_nodes)

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

    def _extract_inline_images(
        self, root_node: "tree_sitter.Node", images: list[MarkdownElement]
    ) -> None:
        from .link_image_extractor import _extract_inline_images as _impl

        _impl(root_node, images, self._get_node_text_optimized, self._traverse_nodes)

    def _extract_reference_images(
        self, root_node: "tree_sitter.Node", images: list[MarkdownElement]
    ) -> None:
        from .link_image_extractor import _extract_reference_images as _impl

        _impl(root_node, images, self._get_node_text_optimized, self._traverse_nodes)

    def _extract_image_reference_definitions(
        self, root_node: "tree_sitter.Node", images: list[MarkdownElement]
    ) -> None:
        from .link_image_extractor import _extract_image_reference_definitions as _impl

        _impl(root_node, images, self._get_node_text_optimized, self._traverse_nodes)

    def _extract_link_reference_definitions(
        self, root_node: "tree_sitter.Node", references: list[MarkdownElement]
    ) -> None:
        refs = _extract_md_link_refs_standalone(
            root_node, self._get_node_text_optimized, self._traverse_nodes
        )
        references.extend(refs)


class MarkdownMiscPrivateExtractionMixin:
    """Private extraction adapters for miscellaneous Markdown elements."""

    def _extract_block_quotes(
        self, root_node: "tree_sitter.Node", blockquotes: list[MarkdownElement]
    ) -> None:
        _misc.extract_block_quotes(
            root_node, blockquotes, self._get_node_text_optimized, self._traverse_nodes
        )

    def _extract_thematic_breaks(
        self, root_node: "tree_sitter.Node", horizontal_rules: list[MarkdownElement]
    ) -> None:
        _misc.extract_thematic_breaks(
            root_node,
            horizontal_rules,
            self._get_node_text_optimized,
            self._traverse_nodes,
        )

    def _extract_html_blocks(
        self, root_node: "tree_sitter.Node", html_elements: list[MarkdownElement]
    ) -> None:
        _misc.extract_html_blocks(
            root_node,
            html_elements,
            self._get_node_text_optimized,
            self._traverse_nodes,
        )

    def _extract_inline_html(
        self, root_node: "tree_sitter.Node", html_elements: list[MarkdownElement]
    ) -> None:
        _misc.extract_inline_html(
            root_node,
            html_elements,
            self._get_node_text_optimized,
            self._traverse_nodes,
        )

    def _extract_emphasis_elements(
        self, root_node: "tree_sitter.Node", formatting_elements: list[MarkdownElement]
    ) -> None:
        _misc.extract_emphasis_elements(
            root_node,
            formatting_elements,
            self._get_node_text_optimized,
            self._traverse_nodes,
        )

    def _extract_inline_code_spans(
        self, root_node: "tree_sitter.Node", formatting_elements: list[MarkdownElement]
    ) -> None:
        _misc.extract_inline_code_spans(
            root_node,
            formatting_elements,
            self._get_node_text_optimized,
            self._traverse_nodes,
        )

    def _extract_strikethrough_elements(
        self, root_node: "tree_sitter.Node", formatting_elements: list[MarkdownElement]
    ) -> None:
        _misc.extract_strikethrough_elements(
            root_node,
            formatting_elements,
            self._get_node_text_optimized,
            self._traverse_nodes,
        )

    def _extract_footnote_elements(
        self, root_node: "tree_sitter.Node", footnotes: list[MarkdownElement]
    ) -> None:
        _misc.extract_footnote_elements(
            root_node, footnotes, self._get_node_text_optimized, self._traverse_nodes
        )


class MarkdownPrivateExtractionMixin(
    MarkdownExtractorStateMixin,
    MarkdownBlockPrivateExtractionMixin,
    MarkdownLinkImagePrivateExtractionMixin,
    MarkdownMiscPrivateExtractionMixin,
):
    """Combined private extraction behavior for MarkdownElementExtractor."""
