"""Known MCP tool-response envelope violations (shrink-only).

Each entry silences one ``(tool, rule)`` pair reported by
``tests/pytest_tool_response_guard.py``. ``tool`` is an ``fnmatch`` pattern
over the guard's tool label (``nav action=callers`` for a facade call, the
tool definition name otherwise). Every entry names the issue that tracks the
producer fix; remove the entry in the PR that fixes it.

``tests/governance/test_tool_response_allowlist.py`` pins the entry count, so
the list can only get shorter.
"""

from __future__ import annotations

ALLOWLIST: list[dict[str, str]] = [
    {
        "tool": "analyze_change_impact",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "check_constraints",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "codegraph_complexity_heatmap",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "codegraph_dead_code",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "codegraph_full_index",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "codegraph_incremental_sync",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "codegraph_knowledge_graph",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "codegraph_knowledge_index",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "codegraph_pr_review",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "codegraph_query",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "codegraph_refactor",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "codegraph_resolve",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "codegraph_test_gap",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "codegraph_uml",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "codegraph_visualize",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "edit action=pr",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "extract_code_section",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "get_project_schema",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "hyphae_select",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "modification_guard",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "nav action=co_change",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "nav action=test_map",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "pulse",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "query_code",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "refactoring_suggestions",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "semantic_neighbors",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "tql_execute",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "trace_impact",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "unreachable_code",
        "rule": "error-code",
        "issue": "#1808",
        "reason": "failure without error_code/error_type",
    },
    {
        "tool": "codegraph_incremental_sync",
        "rule": "base",
        "issue": "#1809",
        "reason": "success=False without an 'error' string",
    },
    {
        "tool": "codegraph_refactor",
        "rule": "base",
        "issue": "#1809",
        "reason": "success=False without an 'error' string",
    },
    {
        "tool": "edit action=verify",
        "rule": "base",
        "issue": "#1809",
        "reason": "success=False without an 'error' string",
    },
    {
        "tool": "pulse_batch",
        "rule": "base",
        "issue": "#1809",
        "reason": "success=False without an 'error' string",
    },
    {
        "tool": "verify_plan",
        "rule": "base",
        "issue": "#1809",
        "reason": "success=False without an 'error' string",
    },
    {
        "tool": "check_file_health",
        "rule": "base",
        "issue": "#1810",
        "reason": "non-canonical verdict 'N/A' on empty/non-code files",
    },
    {
        "tool": "health action=file",
        "rule": "base",
        "issue": "#1810",
        "reason": "non-canonical verdict 'N/A' on empty/non-code files",
    },
    {
        "tool": "codegraph_full_index",
        "rule": "completeness-reasons",
        "issue": "#1811",
        "reason": "completeness status/reason codes",
    },
    {
        "tool": "codegraph_status",
        "rule": "completeness-reasons",
        "issue": "#1811",
        "reason": "completeness status/reason codes",
    },
    {
        "tool": "codegraph_status",
        "rule": "completeness-status",
        "issue": "#1811",
        "reason": "completeness status/reason codes",
    },
    {
        "tool": "index action=status",
        "rule": "completeness-reasons",
        "issue": "#1811",
        "reason": "completeness status/reason codes",
    },
    {
        "tool": "search action=uql",
        "rule": "completeness-reasons",
        "issue": "#1811",
        "reason": "completeness status/reason codes",
    },
    {
        "tool": "uql",
        "rule": "completeness-reasons",
        "issue": "#1811",
        "reason": "completeness status/reason codes",
    },
    {
        "tool": "advise_parser_readiness",
        "rule": "failure-verdict",
        "issue": "#1812",
        "reason": "verdict inconsistent with success/agent_summary",
    },
    {
        "tool": "advise_parser_readiness",
        "rule": "verdict-mirror",
        "issue": "#1812",
        "reason": "verdict inconsistent with success/agent_summary",
    },
    {
        "tool": "ast_diff",
        "rule": "success-verdict",
        "issue": "#1812",
        "reason": "verdict inconsistent with success/agent_summary",
    },
    {
        "tool": "check_constraints",
        "rule": "failure-verdict",
        "issue": "#1812",
        "reason": "verdict inconsistent with success/agent_summary",
    },
    {
        "tool": "codegraph_test_gap",
        "rule": "agent-summary-shape",
        "issue": "#1812",
        "reason": "verdict inconsistent with success/agent_summary",
    },
    {
        "tool": "hyphae_select",
        "rule": "verdict-mirror",
        "issue": "#1812",
        "reason": "verdict inconsistent with success/agent_summary",
    },
    {
        "tool": "safe_to_edit",
        "rule": "success-verdict",
        "issue": "#1812",
        "reason": "verdict inconsistent with success/agent_summary",
    },
    {
        "tool": "smart_context",
        "rule": "success-verdict",
        "issue": "#1812",
        "reason": "verdict inconsistent with success/agent_summary",
    },
]
