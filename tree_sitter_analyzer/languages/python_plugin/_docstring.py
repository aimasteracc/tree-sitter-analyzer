"""Docstring helpers for the Python language extractor."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DocstringSearchResult:
    value: str | None
    cache_value: str
    should_cache: bool


def find_docstring_after_line(
    content_lines: list[str], target_line: int
) -> DocstringSearchResult:
    if not content_lines or target_line >= len(content_lines):
        return DocstringSearchResult(None, "", False)

    for line_index in range(target_line, min(target_line + 5, len(content_lines))):
        line = content_lines[line_index].strip()
        quote_type = _docstring_quote_type(line)
        if not quote_type:
            continue

        return _extract_docstring_from_quoted_lines(
            content_lines, line_index, quote_type
        )

    return DocstringSearchResult(None, "", True)


def _docstring_quote_type(line: str) -> str | None:
    if line.startswith('"""'):
        return '"""'
    if line.startswith("'''"):
        return "'''"
    return None


def _extract_docstring_from_quoted_lines(
    content_lines: list[str], line_index: int, quote_type: str
) -> DocstringSearchResult:
    line = content_lines[line_index].strip()
    if line.count(quote_type) >= 2:
        docstring = line.replace(quote_type, "").strip()
        return DocstringSearchResult(docstring, docstring, True)

    docstring_lines = [line.replace(quote_type, "")]
    for next_line in content_lines[line_index + 1 :]:
        if quote_type in next_line:
            docstring_lines.append(next_line.replace(quote_type, ""))
            docstring = _format_multiline_docstring(docstring_lines)
            return DocstringSearchResult(docstring, docstring, True)
        docstring_lines.append(next_line)

    return DocstringSearchResult(None, "", True)


def _format_multiline_docstring(docstring_lines: list[str]) -> str:
    docstring = "\n".join(docstring_lines)
    if not docstring.startswith("\n"):
        return "\n" + docstring
    return docstring
