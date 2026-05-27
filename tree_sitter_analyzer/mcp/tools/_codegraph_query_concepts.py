"""Concept-search fallback helpers for chained CodeGraph queries."""

from __future__ import annotations

import re
from typing import Any

from . import _codegraph_explore_helpers as _h

_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_QUERY_STOPWORDS = {
    "abstract",
    "async",
    "await",
    "class",
    "const",
    "def",
    "defer",
    "else",
    "enum",
    "export",
    "extends",
    "false",
    "for",
    "func",
    "function",
    "if",
    "implements",
    "import",
    "interface",
    "let",
    "nil",
    "null",
    "package",
    "private",
    "protected",
    "public",
    "range",
    "return",
    "static",
    "struct",
    "this",
    "true",
    "type",
    "var",
    "void",
}


def concept_entries_for_queries(
    cache: Any,
    queries: list[str],
    *,
    project_root: str,
    max_files: int,
) -> list[dict[str, Any]]:
    """Return file-level concept matches for unresolved chain seeds."""
    query_terms, file_tokens = _split_seed_queries(queries)
    if not query_terms and not file_tokens:
        return []
    return _h.concept_search(
        cache,
        query_terms,
        file_tokens,
        project_root,
        max_files,
    )


def symbol_candidate_tokens(query: str) -> list[str]:
    """Return high-signal resolver tokens for code-like query strings."""
    declared_type = _declared_type_name(query)
    if declared_type:
        return [declared_type]
    declared_const = _declared_const_name(query)
    terms = normalized_query_terms(query)
    if not terms:
        return [query] if query else []
    if declared_const:
        return _dedupe_tokens([declared_const, *terms])
    primary = _primary_signature_terms(query, terms)
    return _dedupe_tokens([*primary, *terms])


def normalized_query_terms(query: str) -> list[str]:
    """Extract identifier-like query terms while dropping syntax noise."""
    symbol_tokens, file_tokens = _h.split_query(query)
    file_token_parts = {
        part.lower()
        for file_token in file_tokens
        for part in _IDENTIFIER_RE.findall(file_token)
    }
    ignored = _receiver_variable_terms(query)
    terms: list[str] = []
    for raw in [*symbol_tokens, *_IDENTIFIER_RE.findall(query)]:
        token = _clean_identifier(raw)
        if not token:
            continue
        if token.lower() in file_token_parts:
            continue
        if token.lower() in _QUERY_STOPWORDS or token in ignored:
            continue
        terms.append(token)
    return _dedupe_tokens(terms)


def concept_query_terms(query: str) -> list[str]:
    """Return terms for source concept search, including declaration hints."""
    declared_type = _declared_type_name(query)
    if declared_type:
        return _dedupe_tokens([declared_type, *_declaration_hint_terms(query)])
    declared_const = _declared_const_name(query)
    normalized_terms = normalized_query_terms(query)
    if declared_const:
        return _dedupe_tokens(
            [
                declared_const,
                *normalized_terms,
                *_const_declaration_hint_terms(
                    query, [declared_const, *normalized_terms]
                ),
            ]
        )
    return _dedupe_tokens(
        [
            *normalized_terms,
            *_const_declaration_hint_terms(query, normalized_terms),
            *_declaration_hint_terms(query),
        ]
    )


def symbols_from_concept_entries(
    entries: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Lift nearby concept-search symbols into the query chain state."""
    symbols: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for entry in entries:
        file_path = str(entry.get("file_path") or "")
        language = str(entry.get("language") or "")
        for symbol in entry.get("symbols", []):
            line = int(symbol.get("start_line", 0) or 0)
            name = str(symbol.get("name") or "")
            if not file_path or not line or not name:
                continue
            key = (file_path, line, name)
            if key in seen:
                continue
            seen.add(key)
            symbols.append(
                {
                    "name": name,
                    "kind": symbol.get("kind", "unknown"),
                    "file": file_path,
                    "line": line,
                    "end_line": int(symbol.get("end_line", line) or line),
                    "language": language,
                }
            )
            if len(symbols) >= limit:
                return symbols
    return symbols


def _split_seed_queries(queries: list[str]) -> tuple[list[str], list[str]]:
    query_terms: list[str] = []
    file_tokens: list[str] = []
    seen_terms: set[str] = set()
    seen_files: set[str] = set()
    for query in queries:
        _, files = _h.split_query(query)
        for symbol in concept_query_terms(query):
            token = symbol.strip()
            if token and token not in seen_terms:
                seen_terms.add(token)
                query_terms.append(token)
        for file_token in files:
            token = file_token.strip()
            if token and token not in seen_files:
                seen_files.add(token)
                file_tokens.append(token)
    return query_terms, file_tokens


def _clean_identifier(raw: str) -> str:
    match = _IDENTIFIER_RE.search(raw)
    return match.group(0) if match else ""


def _receiver_variable_terms(query: str) -> set[str]:
    ignored: set[str] = set()
    for match in re.finditer(
        r"\(\s*([a-z_][A-Za-z0-9_]*)\s+(?:\*|\.\*)?[A-Za-z_][A-Za-z0-9_]*",
        query,
    ):
        ignored.add(match.group(1))
    return ignored


def _primary_signature_terms(query: str, terms: list[str]) -> list[str]:
    primary: list[str] = []
    primary.extend(
        _clean_identifier(match.group(1))
        for match in re.finditer(r"\)\s*([A-Za-z_][A-Za-z0-9_]*)", query)
    )
    primary.extend(
        _clean_identifier(match.group(1))
        for match in re.finditer(
            r"\b(?:def|func|function)\s+([A-Za-z_][A-Za-z0-9_]*)",
            query,
        )
    )
    if terms:
        primary.append(terms[-1])
    return [term for term in primary if term]


def _declared_type_name(query: str) -> str:
    match = re.search(r"\btype\s+([A-Za-z_][A-Za-z0-9_]*)\b", query)
    return match.group(1) if match else ""


def _declared_const_name(query: str) -> str:
    match = re.search(r"\b(?:const|var|let)\s+([A-Za-z_][A-Za-z0-9_]*)\b", query)
    if match:
        return match.group(1)
    if not re.search(r"\biota\b", query):
        return ""
    match = re.search(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\b", query)
    return match.group(1) if match else ""


def _const_declaration_hint_terms(query: str, terms: list[str]) -> list[str]:
    if re.search(r"\biota\b", query):
        return ["const"]
    if (
        len(terms) >= 2
        and _is_lower_camel(terms[0])
        and any(term.lower().endswith("type") for term in terms[1:])
    ):
        return ["const"]
    return []


def _is_lower_camel(token: str) -> bool:
    return bool(re.match(r"^[a-z][A-Za-z0-9]*[A-Z][A-Za-z0-9]*$", token))


def _declaration_hint_terms(query: str) -> list[str]:
    hints: list[str] = []
    lowered = query.lower()
    if re.search(r"\btype\b", lowered):
        hints.append("type")
    for keyword in ("struct", "interface", "class", "enum"):
        if re.search(rf"\b{keyword}\b", lowered):
            hints.append(keyword)
    return hints


def _dedupe_tokens(tokens: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(token)
    return out


__all__ = [
    "concept_query_terms",
    "concept_entries_for_queries",
    "normalized_query_terms",
    "symbol_candidate_tokens",
    "symbols_from_concept_entries",
]
