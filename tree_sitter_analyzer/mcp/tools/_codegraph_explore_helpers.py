"""Pure helpers for :mod:`codegraph_explore_tool`.

Split out (a) so the main tool file stays under the project's 500-line
cap and (b) so these utilities are testable without instantiating the
tool — the tests import them directly via the re-export in the main
module's namespace.
"""

from __future__ import annotations

import os
from typing import Any

from ...utils import setup_logger

logger = setup_logger(__name__)

# Tokens shorter than this are noise (e.g. "to", "or", "in").
MIN_TOKEN_LEN = 2

# Recognise file-hint tokens by these markers.
FILE_EXT_MARKERS = (
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".java",
    ".go",
    ".rs",
    ".rb",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".md",
    ".yml",
    ".yaml",
    ".json",
    ".toml",
)


def split_query(query: str) -> tuple[list[str], list[str]]:
    """Return (symbol_tokens, file_tokens) from a whitespace-tokenised query.

    File tokens contain ``/`` or end in a known code extension; everything
    else is treated as a symbol name. Tokens shorter than
    :data:`MIN_TOKEN_LEN` are dropped as noise.
    """
    symbol_tokens: list[str] = []
    file_tokens: list[str] = []
    for raw in query.split():
        tok = raw.strip()
        if len(tok) < MIN_TOKEN_LEN:
            continue
        if "/" in tok or tok.lower().endswith(FILE_EXT_MARKERS):
            file_tokens.append(tok)
        else:
            symbol_tokens.append(tok)
    return symbol_tokens, file_tokens


def resolve_tokens(resolver: Any, tokens: list[str]) -> list[Any]:
    """Resolve each token, dedupe by (file, line), preserve first-seen order."""
    seen: set[tuple[str, int]] = set()
    out: list[Any] = []
    for tok in tokens:
        try:
            res = resolver.resolve(tok)
        except Exception as exc:
            logger.debug(f"resolve({tok!r}) failed: {exc}")
            continue
        for d in getattr(res, "definitions", None) or []:
            key = (d.file, d.line)
            if key in seen:
                continue
            seen.add(key)
            out.append(d)
    return out


def language_of(defs: list[Any]) -> str:
    """First non-empty language string in the definitions, or "" if none."""
    for d in defs:
        lang = getattr(d, "language", "") or ""
        if lang:
            return lang
    return ""


def signature_from(d: Any) -> str:
    """Best-effort signature: ``context`` field if present, else "".

    DefinitionLocation carries an optional ``context`` snippet (the first
    line of the symbol's body in ast_cache) — closest thing to a
    signature without a second SQL lookup.
    """
    ctx = getattr(d, "context", "") or ""
    if isinstance(ctx, str):
        return ctx.strip()
    return ""


def file_size(file_path: str) -> int:
    """Return file size in bytes; 0 if the file is missing/unreadable."""
    try:
        return os.path.getsize(file_path)
    except Exception:
        return 0


def extract_snippet(file_path: str, start_line: int, end_line: int) -> str:
    """Slice ``file_path`` lines [start_line, end_line] (1-based, inclusive).

    Returns an empty string on any failure so the tool degrades to
    outline-only rather than crashing.
    """
    if start_line < 1 or end_line < start_line:
        return ""
    try:
        with open(file_path, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except Exception:
        return ""
    # Clamp to actual file length — defensive against stale line numbers
    # from a re-saved file the AST cache hasn't re-indexed yet.
    last = min(end_line, len(lines))
    if start_line > last:
        return ""
    return "".join(lines[start_line - 1 : last])
