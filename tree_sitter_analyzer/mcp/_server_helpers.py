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
        LoggingCapability,
        PromptsCapability,
        ResourcesCapability,
        ToolsCapability,
    )

    capabilities = ServerCapabilities(
        tools=ToolsCapability(listChanged=True),
        resources=ResourcesCapability(subscribe=True, listChanged=True),
        prompts=PromptsCapability(listChanged=True),
        logging=LoggingCapability(),
    )
    return initialization_options_cls(
        server_name=server_name,
        server_version=server_version,
        capabilities=capabilities,
    )


def attach_tool_aliases(target: Any, tools: Mapping[str, Any]) -> None:
    """Attach backward-compatible tool attributes to the MCP server object."""
    target.analyze_scale_tool = tools["check_code_scale"]
    target.analyze_code_structure_tool = tools["analyze_code_structure"]
    target.table_format_tool = target.analyze_code_structure_tool
    target.read_partial_tool = tools["extract_code_section"]
    target.query_tool = tools["query_code"]
    target.list_files_tool = tools["list_files"]
    target.search_content_tool = tools["search_content"]
    target.find_and_grep_tool = tools["find_and_grep"]
    target.agent_skills_tool = tools["list_agent_skills"]
    target.agent_workflow_tool = tools["get_agent_workflow"]
    target.parser_readiness_tool = tools["advise_parser_readiness"]
    target.project_overview_tool = tools["get_project_overview"]
    target.file_health_tool = tools["check_file_health"]
    target.dependency_analysis_tool = tools["analyze_dependencies"]


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
