"""Argument group sub-modules — each file owns one logical cluster of CLI flags.

All ``_add_*`` functions are re-exported from here so that
``argument_parser_builder`` only needs a single import line.
"""

from ._advanced import (
    _add_batch_search_options,
    _add_decision_journal_options,
    _add_environment_probe_options,
    _add_modification_guard_options,
    _add_trace_impact_options,
)
from ._agents import (
    _add_agent_skills_options,
    _add_agent_workflow_options,
)
from ._analysis import (
    _add_analysis_options,
    _add_mcp_analysis_options,
    _add_mcp_change_options,
    _add_mcp_health_options,
)
from ._analysis_codegraph import _add_mcp_codegraph_map_options
from ._analysis_graph_nav import _add_mcp_graph_nav_options
from ._core import (
    _add_batch_options,
    _add_core_options,
    _add_output_options,
    _add_partial_read_options,
    _add_project_and_logging_options,
)
from ._mcp import (
    _add_clean_state_options,
    _add_mcp_constraints_options,
    _add_mcp_index_management_options,
)
from ._query import (
    _add_query_options,
    _add_sql_platform_options,
)

__all__ = [
    "_add_agent_skills_options",
    "_add_agent_workflow_options",
    "_add_analysis_options",
    "_add_batch_options",
    "_add_batch_search_options",
    "_add_clean_state_options",
    "_add_core_options",
    "_add_decision_journal_options",
    "_add_environment_probe_options",
    "_add_mcp_analysis_options",
    "_add_mcp_change_options",
    "_add_mcp_codegraph_map_options",
    "_add_mcp_graph_nav_options",
    "_add_mcp_constraints_options",
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
