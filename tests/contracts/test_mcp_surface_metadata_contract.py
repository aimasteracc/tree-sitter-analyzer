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
    assert len(skill_files) >= 8, (  # ratchet: nondeterministic
        f"Expected at least 8 tsa-* skills, found {len(skill_files)}. The "
        "10-skill design exists so each skill stays under 12 tools — "
        "collapsing to fewer skills defeats the progressive-disclosure "
        "token savings."
    )


def test_rfc0022_process_local_cli_parity_exception_is_exact() -> None:
    """Keep process-local facade controls narrow and explicitly accounted for."""
    from tree_sitter_analyzer.cli.commands.mcp_commands._read_existing_bridge import (
        READ_EXISTING_BRIDGE_BY_ACTION,
        READ_EXISTING_BRIDGED_CONTROLS,
    )
    from tree_sitter_analyzer.mcp.facade_map import LEGACY_TOOL_MAP, NEW_ACTION_PARITY

    expected = {
        ("index", "status"): {"access_mode"},
        ("nav", "context"): {"access_mode", "snapshot_id", "source_generation"},
        ("edit", "safe"): {"access_mode", "snapshot_id", "source_generation"},
        ("edit", "impact"): {
            "access_mode",
            "capture_diff_snapshot",
            "scope_paths",
        },
        ("edit", "constraints"): {
            "access_mode",
            "diff_snapshot_id",
            "persist",
            "scope_paths",
            "snapshot_id",
            "source_generation",
        },
        ("edit", "classify"): {"access_mode", "diff_snapshot_id"},
        ("edit", "ast_diff"): {"access_mode", "diff_snapshot_id"},
        ("edit", "release_snapshot"): {"diff_snapshot_id", "route_lease_id"},
    }
    _tools, lookup = _create_tool_registry(str(PROJECT_ROOT))
    actual: dict[tuple[str, str], set[str]] = {}
    for facade, tool in lookup.items():
        for param, actions in tool._action_scoped_params.items():
            for action in actions:
                actual.setdefault((facade, action), set()).add(param)
    assert actual == expected

    declared = {
        (facade, action)
        for facade, tool in lookup.items()
        for action in (*tool.action_map, *tool.bespoke_map)
    }
    cli_routes = set(LEGACY_TOOL_MAP.values()) | {
        (facade, action) for facade, action, _flag in NEW_ACTION_PARITY.values()
    }
    facade_level_only = {
        ("search", "select"),
        ("search", "subscribe"),
        ("search", "unsubscribe"),
        ("structure", "signatures"),
    }
    assert declared - cli_routes == facade_level_only | {("edit", "release_snapshot")}

    # Codex P1 (#1257): process-local controls are NOT MCP-only. Every
    # control scoped to a CLI-routed facade action must be forwardable
    # through the in-process CLI-handler bridge
    # (``mcp_commands._read_existing_bridge``). The residual is the only
    # documented exception: producer-only tokens (``capture_diff_snapshot``,
    # forbidden with ``access_mode`` by RFC-0022) and controls with their own
    # dedicated CLI affordance (``scope_paths`` via ``--change-impact-scope``,
    # ``persist`` via ``--constraints-read-only``).
    residual: dict[tuple[str, str], frozenset[str]] = {
        ("edit", "impact"): frozenset({"capture_diff_snapshot", "scope_paths"}),
        ("edit", "constraints"): frozenset({"persist", "scope_paths"}),
    }
    unbridged: dict[tuple[str, str], frozenset[str]] = {}
    for (facade, action), controls in actual.items():
        if (facade, action) not in cli_routes:
            continue
        bridged = READ_EXISTING_BRIDGE_BY_ACTION.get((facade, action), frozenset())
        remaining = frozenset(controls - bridged)
        if remaining:
            unbridged[(facade, action)] = remaining
    assert unbridged == residual

    bridged_params = frozenset(READ_EXISTING_BRIDGED_CONTROLS)
    for (facade, action), controls in READ_EXISTING_BRIDGE_BY_ACTION.items():
        assert (facade, action) in actual, (
            f"bridge row ({facade}, {action}) has no action-scoped params"
        )
        assert controls <= bridged_params, (
            f"bridge row ({facade}, {action}) references unknown controls: "
            f"{sorted(controls - bridged_params)}"
        )
        assert controls <= actual[(facade, action)], (
            f"bridge row ({facade}, {action}) forwards controls not scoped to "
            f"the action: {sorted(controls - actual[(facade, action)])}"
        )


def test_tsa_explore_prototype_is_retired_with_zero_references() -> None:
    """RFC-0022 disposition: the tsa_explore prototype is retired.

    The umbrella-tool experiment remains hypothetical (see
    benchmarks/codegraph_compare/tool_menu_experiment.py, which documents
    tsa_explore as "does not exist"); no code or tests may reference the
    retired module.
    """
    import re

    retired_path = PROJECT_ROOT / "tree_sitter_analyzer" / "mcp" / "tsa_explore.py"
    assert not retired_path.exists(), "tsa_explore.py must stay deleted"

    pattern = re.compile(r"\btsa_explore\b")
    self_path = Path(__file__).resolve()
    offenders: list[str] = []
    for base in ("tree_sitter_analyzer", "tests"):
        for path in (PROJECT_ROOT / base).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if path.resolve() == self_path:
                continue  # this contract test itself names the retired tool
            if pattern.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(PROJECT_ROOT)))
    assert offenders == [], f"retired tsa_explore still referenced: {offenders}"
