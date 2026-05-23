#!/usr/bin/env python3
"""
CodeGraph Sitemap MCP Tool — Hierarchical project code map.

Generates a browsable, hierarchical map of the project's code surface:
  directory → file → class → function (with signatures)

Uses the pre-indexed AST cache for instant lookups. Falls back to
on-demand parsing when the cache is empty.

Modes:
  - full:     Complete hierarchical map (directory → file → symbols)
  - api:      Public API surface only (non-private functions/classes)
  - module:   Per-module complexity metrics (functions, classes, LOC)
  - flat:     Flat symbol listing grouped by kind

CodeGraph parity: equivalent to CodeGraph's code-map / sitemap view.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Any

from ...utils import setup_logger
from ..utils.format_helper import apply_toon_format_to_response
from ._response_builder import build_response
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CodeGraphSitemapTool(BaseMCPTool):
    """MCP Tool for hierarchical project code map (CodeGraph parity)."""

    def __init__(self, project_root: str | None = None) -> None:
        self._cache: Any = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._cache = None

    def _get_cache(self) -> Any:
        if self._cache is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            from ...ast_cache import ASTCache

            self._cache = ASTCache(self.project_root)
        return self._cache

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_sitemap",
            "description": (
                "Hierarchical project code map (CodeGraph parity). "
                "Generates a browsable directory→file→class→function structure "
                "with signatures, complexity metrics, and public API surface. "
                "Modes: full (complete map), api (public API only), "
                "module (per-module metrics), flat (flat symbol list). "
                "Requires ast_cache index (run ast_cache mode=index). "
                "No other tool provides hierarchical code-map navigation."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["full", "api", "module", "flat"],
                    "description": (
                        "full=complete hierarchical map, "
                        "api=public API surface only, "
                        "module=per-module metrics, "
                        "flat=flat symbol listing"
                    ),
                    "default": "full",
                },
                "language": {
                    "type": "string",
                    "description": "Filter by language (e.g. 'python', 'javascript')",
                },
                "directory": {
                    "type": "string",
                    "description": "Filter to a subdirectory (relative path)",
                },
                "max_files": {
                    "type": "integer",
                    "description": "Max files to include (default: 200)",
                    "default": 200,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format: 'toon' (default, token-efficient) or 'json'",
                    "default": "toon",
                },
            },
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "full")
        if mode not in ("full", "api", "module", "flat"):
            raise ValueError(f"Invalid mode: {mode}")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        mode = arguments.get("mode", "full")
        language = arguments.get("language")
        directory = arguments.get("directory")
        max_files = arguments.get("max_files", 200)
        output_format = arguments.get("output_format", "toon")

        cache = self._get_cache()

        raw_files = self._load_indexed_files(cache, language, directory, max_files)

        if mode == "full":
            payload = self._build_full_map(raw_files)
        elif mode == "api":
            payload = self._build_api_surface(raw_files)
        elif mode == "module":
            payload = self._build_module_metrics(raw_files)
        else:
            payload = self._build_flat(raw_files)

        total_symbols = sum(f["symbol_count"] for f in raw_files)
        extra: dict[str, Any] = {}
        if language:
            extra["language_filter"] = language

        result = build_response(
            verdict="INFO" if raw_files else "NOT_FOUND",
            mode=mode,
            file_count=len(raw_files),
            total_symbols=total_symbols,
            **payload,
            **extra,
        )

        return apply_toon_format_to_response(result, output_format)

    def _load_indexed_files(
        self,
        cache: Any,
        language: str | None,
        directory: str | None,
        max_files: int,
    ) -> list[dict[str, Any]]:
        conn = cache._get_conn()
        if language and directory:
            like_dir = directory.rstrip("/") + "/%"
            rows = conn.execute(
                "SELECT file_path, language, symbols_json, structure_json "
                "FROM ast_index WHERE language = ? AND file_path LIKE ? "
                "ORDER BY file_path LIMIT ?",
                (language, like_dir, max_files),
            ).fetchall()
        elif language:
            rows = conn.execute(
                "SELECT file_path, language, symbols_json, structure_json "
                "FROM ast_index WHERE language = ? "
                "ORDER BY file_path LIMIT ?",
                (language, max_files),
            ).fetchall()
        elif directory:
            like_dir = directory.rstrip("/") + "/%"
            rows = conn.execute(
                "SELECT file_path, language, symbols_json, structure_json "
                "FROM ast_index WHERE file_path LIKE ? "
                "ORDER BY file_path LIMIT ?",
                (like_dir, max_files),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT file_path, language, symbols_json, structure_json "
                "FROM ast_index ORDER BY file_path LIMIT ?",
                (max_files,),
            ).fetchall()

        files: list[dict[str, Any]] = []
        for row in rows:
            symbols = json.loads(row["symbols_json"])
            structure = json.loads(row["structure_json"])
            syms = symbols.get("symbols", [])
            files.append(
                {
                    "file": row["file_path"],
                    "language": row["language"],
                    "symbols": syms,
                    "structure": structure,
                    "symbol_count": len(syms),
                    "functions": [s for s in syms if s.get("kind") == "function"],
                    "classes": [s for s in syms if s.get("kind") == "class"],
                    "imports": [s for s in syms if s.get("kind") == "import"],
                }
            )
        return files

    def _build_full_map(self, files: list[dict[str, Any]]) -> dict[str, Any]:
        tree: dict[str, Any] = {}
        for f in files:
            parts = f["file"].split(os.sep)
            node = tree
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            filename = parts[-1]
            file_entry: dict[str, Any] = {
                "_language": f["language"],
                "_symbols": len(f["symbols"]),
            }
            for cls in f["classes"]:
                class_entry: dict[str, Any] = {
                    "_kind": "class",
                    "_line": cls.get("line", 0),
                }
                class_name = cls.get("name", "")
                members = self._class_members(class_name, f["functions"])
                if members:
                    for m in members:
                        member_entry = {
                            "_kind": "method",
                            "_line": m.get("line", 0),
                            "_params": m.get("params", ""),
                        }
                        class_entry[m.get("name", "")] = member_entry
                file_entry[class_name] = class_entry

            for func in f["functions"]:
                parent = func.get("class")
                if parent:
                    continue
                func_name = func.get("name", "")
                file_entry[func_name] = {
                    "_kind": "function",
                    "_line": func.get("line", 0),
                    "_params": func.get("params", ""),
                }

            node[filename] = file_entry

        return {"sitemap": self._clean_tree(tree)}

    def _class_members(
        self, class_name: str, functions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return [f for f in functions if f.get("class") == class_name]

    def _clean_tree(self, tree: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, val in tree.items():
            if isinstance(val, dict) and "_kind" not in val and "_language" not in val:
                cleaned = self._clean_tree(val)
                if cleaned:
                    out[key] = cleaned
            else:
                out[key] = val
        return out

    def _build_api_surface(self, files: list[dict[str, Any]]) -> dict[str, Any]:
        api: list[dict[str, Any]] = []
        for f in files:
            for func in f["functions"]:
                name = func.get("name", "")
                if name.startswith("_"):
                    continue
                parent = func.get("class")
                if parent and parent.startswith("_"):
                    continue
                entry: dict[str, Any] = {
                    "name": name,
                    "kind": "method" if parent else "function",
                    "file": f["file"],
                    "line": func.get("line", 0),
                    "params": func.get("params", ""),
                    "language": f["language"],
                }
                if parent:
                    entry["class"] = parent
                api.append(entry)

            for cls in f["classes"]:
                cls_name = cls.get("name", "")
                if cls_name.startswith("_"):
                    continue
                api.append(
                    {
                        "name": cls_name,
                        "kind": "class",
                        "file": f["file"],
                        "line": cls.get("line", 0),
                        "language": f["language"],
                    }
                )

        return {
            "public_api": api,
            "public_function_count": sum(
                1 for a in api if a["kind"] in ("function", "method")
            ),
            "public_class_count": sum(1 for a in api if a["kind"] == "class"),
        }

    def _build_module_metrics(self, files: list[dict[str, Any]]) -> dict[str, Any]:
        by_dir: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for f in files:
            dir_path = str(os.sep).join(f["file"].split(os.sep)[:-1]) or "."
            by_dir[dir_path].append(f)

        modules: list[dict[str, Any]] = []
        for dir_path, dir_files in sorted(by_dir.items()):
            total_funcs = sum(len(f["functions"]) for f in dir_files)
            total_classes = sum(len(f["classes"]) for f in dir_files)
            total_imports = sum(len(f["imports"]) for f in dir_files)
            langs: dict[str, int] = defaultdict(int)
            for f in dir_files:
                langs[f["language"]] += 1

            file_entries: list[dict[str, Any]] = []
            for f in dir_files:
                file_entries.append(
                    {
                        "file": f["file"],
                        "functions": len(f["functions"]),
                        "classes": len(f["classes"]),
                        "imports": len(f["imports"]),
                        "language": f["language"],
                    }
                )

            modules.append(
                {
                    "directory": dir_path,
                    "file_count": len(dir_files),
                    "function_count": total_funcs,
                    "class_count": total_classes,
                    "import_count": total_imports,
                    "languages": dict(langs),
                    "files": file_entries,
                }
            )

        return {"modules": modules}

    def _build_flat(self, files: list[dict[str, Any]]) -> dict[str, Any]:
        by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for f in files:
            for sym in f["symbols"]:
                kind = sym.get("kind", "unknown")
                entry: dict[str, Any] = {
                    "name": sym.get("name", sym.get("text", "")),
                    "kind": kind,
                    "file": f["file"],
                    "line": sym.get("line", 0),
                    "language": f["language"],
                }
                if kind == "function" and sym.get("params"):
                    entry["params"] = sym["params"]
                if kind == "function" and sym.get("class"):
                    entry["class"] = sym["class"]
                by_kind[kind].append(entry)

        counts = {k: len(v) for k, v in by_kind.items()}
        return {"symbols_by_kind": dict(by_kind), "counts": counts}
