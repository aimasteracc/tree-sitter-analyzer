"""Markdown element model and small element-building helpers."""

from typing import TYPE_CHECKING, Any

from ...models import CodeElement

if TYPE_CHECKING:
    import tree_sitter


class MarkdownElement(CodeElement):
    """Markdown-specific code element."""

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
        self.level = level
        self.url = url
        self.alt_text = alt_text
        self.title = title
        self.language_info = language_info
        self.is_checked = is_checked

        self.text: str | None = None
        self.type: str | None = None
        self.alt: str | None = None
        self.list_type: str | None = None
        self.item_count: int | None = None
        self.row_count: int | None = None
        self.column_count: int | None = None


def _is_pipe_table_separator(line: str) -> bool:
    """Return True for Markdown table separator rows like ``| --- | :---: |``."""
    cells = [
        cell.strip() for cell in line.strip().strip("|").split("|") if cell.strip()
    ]
    return bool(cells) and all(
        "-" in cell and set(cell) <= {"-", ":"} for cell in cells
    )


def _summarize_markdown_list(
    node: "tree_sitter.Node",
    get_node_text: Any,
) -> tuple[int, bool, bool]:
    """Return item count plus task/ordered flags for a Markdown list node."""
    item_count = 0
    is_task_list = False
    is_ordered = False

    for child in node.children:
        if child.type != "list_item":
            continue
        item_count += 1
        item_text = get_node_text(child)
        stripped_text = item_text.strip()
        is_task_list = is_task_list or _is_task_list_item(item_text)
        is_ordered = is_ordered or bool(stripped_text and stripped_text[0].isdigit())

    return item_count, is_task_list, is_ordered


def _is_task_list_item(item_text: str) -> bool:
    """Return whether item text uses GitHub-style task list markers."""
    return "[ ]" in item_text or "[x]" in item_text or "[X]" in item_text


def _classify_markdown_list(is_task_list: bool, is_ordered: bool) -> tuple[str, str]:
    """Return formatter list_type and element_type for a Markdown list."""
    if is_task_list:
        return "task", "task_list"
    if is_ordered:
        return "ordered", "list"
    return "unordered", "list"


def _build_markdown_list_element(
    node: "tree_sitter.Node",
    raw_text: str,
    item_count: int,
    list_type: str,
    element_type: str,
) -> MarkdownElement:
    """Build a MarkdownElement for a list node."""
    list_element = MarkdownElement(
        name=f"{list_type.title()} List ({item_count} items)",
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        raw_text=raw_text,
        element_type=element_type,
    )
    list_element.list_type = list_type
    list_element.item_count = item_count
    list_element.type = list_type
    return list_element


def _summarize_setext_header(raw_text: str) -> tuple[str, int]:
    """Return heading text and level for a Setext-style heading."""
    level = 2
    lines = raw_text.strip().split("\n")
    if len(lines) < 2:
        return raw_text.strip(), level

    underline = lines[1].strip()
    if underline.startswith("="):
        level = 1
    elif underline.startswith("-"):
        level = 2
    return lines[0].strip(), level


def _build_markdown_heading_element(
    node: "tree_sitter.Node",
    raw_text: str,
    content: str,
    level: int,
) -> MarkdownElement:
    """Build a MarkdownElement for a heading node."""
    fallback_name = f"Header Level {level}"
    header = MarkdownElement(
        name=content or fallback_name,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        raw_text=raw_text,
        element_type="heading",
        level=level,
    )
    header.text = content or fallback_name
    header.type = "heading"
    return header


def _summarize_fenced_code_block(raw_text: str) -> tuple[str | None, int]:
    """Return language info and content-line count for a fenced code block."""
    lines = raw_text.strip().split("\n")
    language_info = _extract_fenced_code_language(lines)
    return language_info, len(_extract_fenced_code_content_lines(lines))


def _extract_fenced_code_language(lines: list[str]) -> str | None:
    """Return the fence language info when present."""
    if lines and lines[0].startswith("```"):
        return lines[0][3:].strip()
    return None


def _extract_fenced_code_content_lines(lines: list[str]) -> list[str]:
    """Return lines between opening and closing triple-backtick fences."""
    content_lines = []
    in_content = False
    for line in lines:
        if line.startswith("```"):
            if not in_content:
                in_content = True
                continue
            break
        if in_content:
            content_lines.append(line)
    return content_lines


def _build_markdown_code_block_element(
    node: "tree_sitter.Node",
    raw_text: str,
    language_info: str | None,
    line_count: int,
) -> MarkdownElement:
    """Build a MarkdownElement for a fenced code block node."""
    code_block = MarkdownElement(
        name=f"Code Block ({language_info or 'unknown'})",
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        raw_text=raw_text,
        element_type="code_block",
        language_info=language_info,
    )
    code_block.language = language_info or "text"
    # line_count is a computed property on CodeElement (end_line - start_line + 1)
    code_block.type = "code_block"
    return code_block
