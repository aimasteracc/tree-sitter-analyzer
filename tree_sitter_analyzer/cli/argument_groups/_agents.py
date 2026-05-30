"""Agent skills and workflow argument groups."""

from __future__ import annotations

import argparse


def _add_agent_skills_options(parser: argparse.ArgumentParser) -> None:
    """Add the project-local agent skill inventory entrypoint."""
    parser.add_argument(
        "--agent-skills",
        action="store_true",
        help="List project-local .agents/skills metadata, gaps, and read order",
    )
    parser.add_argument(
        "--agent-skills-root",
        help="Override the skills root for --agent-skills (default: .agents/skills)",
    )


def _add_agent_workflow_options(parser: argparse.ArgumentParser) -> None:
    """Add the agent workflow pack entrypoint."""
    parser.add_argument(
        "--agent-workflow",
        action="store_true",
        help="Print a SMART workflow command pack for agent-guided code work",
    )
