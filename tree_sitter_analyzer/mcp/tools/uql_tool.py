"""``search action=uql`` 的 MCP 适配器 (RFC-0041)。

有意保持轻薄：只负责传递参数。解析、执行、完整性判定与投影都在
:mod:`tree_sitter_analyzer.uql` 中，CLI 的 ``--uql`` 参数也经由本工具到达那里。
"""

from __future__ import annotations

from typing import Any

from .base_tool import BaseMCPTool

#: 由 ``search action=help target_action=uql`` 提供的语法卡片 —— 了解该语言的
#: 唯一发现调用。其大小由 ``tests/unit/mcp/test_output_cost_invariants.py`` 固定。
QUERY_DESCRIPTION = (
    "Unified query (RFC-0041). Pipeline: source.stage().stage()... "
    "Sources: symbol('Name'|'Cls.m'|[names], file=?) | select('<TQL selector>') "
    "| a bare TQL selector ('.function:in(src/)'). "
    "Relations (new group from the current set): callers(depth=1..5), "
    "tests(), impact(depth=1..10), callees(). "
    "Refinements (narrow the current group): filter(name=,file=,path=,kind=,"
    "language=,test=bool,regex=) | exclude(...) | untested() | tested() | "
    "take(n) | sort(by='name'|'file'|'line', desc=false). "
    "Output: per-stage n/c (complete|incomplete|unknown) with reason codes r; "
    "total completeness is complete only if every stage is. "
    "Example: symbol('parse').callers(depth=2).filter(path='src/').tests()"
)


class UqlTool(BaseMCPTool):
    """在已索引的代码图上执行统一查询。"""

    def __init__(self, project_root: str | None = None) -> None:
        self._backends: Any = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._backends = None

    def _get_backends(self) -> Any:
        if self._backends is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            from ...uql import IndexBackends

            self._backends = IndexBackends(self.project_root)
        return self._backends

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "uql",
            "description": (
                "Unified, evidence-carrying code query: select -> relate "
                "(callers/tests/impact/callees) -> filter -> take in ONE call, "
                "with per-stage completeness and reason codes."
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "minLength": 1,
                    "description": QUERY_DESCRIPTION,
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 500,
                    "default": 50,
                    "description": "Rows per page across all groups.",
                },
                "cursor": {
                    "type": "string",
                    "description": "page.next_cursor from the previous page of the same query.",
                },
                "detail": {
                    "type": "string",
                    "enum": ["compact", "full"],
                    "default": "compact",
                    "description": "full: structured rows, provenance, every examined input.",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json"],
                    "default": "json",
                    "description": "Output format: JSON",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from ...uql import answer
        from ...uql.errors import INDEX_UNAVAILABLE, QueryError
        from ...uql.output import error_payload

        try:
            backends = self._get_backends()
        except ValueError as exc:
            return error_payload(
                QueryError(INDEX_UNAVAILABLE, str(exc)), arguments.get("query")
            )
        args = {k: v for k, v in arguments.items() if k != "output_format"}
        return await answer(args, backends)
