#!/usr/bin/env python3
"""
AST-aware chunking service for large file analysis.

Splits AnalysisResult elements into semantic chunks based on
language-specific AST boundaries. Each chunk represents a meaningful
code unit (class, function, top-level block) with line range and
estimated token count.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)
from ..models import CodeElement

# Average tokens per line of code (conservative estimate for LLM context budgeting)
TOKENS_PER_LINE = 4

# Languages that group methods inside classes (OOP-first)
_OOP_LANGUAGES = frozenset({"java", "csharp", "kotlin", "scala"})

# Languages with both classes and top-level functions
_SCRIPT_LANGUAGES = frozenset({"python", "javascript", "typescript", "ruby", "php"})

# Languages where functions are top-level only (no class nesting)
_FUNCTION_LANGUAGES = frozenset({"go", "rust", "c", "cpp"})

# All recognized languages for chunking
_ALL_CHUNKABLE = _OOP_LANGUAGES | _SCRIPT_LANGUAGES | _FUNCTION_LANGUAGES


@dataclass(frozen=True)
class AstChunk:
    """A semantic chunk of code, derived from AST boundaries."""

    name: str
    chunk_type: str  # "class", "function", "import_block", "header", "tail"
    start_line: int
    end_line: int
    token_estimate: int
    language: str = ""
    children: tuple[AstChunk, ...] = ()

    @property
    def line_span(self) -> int:
        return self.end_line - self.start_line + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.chunk_type,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "line_span": self.line_span,
            "tokens": self.token_estimate,
            "children": [c.to_dict() for c in self.children],
        }


def _estimate_tokens(start_line: int, end_line: int) -> int:
    return max(1, (end_line - start_line + 1) * TOKENS_PER_LINE)


def _build_import_chunk(
    imports: Sequence[CodeElement], total_lines: int
) -> AstChunk | None:
    if not imports:
        return None
    start = min(e.start_line for e in imports)
    end = max(e.end_line for e in imports)
    return AstChunk(
        name="imports",
        chunk_type="import_block",
        start_line=start,
        end_line=end,
        token_estimate=_estimate_tokens(start, end),
    )


def _build_class_chunks(
    classes: Sequence[CodeElement],
    methods: Sequence[CodeElement],
    fields: Sequence[CodeElement],
    language: str,
) -> list[AstChunk]:
    chunks: list[AstChunk] = []
    for cls in classes:
        cls_start = cls.start_line
        cls_end = cls.end_line

        cls_methods = sorted(
            [m for m in methods if cls_start <= m.start_line <= cls_end],
            key=lambda m: m.start_line,
        )
        children: list[AstChunk] = []
        for m in cls_methods:
            children.append(
                AstChunk(
                    name=m.name,
                    chunk_type="method",
                    start_line=m.start_line,
                    end_line=m.end_line,
                    token_estimate=_estimate_tokens(m.start_line, m.end_line),
                    language=language,
                )
            )

        chunks.append(
            AstChunk(
                name=cls.name,
                chunk_type="class",
                start_line=cls_start,
                end_line=cls_end,
                token_estimate=_estimate_tokens(cls_start, cls_end),
                language=language,
                children=tuple(children),
            )
        )
    return chunks


def _build_function_chunks(
    methods: Sequence[CodeElement],
    class_ranges: list[tuple[int, int]],
    language: str,
) -> list[AstChunk]:
    top_level = [
        m
        for m in methods
        if not any(s <= m.start_line <= e for s, e in class_ranges)
    ]
    return [
        AstChunk(
            name=m.name,
            chunk_type="function",
            start_line=m.start_line,
            end_line=m.end_line,
            token_estimate=_estimate_tokens(m.start_line, m.end_line),
            language=language,
        )
        for m in sorted(top_level, key=lambda m: m.start_line)
    ]


def _build_header_chunk(
    import_chunk: AstChunk | None,
    first_element_line: int,
    total_lines: int,
    language: str,
) -> AstChunk | None:
    header_end = import_chunk.end_line + 1 if import_chunk else first_element_line
    if header_end <= 1 or header_end > total_lines:
        return None
    return AstChunk(
        name="header",
        chunk_type="header",
        start_line=1,
        end_line=header_end - 1,
        token_estimate=_estimate_tokens(1, header_end - 1),
        language=language,
    )


def _build_tail_chunk(
    chunks: list[AstChunk], total_lines: int, language: str
) -> AstChunk | None:
    if not chunks:
        return None
    max_end = max(c.end_line for c in chunks)
    if max_end >= total_lines:
        return None
    return AstChunk(
        name="tail",
        chunk_type="tail",
        start_line=max_end + 1,
        end_line=total_lines,
        token_estimate=_estimate_tokens(max_end + 1, total_lines),
        language=language,
    )


def _chunk_oop(
    elements: Sequence[CodeElement],
    total_lines: int,
    language: str,
) -> list[AstChunk]:
    classes = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_CLASS)]
    methods = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)]
    fields = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_VARIABLE)]
    imports = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_IMPORT)]

    import_chunk = _build_import_chunk(imports, total_lines)
    class_chunks = _build_class_chunks(classes, methods, fields, language)

    first_element_line = total_lines
    if class_chunks:
        first_element_line = min(c.start_line for c in class_chunks)
    elif import_chunk:
        first_element_line = import_chunk.end_line + 1

    header = _build_header_chunk(import_chunk, first_element_line, total_lines, language)
    tail = _build_tail_chunk(class_chunks, total_lines, language)

    result: list[AstChunk] = []
    if header:
        result.append(header)
    if import_chunk:
        result.append(import_chunk)
    result.extend(class_chunks)
    if tail:
        result.append(tail)
    return result


def _chunk_script(
    elements: Sequence[CodeElement],
    total_lines: int,
    language: str,
) -> list[AstChunk]:
    classes = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_CLASS)]
    methods = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)]
    fields = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_VARIABLE)]
    imports = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_IMPORT)]

    import_chunk = _build_import_chunk(imports, total_lines)
    class_ranges = [(c.start_line, c.end_line) for c in classes]
    class_chunks = _build_class_chunks(classes, methods, fields, language)
    function_chunks = _build_function_chunks(methods, class_ranges, language)

    all_body = class_chunks + function_chunks
    first_element_line = total_lines
    if all_body:
        first_element_line = min(c.start_line for c in all_body)
    elif import_chunk:
        first_element_line = import_chunk.end_line + 1

    header = _build_header_chunk(import_chunk, first_element_line, total_lines, language)
    tail = _build_tail_chunk(all_body, total_lines, language)

    result: list[AstChunk] = []
    if header:
        result.append(header)
    if import_chunk:
        result.append(import_chunk)
    result.extend(all_body)
    if tail:
        result.append(tail)
    return result


def _chunk_function_lang(
    elements: Sequence[CodeElement],
    total_lines: int,
    language: str,
) -> list[AstChunk]:
    return _chunk_script(elements, total_lines, language)


def _chunk_default(
    elements: Sequence[CodeElement],
    total_lines: int,
    language: str,
) -> list[AstChunk]:
    return _chunk_script(elements, total_lines, language)


def chunk_analysis_result(
    elements: Sequence[CodeElement],
    total_lines: int,
    language: str,
) -> list[AstChunk]:
    """Split analysis elements into semantic AST-based chunks.

    Args:
        elements: Extracted code elements from analysis
        total_lines: Total line count of the source file
        language: Programming language identifier

    Returns:
        Ordered list of AstChunk objects covering the file
    """
    if not elements or total_lines <= 0:
        return []

    lang = language.lower()

    if lang in _OOP_LANGUAGES:
        return _chunk_oop(elements, total_lines, lang)
    if lang in _SCRIPT_LANGUAGES:
        return _chunk_script(elements, total_lines, lang)
    if lang in _FUNCTION_LANGUAGES:
        return _chunk_function_lang(elements, total_lines, lang)
    return _chunk_default(elements, total_lines, lang)


def chunks_summary(chunks: Sequence[AstChunk]) -> dict[str, Any]:
    """Produce a summary dict from a list of chunks for MCP responses."""
    if not chunks:
        return {"chunk_count": 0, "total_tokens": 0, "chunks": []}

    return {
        "chunk_count": len(chunks),
        "total_tokens": sum(c.token_estimate for c in chunks),
        "chunks": [c.to_dict() for c in chunks],
    }
