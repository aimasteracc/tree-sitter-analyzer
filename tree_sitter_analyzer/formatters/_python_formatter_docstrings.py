"""Docstring and decorator helpers for Python formatter output."""

from typing import Any

_IMPORTANT_DECORATORS = (
    "property",
    "staticmethod",
    "classmethod",
    "dataclass",
    "abstractmethod",
)


def extract_module_docstring(data: dict[str, Any]) -> str | None:
    """Extract module-level docstring"""
    source_code = data.get("source_code", "")
    if not source_code:
        return None

    lines = source_code.split("\n")
    for index, line in enumerate(lines[:10]):
        stripped = line.strip()
        quote_type = _docstring_quote(stripped)
        if quote_type is not None:
            return _docstring_text(lines, index, stripped, quote_type)
    return None


def _docstring_quote(stripped: str) -> str | None:
    if stripped.startswith('"""'):
        return '"""'
    if stripped.startswith("'''"):
        return "'''"
    return None


def _docstring_text(
    lines: list[str], start_index: int, stripped: str, quote_type: str
) -> str:
    if stripped.count(quote_type) >= 2:
        return str(stripped.replace(quote_type, "").strip())

    docstring_lines = [stripped.replace(quote_type, "")]
    for next_line in lines[start_index + 1 :]:
        docstring_lines.append(next_line.replace(quote_type, ""))
        if quote_type in next_line:
            break
    return "\n".join(docstring_lines).strip()


def format_decorators(decorators: list[str]) -> str:
    """Format Python decorators"""
    if not decorators:
        return "-"

    shown_decorators = [
        f"@{decorator}"
        for decorator in decorators
        if _is_important_decorator(decorator)
    ]
    if shown_decorators:
        return ", ".join(shown_decorators)
    if len(decorators) == 1:
        return f"@{decorators[0]}"
    return f"@{decorators[0]} (+{len(decorators) - 1})"


def _is_important_decorator(decorator: str) -> bool:
    return any(important in decorator for important in _IMPORTANT_DECORATORS)
