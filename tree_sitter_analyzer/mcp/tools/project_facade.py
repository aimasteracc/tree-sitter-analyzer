#!/usr/bin/env python3
"""``project`` facade — Wave B consolidation, 16-action project intelligence hub.

Folds project-level capabilities behind one ``action`` parameter:

=============  ==========================================  ==========================
action         inner / route                               when to use
=============  ==========================================  ==========================
overview       ``get_project_overview``                    high-level project summary
files          ``list_files``                              enumerate source files
smart          ``smart_context``                           S2 task-focused context
parser         ``advise_parser_readiness``                 check tree-sitter support
tools          ``check_tools``                             verify tool availability
metrics        ``codegraph_metrics``                       graph-level statistics
skills         ``list_agent_skills``                       enumerate agent skills
workflow       ``get_agent_workflow``                      suggested agent workflow
journal        ``decision_journal``                        read/write decision log
doc_sync       ``doc_sync``                               sync docs to code state
index_status   ``codegraph_status``                        index health check (read)
index_build    ``build_project_index``                     full (re)build of index
index_full     ``codegraph_full_index``                    force full reindex
index_auto     ``codegraph_autoindex``                     enable background indexing
index_sync     ``codegraph_incremental_sync``              incremental sync run
cache          ``ast_cache``                               raw AST cache query
=============  ==========================================  ==========================

Annotation note (spec §6 / review §8 F-extra-3):
    Index lifecycle actions (``index_build`` / ``index_full`` / ``index_auto`` /
    ``index_sync``) WRITE the on-disk index. ``journal`` and ``doc_sync`` also
    carry mutating intent. A single facade spanning read + mutating actions
    CANNOT honestly declare ``readOnlyHint=True``. We therefore set
    ``readOnlyHint=False, destructiveHint=False``. Read-only actions (overview,
    files, smart, parser, tools, metrics, skills, workflow, index_status, cache)
    lose the read-safe signal — accepted tradeoff per PRD §4. If per-action
    honest hints are required in future, split the index lifecycle actions into a
    dedicated ``index`` facade (Wave C+ scope).

    At P0 this facade is NOT registered in ``_tool_registry.py`` (Wave C cutover
    handles registration). The annotation is set correctly now so Wave C is clean.
"""

from __future__ import annotations

from typing import Any

from .facade_tool import FacadeTool

# annotation-honesty rationale in module docstring above
_PROJECT_ANNOTATIONS: dict[str, Any] = {
    "readOnlyHint": False,  # index_build/full/auto/sync + journal/doc_sync write
    "destructiveHint": False,  # writes are additive (index) or append-only (journal)
    "idempotentHint": False,  # index_build is not strictly idempotent
    "openWorldHint": False,
}

_PROJECT_DESCRIPTION = (
    "Unified project-intelligence hub. Pick a capability via `action`:\n"
    "\n"
    "PROJECT INFO (read-only):\n"
    "- action=overview — high-level summary of languages, entry points, and "
    "architecture. Best first call on an unfamiliar repo. Params: format.\n"
    "- action=files — enumerate source files with filtering. "
    "Params: path, extensions, limit, format.\n"
    "- action=smart — S2 task-focused context: surfaces relevant symbols, "
    "callers, and files for a task description. Distinct from overview "
    "(task-scoped vs whole-project). Params: task, limit.\n"
    "- action=parser — check tree-sitter parser readiness for the project "
    "languages. Params: format.\n"
    "- action=tools — verify availability of CLI tools (ripgrep, fd, etc.). "
    "Params: (none).\n"
    "- action=metrics — codegraph graph-level statistics (node/edge counts, "
    "top hubs). Params: format.\n"
    "- action=skills — enumerate available agent skills for this project. "
    "Params: format.\n"
    "- action=workflow — recommended agent workflow for the current task type. "
    "Params: task_type, format.\n"
    "\n"
    "DECISION + DOC (may write):\n"
    "- action=journal — read or append project decision journal entries. "
    "Params: operation, entry, limit.\n"
    "- action=doc_sync — sync documentation to current code state. "
    "Params: path, dry_run.\n"
    "\n"
    "INDEX LIFECYCLE (writes on-disk index):\n"
    "- action=index_status — check codegraph index health without writing. "
    "Params: (none).\n"
    "- action=index_build — full (re)build of the project index. Slow; use "
    "when index is absent or corrupt. Params: force.\n"
    "- action=index_full — force a complete full reindex (codegraph_full_index). "
    "Params: (none).\n"
    "- action=index_auto — enable/configure background auto-indexing. "
    "Params: enable, watch.\n"
    "- action=index_sync — run one incremental sync pass (fast; use after "
    "editing files). Params: paths.\n"
    "\n"
    "AST CACHE:\n"
    "- action=cache — query the raw AST cache for symbols, types, and "
    "references. Params: query, file_path, kind, limit.\n"
)


def build_project_facade(project_root: str | None = None) -> FacadeTool:
    """Construct the ``project`` facade wired to live inner tool instances.

    Imports are inlined to keep cold-start cost off the import path for callers
    that don't build the facade (matches the lazy-import convention in
    ``_tool_registry.py``).
    """
    from .agent_skills_tool import AgentSkillsTool
    from .agent_workflow_tool import AgentWorkflowTool
    from .ast_cache_tool import ASTCacheTool
    from .auto_index_tool import CodeGraphAutoIndexTool
    from .build_project_index_tool import BuildProjectIndexTool
    from .check_tools_tool import CheckToolsTool
    from .codegraph_metrics_tool import CodeGraphMetricsTool
    from .codegraph_status_tool import CodeGraphStatusTool
    from .decision_journal_tool import DecisionJournalTool
    from .doc_sync_tool import DocSyncTool
    from .full_index_tool import CodeGraphFullIndexTool
    from .incremental_sync_tool import CodeGraphIncrementalSyncTool
    from .list_files_tool import ListFilesTool
    from .parser_readiness_tool import ParserReadinessTool
    from .project_overview_tool import ProjectOverviewTool
    from .smart_context_tool import SmartContextTool

    facade = FacadeTool(
        facade_name="project",
        action_map={
            # -- project info (read-only) -----------------------------------
            "overview": ProjectOverviewTool(project_root),
            "files": ListFilesTool(project_root),
            "smart": SmartContextTool(project_root),  # S2 agentic highlight
            "parser": ParserReadinessTool(project_root),
            "tools": CheckToolsTool(project_root),
            "metrics": CodeGraphMetricsTool(project_root),
            "skills": AgentSkillsTool(project_root),
            "workflow": AgentWorkflowTool(project_root),
            # -- decision + doc (may write) ---------------------------------
            "journal": DecisionJournalTool(project_root),
            "doc_sync": DocSyncTool(project_root),
            # -- index lifecycle (writes on-disk index) ---------------------
            "index_status": CodeGraphStatusTool(project_root),
            "index_build": BuildProjectIndexTool(project_root),
            "index_full": CodeGraphFullIndexTool(project_root),
            "index_auto": CodeGraphAutoIndexTool(project_root),
            "index_sync": CodeGraphIncrementalSyncTool(project_root),
            # -- ast cache --------------------------------------------------
            "cache": ASTCacheTool(project_root),
        },
        bespoke_map={},  # all 16 actions are clean action_map delegates
        description=_PROJECT_DESCRIPTION,
        annotations=_PROJECT_ANNOTATIONS,
        project_root=project_root,
    )
    # No bespoke inners to register: every action routes via action_map,
    # so G3 rebind propagation is fully automatic.
    return facade
