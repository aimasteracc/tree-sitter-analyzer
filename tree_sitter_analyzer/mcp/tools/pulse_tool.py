"""MCP tools: pulse / pulse_batch / get_project_schema.

Session initialization flow:
  Step 1: set_project_path(path)    — existing MCP tool
  Step 2: get_project_schema()      — confirm index stats (~100 tokens)
  Step 3: pulse(file, symbol)       — 1-query symbol context (~500 tokens)

Format guide:
  skeletal  (~200 tokens): multi-symbol scanning, callers/callees counts only.
  compact   (default, ~500 tokens): all fields, short keys (see COMPACT_LEGEND).
  verbose   (~2000 tokens): full key names, detailed review / refactoring.

Token budget exceeded: fields are dropped in this order (lowest priority first):
  comments → siblings → imported_by → imports → git_heat → callees → callers
"""

from __future__ import annotations

from typing import Any

from ...api.serialization import COMPACT_LEGEND
from .base_tool import BaseMCPTool


class PulseTool(BaseMCPTool):
    """Single-symbol context query — replaces 10-20 tool calls with one."""

    action_map: dict[str, Any] = {}

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
            "name": "pulse",
            "description": (
                "Get complete context for one symbol in a single query: callers, "
                "callees, git heat, imports, siblings, comments. "
                f"Compact key legend: {COMPACT_LEGEND}. "
                "Formats: skeletal (~200 tok, scan), compact (default ~500 tok), "
                "verbose (~2000 tok, deep review). "
                "Token budget exceeded: drops fields lowest-priority first: "
                "comments→siblings→imported_by→imports→git_heat→callees→callers. "
                "call_graph=false for Bash/CSS/HTML/JSON/YAML/SQL/Markdown files. "
                "Prerequisite: set_project_path → get_project_schema → pulse."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Project-relative file path",
                    },
                    "symbol": {
                        "type": "string",
                        "description": "Symbol name (function, class, method)",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["skeletal", "compact", "verbose"],
                        "default": "compact",
                    },
                    "token_budget": {
                        "type": "integer",
                        "default": 600,
                        "description": "Max tokens for the response",
                    },
                    "max_callers": {"type": "integer", "default": 10},
                    "max_callees": {"type": "integer", "default": 10},
                    "max_siblings": {"type": "integer", "default": 15},
                    "max_comments": {"type": "integer", "default": 10},
                },
                "required": ["file", "symbol"],
                "additionalProperties": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return self.get_tool_definition()["inputSchema"]["properties"]

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if not arguments.get("file"):
            raise ValueError("'file' is required")
        if not arguments.get("symbol"):
            raise ValueError("'symbol' is required")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from ...api.pulse import apply_budget, query_pulse
        from ...api.serialization import serialize

        file_path = arguments.get("file", "")
        symbol = arguments.get("symbol", "")
        fmt = arguments.get("format", "compact")
        budget = int(arguments.get("token_budget", 600))
        max_callers = int(arguments.get("max_callers", 10))
        max_callees = int(arguments.get("max_callees", 10))
        max_siblings = int(arguments.get("max_siblings", 15))
        max_comments = int(arguments.get("max_comments", 10))

        try:
            cache = self._get_cache()
            conn = cache.get_conn()
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        try:
            pulse = query_pulse(
                conn,
                file_path=file_path,
                symbol_name=symbol,
                max_callers=max_callers,
                max_callees=max_callees,
                max_siblings=max_siblings,
                max_comments=max_comments,
            )
        except Exception as exc:
            return {"success": False, "error": f"pulse query failed: {exc}"}

        if pulse is None:
            return {
                "success": False,
                "error": f"Symbol '{symbol}' not found in '{file_path}'",
            }

        budgeted = apply_budget(pulse, token_budget=budget)
        return {"success": True, "result": serialize(budgeted, format=fmt)}


class PulseBatchTool(BaseMCPTool):
    """Batch context query for multiple symbols."""

    action_map: dict[str, Any] = {}

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
            "name": "pulse_batch",
            "description": (
                "Get context for multiple symbols in one call. "
                "Targets exceeding max_symbols are truncated with a warning. "
                "Use format='skeletal' for broad scanning, 'compact' for detail."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "targets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "file": {"type": "string"},
                                "symbol": {"type": "string"},
                            },
                            "required": ["file", "symbol"],
                        },
                        "description": "List of {file, symbol} targets",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["skeletal", "compact"],
                        "default": "compact",
                    },
                    "token_budget_per_symbol": {
                        "type": "integer",
                        "default": 400,
                    },
                    "max_symbols": {
                        "type": "integer",
                        "default": 10,
                    },
                },
                "required": ["targets"],
                "additionalProperties": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return self.get_tool_definition()["inputSchema"]["properties"]

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if not isinstance(arguments.get("targets"), list):
            raise ValueError("'targets' must be a list")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from ...api.pulse import apply_budget, query_pulse
        from ...api.serialization import serialize

        targets = arguments.get("targets", [])
        fmt = arguments.get("format", "compact")
        budget = int(arguments.get("token_budget_per_symbol", 400))
        max_sym = int(arguments.get("max_symbols", 10))

        truncated_count = max(0, len(targets) - max_sym)
        targets = targets[:max_sym]

        try:
            cache = self._get_cache()
            conn = cache.get_conn()
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        results: list[Any] = []
        for t in targets:
            file_path = t.get("file", "")
            symbol = t.get("symbol", "")
            try:
                pulse = query_pulse(conn, file_path=file_path, symbol_name=symbol)
                if pulse is None:
                    results.append({"file": file_path, "symbol": symbol, "error": "not found"})
                else:
                    budgeted = apply_budget(pulse, token_budget=budget)
                    results.append(serialize(budgeted, format=fmt))
            except Exception as exc:
                results.append({"file": file_path, "symbol": symbol, "error": str(exc)})

        if truncated_count > 0:
            results.append({"warning": f"{truncated_count} targets truncated"})

        return {"success": True, "results": results}


class GetProjectSchemaTool(BaseMCPTool):
    """Return indexed project statistics (~100 tokens).

    Session initialization flow:
      Step 1: set_project_path(path)
      Step 2: get_project_schema()    ← you are here
      Step 3: pulse(file, symbol)

    When indexed=false, call index action=warm to build the index first.
    """

    action_map: dict[str, Any] = {}

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
            "name": "get_project_schema",
            "description": (
                "Return index statistics: languages, symbol count, edge count, "
                "index age, available pulse fields, Hyphae pseudo-classes. "
                "Call this (Step 2) after set_project_path and before pulse. "
                "If indexed=false, call index action=warm first."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return self.get_tool_definition()["inputSchema"]["properties"]

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        import time

        try:
            cache = self._get_cache()
            conn = cache.get_conn()
        except Exception as exc:
            return {"success": True, "result": {"indexed": False, "error": str(exc)}}

        try:
            sym_count = conn.execute("SELECT COUNT(*) FROM ast_symbol_rows").fetchone()[0]
            edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            langs = [
                r[0] for r in conn.execute(
                    "SELECT DISTINCT language FROM ast_symbol_rows ORDER BY language"
                )
            ]
            # Estimate index age from the most recently indexed file.
            age_row = conn.execute(
                "SELECT MAX(indexed_at) FROM ast_index"
            ).fetchone()
            age_secs: int | None = None
            if age_row and age_row[0]:
                try:
                    import datetime as _dt
                    ts = _dt.datetime.fromisoformat(str(age_row[0]))
                    age_secs = int(time.time() - ts.timestamp())
                except Exception:
                    age_secs = None
        except Exception as exc:
            return {"success": True, "result": {"indexed": False, "error": str(exc)}}

        return {
            "success": True,
            "result": {
                "indexed": sym_count > 0,
                "languages": langs,
                "total_symbols": sym_count,
                "total_edges": edge_count,
                "index_age_seconds": age_secs,
                "available_pulse_fields": [
                    "callers", "callees", "git_heat", "imports",
                    "imported_by", "siblings", "comments",
                ],
                "hyphae_pseudo_classes": [
                    ":calls(#X)", ":callees(#X)", ":called-by(#X)",
                    ":extends(#X)", ":implements(#X)", ":subclasses(#X)",
                    ":imports(mod)", ":has(#X)", ":not(sel)", ":in(path)",
                    ":first-child", ":only-child", ":nth-child(n)",
                    ":calls(#X){n,m}", ":called-by(#X){n,m}",
                    ":hot", ":hot(N)", ":recently_modified", ":stale", ":hotspot",
                    ":violates(rule_id)", ":reaches(#X){n,m}", ":branch(kind)",
                ],
            },
        }


def build_pulse_tool(project_root: str | None) -> PulseTool:
    """Factory function for the ``pulse`` MCP tool."""
    return PulseTool(project_root)


def build_pulse_batch_tool(project_root: str | None) -> PulseBatchTool:
    """Factory function for the ``pulse_batch`` MCP tool."""
    return PulseBatchTool(project_root)


def build_project_schema_tool(project_root: str | None) -> GetProjectSchemaTool:
    """Factory function for the ``get_project_schema`` MCP tool."""
    return GetProjectSchemaTool(project_root)
