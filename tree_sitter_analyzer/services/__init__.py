"""Service layer — pure functions shared between cli/ and mcp/tools/.

ARCH-A1 (docs/AUDIT_FINDINGS_2026-05-20.md). Before this package
existed, three MCP tools reached up into ``cli/`` for builder
functions:

  * mcp/tools/parser_readiness_tool.py  -> cli/parser_readiness
  * mcp/tools/agent_skills_tool.py      -> cli/agent_skills
  * mcp/tools/agent_workflow_tool.py    -> cli/agent_workflow

That created a bidirectional cycle with ``cli/commands/mcp_commands.py``
(which imports MCP tools). Now both ``cli/`` and ``mcp/tools/`` depend
on ``services/`` and not on each other.

To stay backwards-compatible we re-export the builders from their
existing ``cli/`` locations rather than moving the source files in a
single big-bang patch. A follow-up sprint can do the physical relocation
behind these re-exports without changing any consumer.

The contract test ``test_no_mcp_tool_imports_cli`` in
``tests/unit/test_agent_contracts.py`` AST-walks ``mcp/tools/*.py`` and
fails if anyone re-introduces a ``from ...cli.*`` import.
"""

from __future__ import annotations

# Re-export the builders so callers depend on the services boundary,
# not on cli/.
from tree_sitter_analyzer.cli.agent_skills import build_agent_skills_inventory
from tree_sitter_analyzer.cli.agent_workflow import build_agent_workflow_pack
from tree_sitter_analyzer.cli.parser_readiness import build_parser_readiness_advice

__all__ = [
    "build_agent_skills_inventory",
    "build_agent_workflow_pack",
    "build_parser_readiness_advice",
]
