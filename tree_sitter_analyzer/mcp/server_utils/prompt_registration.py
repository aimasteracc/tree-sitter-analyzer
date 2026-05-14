"""Prompt registration for MCP server — extracted from server.py create_server."""

import contextlib
from typing import Any

from ...utils import setup_logger
from .smart_prompts import build_smart_analyze_response, build_smart_explore_response

logger = setup_logger(__name__)


def register_prompts(server: Any) -> None:
    """Register SMART workflow prompts on the MCP server."""
    try:
        from mcp.types import Prompt, PromptArgument

        _smart_prompt_args = [
            PromptArgument(
                name="file_path",
                description="Path to the source file to analyze",
                required=True,
            ),
            PromptArgument(
                name="question",
                description="What you want to understand about the code",
                required=False,
            ),
        ]

        _project_prompt_args = [
            PromptArgument(
                name="project_root",
                description="Absolute path to the project root directory",
                required=True,
            ),
        ]

        @server.list_prompts()  # type: ignore
        async def handle_list_prompts() -> list[Prompt]:
            return [
                Prompt(
                    name="smart_analyze",
                    description="SMART Workflow: Systematic code analysis for a single file. Recommended for files you haven't seen before.",
                    arguments=_smart_prompt_args,
                ),
                Prompt(
                    name="smart_explore",
                    description="SMART Workflow: Explore a new project. Get the full picture before diving into code.",
                    arguments=_project_prompt_args,
                ),
            ]

        @server.get_prompt()  # type: ignore
        async def handle_get_prompt(name: str, arguments: dict[str, str] | None) -> Any:
            args = arguments or {}
            if name == "smart_analyze":
                file_path = args.get("file_path", "<file_path>")
                question = args.get(
                    "question", "understand the structure and key logic"
                )
                return build_smart_analyze_response(file_path, question)
            elif name == "smart_explore":
                project_root = args.get("project_root", "<project_root>")
                return build_smart_explore_response(project_root)
            raise ValueError(f"Unknown prompt: {name}")

    except ImportError:
        with contextlib.suppress(ValueError, OSError):
            logger.debug("Prompts API unavailable, skipping SMART prompt registration")
    except Exception as e:
        with contextlib.suppress(ValueError, OSError):
            logger.debug(f"Prompts registration failed: {e}")
