"""Tool registration — safety."""
from typing import Any

from ..tools.modification_guard_tool import ModificationGuardTool
from ..tools.security_scan_tool import SecurityScanTool
from ._shared import _make_handler


def _register_safety_tools(registry: Any, project_root: str | None) -> None:
    """Register safety tools."""
    # modification_guard
    guard_tool = ModificationGuardTool(project_root)
    registry.register(
        name="modification_guard",
        toolset="safety",
        category="pre-modification-check",
        schema=guard_tool.get_tool_definition(),
        handler=_make_handler(guard_tool),
        description="Pre-modification safety check: impact analysis, warnings",
        emoji="🛡️",
    )

    # security_scan
    security_tool = SecurityScanTool(project_root)
    registry.register(
        name="security_scan",
        toolset="safety",
        category="security-scanning",
        schema=security_tool.get_tool_definition(),
        handler=_make_handler(security_tool),
        description="Security vulnerability scanner: secrets, injection, XSS, deserialization",
        emoji="🔒",
    )
