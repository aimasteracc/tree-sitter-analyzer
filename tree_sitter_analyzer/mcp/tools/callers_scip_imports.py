"""Where a TS / JS file's import and export-list statements are, for the SCIP layer.

An import specifier (``import { run } from "./b"``) or an export-list entry
(``export { run }``, ``export { run } from "./b"``) references the target
without calling it, so ``scip_agreement`` does not count it as an unlisted
reference. Such statements can span several lines::

    import {
      a,
      run,
    } from "./b"

A line-start pattern only sees the first line; this module parses the file
with tree-sitter and returns the exact character span of every such statement,
so an occurrence on any line of it is recognised (issue #1892).

Fail-closed: skipping a reference can only hide an unlisted caller, so a span
is returned only when tree-sitter parsed it as one of these statements without
an error inside. An occurrence counts only when it lies inside the span (a
call after the closing ``} from "./b";`` on the same line still counts), and
comments, strings and template literals never open a span. Dynamic
``import("./b")``, ``import x = NS.run`` aliases, ``export default`` and
``export const`` are not covered. An unparseable or unsupported file gives no
spans: every reference in it counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Grammar per file suffix (``.js`` files are parsed as JavaScript with JSX).
_GRAMMARS = {
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
}
#: Children of an export statement that make it an export list / re-export.
_EXPORT_LIST = frozenset({"export_clause", "namespace_export", "*"})
#: Children that make an export statement export a value or a declaration.
_EXPORT_VALUE_FIELDS = ("declaration", "value")


@dataclass(frozen=True)
class Span:
    """A statement's extent; columns are bounds valid in both UTF-16 and code points.

    SCIP columns may count UTF-16 code units or code points. ``start_col`` is
    the larger of the two counts and ``end_col`` the smaller, so an occurrence
    is inside under either unit only when it is inside under both.
    """

    start_line: int
    start_col: int
    end_line: int
    end_col: int

    def covers(self, line: int, col: int, end_line: int, end_col: int) -> bool:
        return self._after_start(line, col) and self._before_end(end_line, end_col)

    def _after_start(self, line: int, col: int) -> bool:
        return line > self.start_line or (
            line == self.start_line and col >= self.start_col
        )

    def _before_end(self, line: int, col: int) -> bool:
        return line < self.end_line or (line == self.end_line and col <= self.end_col)


def grammar_for(path: str) -> str | None:
    """The tree-sitter grammar for a project file, or ``None`` when unsupported."""
    lower = path.lower()
    for suffix, grammar in _GRAMMARS.items():
        if lower.endswith(suffix):
            return grammar
    return None


def import_spans(path: str, lines: list[str]) -> tuple[Span, ...]:
    """Spans of the import / export-list statements in ``lines`` (0-based rows)."""
    grammar = grammar_for(path)
    if grammar is None or not lines:
        return ()
    root = _parse(grammar, "\n".join(lines).encode("utf-8"))
    if root is None:
        return ()
    return tuple(_span(node, lines) for node in _statements(root))


def covers(
    spans: tuple[Span, ...], line: int, col: int, end_line: int, end_col: int
) -> bool:
    """Whether one of ``spans`` contains the occurrence at ``line:col-end_line:end_col``."""
    return any(span.covers(line, col, end_line, end_col) for span in spans)


def _parse(grammar: str, source: bytes) -> Any | None:
    try:
        import tree_sitter

        from ...language_loader import load_language

        language = load_language(grammar)
        if language is None:
            return None
        # A fresh parser: the loader's cached parsers are shared across threads.
        return tree_sitter.Parser(language).parse(source).root_node
    except Exception:  # noqa: BLE001 - no parse: no spans (every reference counts)
        return None


def _statements(root: Any) -> list[Any]:
    found: list[Any] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if _is_import(node):
            found.append(node)
        elif not node.is_error:  # nothing inside an error region is trusted
            stack.extend(node.children)
    return found


def _is_import(node: Any) -> bool:
    if node.has_error:
        return False
    if node.type == "import_statement":
        return True
    if node.type != "export_statement":
        return False
    if any(node.child_by_field_name(f) is not None for f in _EXPORT_VALUE_FIELDS):
        return False
    return any(child.type in _EXPORT_LIST for child in node.children)


def _span(node: Any, lines: list[str]) -> Span:
    (start_row, start_byte), (end_row, end_byte) = node.start_point, node.end_point
    start_cp, start_u16 = _columns(lines[start_row], start_byte)
    end_cp, end_u16 = _columns(lines[end_row], end_byte)
    return Span(start_row, max(start_cp, start_u16), end_row, min(end_cp, end_u16))


def _columns(line: str, byte_col: int) -> tuple[int, int]:
    """``(code points, UTF-16 units)`` before byte column ``byte_col`` of ``line``."""
    prefix = line.encode("utf-8")[:byte_col].decode("utf-8", errors="ignore")
    return len(prefix), len(prefix.encode("utf-16-le")) // 2


__all__ = ["Span", "covers", "grammar_for", "import_spans"]
