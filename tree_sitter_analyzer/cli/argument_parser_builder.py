"""Argument parser construction for the tree-sitter-analyzer CLI.

This module is the assembler: it imports all ``_add_*`` helpers from the
``argument_groups`` sub-package and wires them together into a single
``argparse.ArgumentParser``.  Each helper lives in a focused module:

    argument_groups/_core.py       — core, output, project/logging, partial-read, batch
    argument_groups/_query.py      — query selection, SQL platform
    argument_groups/_analysis.py   — analysis, health, change-impact, dependency/graph flags
    argument_groups/_mcp.py        — index management, constraints, clean-state
    argument_groups/_agents.py     — agent skills, agent workflow
    argument_groups/_advanced.py   — trace-impact, env probe, modification guard,
                                     decision journal, batch search
"""

from __future__ import annotations

import argparse

from .argument_groups import (
    _add_agent_skills_options,
    _add_agent_workflow_options,
    _add_analysis_options,
    _add_batch_options,
    _add_batch_search_options,
    _add_clean_state_options,
    _add_core_options,
    _add_decision_journal_options,
    _add_environment_probe_options,
    _add_install_skills_options,
    _add_mcp_analysis_options,
    _add_mcp_change_options,
    _add_mcp_constraints_options,
    _add_mcp_health_options,
    _add_mcp_index_management_options,
    _add_modification_guard_options,
    _add_output_options,
    _add_partial_read_options,
    _add_project_and_logging_options,
    _add_query_options,
    _add_sql_platform_options,
    _add_trace_impact_options,
)

# Re-export so that existing imports from this module continue to work.
__all__ = [
    "CLI_EPILOG",
    "create_argument_parser",
    "_add_agent_skills_options",
    "_add_agent_workflow_options",
    "_add_analysis_options",
    "_add_batch_options",
    "_add_batch_search_options",
    "_add_clean_state_options",
    "_add_core_options",
    "_add_decision_journal_options",
    "_add_environment_probe_options",
    "_add_install_skills_options",
    "_add_mcp_analysis_options",
    "_add_mcp_change_options",
    "_add_mcp_constraints_options",
    "_add_mcp_equivalent_options",
    "_add_mcp_health_options",
    "_add_mcp_index_management_options",
    "_add_modification_guard_options",
    "_add_output_options",
    "_add_partial_read_options",
    "_add_project_and_logging_options",
    "_add_query_options",
    "_add_sql_platform_options",
    "_add_trace_impact_options",
]

CLI_EPILOG = (
    "Examples:  (grouped by task)\n"
    "\n"
    "Cold-start  (1 call, full file picture — use these first):\n"
    "  tree-sitter-analyzer file.py --smart-context         Killer 1-call: health, exports, structure, deps, edit risk\n"
    "  tree-sitter-analyzer --overview                      Project portrait + health summary\n"
    "  tree-sitter-analyzer agent-skills                    Project-local agent skill inventory\n"
    "  tree-sitter-analyzer agent-workflow file.py          SMART workflow command pack\n"
    "\n"
    "Read code  (extract content from a single file):\n"
    "  tree-sitter-analyzer file.java --table=full          Markdown table of classes/methods\n"
    "  tree-sitter-analyzer file.java --structure           Structure overview in JSON\n"
    "  tree-sitter-analyzer file.java --summary             Quick summary of classes/methods\n"
    "  tree-sitter-analyzer file.java --advanced            Full analysis with all elements\n"
    "  tree-sitter-analyzer file.java --query-key class     Extract all class definitions\n"
    "  tree-sitter-analyzer file.java --partial-read --start-line 10 --end-line 20\n"
    "\n"
    "Health  (per-file or project-wide grading):\n"
    "  tree-sitter-analyzer file.py --file-health           A-F health grade + signal + smells\n"
    "  tree-sitter-analyzer file-health file.py             Agent-friendly alias for --file-health\n"
    "  tree-sitter-analyzer --project-health                Score ALL project files\n"
    "  tree-sitter-analyzer --watch-health                  Daemon: alert when health grades drop\n"
    "\n"
    "Edit safety  (risk + impact before/after a change):\n"
    "  tree-sitter-analyzer file.py --safe-to-edit --edit-type refactor\n"
    "  tree-sitter-analyzer file.py --refactor              Refactoring suggestions with plans\n"
    "  tree-sitter-analyzer --change-impact                 Git diff impact (trimmed surface by default)\n"
    "  tree-sitter-analyzer --change-impact --change-impact-full   Full verbose envelope (~145 KB)\n"
    "  tree-sitter-analyzer change-impact --change-impact-mode staged\n"
    "\n"
    "Graph & deps  (cross-file relationships):\n"
    "  tree-sitter-analyzer --dependencies summary          Project dependency summary\n"
    "  tree-sitter-analyzer file.py --dependencies file_deps  File dependency graph\n"
    "  tree-sitter-analyzer --detect-routes                 URL→handler routes (Flask/Django/FastAPI/Express/Spring)\n"
    "  tree-sitter-analyzer detect-routes --detect-routes-mode all\n"
    "  tree-sitter-analyzer --codegraph-overview            Entry points, dead code, hubs, coupling\n"
    "  tree-sitter-analyzer --codegraph-navigate SYMBOL     Go-to-def + refs + call hierarchy\n"
    "\n"
    "Architecture rules  (constraint DSL):\n"
    "  tree-sitter-analyzer --check-constraints             Evaluate architectural-constraints.yml\n"
    "  tree-sitter-analyzer --check-constraints --severity-min error\n"
    "\n"
    "Cache ops  (manage the pre-indexed AST cache):\n"
    "  tree-sitter-analyzer --autoindex                     Idempotent cache status / warm\n"
    "  tree-sitter-analyzer --autoindex --autoindex-mode warm\n"
    "  tree-sitter-analyzer --full-index                    Force a fresh full re-index\n"
    "  tree-sitter-analyzer --codegraph-metrics             Cross-domain project dashboard\n"
    "  tree-sitter-analyzer --clean-state                   Remove ephemeral workspace state\n"
    "  tree-sitter-analyzer --clean-state-dry-run           Preview what --clean-state would remove\n"
    "\n"
    "Discovery  (what does this CLI know?):\n"
    "  tree-sitter-analyzer parser-readiness swift          Parser/plugin readiness advisor\n"
    "  tree-sitter-analyzer --list-queries                  Show available query keys\n"
    "  tree-sitter-analyzer --show-supported-languages      List supported languages\n"
)


def _add_mcp_equivalent_options(parser: argparse.ArgumentParser) -> None:
    """Add CLI flags that mirror MCP tools."""
    _add_agent_skills_options(parser)
    _add_agent_workflow_options(parser)
    _add_mcp_health_options(parser)
    _add_mcp_change_options(parser)
    _add_mcp_analysis_options(parser)
    _add_mcp_constraints_options(parser)
    # consolidated-only families (ported during merge of feat/autonomous-dev)
    _add_trace_impact_options(parser)
    _add_environment_probe_options(parser)
    _add_modification_guard_options(parser)
    _add_decision_journal_options(parser)
    _add_batch_search_options(parser)
    # PL-C sprint additions
    _add_mcp_index_management_options(parser)
    _add_clean_state_options(parser)


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Analyze code using Tree-sitter and extract structured information.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=CLI_EPILOG,
    )
    _add_core_options(parser)
    _add_query_options(parser)
    _add_output_options(parser)
    _add_analysis_options(parser)
    _add_sql_platform_options(parser)
    _add_project_and_logging_options(parser)
    _add_partial_read_options(parser)
    _add_batch_options(parser)
    _add_install_skills_options(parser)
    _add_mcp_equivalent_options(parser)
    return parser
