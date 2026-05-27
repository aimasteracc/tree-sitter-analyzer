"""Pure helpers for :mod:`codegraph_explore_tool`.

Split out (a) so the main tool file stays under the project's 500-line
cap and (b) so these utilities are testable without instantiating the
tool — the tests import them directly via the re-export in the main
module's namespace.
"""

from __future__ import annotations

import json
import os
import re
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

DECLARATION_TERMS = {"class", "const", "enum", "interface", "struct", "type"}


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
    return extract_snippet_from_lines(read_file_lines(file_path), start_line, end_line)


def read_file_lines(file_path: str) -> list[str]:
    """Return all lines for ``file_path`` or [] when unreadable."""
    try:
        with open(file_path, encoding="utf-8", errors="replace") as fh:
            return fh.readlines()
    except Exception:
        return []


def extract_snippet_from_lines(lines: list[str], start_line: int, end_line: int) -> str:
    """Slice an already-read line list without re-opening the file."""
    if start_line < 1 or end_line < start_line:
        return ""
    if not lines:
        return ""
    # Clamp to actual file length — defensive against stale line numbers
    # from a re-saved file the AST cache hasn't re-indexed yet.
    last = min(end_line, len(lines))
    if start_line > last:
        return ""
    return "".join(lines[start_line - 1 : last])


def concept_search(
    cache: Any,
    query_terms: list[str],
    file_tokens: list[str],
    project_root: str,
    max_files: int,
    *,
    max_matches_per_file: int = 5,
    max_file_bytes: int = 1_000_000,
) -> list[dict[str, Any]]:
    """Return ranked file-level matches for concept/natural-language queries."""
    terms = _search_terms(query_terms)
    if not terms:
        return []

    conn = cache._get_conn()
    rows = conn.execute(
        "SELECT file_path, language, file_size, symbols_json FROM ast_index"
    ).fetchall()
    candidate_paths = _concept_candidate_paths(
        conn, terms, file_tokens, max_paths=max(max_files * 25, 50)
    )

    candidates: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        rel_path = row["file_path"]
        if candidate_paths and rel_path not in candidate_paths:
            continue
        if file_tokens and not any(t.lower() in rel_path.lower() for t in file_tokens):
            continue
        if int(row["file_size"] or 0) > max_file_bytes:
            continue
        entry = _concept_file_entry(
            project_root=project_root,
            rel_path=rel_path,
            language=row["language"],
            symbols_json=row["symbols_json"],
            terms=terms,
            max_matches=max_matches_per_file,
        )
        if entry is None:
            continue
        candidates.append((_concept_rank(entry, terms), entry))

    candidates.sort(key=lambda item: (-item[0], item[1]["file_path"]))
    return [entry for _, entry in candidates[:max_files]]


def _concept_candidate_paths(
    conn: Any,
    terms: list[str],
    file_tokens: list[str],
    *,
    max_paths: int,
) -> set[str]:
    """Use structured path/symbol indexes to avoid scanning every file.

    Returns an empty set when no useful candidates are found or when a
    legacy test/cache schema lacks ``ast_symbol_rows``. Callers treat an
    empty set as "fall back to the full scan" so concept search remains
    recall-oriented.
    """
    if not terms and not file_tokens:
        return set()
    if any(term in DECLARATION_TERMS for term in terms):
        return set()
    candidates: set[str] = set()

    def _add_rows(sql: str, params: tuple[Any, ...]) -> None:
        if len(candidates) >= max_paths:
            return
        for row in conn.execute(sql, params).fetchall():
            path = row["file_path"] if hasattr(row, "keys") else row[0]
            candidates.add(str(path))
            if len(candidates) >= max_paths:
                break

    try:
        for token in file_tokens:
            _add_rows(
                "SELECT file_path FROM ast_index WHERE lower(file_path) LIKE ? LIMIT ?",
                (f"%{token.lower()}%", max_paths),
            )
        for term in terms:
            pattern = f"%{term.lower()}%"
            _add_rows(
                "SELECT DISTINCT file_path FROM ast_symbol_rows "
                "WHERE lower(name) LIKE ? LIMIT ?",
                (pattern, max_paths),
            )
            _add_rows(
                "SELECT file_path FROM ast_index WHERE lower(file_path) LIKE ? LIMIT ?",
                (pattern, max_paths),
            )
            if len(candidates) >= max_paths:
                break
    except Exception:
        return set()
    return candidates


def concept_response_payload(
    query: str,
    entries: list[dict[str, Any]],
    *,
    query_terms: int,
) -> dict[str, Any]:
    return {
        "query": query,
        "files": entries,
        "relationship_map": {},
        "stats": {
            "query_terms": query_terms,
            "symbols_resolved": 0,
            "symbols_returned": sum(len(f.get("symbols", [])) for f in entries),
            "files_returned": len(entries),
            "concept_files_returned": len(entries),
        },
        "hint": (
            "no exact symbol definitions matched; returned ranked concept "
            "matches from indexed source files."
        ),
    }


def _search_terms(query_terms: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in query_terms:
        for part in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", raw):
            term = part.lower()
            if len(term) < 3 or term in seen:
                continue
            seen.add(term)
            out.append(term)
    return out


def _concept_file_entry(
    *,
    project_root: str,
    rel_path: str,
    language: str,
    symbols_json: str,
    terms: list[str],
    max_matches: int,
) -> dict[str, Any] | None:
    abs_path = (
        rel_path if os.path.isabs(rel_path) else os.path.join(project_root, rel_path)
    )
    try:
        with open(abs_path, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return None

    raw_matches: list[dict[str, Any]] = []
    for line_no, line in enumerate(lines, start=1):
        lowered = line.lower()
        terms_on_line = [term for term in terms if term in lowered]
        if not terms_on_line:
            continue
        if not _concept_line_satisfies_declaration_query(terms_on_line, terms):
            continue
        raw_matches.append(
            {
                "line": line_no,
                "text": line.strip()[:300],
                "terms": terms_on_line,
            }
        )

    if not raw_matches:
        return None
    scored_matches = [
        (_concept_match_rank(match, terms, lines), match) for match in raw_matches
    ]
    scored_matches.sort(key=lambda item: (-item[0], item[1]["line"]))
    matches = [match for _, match in scored_matches[:max_matches]]
    matches.sort(key=lambda match: int(match["line"]))
    matched_terms = {term for match in matches for term in match.get("terms", [])}
    declaration_symbols = _declaration_symbols_from_matches(lines, matches, terms)
    nearby_symbols = _nearby_symbols(symbols_json, matches)

    return {
        "file_path": rel_path,
        "language": language,
        "symbols": _dedupe_concept_symbols([*declaration_symbols, *nearby_symbols]),
        "matches": matches,
        "matched_terms": sorted(matched_terms),
    }


def _concept_line_satisfies_declaration_query(
    terms_on_line: list[str], terms: list[str]
) -> bool:
    specific_terms = [term for term in terms if term not in DECLARATION_TERMS]
    kind_terms = [
        term
        for term in terms
        if term in DECLARATION_TERMS and term not in {"const", "type"}
    ]
    if specific_terms and not any(term in terms_on_line for term in specific_terms):
        return False
    if kind_terms and not any(term in terms_on_line for term in kind_terms):
        return False
    return True


def _concept_match_rank(
    match: dict[str, Any], terms: list[str], lines: list[str] | None = None
) -> int:
    text = str(match.get("text") or "")
    matched = set(match.get("terms", []))
    rank = len(matched) * 20
    if terms and all(term in matched for term in terms):
        rank += 100
    if _is_definition_like_match(text, terms):
        rank += 80
    line_no = int(match.get("line", 0) or 0)
    source_line = lines[line_no - 1] if lines and 1 <= line_no <= len(lines) else text
    if _declaration_symbol_from_line(source_line, line_no, lines or [], terms):
        rank += 120
    return rank


def _nearby_symbols(
    symbols_json: str, matches: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    try:
        symbols = json.loads(symbols_json).get("symbols", [])
    except Exception:
        return []
    match_lines = [int(m["line"]) for m in matches]
    nearby: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for sym in symbols:
        if _is_noise_nearby_symbol(sym):
            continue
        line = int(sym.get("line", 0) or 0)
        if not line or all(abs(line - ml) > 30 for ml in match_lines):
            continue
        key = (str(sym.get("name", sym.get("text", ""))), line)
        if key in seen:
            continue
        seen.add(key)
        nearby.append(
            {
                "name": key[0],
                "kind": sym.get("kind", "unknown"),
                "start_line": line,
                "end_line": sym.get("end_line", 0),
            }
        )
        if len(nearby) >= 8:
            break
    return nearby


def _declaration_symbols_from_matches(
    lines: list[str],
    matches: list[dict[str, Any]],
    terms: list[str],
) -> list[dict[str, Any]]:
    symbols: list[dict[str, Any]] = []
    for match in matches:
        line_no = int(match.get("line", 0) or 0)
        if line_no < 1 or line_no > len(lines):
            continue
        symbol = _declaration_symbol_from_line(
            lines[line_no - 1], line_no, lines, terms
        )
        if symbol:
            symbols.append(symbol)
    symbols.sort(
        key=lambda symbol: (
            _term_position(symbol.get("name", ""), terms),
            symbol["start_line"],
        )
    )
    return symbols


def _term_position(name: object, terms: list[str]) -> int:
    lowered = str(name or "").lower()
    try:
        return terms.index(lowered)
    except ValueError:
        return len(terms)


def _declaration_symbol_from_line(
    line: str,
    line_no: int,
    lines: list[str],
    terms: list[str],
) -> dict[str, Any] | None:
    stripped = line.strip()
    patterns = (
        (r"^type\s+([A-Za-z_][A-Za-z0-9_]*)\b", "type"),
        (r"^const\s+([A-Za-z_][A-Za-z0-9_]*)\b", "constant"),
        (r"^(?:var|let)\s+([A-Za-z_][A-Za-z0-9_]*)\b", "variable"),
        (
            r"^(?:export\s+)?(?:class|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)\b",
            "type",
        ),
    )
    for pattern, kind in patterns:
        match = re.search(pattern, stripped)
        if not match:
            continue
        name = match.group(1)
        if terms and name.lower() not in terms:
            continue
        end_line = _declaration_end_line(lines, line_no)
        code = (
            extract_snippet_from_lines(lines, line_no, end_line) if lines else stripped
        )
        return {
            "name": name,
            "kind": kind,
            "start_line": line_no,
            "end_line": end_line,
            "code": code,
        }
    block_symbol = _block_member_declaration_symbol(stripped, line_no, lines, terms)
    if block_symbol:
        return block_symbol
    return None


def _block_member_declaration_symbol(
    stripped: str,
    line_no: int,
    lines: list[str],
    terms: list[str],
) -> dict[str, Any] | None:
    if not lines or not stripped or stripped.startswith(("//", ")")):
        return None
    name_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\b", stripped)
    if not name_match:
        return None
    name = name_match.group(1)
    if terms and name.lower() not in terms:
        return None
    bounds = _block_declaration_bounds(lines, line_no)
    if bounds is None:
        return None
    block_start, block_end, kind = bounds
    return {
        "name": name,
        "kind": kind,
        "start_line": line_no,
        "end_line": block_end,
        "code": extract_snippet_from_lines(lines, block_start, block_end),
    }


def _block_declaration_bounds(
    lines: list[str], line_no: int
) -> tuple[int, int, str] | None:
    if line_no < 1 or line_no > len(lines):
        return None
    start = line_no - 1
    while start >= 0:
        stripped = lines[start].strip()
        if re.match(r"^(const|var)\s*\(", stripped):
            kind = "constant" if stripped.startswith("const") else "variable"
            break
        if stripped in {"}", ")"}:
            return None
        start -= 1
    else:
        return None

    end = start
    while end < len(lines):
        if lines[end].strip().startswith(")"):
            return start + 1, end + 1, kind
        end += 1
    return start + 1, line_no, kind


def _declaration_end_line(lines: list[str], start_line: int) -> int:
    if not lines or start_line < 1 or start_line > len(lines):
        return start_line
    brace_balance = 0
    saw_open = False
    for idx in range(start_line - 1, min(len(lines), start_line + 80)):
        line = lines[idx]
        brace_balance += line.count("{")
        if "{" in line:
            saw_open = True
        brace_balance -= line.count("}")
        if saw_open and brace_balance <= 0:
            return idx + 1
    return start_line


def _dedupe_concept_symbols(symbols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for symbol in symbols:
        key = (str(symbol.get("name") or ""), int(symbol.get("start_line", 0) or 0))
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        out.append(symbol)
    return out


def _concept_rank(entry: dict[str, Any], terms: list[str]) -> int:
    path = entry["file_path"].lower()
    matched = set(entry.get("matched_terms", []))
    rank = len(matched) * 100
    if terms and all(term in matched for term in terms):
        rank += 100
    rank += sum(60 for term in terms if term in path)
    rank += min(len(entry.get("matches", [])), 5) * 3
    if any(
        _is_definition_like_match(m.get("text", ""), terms)
        for m in entry.get("matches", [])
    ):
        rank += 70
    if any(
        symbol.get("kind") in {"constant", "type", "variable"}
        for symbol in entry.get("symbols", [])
    ):
        rank += 180
    if path.startswith("src/"):
        rank += 40
    if any(part in path for part in ("/test/", "/tests/", "/fixtures/", "/gen/")):
        rank -= 80
    if _is_test_like_path(path):
        rank -= 80
    if "/copilot/" in path:
        rank -= 40
    return rank


def _is_definition_like_match(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    if not any(term in lowered for term in terms):
        return False
    return bool(
        re.search(
            r"\b(export\s+)?(abstract\s+)?"
            r"(class|interface|function|const|let|var|type|enum|func|struct)\b",
            lowered,
        )
    )


def _is_noise_nearby_symbol(symbol: dict[str, Any]) -> bool:
    kind = str(symbol.get("kind", "")).lower()
    name = str(symbol.get("name", "")).strip().lower()
    return kind in {"import", "package", "module"} or name.startswith("import (")


def _is_test_like_path(path: str) -> bool:
    name = os.path.basename(path)
    return bool(
        name.startswith("test_")
        or "_test." in name
        or name.endswith(".test")
        or name.endswith(".spec.ts")
        or name.endswith(".test.ts")
        or name.endswith(".spec.js")
        or name.endswith(".test.js")
    )
