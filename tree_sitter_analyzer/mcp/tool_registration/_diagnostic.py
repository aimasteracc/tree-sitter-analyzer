"""Tool registration — diagnostic."""
from typing import Any

from ..tools.change_impact_tool import ChangeImpactTool
from ..tools.check_tools_tool import CheckToolsTool
from ..tools.ci_report_tool import CIReportTool
from ..tools.pr_summary_tool import PRSummaryTool
from ._shared import _make_handler


def _register_diagnostic_tools(registry: Any, project_root: str | None) -> None:
    """Register diagnostic tools."""
    # check_tools
    check_tool = CheckToolsTool(project_root)
    registry.register(
        name="check_tools",
        toolset="diagnostic",
        category="diagnostics",
        schema=check_tool.get_tool_definition(),
        handler=_make_handler(check_tool),
        description="Check tool availability and configuration",
        emoji="🩺",
    )

    # ci_report
    ci_tool = CIReportTool(project_root)
    registry.register(
        name="ci_report",
        toolset="diagnostic",
        category="ci-integration",
        schema=ci_tool.get_tool_definition(),
        handler=_make_handler(ci_tool),
        description="Generate CI/CD friendly reports with pass/fail status",
        emoji="🚦",
    )

    # pr_summary
    pr_summary_tool = PRSummaryTool(project_root)
    registry.register(
        name="pr_summary",
        toolset="diagnostic",
        category="git-analysis",
        schema=pr_summary_tool.get_tool_definition(),
        handler=_make_handler(pr_summary_tool),
        description="Generate PR summaries from git diff: categorization, breaking changes, semantic analysis",
        emoji="📋",
    )

    # change_impact
    change_impact_tool = ChangeImpactTool(project_root)
    registry.register(
        name="change_impact",
        toolset="diagnostic",
        category="impact-analysis",
        schema=change_impact_tool.get_tool_definition(),
        handler=_make_handler(change_impact_tool),
        description="Analyze blast radius of file changes: impacted files, tools, and tests",
        emoji="💥",
    )
