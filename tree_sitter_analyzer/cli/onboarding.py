"""onboarding — one-command setup: index + agent registration + overview (#1856).

``tree-sitter-analyzer setup`` (alias of ``--setup``):

1. detects the AI assistant(s) used in a project,
2. plans the exact config files it would create or update (project-scoped
   only: ``.mcp.json``, ``.cursor/mcp.json``, ``.vscode/mcp.json`` and
   ``.claude/skills/tsa-*``),
3. applies the plan only after explicit confirmation (``--setup-yes`` or an
   interactive ``y``), then warms the index and prints a project overview.

Safety properties: no network access, no write to the home directory or any
user-global config, dry-run by default, idempotent (an existing
``tree-sitter-analyzer`` server entry is never overwritten), and malformed
existing config files are reported and left untouched.
"""

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SERVER_NAME = "tree-sitter-analyzer"
SUPPORTED_AGENTS: tuple[str, ...] = ("claude-code", "cursor", "vscode")

# agent -> (config path relative to project root, top-level key)
_MCP_CONFIG: dict[str, tuple[str, str]] = {
    "claude-code": (".mcp.json", "mcpServers"),
    "cursor": (".cursor/mcp.json", "mcpServers"),
    "vscode": (".vscode/mcp.json", "servers"),
}
# agent -> project marker directories that signal usage
_MARKERS: dict[str, tuple[str, ...]] = {
    "claude-code": (".claude",),
    "cursor": (".cursor",),
    "vscode": (".vscode",),
}
_DEFAULT_AGENT = "claude-code"


@dataclass(frozen=True)
class PlannedChange:
    """One file-level change the setup would make."""

    kind: str  # "mcp" | "skills"
    agent: str
    path: str
    action: str  # "create" | "update" | "unchanged" | "error"
    detail: str = ""

    @property
    def writes(self) -> bool:
        return self.action in ("create", "update")


@dataclass(frozen=True)
class SetupPlan:
    project_root: str
    agents: tuple[str, ...]
    detected: tuple[str, ...]
    changes: tuple[PlannedChange, ...] = field(default_factory=tuple)

    @property
    def pending(self) -> tuple[PlannedChange, ...]:
        return tuple(c for c in self.changes if c.writes)

    @property
    def errors(self) -> tuple[PlannedChange, ...]:
        return tuple(c for c in self.changes if c.action == "error")


def mcp_server_entry(project_root: Path) -> dict[str, Any]:
    """Return the server definition registered with each assistant."""
    return {
        "command": "uvx",
        "args": [
            "--from",
            "tree-sitter-analyzer[mcp]",
            "tree-sitter-analyzer-mcp",
        ],
        "env": {"TREE_SITTER_PROJECT_ROOT": str(project_root)},
    }


def detect_agents(
    project_root: Path,
    *,
    home: Path | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> tuple[str, ...]:
    """Detect assistants from project markers, ``claude`` on PATH, or ~/.claude.

    The home directory is only *read* (existence check), never written.
    """
    found: list[str] = []
    home_dir = home if home is not None else Path.home()
    for agent in SUPPORTED_AGENTS:
        if any((project_root / m).is_dir() for m in _MARKERS[agent]):
            found.append(agent)
    if "claude-code" not in found and (
        which("claude") or (home_dir / ".claude").is_dir()
    ):
        found.insert(0, "claude-code")
    return tuple(found)


def parse_agents(value: str | None) -> tuple[str, ...] | None:
    """Parse ``--setup-agents``; raises ValueError on unknown names."""
    if not value:
        return None
    names = [n.strip().lower() for n in value.split(",") if n.strip()]
    unknown = [n for n in names if n not in SUPPORTED_AGENTS]
    if unknown:
        raise ValueError(
            f"Unknown agent(s): {', '.join(unknown)}. "
            f"Supported: {', '.join(SUPPORTED_AGENTS)}"
        )
    return tuple(dict.fromkeys(names))


def _plan_mcp(project_root: Path, agent: str) -> PlannedChange:
    rel, key = _MCP_CONFIG[agent]
    path = project_root / rel
    if not path.exists():
        return PlannedChange("mcp", agent, str(path), "create", f"add {SERVER_NAME}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return PlannedChange("mcp", agent, str(path), "error", f"unreadable: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get(key, {}), dict):
        return PlannedChange(
            "mcp",
            agent,
            str(path),
            "error",
            f"unexpected structure (no '{key}' object)",
        )
    if SERVER_NAME in data.get(key, {}):
        return PlannedChange("mcp", agent, str(path), "unchanged", "already registered")
    return PlannedChange("mcp", agent, str(path), "update", f"add {SERVER_NAME}")


def _bundled_skill_names() -> list[str]:
    from .install_skills import _bundled_skills_dir

    root = _bundled_skills_dir()
    return sorted(
        p.name for p in root.iterdir() if p.is_dir() and p.name.startswith("tsa-")
    )


def _plan_skills(project_root: Path) -> PlannedChange:
    dest = project_root / ".claude" / "skills"
    missing = [n for n in _bundled_skill_names() if not (dest / n).exists()]
    if not missing:
        return PlannedChange(
            "skills", "claude-code", str(dest), "unchanged", "all skills present"
        )
    return PlannedChange(
        "skills",
        "claude-code",
        str(dest),
        "create",
        f"install {len(missing)} skill(s): {', '.join(missing)}",
    )


def build_plan(
    project_root: Path,
    agents: Sequence[str] | None = None,
    *,
    home: Path | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> SetupPlan:
    """Compute the changes without touching the filesystem."""
    detected = detect_agents(project_root, home=home, which=which)
    chosen = tuple(agents) if agents else (detected or (_DEFAULT_AGENT,))
    changes: list[PlannedChange] = [_plan_mcp(project_root, a) for a in chosen]
    if "claude-code" in chosen:
        changes.append(_plan_skills(project_root))
    return SetupPlan(str(project_root), chosen, detected, tuple(changes))


def _apply_mcp(project_root: Path, change: PlannedChange) -> None:
    key = _MCP_CONFIG[change.agent][1]
    path = Path(change.path)
    data: dict[str, Any] = {}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    servers = {**data.get(key, {}), SERVER_NAME: mcp_server_entry(project_root)}
    merged = {**data, key: servers}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")


def apply_plan(plan: SetupPlan) -> list[str]:
    """Write the pending changes. Returns the paths written."""
    if plan.errors:
        raise ValueError("Refusing to apply: plan has errors")
    root = Path(plan.project_root)
    written: list[str] = []
    for change in plan.pending:
        if change.kind == "mcp":
            _apply_mcp(root, change)
        elif change.kind == "skills":
            import contextlib
            import io

            from .install_skills import install_skills

            with contextlib.redirect_stderr(io.StringIO()):
                install_skills(target_dir=root)
        written.append(change.path)
    return written


def default_index_runner(project_root: Path) -> dict[str, Any]:
    """Warm the local AST index (no network)."""
    import asyncio

    from ..mcp.tools.auto_index_tool import CodeGraphAutoIndexTool

    tool = CodeGraphAutoIndexTool(project_root=str(project_root))
    return dict(asyncio.run(tool.execute({"mode": "warm", "output_format": "json"})))


def default_overview_runner(project_root: Path) -> dict[str, Any]:
    """Reuse the existing project card facade for the overview."""
    import asyncio

    from ..mcp.tools.project_facade import build_project_facade

    facade = build_project_facade(project_root=str(project_root))
    return dict(
        asyncio.run(facade.execute({"action": "card", "output_format": "json"}))
    )


def render_plan(plan: SetupPlan) -> str:
    lines = [
        f"Project: {plan.project_root}",
        f"Assistants: {', '.join(plan.agents)}"
        + ("" if plan.detected else " (none detected; defaulting)"),
        "Planned changes:",
    ]
    for c in plan.changes:
        lines.append(f"  [{c.action:9}] {c.path}  ({c.detail})")
    lines.append(
        "After applying: warms the local index (.ast-cache/, .tree-sitter-cache/ "
        "in the project; skip with --setup-no-index)."
    )
    return "\n".join(lines)


def _confirm(prompt_fn: Callable[[str], str]) -> bool:
    try:
        return prompt_fn("Apply these changes? [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def run_setup(
    project_root: Path,
    *,
    agents: Sequence[str] | None = None,
    assume_yes: bool = False,
    skip_index: bool = False,
    interactive: bool | None = None,
    home: Path | None = None,
    which: Callable[[str], str | None] = shutil.which,
    prompt_fn: Callable[[str], str] = input,
    index_runner: Callable[[Path], dict[str, Any]] = default_index_runner,
    overview_runner: Callable[[Path], dict[str, Any]] = default_overview_runner,
    out: Callable[[str], None] = print,
) -> int:
    """Run the setup flow. Returns a process exit code."""
    plan = build_plan(project_root, agents, home=home, which=which)
    out(render_plan(plan))
    if plan.errors:
        out("Cannot continue: fix or remove the files marked [error] first.")
        return 1
    if not plan.pending:
        out("Nothing to change: already set up.")
    else:
        is_tty = sys.stdin.isatty() if interactive is None else interactive
        if not assume_yes and not (is_tty and _confirm(prompt_fn)):
            out("Dry run: nothing written. Re-run with --setup-yes to apply.")
            return 0
        written = apply_plan(plan)
        out(f"Applied {len(written)} change(s).")
    if skip_index:
        return 0
    return _index_and_overview(project_root, index_runner, overview_runner, out)


def format_overview(card: dict[str, Any]) -> str:
    """Condense a project card into a few readable lines."""
    summary = card.get("agent_summary") or {}
    langs = card.get("language_distribution") or {}
    headline = card.get("summary_line") or summary.get("summary_line")
    lines = [f"  {headline or '(no summary)'}"]
    if "file_count" in card:
        lines.append(f"  files: {card['file_count']}")
    if langs:
        lines.append("  languages: " + ", ".join(f"{k} {v}" for k, v in langs.items()))
    if summary.get("next_step"):
        lines.append(f"  next: {summary['next_step']}")
    return "\n".join(lines)


def _index_and_overview(
    project_root: Path,
    index_runner: Callable[[Path], dict[str, Any]],
    overview_runner: Callable[[Path], dict[str, Any]],
    out: Callable[[str], None],
) -> int:
    try:
        result = index_runner(project_root)
        out(f"Index: {'ok' if result.get('success', True) else 'failed'}")
        card = overview_runner(project_root)
        out("Overview:")
        out(format_overview(card))
    except Exception as exc:  # noqa: BLE001 - report, never crash after writes
        out(f"Index/overview failed: {exc}")
        return 1
    out("Restart your assistant to load the MCP server.")
    return 0
