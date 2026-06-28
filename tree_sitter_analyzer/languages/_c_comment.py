"""C comment extraction helpers."""

from ..utils import log_debug


def extract_comment_for_line(line: int, content_lines: list[str]) -> str | None:
    """Extract comment for a specific line."""
    try:
        for index in range(max(0, line - 5), line):
            if index >= len(content_lines):
                continue

            line_content = content_lines[index].strip()
            if _is_block_comment_start(line_content):
                return _collect_block_comment(index, line, content_lines)
            if line_content.startswith("///"):
                return line_content
    except Exception as e:
        log_debug(f"Failed to extract comment: {e}")
    return None


def _is_block_comment_start(line_content: str) -> bool:
    return line_content.startswith(("/**", "/*"))


def _collect_block_comment(
    start_index: int, target_line: int, content_lines: list[str]
) -> str:
    comment_lines = []
    for index in range(start_index, min(len(content_lines), target_line)):
        doc_line = content_lines[index].strip()
        comment_lines.append(doc_line)
        if doc_line.endswith("*/"):
            break
    return "\n".join(comment_lines)
