"""Public extraction methods for the Markdown Element Extractor."""

from collections.abc import Callable
from typing import TYPE_CHECKING

from ...models import Class as ModelClass
from ...models import Function as ModelFunction
from ...models import Import as ModelImport
from ...models import Variable as ModelVariable
from ...utils import log_debug
from .elements import MarkdownElement
from .link_image_extractor import (
    extract_md_images as _extract_md_images_standalone,
)
from .link_image_extractor import (
    extract_md_link_reference_definitions as _extract_md_link_refs_standalone,
)
from .link_image_extractor import (
    extract_md_links as _extract_md_links_standalone,
)

if TYPE_CHECKING:
    import tree_sitter


def _prepare_public_extraction(
    extractor: object, tree: object | None, source_code: str
) -> object | None:
    """Set per-call extractor state and return the tree root, if available."""
    extractor.source_code = source_code or ""
    extractor.content_lines = extractor.source_code.split("\n")
    extractor._reset_caches()
    if tree is None:
        return None
    return getattr(tree, "root_node", None)


def _run_extractors(
    root_node: object | None,
    error_context: str,
    *extractors: Callable[[object], None],
) -> None:
    """Run public extraction callbacks with consistent error logging."""
    if root_node is None:
        return
    try:
        for extractor in extractors:
            extractor(root_node)
    except Exception as e:
        log_debug(f"Error during {error_context}: {e}")


def _deduplicate_elements(
    elements: list[MarkdownElement],
    key_for: Callable[[MarkdownElement], tuple[str, str]],
) -> list[MarkdownElement]:
    """Return elements with duplicate display/url pairs removed."""
    seen: set[tuple[str, str]] = set()
    unique_elements: list[MarkdownElement] = []
    for element in elements:
        key = key_for(element)
        if key in seen:
            continue
        seen.add(key)
        unique_elements.append(element)
    return unique_elements


class MarkdownModelExtractionMixin:
    """Map Markdown elements into the generic analyzer model types."""

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelFunction]:
        """Extract Markdown elements (headers act as 'functions')."""
        return [
            ModelFunction(
                name=header.name,
                start_line=header.start_line,
                end_line=header.end_line,
                raw_text=header.raw_text,
                language=header.language,
            )
            for header in self.extract_headers(tree, source_code)
        ]

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelClass]:
        """Extract Markdown sections (code blocks act as 'classes')."""
        return [
            ModelClass(
                name=block.name,
                start_line=block.start_line,
                end_line=block.end_line,
                raw_text=block.raw_text,
                language=block.language,
            )
            for block in self.extract_code_blocks(tree, source_code)
        ]

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelVariable]:
        """Extract Markdown links and images (act as 'variables')."""
        elements = []
        elements.extend(self.extract_links(tree, source_code))
        elements.extend(self.extract_images(tree, source_code))

        return [
            ModelVariable(
                name=element.name,
                start_line=element.start_line,
                end_line=element.end_line,
                raw_text=element.raw_text,
                language=element.language,
            )
            for element in elements
        ]

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[ModelImport]:
        """Extract Markdown references and definitions."""
        return [
            ModelImport(
                name=ref.name,
                start_line=ref.start_line,
                end_line=ref.end_line,
                raw_text=ref.raw_text,
                language=ref.language,
            )
            for ref in self.extract_references(tree, source_code)
        ]


class MarkdownBlockExtractionMixin:
    """Public extraction methods for block-level Markdown elements."""

    def extract_headers(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown headers (H1-H6)."""
        root_node = _prepare_public_extraction(self, tree, source_code)
        headers: list[MarkdownElement] = []
        _run_extractors(
            root_node,
            "header extraction",
            lambda node: self._extract_atx_headers(node, headers),
            lambda node: self._extract_setext_headers(node, headers),
        )
        log_debug(f"Extracted {len(headers)} Markdown headers")
        return headers

    def extract_code_blocks(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown code blocks."""
        root_node = _prepare_public_extraction(self, tree, source_code)
        code_blocks: list[MarkdownElement] = []
        _run_extractors(
            root_node,
            "code block extraction",
            lambda node: self._extract_fenced_code_blocks(node, code_blocks),
            lambda node: self._extract_indented_code_blocks(node, code_blocks),
        )
        log_debug(f"Extracted {len(code_blocks)} Markdown code blocks")
        return code_blocks

    def extract_blockquotes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown blockquotes."""
        root_node = _prepare_public_extraction(self, tree, source_code)
        blockquotes: list[MarkdownElement] = []
        _run_extractors(
            root_node,
            "blockquote extraction",
            lambda node: self._extract_block_quotes(node, blockquotes),
        )
        log_debug(f"Extracted {len(blockquotes)} Markdown blockquotes")
        return blockquotes

    def extract_horizontal_rules(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown horizontal rules."""
        root_node = _prepare_public_extraction(self, tree, source_code)
        horizontal_rules: list[MarkdownElement] = []
        _run_extractors(
            root_node,
            "horizontal rule extraction",
            lambda node: self._extract_thematic_breaks(node, horizontal_rules),
        )
        log_debug(f"Extracted {len(horizontal_rules)} Markdown horizontal rules")
        return horizontal_rules

    def extract_html_elements(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract HTML elements."""
        root_node = _prepare_public_extraction(self, tree, source_code)
        html_elements: list[MarkdownElement] = []
        _run_extractors(
            root_node,
            "HTML element extraction",
            lambda node: self._extract_html_blocks(node, html_elements),
        )
        log_debug(f"Extracted {len(html_elements)} HTML elements")
        return html_elements

    def extract_lists(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown lists."""
        root_node = _prepare_public_extraction(self, tree, source_code)
        lists: list[MarkdownElement] = []
        _run_extractors(
            root_node,
            "list extraction",
            lambda node: self._extract_list_items(node, lists),
        )
        log_debug(f"Extracted {len(lists)} Markdown list items")
        return lists

    def extract_tables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown tables."""
        root_node = _prepare_public_extraction(self, tree, source_code)
        tables: list[MarkdownElement] = []
        _run_extractors(
            root_node,
            "table extraction",
            lambda node: self._extract_pipe_tables(node, tables),
        )
        log_debug(f"Extracted {len(tables)} Markdown tables")
        return tables


class MarkdownInlineExtractionMixin:
    """Public extraction methods for inline Markdown elements."""

    def extract_links(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown links."""
        root_node = _prepare_public_extraction(self, tree, source_code)
        links: list[MarkdownElement] = []
        _run_extractors(
            root_node,
            "link extraction",
            lambda node: links.extend(
                _extract_md_links_standalone(
                    node,
                    self._get_node_text_optimized,
                    self._traverse_nodes,
                    getattr(self, "_extracted_links", None),
                )
            ),
        )
        unique_links = _deduplicate_elements(
            links,
            lambda link: (
                getattr(link, "text", "") or "",
                getattr(link, "url", "") or "",
            ),
        )
        log_debug(f"Extracted {len(unique_links)} Markdown links")
        return unique_links

    def extract_images(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown images."""
        root_node = _prepare_public_extraction(self, tree, source_code)
        images: list[MarkdownElement] = []
        _run_extractors(
            root_node,
            "image extraction",
            lambda node: images.extend(
                _extract_md_images_standalone(
                    node,
                    self._get_node_text_optimized,
                    self._traverse_nodes,
                )
            ),
        )
        unique_images = _deduplicate_elements(
            images,
            lambda image: (image.alt_text or "", image.url or ""),
        )
        log_debug(f"Extracted {len(unique_images)} Markdown images")
        return unique_images

    def extract_references(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract Markdown reference definitions."""
        root_node = _prepare_public_extraction(self, tree, source_code)
        references: list[MarkdownElement] = []
        _run_extractors(
            root_node,
            "reference extraction",
            lambda node: references.extend(
                _extract_md_link_refs_standalone(
                    node,
                    self._get_node_text_optimized,
                    self._traverse_nodes,
                )
            ),
        )
        log_debug(f"Extracted {len(references)} Markdown references")
        return references

    def extract_text_formatting(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract text formatting elements."""
        root_node = _prepare_public_extraction(self, tree, source_code)
        formatting_elements: list[MarkdownElement] = []
        _run_extractors(
            root_node,
            "text formatting extraction",
            lambda node: self._extract_emphasis_elements(node, formatting_elements),
            lambda node: self._extract_inline_code_spans(node, formatting_elements),
            lambda node: self._extract_strikethrough_elements(
                node, formatting_elements
            ),
        )
        log_debug(f"Extracted {len(formatting_elements)} text formatting elements")
        return formatting_elements

    def extract_footnotes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkdownElement]:
        """Extract footnotes."""
        root_node = _prepare_public_extraction(self, tree, source_code)
        footnotes: list[MarkdownElement] = []
        _run_extractors(
            root_node,
            "footnote extraction",
            lambda node: self._extract_footnote_elements(node, footnotes),
        )
        log_debug(f"Extracted {len(footnotes)} footnotes")
        return footnotes
