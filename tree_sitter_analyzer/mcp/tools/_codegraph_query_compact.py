"""Compact-output formatters for CodeGraph query results.

Pure dict → dict transformations — no external state or I/O.
"""

from __future__ import annotations

from typing import Any


def compact_symbol(symbol: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": symbol.get("name", ""),
        "file": symbol.get("file", ""),
        "line": symbol.get("line", 0),
    }
    if symbol.get("kind"):
        entry["kind"] = symbol["kind"]
    if symbol.get("depth"):
        entry["depth"] = symbol["depth"]
    return entry


def compact_relationships(
    relationships: dict[str, dict[str, list[dict[str, Any]]]],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    return {
        direction: compact_edge_map(edges)
        for direction, edges in relationships.items()
        if edges
    }


def compact_edge_map(
    edges: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    return {
        source_key: [compact_symbol(entry) for entry in entries]
        for source_key, entries in edges.items()
        if entries
    }


def compact_facets(facets: dict[str, Any]) -> dict[str, Any]:
    compacted: dict[str, Any] = {}
    for name, facet in facets.items():
        if name == "source":
            compacted[name] = {
                "status": facet.get("status"),
                "file_count": facet.get("file_count", 0),
                "files": [
                    compact_file_entry(entry) for entry in facet.get("files", [])
                ],
            }
        elif name in {"callers", "callees"}:
            compacted[name] = {
                "status": facet.get("status"),
                "edges": compact_edge_map(facet.get("edges", {})),
            }
        elif name == "complexity":
            compacted[name] = compact_complexity_facet(facet)
        elif name == "health":
            compacted[name] = compact_health_facet(facet)
        else:
            compacted[name] = facet
    return compacted


def compact_file_entry(entry: dict[str, Any]) -> dict[str, Any]:
    compacted: dict[str, Any] = {
        "file": entry.get("file_path", ""),
        "symbols": [],
    }
    if entry.get("language"):
        compacted["lang"] = entry["language"]
    if entry.get("matches"):
        compacted["matches"] = [
            {
                "line": match.get("line", 0),
                "text": match.get("text", ""),
                "terms": match.get("terms", []),
            }
            for match in entry.get("matches", [])[:5]
        ]
    for symbol in entry.get("symbols", []):
        start_line = int(symbol.get("start_line", 0) or 0)
        end_line = int(symbol.get("end_line", start_line) or start_line)
        symbol_entry: dict[str, Any] = {
            "name": symbol.get("name", ""),
            "lines": f"{start_line}-{end_line}"
            if end_line != start_line
            else start_line,
        }
        if symbol.get("kind"):
            symbol_entry["kind"] = symbol["kind"]
        if symbol.get("code"):
            symbol_entry["code"] = symbol["code"]
        if symbol.get("code_truncated"):
            symbol_entry["code_truncated"] = True
        if symbol.get("code_lines"):
            symbol_entry["code_lines"] = symbol["code_lines"]
        compacted["symbols"].append(symbol_entry)
    return compacted


def compact_complexity_facet(facet: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": facet.get("status"),
        "files": [
            {
                "file": entry.get("file"),
                "status": entry.get("status"),
                "max": entry.get("max_complexity"),
                "total": entry.get("total_complexity"),
                "hotspots": [
                    {
                        "name": hotspot.get("name"),
                        "line": hotspot.get("line"),
                        "cc": hotspot.get("complexity"),
                    }
                    for hotspot in entry.get("hotspots", [])
                ],
            }
            for entry in facet.get("files", [])
        ],
    }


def compact_health_facet(facet: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": facet.get("status"),
        "files": [
            {
                "file": entry.get("file"),
                "status": entry.get("status"),
                "total": entry.get("total"),
                "grade": entry.get("grade"),
            }
            for entry in facet.get("files", [])
        ],
    }
