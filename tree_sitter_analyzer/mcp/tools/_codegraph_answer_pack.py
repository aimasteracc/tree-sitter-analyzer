"""Answer-pack builders for codegraph_query."""

from __future__ import annotations

from typing import Any


def build_answer_pack(
    *,
    state: Any,
    query: str,
    warnings: list[str],
) -> dict[str, Any]:
    """Build a compact evidence package for an agent final answer."""
    file_summaries = [file_answer_summary(entry) for entry in state.files[:8]]
    coverage = build_coverage(state=state, file_summaries=file_summaries)
    relationship_summary = build_relationship_summary(state.relationships)
    missing = build_missing(state=state, warnings=warnings)
    decision = build_decision(coverage=coverage, missing=missing)
    citations = build_citations(
        symbols=state.symbols,
        file_summaries=file_summaries,
        relationships=state.relationships,
    )

    return {
        "version": 2,
        "stop_signal": True,
        "intent": state.intent or "custom",
        "query": query,
        "summary": (
            f"Answer pack ready: {len(state.files)} files, "
            f"{len(state.symbols)} symbols, "
            f"{coverage['edge_count']} edges."
        ),
        "confidence": confidence_for(coverage=coverage, missing=missing),
        "decision": decision,
        "coverage": coverage,
        "core_path": build_core_path(state=state, file_summaries=file_summaries),
        "core_files": [entry["file_path"] for entry in file_summaries],
        "key_symbols": [
            {
                "name": symbol.get("name", ""),
                "kind": symbol.get("kind", ""),
                "file": symbol.get("file", ""),
                "line": symbol.get("line", 0),
            }
            for symbol in state.symbols[:12]
        ],
        "citations": citations,
        "relationship_summary": relationship_summary,
        "quality_gates": [
            "cite core_files and citations in the final answer",
            "do not raw-read files unless a named required detail is missing",
            "run at most one targeted follow-up when decision.followup_allowed is true",
        ],
        "evidence": file_summaries,
        "missing": missing,
        "next_step": (
            "Answer from this evidence. Run at most one targeted follow-up only "
            "if a named detail required by the question is missing."
        ),
    }


def build_coverage(
    *,
    state: Any,
    file_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    counts = state.counts()
    match_count = sum(len(entry.get("matches", [])) for entry in file_summaries)
    code_symbol_count = sum(
        1
        for entry in file_summaries
        for symbol in entry.get("symbols", [])
        if symbol.get("has_code")
    )
    return {
        "file_count": len(state.files),
        "symbol_count": len(state.symbols),
        "evidence_files": len(file_summaries),
        "match_count": match_count,
        "code_symbol_count": code_symbol_count,
        "caller_edges": counts["caller_edges"],
        "callee_edges": counts["callee_edges"],
        "edge_count": counts["caller_edges"] + counts["callee_edges"],
        "has_code": code_symbol_count > 0,
        "has_relationships": counts["caller_edges"] + counts["callee_edges"] > 0,
        "has_concept_matches": match_count > 0,
    }


def build_missing(*, state: Any, warnings: list[str]) -> list[str]:
    missing: list[str] = []
    if not state.symbols and not state.files:
        missing.append("No symbols or files matched the chain.")
    missing.extend(warnings)
    return missing


def build_decision(
    *,
    coverage: dict[str, Any],
    missing: list[str],
) -> dict[str, Any]:
    has_evidence = bool(
        coverage["file_count"]
        or coverage["symbol_count"]
        or coverage["has_relationships"]
        or coverage["has_concept_matches"]
    )
    followup_allowed = not has_evidence or bool(missing)
    if has_evidence and not missing:
        reason = "The chain produced enough cited evidence to answer."
    elif has_evidence:
        reason = "Evidence exists, but warnings may justify one targeted follow-up."
    else:
        reason = "No cited evidence was found; run one narrower follow-up."
    return {
        "should_stop": has_evidence and not followup_allowed,
        "followup_allowed": followup_allowed,
        "reason": reason,
    }


def confidence_for(
    *,
    coverage: dict[str, Any],
    missing: list[str],
) -> str:
    if missing and not coverage["file_count"]:
        return "low"
    if coverage["has_code"] and (
        coverage["symbol_count"] or coverage["has_relationships"]
    ):
        return "high"
    if coverage["file_count"] or coverage["has_concept_matches"]:
        return "medium"
    return "low"


def file_answer_summary(entry: dict[str, Any]) -> dict[str, Any]:
    symbols = entry.get("symbols") or []
    matches = entry.get("matches") or []
    return {
        "file_path": entry.get("file_path", ""),
        "language": entry.get("language", ""),
        "has_code": any(bool(symbol.get("code")) for symbol in symbols),
        "symbols": [
            {
                "name": symbol.get("name", ""),
                "kind": symbol.get("kind", ""),
                "start_line": symbol.get("start_line", 0),
                "end_line": symbol.get("end_line", 0),
                "has_code": bool(symbol.get("code")),
                "truncated": bool(symbol.get("truncated")),
            }
            for symbol in symbols[:6]
        ],
        "matches": [
            {
                "line": match.get("line", 0),
                "text": str(match.get("text", ""))[:240],
            }
            for match in matches[:6]
        ],
    }


def build_core_path(
    *,
    state: Any,
    file_summaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    path: list[dict[str, Any]] = []
    for symbol in state.symbols[:8]:
        path.append(
            {
                "kind": "symbol",
                "name": symbol.get("name", ""),
                "file": symbol.get("file", ""),
                "line": symbol.get("line", 0),
            }
        )
    if path:
        return path
    return [
        {
            "kind": "file",
            "file": entry.get("file_path", ""),
            "line": first_evidence_line(entry),
        }
        for entry in file_summaries[:8]
    ]


def build_citations(
    *,
    symbols: list[dict[str, Any]],
    file_summaries: list[dict[str, Any]],
    relationships: dict[str, dict[str, list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()

    def add(file_path: str, line: int, symbol: str, source: str) -> None:
        if not file_path:
            return
        symbol = clean_symbol_name(symbol)
        key = (file_path, line, symbol)
        if key in seen:
            return
        seen.add(key)
        citations.append(
            {
                "file": file_path,
                "line": line,
                "symbol": symbol,
                "source": source,
            }
        )

    for symbol in symbols[:12]:
        add(
            str(symbol.get("file") or ""),
            int(symbol.get("line", 0) or 0),
            str(symbol.get("name") or ""),
            "symbol",
        )
    for entry in file_summaries:
        file_path = str(entry.get("file_path") or "")
        for symbol in entry.get("symbols", [])[:4]:
            add(
                file_path,
                int(symbol.get("start_line", 0) or 0),
                str(symbol.get("name") or ""),
                "evidence",
            )
        for match in entry.get("matches", [])[:2]:
            add(file_path, int(match.get("line", 0) or 0), "", "match")
    for direction, sources in relationships.items():
        for entries in sources.values():
            for symbol in entries[:3]:
                add(
                    str(symbol.get("file") or ""),
                    int(symbol.get("line", 0) or 0),
                    str(symbol.get("name") or ""),
                    direction,
                )
            if len(citations) >= 24:
                return citations
    return citations


def clean_symbol_name(symbol: str) -> str:
    cleaned = symbol.strip()
    if "\n" in cleaned or len(cleaned) > 80:
        return ""
    return cleaned


def build_relationship_summary(
    relationships: dict[str, dict[str, list[dict[str, Any]]]],
) -> dict[str, Any]:
    callers = direction_summary(relationships.get("callers", {}))
    callees = direction_summary(relationships.get("callees", {}))
    return {
        "caller_edges": callers["edge_count"],
        "callee_edges": callees["edge_count"],
        "callers": callers,
        "callees": callees,
    }


def direction_summary(sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {
        "source_count": len(sources),
        "edge_count": sum(len(entries) for entries in sources.values()),
        "sources": [
            {
                "source": source,
                "edge_count": len(entries),
                "examples": [
                    {
                        "name": entry.get("name", ""),
                        "file": entry.get("file", ""),
                        "line": entry.get("line", 0),
                        "depth": entry.get("depth", 1),
                    }
                    for entry in entries[:4]
                ],
            }
            for source, entries in list(sources.items())[:6]
        ],
    }


def first_evidence_line(entry: dict[str, Any]) -> int:
    symbols = entry.get("symbols") or []
    if symbols:
        return int(symbols[0].get("start_line", 0) or 0)
    matches = entry.get("matches") or []
    if matches:
        return int(matches[0].get("line", 0) or 0)
    return 0


__all__ = [
    "build_answer_pack",
    "file_answer_summary",
]
