#!/usr/bin/env python3
"""
check_tools MCP Tool

Verify that fd and ripgrep are installed and return their versions.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .base_tool import BaseMCPTool


class CheckToolsTool(BaseMCPTool):
    """MCP tool that checks whether fd and ripgrep are available."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "check_tools",
            "description": (
                "Verify that fd and ripgrep are installed and return their versions.\n\n"
                "WHEN TO USE:\n"
                "- Call this first if list_files, search_content, or find_and_grep returns "
                "unexpected empty results\n"
                "- Call this when setting up tree-sitter-analyzer in a new environment\n"
                "- Call this to diagnose why file search tools are not finding expected files\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- Do not call this on every session — only when search tools behave unexpectedly\n"
                "- Do not use this to search for files (use list_files or search_content instead)\n"
                "\n"
                "Returns version strings for fd and ripgrep, availability status, and installation\n"
                "recommendations if tools are missing."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        return True

    async def _check_command(self, cmd: str) -> dict[str, Any]:
        """Check if a command is available and return its version info."""
        try:
            proc = await asyncio.create_subprocess_exec(
                cmd,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            output = stdout.decode("utf-8", errors="replace").strip()
            if not output:
                output = stderr.decode("utf-8", errors="replace").strip()
            first_line = output.splitlines()[0] if output else ""
            return {"available": True, "version": first_line}
        except FileNotFoundError:
            return {"available": False, "version": None}
        except asyncio.TimeoutError:
            return {"available": False, "version": None}
        except Exception:
            return {"available": False, "version": None}

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Check fd and rg availability and return version info."""
        fd_result, rg_result = await asyncio.gather(
            self._check_command("fd"),
            self._check_command("rg"),
        )

        fd_available: bool = fd_result["available"]
        rg_available: bool = rg_result["available"]

        missing: list[str] = []
        if not fd_available:
            missing.append("fd")
        if not rg_available:
            missing.append("rg")

        if not missing:
            status = "all_tools_available"
            recommendation: str | None = None
        else:
            status = "missing_tools"
            install_hints: list[str] = []
            if "fd" in missing:
                install_hints.append(
                    "Install fd: brew install fd (macOS) or apt-get install fd-find (Ubuntu)"
                )
            if "rg" in missing:
                install_hints.append(
                    "Install ripgrep: brew install ripgrep (macOS) or apt-get install ripgrep (Ubuntu)"
                )
            recommendation = "; ".join(install_hints)

        return {
            "fd": fd_result,
            "rg": rg_result,
            "status": status,
            "recommendation": recommendation,
        }
