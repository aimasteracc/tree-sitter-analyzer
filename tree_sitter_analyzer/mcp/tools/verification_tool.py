"""显式执行经过重新分析校验的验证计划。"""

import asyncio
import threading
from typing import Any

from ...verification_runner import run_verification_request
from ..utils.format_helper import apply_output_format_to_response
from .base_tool import BaseMCPTool


class VerificationTool(BaseMCPTool):
    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "request": {"type": "string", "maxLength": 5800},
                "output_format": {
                    "type": "string",
                    "enum": ["json"],
                    "default": "json",
                },
            },
            "required": ["request"],
            "additionalProperties": False,
        }

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "verify_plan",
            "description": "Rebuild and execute a bound verification plan.",
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": False,
                "openWorldHint": True,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if not isinstance(arguments.get("request"), str):
            raise ValueError("request must be a verification descriptor")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        cancel = threading.Event()
        task = asyncio.create_task(
            asyncio.to_thread(
                run_verification_request,
                arguments["request"],
                self.project_root or ".",
                cancel,
            )
        )
        try:
            result = await asyncio.shield(task)
        except asyncio.CancelledError:
            cancel.set()
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
            raise
        return apply_output_format_to_response(
            result, arguments.get("output_format", "json")
        )
