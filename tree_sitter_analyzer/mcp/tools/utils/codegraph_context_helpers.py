"""Code-graph context helpers — Phase 3 REQ-CLEAN-002.

Context collection, graph operation, and entry-point ranking helpers
for CodeGraphContextTool.

Functions:
    _bounded_int, _coerce_bool
    _extract_symbol_candidates, _compound_candidates
    _normalise_hit, _nodes_from_hits, _node_from_ref, _node_id
    _safe_refs, _callee_ref_to_hit, _caller_ref_to_hit, _safe_chain
    _build_code_blocks, _edge_degrees, _unique_files
    _entry_rank, _name_match_score, _entry_rank_v2
"""

from __future__ import annotations

import os
import re
from typing import Any

from .._codegraph_explore_helpers import extract_snippet_from_lines, read_file_lines

# --- constants (used by helpers in this module) ---

_STOP_WORDS = frozenset(
    "a an and are as at by call calls does flow for from how in into is of on "
    "or through to trace what when where which why with work works "
    "like the per this that via than then such these those be been also just "
    "only about after before between within "
    "server client action call right tool type item node list data code file "
    "request response result output input value kind line".split()
)

_GENERIC_VERBS = frozenset(
    "dispatch dispatcher handle handler process processor run runner execute "
    "executor get set send receive emit notify invoke route resolve register "
    "lookup parse load store update fetch".split()
)

_CODE_FILE_EXT = (
    "py|pyi|js|jsx|ts|tsx|go|rs|java|kt|kts|c|h|hpp|cpp|cc|cs|rb|php|swift|"
    "scala|m|mm|sh|sql|lua|dart|ex|exs|clj|hs|ml"
)
_PATH_FRAGMENT_RE = re.compile(
    rf"[\w.\-]*[\\/][\w.\\/\-]*|\b[\w\-]+\.(?:{_CODE_FILE_EXT})\b",
    re.IGNORECASE,
)
_PATH_COMPONENT_SPLIT = re.compile(r"[\\/.:\-]+")

_MAX_BLOCK_LINES = 16
_MAX_ENTRY_BODY_LINES = 160
_MAX_INLINE_EDGES = 12
_MAX_INLINE_NODES = 12
_MAX_INLINE_ENTRY_POINTS = 6

_FALSEY_STRINGS = frozenset({"false", "0", "no", "off", "none", "null", ""})


# --- coercion helpers ---


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = minimum
    return max(minimum, min(maximum, parsed))


def _coerce_bool(value: Any, default: bool = False) -> bool:
    """Coerce an MCP/CLI argument to bool, honouring JS-style string booleans."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in _FALSEY_STRINGS
    return bool(value)


# --- symbol candidate extraction ---


def _extract_symbol_candidates(task: str) -> list[str]:
    tokens = re.findall(
        r"`[^`]+`|\"[^\"]+\"|'[^']+'|[A-Za-z_][A-Za-z0-9_.]*",
        task,
    )
    seen: set[str] = set()
    out: list[str] = []
    for raw in tokens:
        was_quoted = raw[:1] in "`\"'"
        raw = raw.strip("`\"'")
        for part in re.split(r"[.:\->]+", raw):
            token = part.strip("_.,;:!?()[]{}")
            if not token:
                continue
            lowered = token.lower()
            is_plain_prose = token == lowered and not was_quoted
            if (lowered in _STOP_WORDS and is_plain_prose) or len(token) < 3:
                continue
            if not (
                "_" in token or any(ch.isupper() for ch in token) or len(token) >= 4
            ):
                continue
            if token not in seen:
                seen.add(token)
                out.append(token)

    def _is_specific(tok: str) -> bool:
        return "_" in tok or any(ch.isupper() for ch in tok)

    def _named_explicitly(verb: str) -> bool:
        pattern = (
            r"(?:[`'\"]|\.|::|->)\s*"
            + re.escape(verb)
            + r"\b|\b"
            + re.escape(verb)
            + r"\s*\("
        )
        return bool(re.search(pattern, task, re.IGNORECASE))

    path_tokens: set[str] = set()
    for match in _PATH_FRAGMENT_RE.finditer(task):
        for part in _PATH_COMPONENT_SPLIT.split(match.group(0)):
            cleaned = part.strip("_")
            if cleaned:
                path_tokens.add(part)
                path_tokens.add(cleaned)

    def _is_anchor(tok: str) -> bool:
        if tok in path_tokens:
            return False
        return _is_specific(tok) or _named_explicitly(tok)

    if any(_is_anchor(tok) for tok in out):
        out = [
            tok
            for tok in out
            if _is_specific(tok)
            or tok.lower() not in _GENERIC_VERBS
            or _named_explicitly(tok)
        ]
    return out


def _compound_candidates(candidates: list[str]) -> list[str]:
    """Build camelCase joins of ordered task-word pairs."""
    words = [c for c in candidates if len(c) >= 3][:6]
    out: list[str] = []
    seen: set[str] = set()
    existing = {c.lower() for c in candidates}
    for i, a in enumerate(words):
        for j, b in enumerate(words):
            if i == j:
                continue
            joined = a[0].lower() + a[1:] + b[0].upper() + b[1:]
            low = joined.lower()
            if low in seen or low in existing:
                continue
            seen.add(low)
            out.append(joined)
    return out[:12]


# --- node / hit helpers ---


def _normalise_hit(hit: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": hit.get("name", ""),
        "kind": hit.get("kind", "unknown"),
        "file": hit.get("file") or hit.get("file_path", ""),
        "line": int(hit.get("line", 0) or 0),
        "end_line": int(hit.get("end_line", 0) or 0),
        "language": hit.get("language", ""),
    }


def _nodes_from_hits(
    hits: list[dict[str, Any]], max_nodes: int
) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()
    for hit in hits:
        if len(nodes) >= max_nodes:
            break
        node = _node_from_ref(hit)
        node["is_entry"] = True
        key = (node["name"], node.get("file", ""), node.get("line", 0))
        if key in seen:
            continue
        seen.add(key)
        nodes.append(node)
    return nodes


def _node_from_ref(ref: dict[str, Any]) -> dict[str, Any]:
    hit = _normalise_hit(ref)
    node: dict[str, Any] = {
        "id": _node_id(hit["name"], hit["file"], hit["line"]),
        "name": hit["name"],
        "kind": hit["kind"],
        "file": hit["file"],
        "line": hit["line"],
    }
    if hit["end_line"] >= hit["line"] > 0:
        node["end_line"] = hit["end_line"]
    if hit["language"]:
        node["language"] = hit["language"]
    return node


def _node_id(name: str, file_path: str, line: int) -> str:
    return f"{os.path.basename(file_path)}:{name}:{line}"


def _safe_refs(
    callable_obj: Any, name: str, file_path: str | None
) -> list[dict[str, Any]]:
    try:
        return callable_obj(name, file_path) or []
    except Exception:
        try:
            return callable_obj(name) or []
        except Exception:
            return []


def _callee_ref_to_hit(ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": ref.get("callee_name", ""),
        "kind": "function",
        "file": ref.get("callee_file", ""),
        "line": int(ref.get("callee_line", 0) or 0),
        "end_line": 0,
        "language": "",
    }


def _caller_ref_to_hit(ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": ref.get("caller_name", ""),
        "kind": "function",
        "file": ref.get("caller_file", ""),
        "line": int(ref.get("caller_line", 0) or 0),
        "end_line": 0,
        "language": "",
    }


def _safe_chain(
    graph: Any, name: str, file_path: str | None, depth: int
) -> list[dict[str, Any]]:
    try:
        return graph.call_chain(name, file_path=file_path, depth=depth) or []
    except Exception:
        try:
            return graph.call_chain(name, depth=depth) or []
        except Exception:
            return []


def _build_code_blocks(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    max_code_blocks: int,
    project_root: str,
) -> list[dict[str, Any]]:
    if max_code_blocks <= 0:
        return []
    degrees = _edge_degrees(nodes, edges)
    ranked = sorted(
        nodes,
        key=lambda n: (
            not n.get("is_entry", False),
            -degrees.get(n["id"], 0),
            n.get("line", 0),
        ),
    )
    blocks: list[dict[str, Any]] = []
    seen_files_lines: set[tuple[str, int]] = set()
    for node in ranked:
        if len(blocks) >= max_code_blocks:
            break
        file_path = node.get("file", "")
        start_line = int(node.get("line", 0) or 0)
        if not file_path or start_line < 1:
            continue
        dedupe_key = (file_path, start_line)
        if dedupe_key in seen_files_lines:
            continue
        seen_files_lines.add(dedupe_key)
        abs_path = (
            file_path
            if os.path.isabs(file_path)
            else os.path.join(project_root, file_path)
        )
        lines = read_file_lines(abs_path)
        if not lines:
            continue
        raw_end = int(node.get("end_line", 0) or 0)
        end_known = raw_end >= start_line
        block_cap = _MAX_ENTRY_BODY_LINES if node.get("is_entry") else _MAX_BLOCK_LINES
        full_end = raw_end if end_known else start_line + block_cap - 1
        capped_end = min(full_end, start_line + block_cap - 1)
        capped_end = min(capped_end, len(lines))
        content = extract_snippet_from_lines(lines, start_line, capped_end)
        if not content:
            continue
        if end_known:
            real_end = min(full_end, len(lines))
            if real_end > capped_end:
                content = (
                    content.rstrip("\n")
                    + f"\n    # … {real_end - capped_end} more lines "
                    f"({file_path}:{capped_end + 1}-{real_end})\n"
                )
        elif capped_end < len(lines):
            content = (
                content.rstrip("\n")
                + f"\n    # … snippet capped at {block_cap} lines; "
                f"end unknown — read {file_path}:{capped_end + 1}+ if needed\n"
            )
        blocks.append(
            {
                "file": file_path,
                "name": node["name"],
                "start_line": start_line,
                "end_line": capped_end,
                "content": content,
            }
        )
    return blocks


def _edge_degrees(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> dict[str, int]:
    degrees = {node["id"]: 0 for node in nodes}
    for edge in edges:
        if edge["source"] in degrees:
            degrees[edge["source"]] += 1
        if edge["target"] in degrees:
            degrees[edge["target"]] += 1
    return degrees


def _unique_files(nodes: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for node in nodes:
        file_path = node.get("file", "")
        if file_path and file_path not in seen:
            seen.add(file_path)
            out.append(file_path)
    return out


# --- ranking helpers ---


def _is_test_file(file_path: str) -> int:
    """Rank-tier wrapper: 1 for test files, 0 otherwise."""
    from ....utils.test_detection import is_test_file as _shared

    return 1 if _shared(file_path) else 0


def _is_non_prod_file(file_path: str) -> int:
    """Rank-tier wrapper: 1 for non-production files, 0 otherwise."""
    from ....test_gap_analyzer import _NON_PROD_DIRS as _shared_dirs

    lowered = file_path.lower().replace("\\", "/")
    return 1 if any(d in lowered for d in _shared_dirs) else 0


def _entry_rank(hit: dict[str, Any]) -> tuple[int, int, str, int]:
    file_path = hit.get("file", "")
    is_test = _is_test_file(file_path)
    kind_rank = 0 if hit.get("kind") in {"class", "function", "method"} else 1
    return (is_test, kind_rank, hit.get("file", ""), int(hit.get("line", 0) or 0))


def _name_match_score(name: str, candidates: list[str]) -> int:
    """Count how many task candidates appear inside a symbol name."""
    if not name:
        return 0
    lowered = name.lower()
    score = 0
    for cand in candidates:
        c = cand.lower()
        if len(c) >= 3 and c in lowered:
            score += 1
    return score


def _entry_rank_v2(
    entry: dict[str, Any],
    candidates: list[str],
    wants_tests: bool = False,
) -> tuple[int, int, int, int, int, int, str, int]:
    """Relevance-aware ranking key for an aggregated entry-point hit."""
    hit = entry["hit"]
    file_path = hit.get("file", "")
    non_prod_tier = 0 if wants_tests else _is_non_prod_file(file_path)
    test_tier = 0 if wants_tests else _is_test_file(file_path)
    kind_rank = 0 if hit.get("kind") in {"class", "function", "method"} else 1
    name_match = _name_match_score(hit.get("name", ""), candidates)
    return (
        non_prod_tier,
        test_tier,
        kind_rank,
        -name_match,
        -int(entry.get("matches", 0)),
        int(entry.get("best_rank", 0)),
        file_path,
        int(hit.get("line", 0) or 0),
    )


# --- entry-point resolution from cache ---


def _resolve_entry_points_from_cache(
    cache: Any,
    candidates: list[str],
    limit: int,
    wants_tests: bool = False,
) -> list[dict[str, Any]]:
    """Resolve entry-point hits from an ASTCache using BM25 + cascade fallback."""
    fetch = max(limit * 3, limit)
    agg: dict[tuple[str, str, int], dict[str, Any]] = {}

    def _absorb(raw_hits: list[Any]) -> int:
        usable = 0
        for bm25_rank, raw in enumerate(raw_hits):
            hit = _normalise_hit(raw)
            if not hit["name"] or hit["kind"] == "import":
                continue
            usable += 1
            key = (hit["name"], hit["file"], hit["line"])
            entry = agg.get(key)
            if entry is None:
                agg[key] = {"hit": hit, "matches": 1, "best_rank": bm25_rank}
            else:
                entry["matches"] += 1
                if bm25_rank < entry["best_rank"]:
                    entry["best_rank"] = bm25_rank
        return usable

    cascade = getattr(cache, "search_symbols_cascade", None)
    for candidate in candidates[:10]:
        try:
            raw_hits = cache.fts_search_ranked(candidate, limit=fetch) or []
        except Exception:
            try:
                raw_hits = cache.fts_search(candidate, limit=fetch) or []
            except Exception:
                raw_hits = []
        if _absorb(raw_hits) == 0 and callable(cascade):
            try:
                cascade_hits = cascade(candidate, limit=fetch) or []
            except Exception:
                cascade_hits = []
            _absorb(cascade_hits)

    if callable(cascade):
        for compound in _compound_candidates(candidates):
            try:
                raw_hits = cascade(compound, limit=limit) or []
            except Exception:
                raw_hits = []
            _absorb(raw_hits)

    ranked = sorted(
        agg.values(),
        key=lambda e: _entry_rank_v2(e, candidates, wants_tests),
    )
    return [e["hit"] for e in ranked[:limit]]


# --- edge building helpers ---


def _add_edge(
    source: dict[str, Any],
    target_name: str,
    target_file: str,
    by_key: dict,
    by_name: dict,
    edges: list,
    seen: set,
    line: int,
) -> None:
    target = by_key.get((target_name, target_file))
    if target is None:
        matches = by_name.get(target_name, [])
        target = matches[0] if matches else None
    if target is None or target["id"] == source["id"]:
        return
    edge_key = (source["id"], target["id"])
    if edge_key in seen:
        return
    seen.add(edge_key)
    edges.append(
        {"source": source["id"], "target": target["id"], "kind": "calls", "line": line}
    )


def _build_edges_from_graph(
    graph: Any, nodes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Build call edges between nodes using the call graph."""
    by_key = {(n["name"], n.get("file", "")): n for n in nodes}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        by_name.setdefault(node["name"], []).append(node)

    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for node in nodes:
        is_edge_store = hasattr(graph, "query_callees")
        if is_edge_store:
            callees = graph.query_callees(node["name"], node.get("file") or None) or []
            for ref in callees:
                callee = _callee_ref_to_hit(ref)
                _add_edge(
                    node,
                    callee["name"],
                    callee["file"],
                    by_key,
                    by_name,
                    edges,
                    seen,
                    ref.get("callee_line", 0),
                )
        else:
            for ref in _safe_refs(
                graph.callees_of, node["name"], node.get("file") or None
            ):
                callee = _normalise_hit(ref)
                _add_edge(
                    node,
                    callee["name"],
                    callee["file"],
                    by_key,
                    by_name,
                    edges,
                    seen,
                    node.get("line", 0),
                )
    return edges
