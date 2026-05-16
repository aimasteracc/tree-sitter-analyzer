"""Markdown miscellaneous element extraction — extracted from extractor.py."""

import re
from collections.abc import Callable, Iterator
from typing import Any

from ...utils import log_debug


# Extract elements from AST: extract_block_quotes
# Section: imports and module configuration
# Section: main class definition
# Section: helper functions
# Section: data processing methods
# Section: output formatting methods
# Section: validation and error handling
def extract_block_quotes(
    root_node: Any,
    blockquotes: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    """Extract blockquotes."""
    from .extractor import MarkdownElement

    for node in traverse_nodes(root_node):
        if node.type == "block_quote":
            try:
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                raw_text = get_node_text(node)

                lines = raw_text.strip().split("\n")
                content_lines = []
                for line in lines:
                    cleaned = re.sub(r"^>\s?", "", line)
                    content_lines.append(cleaned)
                content = "\n".join(content_lines).strip()

                blockquote = MarkdownElement(
                    name=(
                        f"Blockquote: {content[:50]}..."
                        if len(content) > 50
                        else f"Blockquote: {content}"
                    ),
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


# Extract elements from AST: extract_thematic_breaks
def extract_thematic_breaks(
    root_node: Any,
    horizontal_rules: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    """Extract thematic breaks (horizontal rules)."""
    from .extractor import MarkdownElement

    for node in traverse_nodes(root_node):
        if node.type == "thematic_break":
            try:
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                raw_text = get_node_text(node)

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


# Extract elements from AST: extract_html_blocks
def extract_html_blocks(
    root_node: Any,
    html_elements: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    """Extract HTML block elements."""
    from .extractor import MarkdownElement

    for node in traverse_nodes(root_node):
        if node.type == "html_block":
            try:
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                raw_text = get_node_text(node)

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


# Extract elements from AST: extract_inline_html
def extract_inline_html(
    root_node: Any,
    html_elements: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    """Extract inline HTML elements."""
    from .extractor import MarkdownElement

    for node in traverse_nodes(root_node):
        if node.type == "inline":
            try:
                raw_text = get_node_text(node)
                if not raw_text:
                    continue

                html_pattern = (
                    r"<(?!(?:https?://|mailto:|[^@\s]+@[^@\s]+\.[^@\s]+)[^>]*>)[^>]+>"
                )
                matches = re.finditer(html_pattern, raw_text)

                for match in matches:
                    tag_text = match.group(0)

                    tag_match = re.search(r"<(\w+)", tag_text)
                    tag_name = tag_match.group(1) if tag_match else "HTML"

                    text_before_match = raw_text[: match.start()]
                    newlines_before = text_before_match.count("\n")
                    start_line = node.start_point[0] + 1 + newlines_before
                    end_line = start_line

                    html_element = MarkdownElement(
                        name=f"HTML Tag: {tag_name}",
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=tag_text,
                        element_type="html_inline",
                    )
                    html_element.type = "html_inline"
                    html_element.name = tag_name
                    html_elements.append(html_element)

            except Exception as e:
                log_debug(f"Failed to extract inline HTML: {e}")


# Extract elements from AST: extract_emphasis_elements
def extract_emphasis_elements(
    root_node: Any,
    formatting_elements: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    """Extract emphasis and strong emphasis elements."""
    from .extractor import MarkdownElement

    for node in traverse_nodes(root_node):
        if node.type == "inline":
            try:
                raw_text = get_node_text(node)
                if not raw_text:
                    continue

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


# Extract elements from AST: extract_inline_code_spans
def extract_inline_code_spans(
    root_node: Any,
    formatting_elements: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    """Extract inline code spans."""
    from .extractor import MarkdownElement

    for node in traverse_nodes(root_node):
        if node.type == "inline":
            try:
                raw_text = get_node_text(node)
                if not raw_text:
                    continue

                code_pattern = r"`([^`]+)`"
                matches = re.finditer(code_pattern, raw_text)

                for match in matches:
                    content = match.group(1) or ""

                    text_before_match = raw_text[: match.start()]
                    newlines_before = text_before_match.count("\n")
                    start_line = node.start_point[0] + 1 + newlines_before
                    end_line = start_line

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


# Extract elements from AST: extract_strikethrough_elements
def extract_strikethrough_elements(
    root_node: Any,
    formatting_elements: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    """Extract strikethrough elements."""
    from .extractor import MarkdownElement

    for node in traverse_nodes(root_node):
        if node.type == "inline":
            try:
                raw_text = get_node_text(node)
                if not raw_text:
                    continue

                strike_pattern = r"~~([^~]+)~~"
                matches = re.finditer(strike_pattern, raw_text)

                for match in matches:
                    content = match.group(1) or ""

                    text_before_match = raw_text[: match.start()]
                    newlines_before = text_before_match.count("\n")
                    start_line = node.start_point[0] + 1 + newlines_before
                    end_line = start_line

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


# Extract elements from AST: extract_footnote_elements
def extract_footnote_elements(
    root_node: Any,
    footnotes: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    """Extract footnote elements."""
    from .extractor import MarkdownElement

    for node in traverse_nodes(root_node):
        if node.type == "inline":
            try:
                raw_text = get_node_text(node)
                if not raw_text:
                    continue

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

        elif node.type == "paragraph":
            try:
                raw_text = get_node_text(node)
                if not raw_text:
                    continue

                footnote_def_pattern = r"^\[\^([^\]]+)\]:\s*(.+)$"
                footnote_match: re.Match[str] | None = re.match(
                    footnote_def_pattern, raw_text.strip(), re.MULTILINE
                )

                if footnote_match:
                    ref_id = footnote_match.group(1) or ""
                    content = footnote_match.group(2) or ""
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

