"""Small helpers for MCP server startup wiring."""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


def build_initialization_options(
    server_name: str,
    server_version: str,
    initialization_options_cls: type[Any],
) -> Any:
    """Build MCP initialization options without bloating the runtime method."""
    from mcp.server.models import ServerCapabilities
    from mcp.types import (
        PromptsCapability,
        ResourcesCapability,
        ToolsCapability,
    )

    # NOTE: We deliberately do NOT advertise ``LoggingCapability()``.
    # The spec lets clients that see this capability call
    # ``logging/setLevel`` to adjust server verbosity (see
    # https://spec.modelcontextprotocol.io/specification/server/utilities/logging/),
    # but we never registered a handler — so the call returned JSON-RPC
    # ``-32601 Method not found`` and surfaced as ``[error]`` in every
    # client log (e.g. VS Code MCP, Claude Desktop). Until we actually
    # implement set-level routing through our logger, advertising the
    # capability is a contract lie; dropping it is the honest fix.
    capabilities = ServerCapabilities(
        tools=ToolsCapability(listChanged=True),
        resources=ResourcesCapability(subscribe=True, listChanged=True),
        prompts=PromptsCapability(listChanged=True),
    )
    return initialization_options_cls(
        server_name=server_name,
        server_version=server_version,
        capabilities=capabilities,
        instructions=_SERVER_INSTRUCTIONS,
    )


_SERVER_INSTRUCTIONS = """
## TSA MCP Routing

Use the codegraph tools first for code-intelligence questions. They are built
for indexed, cross-file answers and are usually cheaper than grep/read loops.

## Intent -> first tool

| Intent | Tool |
| --- | --- |
| Understand an area or trace a flow from a task description | codegraph_context |
| Find a symbol, class, function, or method | codegraph_symbol_search |
| Inspect a symbol with definition and references | codegraph_navigate |
| Understand several related symbols at once | codegraph_explore |
| Who calls X? | codegraph_callers |
| What does X call? | codegraph_callees |
| Trace a path from A to B | codegraph_call_graph |
| File/module dependency questions | codegraph_import_graph |
| Is the index ready? | codegraph_status |
| File discovery | list_files |
| Text search fallback after graph lookup misses | search_content |

## Default chains

- Understand an area: codegraph_context first; then answer from code_blocks.
- Trace a flow: codegraph_context first; use callers/callees only for a missing edge.
- Trace impact: codegraph_callers -> codegraph_import_graph -> synthesize.
- Unknown name: codegraph_symbol_search with a fuzzy query once, then stop.

## Stop rules

- Prefer 2-3 tool calls, then answer.
- Do not keep drilling after 4 tool calls for one question.
- Do not use grep/read loops when a codegraph tool covers the question.

## Anti-patterns (DO NOT)

- Do NOT chain codegraph_symbol_search -> codegraph_callers -> codegraph_callees
  for architecture questions — use codegraph_context (one call does all three).
- Do NOT loop codegraph_navigate over many symbols — use codegraph_explore.
- Do NOT re-verify codegraph results with grep or file reads — the AST index
  is the source of truth.
- Do NOT call codegraph_callers for a symbol found via codegraph_context —
  it already includes callers and callees.
- Do NOT call codegraph_context for a simple "where is X defined?" —
  use codegraph_symbol_search instead.

## Small project mode

When codegraph_status reports fewer than 500 nodes, only the 5 core tools
are needed: codegraph_context, codegraph_symbol_search, codegraph_navigate,
codegraph_status, and list_files. Skip batch and heavy-graph tools.
""".strip()


def attach_tool_aliases(
    target: Any, tools: Mapping[str, Any], project_root: str | None = None
) -> None:
    """Attach backward-compatible inner-tool attributes to the MCP server.

    Wave C2: the public registry now holds the 8 facades (``tools`` is keyed by
    facade name), so these legacy ``*_tool`` attributes can no longer be pulled
    from the registry. They are still used by:

      * ``server._handle_extract_code_section`` (``read_partial_tool``) and
        ``server_utils.tool_registration`` bespoke paths (``table_format_tool``);
      * ~dozens of tests that call ``server.analyze_scale_tool.execute(...)`` etc.

    We therefore build fresh inner instances directly (lazy import) and collect
    them in ``target._legacy_alias_tools`` so ``set_project_path`` rebinds them
    alongside the facades (G3 parity for these direct-access handles).
    """
    from .tools.agent_skills_tool import AgentSkillsTool
    from .tools.agent_workflow_tool import AgentWorkflowTool
    from .tools.analyze_code_structure_tool import AnalyzeCodeStructureTool
    from .tools.analyze_scale_tool import AnalyzeScaleTool
    from .tools.dependency_analysis_tool import DependencyAnalysisTool
    from .tools.file_health_tool import FileHealthTool
    from .tools.find_and_grep_tool import FindAndGrepTool
    from .tools.list_files_tool import ListFilesTool
    from .tools.parser_readiness_tool import ParserReadinessTool
    from .tools.project_overview_tool import ProjectOverviewTool
    from .tools.query_tool import QueryTool
    from .tools.read_partial_tool import ReadPartialTool
    from .tools.search_content_tool import SearchContentTool

    target.analyze_scale_tool = AnalyzeScaleTool(project_root)
    target.analyze_code_structure_tool = AnalyzeCodeStructureTool(project_root)
    # table_format_tool is the legacy alias for the structure-analysis tool.
    target.table_format_tool = target.analyze_code_structure_tool
    target.read_partial_tool = ReadPartialTool(project_root)
    target.query_tool = QueryTool(project_root)
    target.list_files_tool = ListFilesTool(project_root)
    target.search_content_tool = SearchContentTool(project_root)
    target.find_and_grep_tool = FindAndGrepTool(project_root)
    target.agent_skills_tool = AgentSkillsTool(project_root)
    target.agent_workflow_tool = AgentWorkflowTool(project_root)
    target.parser_readiness_tool = ParserReadinessTool(project_root)
    target.project_overview_tool = ProjectOverviewTool(project_root)
    target.file_health_tool = FileHealthTool(project_root)
    target.dependency_analysis_tool = DependencyAnalysisTool(project_root)

    target._legacy_alias_tools = [
        target.analyze_scale_tool,
        target.analyze_code_structure_tool,
        target.read_partial_tool,
        target.query_tool,
        target.list_files_tool,
        target.search_content_tool,
        target.find_and_grep_tool,
        target.agent_skills_tool,
        target.agent_workflow_tool,
        target.parser_readiness_tool,
        target.project_overview_tool,
        target.file_health_tool,
        target.dependency_analysis_tool,
    ]


def init_universal_tool(
    project_root: str | None,
    *,
    universal_tool_available: bool,
    universal_tool_cls: type[Any] | None,
) -> Any:
    """Initialize the optional universal analysis tool."""
    if not universal_tool_available or universal_tool_cls is None:
        return None
    try:
        return universal_tool_cls(project_root)
    except Exception:
        return None


def detect_server_version(
    base_version: str,
    *,
    platform_detector: type[Any],
    logger: Any,
) -> str:
    """Return server version annotated with platform details when available."""
    version = base_version
    try:
        platform_info = platform_detector.detect()
        version = f"{version} ({platform_info.platform_key})"
        with contextlib.suppress(Exception):
            logger.info(f"Running on platform: {platform_info}")
    except Exception as exc:
        with contextlib.suppress(Exception):
            logger.warning(f"Failed to detect platform: {exc}")
    return version


def resolve_project_root(
    cli_project_root: str | None,
    *,
    cwd_factory: Callable[[], Any] = Path.cwd,
    path_class: type[Any] = Path,
    environ: Mapping[str, str] = os.environ,
    detect_project_root_func: Callable[[], str | None],
    logger: Any,
) -> str | None:
    """Resolve the MCP project root from CLI, environment, or auto-detection."""
    project_root = _select_project_root(
        cli_project_root,
        cwd_factory=cwd_factory,
        environ=environ,
        detect_project_root_func=detect_project_root_func,
    )

    if _should_fallback_to_cwd(project_root, path_class=path_class):
        fallback_root = str(cwd_factory())
        with contextlib.suppress(ValueError, OSError):
            logger.warning(
                f"Invalid project root '{project_root}', falling back to current directory: {fallback_root}"
            )
        return fallback_root

    return project_root


def _select_project_root(
    cli_project_root: str | None,
    *,
    cwd_factory: Callable[[], Any],
    environ: Mapping[str, str],
    detect_project_root_func: Callable[[], str | None],
) -> str | None:
    """Select a candidate project root using existing priority order."""
    if cli_project_root:
        return cli_project_root

    env_project_root = environ.get("TREE_SITTER_PROJECT_ROOT")
    if cwd_factory().joinpath(env_project_root or "").exists():
        return env_project_root

    return detect_project_root_func()


def _should_fallback_to_cwd(
    project_root: str | None,
    *,
    path_class: type[Any],
) -> bool:
    """Return whether a resolved project root is unusable."""
    invalid_placeholder = isinstance(project_root, str) and (
        "${" in project_root or "}" in project_root or "$" in project_root
    )
    return bool(
        not project_root
        or invalid_placeholder
        or (isinstance(project_root, str) and not path_class(project_root).is_dir())
    )
