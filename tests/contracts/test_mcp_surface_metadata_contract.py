"""Contract tests split from the former agent workflow monolith."""
# ruff: noqa: F401

from __future__ import annotations

import ast
import configparser
import os
import re
from pathlib import Path

import pytest

try:
    import tomllib  # Python 3.11+ stdlib
except ImportError:  # Python 3.10 — fall back to the tomli back-port
    import tomli as tomllib
from hypothesis import settings as hypothesis_settings

from tree_sitter_analyzer.cli_main import create_argument_parser
from tree_sitter_analyzer.mcp.server import _create_tool_registry

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKIPPED_SCAN_DIRS = {
    ".git",
    ".benchmark-repos",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    ".venv",
}

def test_registered_mcp_tools_have_codemap_parity() -> None:
    """Every registered MCP tool must appear in `docs/CODEMAPS/mcp-tools.md`.

    The codemap is the single source of truth for the agent landing
    experience — if a tool is registered but absent from the codemap,
    agents reading AGENTS.md → the codemap will be blind to it. A
    pre-commit hook (`scripts/codemap-sync-check.sh`) catches this at
    commit time; this test is the CI safety net for `SKIP_CODEMAP_SYNC=1`
    bypasses and non-AI commits.

    Mirrors `test_registered_mcp_tools_have_cli_parity` /
    `_have_skill_parity` — same contract pattern, codemap layer.
    """
    codemap_path = PROJECT_ROOT / "docs" / "CODEMAPS" / "mcp-tools.md"
    assert codemap_path.exists(), (
        f"{codemap_path} is missing — the codemap is the single source "
        "of truth for the agent landing experience."
    )

    # Parse codemap table rows: ``| `tool_name` | ... | ... |``
    codemap_re = re.compile(r"^\|\s*`([a-z_]+)`\s*\|")
    codemap_tools: set[str] = set()
    for line in codemap_path.read_text(encoding="utf-8").splitlines():
        m = codemap_re.match(line)
        if m:
            codemap_tools.add(m.group(1))

    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry
    from tree_sitter_analyzer.mcp.facade_map import (
        FACADE_NAMES,
        LEGACY_TOOL_MAP,
        NEW_ACTION_PARITY,
    )

    registered = {name for name, _tool in create_tool_registry(str(PROJECT_ROOT))[0]}

    # Wave C2 re-key: the codemap documents BOTH the 8 live facades (the new
    # public surface) AND the 62 legacy capability names (so agents reading
    # the codemap can still find "what happened to codegraph_callers?"). Every
    # codemap row must therefore be either a live facade or a known legacy
    # capability name — and all 8 facades must be present.
    missing_facades_in_codemap = sorted(registered - codemap_tools)
    assert missing_facades_in_codemap == [], (
        "These registered MCP facades have NO row in "
        "docs/CODEMAPS/mcp-tools.md. Add each to the table and re-stage in "
        f"the same commit: {missing_facades_in_codemap}"
    )

    allowed_codemap_names = (
        set(FACADE_NAMES) | set(LEGACY_TOOL_MAP) | set(NEW_ACTION_PARITY)
    )
    stale_in_codemap = sorted(codemap_tools - allowed_codemap_names)
    assert stale_in_codemap == [], (
        "These codemap rows reference names that are neither a live facade "
        "nor a known legacy capability (likely typo or removed tool): "
        f"{stale_in_codemap}"
    )


def test_registered_mcp_tools_have_skill_parity() -> None:
    """Every registered MCP tool must appear in at least one tsa-* skill's
    ``allowed-tools`` list.

    Skills sit on top of the MCP registry as progressive-disclosure
    bundles: each skill loads only its own tool definitions on invocation,
    cutting per-turn token cost vs. exposing all tools every turn. If a
    new MCP tool ships without being added to any skill, agents lose the
    discovery + routing path for it. This test enforces the contract.

    Mirrors ``test_registered_mcp_tools_have_cli_parity`` — same idea but
    for the skill layer instead of the CLI layer.

    Wave D (G1): skill allowlists rewritten to the 8 facade names; xfail removed.
    """
    skills_dir = PROJECT_ROOT / ".claude" / "skills"
    if not skills_dir.exists():
        # Skills are an optional layer. If the project hasn't shipped any
        # skills yet, the contract degrades to "no requirement".
        return

    tool_re = re.compile(r"^\s*-\s*mcp__tree-sitter-analyzer__([a-z_]+)\s*$")
    covered: set[str] = set()
    skill_files = sorted(skills_dir.glob("tsa-*/SKILL.md"))
    for skill_path in skill_files:
        in_allowed = False
        for line in skill_path.read_text(encoding="utf-8").splitlines():
            stripped = line.rstrip()
            if stripped.startswith("allowed-tools:"):
                in_allowed = True
                continue
            if in_allowed:
                # YAML frontmatter ends at the closing `---` or when a new
                # top-level key starts (no leading space).
                if stripped == "---":
                    break
                if stripped and not stripped.startswith((" ", "\t", "-")):
                    in_allowed = False
                    continue
                match = tool_re.match(line)
                if match:
                    covered.add(match.group(1))

    # Use the central registry (``_tool_registry.create_tool_registry``)
    # as source of truth, not ``server._create_tool_registry`` which is
    # known to be stale (see Pain pass 2 / pain #26 comments in the
    # central registry). The skill layer must align with the *canonical*
    # tool list, not the historical drift in ``server.py``.
    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

    registered = {name for name, _tool in create_tool_registry(str(PROJECT_ROOT))[0]}

    missing_skill_coverage = sorted(registered - covered)
    typo_in_skill = sorted(covered - registered)

    assert missing_skill_coverage == [], (
        "These registered MCP tools have NO skill listing them in "
        "allowed-tools. Add each to the most appropriate tsa-* skill "
        f"under .claude/skills/: {missing_skill_coverage}"
    )
    assert typo_in_skill == [], (
        "These tools appear in a skill's allowed-tools but are NOT "
        "registered in the MCP server (likely typo or stale entry): "
        f"{typo_in_skill}"
    )
    # Guard against the skill layer being silently empty if someone moves
    # the directory: insist on at least the canonical landing skill.
    assert (skills_dir / "tsa-landing" / "SKILL.md").exists(), (
        "tsa-landing skill is missing — the cold-start landing skill is "
        "the entry point every other skill builds on."
    )
    assert len(skill_files) >= 8, (
        f"Expected at least 8 tsa-* skills, found {len(skill_files)}. The "
        "10-skill design exists so each skill stays under 12 tools — "
        "collapsing to fewer skills defeats the progressive-disclosure "
        "token savings."
    )
