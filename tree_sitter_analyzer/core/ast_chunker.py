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


def detect_semantic_boundaries(
    source: str,
    total_lines: int,
) -> list[int]:
    """Detect natural code boundary lines suitable for splitting.

    Returns sorted list of 1-based line numbers where the code has
    natural semantic breaks: blank-line gaps, block comment endings,
    and annotation group boundaries.

    Args:
        source: raw source text
        total_lines: total number of lines in the file

    Returns:
        list of 1-based line numbers representing boundary positions
    """
    if total_lines <= 0:
        return []

    lines = source.split("\n")
    boundaries: set[int] = set()

    # Blank-line gaps: 2+ consecutive blank lines mark a section break
    blank_run_start = -1
    for i, line in enumerate(lines):
        if line.strip() == "":
            if blank_run_start < 0:
                blank_run_start = i
        else:
            if blank_run_start >= 0 and i - blank_run_start >= 2:
                boundaries.add(blank_run_start + 1)
            blank_run_start = -1

    # Block comment endings: */ on its own line marks a section boundary
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "*/" or stripped.endswith("*/") and stripped.startswith("*"):
            if i + 2 < len(lines):
                boundaries.add(i + 2)

    # Annotation groups: line after a run of @annotations
    in_annotation_run = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        is_annotation = stripped.startswith("@")
        if is_annotation:
            in_annotation_run = True
        elif in_annotation_run and stripped:
            boundaries.add(i + 1)
            in_annotation_run = False

    return sorted(boundaries)


def enrich_chunks_with_imports(
    chunks: list[AstChunk],
    import_chunk: AstChunk | None,
    source: str,
) -> list[AstChunk]:
    """Return new chunk list with import context appended to each chunk.

    For each chunk, computes which import lines are referenced by names
    appearing in that chunk's code region. This preserves necessary
    context when chunks are consumed independently.

    Args:
        chunks: existing chunks (not modified)
        import_chunk: the import_block chunk, or None
        source: raw source text

    Returns:
        new list of AstChunk with updated children including import_context
    """
    if not import_chunk:
        return list(chunks)

    lines = source.split("\n")
    import_lines = lines[import_chunk.start_line - 1 : import_chunk.end_line]

    # Build a map of imported symbol -> import line index within the import block
    import_symbols: dict[str, int] = {}
    for offset, line in enumerate(import_lines):
        for word in line.replace(",", " ").split():
            clean = word.strip("(){};*")
            if clean and clean[0].isupper():
                import_symbols[clean] = offset

    enriched: list[AstChunk] = []
    for chunk in chunks:
        if chunk.chunk_type in ("import_block", "header", "tail"):
            enriched.append(chunk)
            continue

        chunk_lines = lines[chunk.start_line - 1 : chunk.end_line]
        chunk_text = " ".join(chunk_lines)

        referenced_offsets: set[int] = set()
        for sym in import_symbols:
            if sym in chunk_text:
                referenced_offsets.add(import_symbols[sym])

        if referenced_offsets:
            import_start = import_chunk.start_line + min(referenced_offsets)
            import_end = import_chunk.start_line + max(referenced_offsets)
            import_ctx = AstChunk(
                name="import_context",
                chunk_type="import_context",
                start_line=import_start,
                end_line=import_end,
                token_estimate=_estimate_tokens(import_start, import_end),
                language=chunk.language,
            )
            enriched.append(
                AstChunk(
                    name=chunk.name,
                    chunk_type=chunk.chunk_type,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    token_estimate=chunk.token_estimate,
                    language=chunk.language,
                    children=chunk.children + (import_ctx,),
                )
            )
        else:
            enriched.append(chunk)

    return enriched
