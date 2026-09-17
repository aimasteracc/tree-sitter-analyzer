#!/usr/bin/env python3
"""``project`` 门面：聚合九个项目级智能动作。

项目级能力统一通过 ``action`` 参数选择：

=============  ==========================================  ==========================
action         内部路由                                    用途
=============  ==========================================  ==========================
overview       ``get_project_overview``                    项目概览
smart          ``smart_context``                           面向任务的上下文
parser         ``advise_parser_readiness``                 解析器就绪检查
metrics        ``codegraph_metrics``                       图统计
skills         ``list_agent_skills``                       代理技能清单
workflow       ``get_agent_workflow``                      建议工作流
journal        ``decision_journal``                        读写决策日志
doc_sync       ``doc_sync``                                同步文档与代码状态
card           ``get_project_summary``                     项目名片
=============  ==========================================  ==========================

RFC-0027 §L7：``card`` 接入此前无法访问的 ``GetProjectSummaryTool``，根据
TSA 已计算的事实生成项目用途、主要语言、入口和模块说明，无需 LLM 客户端。

索引生命周期动作（``status`` / ``build`` / ``full`` / ``auto`` / ``sync`` /
``cache``）由独立的 ``index`` 门面（``build_index_facade``）负责。

注解说明（spec §6 / review §8 F-extra-3）：
    ``journal`` 和 ``doc_sync`` 可能写入。混合读写动作的门面不能声明
    ``readOnlyHint=True``，因此使用 ``readOnlyHint=False`` 与
    ``destructiveHint=False``。只读动作会失去只读提示，这是 PRD §4 接受的取舍。

    P0 阶段该门面尚未在 ``_tool_registry.py`` 注册；Wave C 完成注册切换。
"""

from __future__ import annotations

from typing import Any

from .facade_tool import FacadeTool

# annotation-honesty rationale in module docstring above
_PROJECT_ANNOTATIONS: dict[str, Any] = {
    "readOnlyHint": False,  # journal/doc_sync write; honest for a mixed facade
    "destructiveHint": False,  # writes are append-only (journal) or sync (doc_sync)
    "idempotentHint": False,  # doc_sync is not strictly idempotent
    "openWorldHint": False,
}

_PROJECT_DESCRIPTION = (
    "Code-intelligence (codegraph-compatible) project-intelligence hub. "
    "Covers codegraph_metrics (graph-level stats), project overview, "
    "smart task-focused context, parser readiness, "
    "agent skills/workflow, decision journal, and doc sync in one tool. "
    "Pick a capability via `action`:\n"
    "\n"
    "PROJECT INFO (read-only):\n"
    "- action=overview — high-level summary of languages, entry points, and "
    "architecture. Best first call on an unfamiliar repo. Params: format.\n"
    "- action=smart — one-shot orientation for a single file: file_health "
    "grade, exported symbols (the file's public API), upstream/downstream "
    "dependencies, associated test files, and edit-risk in one envelope "
    "(replaces Read + file_health + dependency_analysis + safe_to_edit). "
    "Params: file_path.\n"
    "- action=parser — check tree-sitter parser readiness for the project "
    "languages. Params: format.\n"
    "- action=metrics — codegraph graph-level statistics (node/edge counts, "
    "top hubs, codegraph_metrics equivalent). Params: format.\n"
    "- action=skills — enumerate available agent skills for this project. "
    "Params: format.\n"
    "- action=workflow — recommended agent workflow for the current task type. "
    "Params: task_type, format.\n"
    "- action=card — the project card (RFC-0027 §L7): purpose from the README, "
    "top code languages, entry points, key config files, and per-module "
    "descriptions of the top-level structure. Persistent — built once into "
    ".tree-sitter-cache/project-index.json and recalled instantly. Best first "
    "call on an unfamiliar repo when you want the *what*, not the file list. "
    "Params: force_refresh, include_notes, output_format.\n"
    "\n"
    "DECISION + DOC (may write):\n"
    "- action=journal — persistent architectural decision journal. "
    "Params: mode (record/get/search/supersede), title, rationale, verdict, "
    "query, verdict_filter, id, new_id, scope_paths, alternatives, "
    "related_symbols, tags, path_scope, limit.\n"
    "- action=doc_sync — sync documentation to current code state. "
    "Params: path, dry_run.\n"
    "\n"
    "For index lifecycle (status/build/full/auto/sync/cache), use the "
    "``index`` facade instead.\n"
)


def build_project_facade(project_root: str | None = None) -> FacadeTool:
    """Construct the ``project`` facade wired to live inner tool instances.

    Imports are inlined to keep cold-start cost off the import path for callers
    that don't build the facade (matches the lazy-import convention in
    ``_tool_registry.py``).

    Index lifecycle actions (status/build/full/auto/sync/cache) are handled
    by the dedicated ``index`` facade; see ``build_index_facade``.
    """
    from .agent_skills_tool import AgentSkillsTool
    from .agent_workflow_tool import AgentWorkflowTool
    from .codegraph_metrics_tool import CodeGraphMetricsTool
    from .decision_journal_tool import DecisionJournalTool
    from .doc_sync_tool import DocSyncTool
    from .get_project_summary_tool import GetProjectSummaryTool
    from .parser_readiness_tool import ParserReadinessTool
    from .project_overview_tool import ProjectOverviewTool
    from .smart_context_tool import SmartContextTool

    facade = FacadeTool(
        facade_name="project",
        action_map={
            # -- project info (read-only) -----------------------------------
            "overview": ProjectOverviewTool(project_root),
            "smart": SmartContextTool(project_root),  # S2 agentic highlight
            "parser": ParserReadinessTool(project_root),
            "metrics": CodeGraphMetricsTool(project_root),
            "skills": AgentSkillsTool(project_root),
            "workflow": AgentWorkflowTool(project_root),
            # RFC-0027 §L7: the project card, wired from the orphaned tool.
            "card": GetProjectSummaryTool(project_root),
            # -- decision + doc (may write) ---------------------------------
            "journal": DecisionJournalTool(project_root),
            "doc_sync": DocSyncTool(project_root),
        },
        bespoke_map={},  # 九个动作都直接委托给 action_map
        description=_PROJECT_DESCRIPTION,
        annotations=_PROJECT_ANNOTATIONS,
        project_root=project_root,
    )
    # No bespoke inners to register: every action routes via action_map,
    # so G3 rebind propagation is fully automatic.
    return facade
