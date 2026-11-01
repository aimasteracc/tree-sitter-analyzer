"""Tests for one-command onboarding (#1856). Temp dirs only; never touches ~."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tree_sitter_analyzer.cli import onboarding as ob
from tree_sitter_analyzer.cli.special_commands import (
    SpecialCommandContext,
    _handle_setup,
)

NO_CLAUDE = lambda _name: None  # noqa: E731


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    p = tmp_path / "proj"
    p.mkdir()
    return p


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    return h


def _run(proj: Path, home: Path, **kw: Any) -> tuple[int, list[str]]:
    lines: list[str] = []
    kw.setdefault("which", NO_CLAUDE)
    kw.setdefault("interactive", False)
    kw.setdefault("index_runner", lambda _r: {"success": True})
    kw.setdefault("overview_runner", lambda _r: {"card": "x"})
    code = ob.run_setup(proj, home=home, out=lines.append, **kw)
    return code, lines


def test_detect_defaults_empty(proj, home):
    assert ob.detect_agents(proj, home=home, which=NO_CLAUDE) == ()


def test_detect_markers_and_claude_binary(proj, home):
    (proj / ".cursor").mkdir()
    (proj / ".vscode").mkdir()
    assert ob.detect_agents(proj, home=home, which=NO_CLAUDE) == ("cursor", "vscode")
    got = ob.detect_agents(proj, home=home, which=lambda n: "/bin/claude")
    assert got[0] == "claude-code"


def test_detect_home_claude_dir(proj, home):
    (home / ".claude").mkdir()
    assert ob.detect_agents(proj, home=home, which=NO_CLAUDE) == ("claude-code",)


def test_parse_agents():
    assert ob.parse_agents(None) is None
    assert ob.parse_agents("cursor, claude-code,cursor") == ("cursor", "claude-code")
    with pytest.raises(ValueError):
        ob.parse_agents("emacs")


def test_dry_run_writes_nothing(proj, home):
    code, lines = _run(proj, home)
    assert code == 0
    assert list(proj.iterdir()) == []
    assert list(home.iterdir()) == []
    text = "\n".join(lines)
    assert str(proj / ".mcp.json") in text
    assert "Dry run" in text


def test_yes_applies_and_is_idempotent(proj, home):
    code, _ = _run(proj, home, assume_yes=True)
    assert code == 0
    cfg = json.loads((proj / ".mcp.json").read_text(encoding="utf-8"))
    entry = cfg["mcpServers"][ob.SERVER_NAME]
    assert entry["env"]["TREE_SITTER_PROJECT_ROOT"] == str(proj)
    skills = sorted(p.name for p in (proj / ".claude" / "skills").iterdir())
    assert skills and all(s.startswith("tsa-") for s in skills)
    assert list(home.iterdir()) == []

    before = (proj / ".mcp.json").read_text(encoding="utf-8")
    code, lines = _run(proj, home, assume_yes=True)
    assert code == 0
    assert (proj / ".mcp.json").read_text(encoding="utf-8") == before
    assert "already set up" in "\n".join(lines)


def test_merge_preserves_existing_servers(proj, home):
    (proj / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"other": {"command": "x"}}, "keep": 1}),
        encoding="utf-8",
    )
    _run(proj, home, assume_yes=True, agents=("claude-code",))
    cfg = json.loads((proj / ".mcp.json").read_text(encoding="utf-8"))
    assert cfg["keep"] == 1
    assert set(cfg["mcpServers"]) == {"other", ob.SERVER_NAME}


def test_existing_entry_never_overwritten(proj, home):
    custom = {"mcpServers": {ob.SERVER_NAME: {"command": "custom"}}}
    (proj / ".mcp.json").write_text(json.dumps(custom), encoding="utf-8")
    plan = ob.build_plan(proj, ("claude-code",), home=home, which=NO_CLAUDE)
    assert plan.changes[0].action == "unchanged"
    _run(proj, home, assume_yes=True, agents=("claude-code",))
    assert json.loads((proj / ".mcp.json").read_text(encoding="utf-8")) == custom


@pytest.mark.parametrize("content", ["{not json", "[]", '{"mcpServers": []}'])
def test_bad_config_is_error_and_untouched(proj, home, content):
    (proj / ".mcp.json").write_text(content, encoding="utf-8")
    code, lines = _run(proj, home, assume_yes=True, agents=("claude-code",))
    assert code == 1
    assert (proj / ".mcp.json").read_text(encoding="utf-8") == content
    assert "[error" in "\n".join(lines)
    with pytest.raises(ValueError):
        ob.apply_plan(ob.build_plan(proj, ("claude-code",), home=home, which=NO_CLAUDE))


def test_other_agents_use_their_schema(proj, home):
    _run(proj, home, assume_yes=True, agents=("cursor", "vscode"), skip_index=True)
    cur = json.loads((proj / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    vsc = json.loads((proj / ".vscode" / "mcp.json").read_text(encoding="utf-8"))
    assert ob.SERVER_NAME in cur["mcpServers"]
    assert ob.SERVER_NAME in vsc["servers"]
    assert not (proj / ".claude").exists()


def test_interactive_confirm(proj, home):
    code, _ = _run(proj, home, interactive=True, prompt_fn=lambda _p: "n")
    assert not (proj / ".mcp.json").exists()
    code, _ = _run(proj, home, interactive=True, prompt_fn=lambda _p: "y")
    assert (proj / ".mcp.json").exists() and code == 0


def test_interactive_eof_means_no(proj, home):
    def boom(_p: str) -> str:
        raise EOFError

    _run(proj, home, interactive=True, prompt_fn=boom)
    assert not (proj / ".mcp.json").exists()


def test_index_and_overview_called_only_after_apply(proj, home):
    calls: list[str] = []
    _run(
        proj,
        home,
        index_runner=lambda _r: calls.append("i") or {"success": True},
        overview_runner=lambda _r: calls.append("o") or {},
    )
    assert calls == []
    _run(
        proj,
        home,
        assume_yes=True,
        index_runner=lambda _r: calls.append("i") or {"success": True},
        overview_runner=lambda _r: calls.append("o") or {},
    )
    assert calls == ["i", "o"]


def test_skip_index(proj, home):
    calls: list[str] = []
    _run(
        proj,
        home,
        assume_yes=True,
        skip_index=True,
        index_runner=lambda _r: calls.append("i") or {},
    )
    assert calls == []


def test_index_failure_reported(proj, home):
    def boom(_r: Path) -> dict[str, Any]:
        raise RuntimeError("nope")

    code, lines = _run(proj, home, assume_yes=True, index_runner=boom)
    assert code == 1
    assert "nope" in "\n".join(lines)
    assert (proj / ".mcp.json").exists()


def test_index_reported_failed(proj, home):
    code, lines = _run(
        proj, home, assume_yes=True, index_runner=lambda _r: {"success": False}
    )
    assert "Index: failed" in "\n".join(lines)


def test_default_runners_delegate(proj, monkeypatch):
    import asyncio

    class FakeTool:
        def __init__(self, **kw: Any) -> None:
            pass

        async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
            return {"success": True, "args": args}

    import tree_sitter_analyzer.mcp.tools.auto_index_tool as ait
    import tree_sitter_analyzer.mcp.tools.project_facade as pf

    monkeypatch.setattr(ait, "CodeGraphAutoIndexTool", FakeTool)
    monkeypatch.setattr(pf, "build_project_facade", lambda **kw: FakeTool())
    assert ob.default_index_runner(proj)["args"]["mode"] == "warm"
    assert ob.default_overview_runner(proj)["args"]["action"] == "card"
    assert asyncio  # keep import used


def test_format_overview():
    assert ob.format_overview({}) == "  (no summary)"
    out = ob.format_overview(
        {
            "summary_line": "p python 100%",
            "file_count": 3,
            "language_distribution": {"python": 3},
            "agent_summary": {"next_step": "do x"},
        }
    )
    assert "files: 3" in out and "python 3" in out and "next: do x" in out


def test_handler_not_requested():
    ctx = SimpleNamespace()
    assert _handle_setup(SimpleNamespace(setup=False), ctx) is None  # type: ignore[arg-type]


def test_handler_bad_agent_and_dispatch(proj, monkeypatch):
    errors: list[str] = []
    ctx = SpecialCommandContext(
        asyncio_run=lambda c: c,
        output_json=lambda d: None,
        output_error=errors.append,
        output_info=lambda m: None,
        output_list=lambda m: None,
        query_loader=None,
    )
    args = SimpleNamespace(setup=True, setup_agents="emacs", project_root=str(proj))
    assert _handle_setup(args, ctx) == 1
    assert errors

    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        ob, "run_setup", lambda root, **kw: seen.update(root=root, **kw) or 0
    )
    args = SimpleNamespace(
        setup=True,
        setup_agents="cursor",
        setup_yes=True,
        setup_no_index=True,
        project_root=str(proj),
    )
    assert _handle_setup(args, ctx) == 0
    assert seen["agents"] == ("cursor",) and seen["assume_yes"] and seen["skip_index"]


def test_cli_alias_and_flags():
    from tree_sitter_analyzer.cli_main import (
        _normalize_agent_command_aliases,
        create_argument_parser,
    )

    argv = _normalize_agent_command_aliases(["setup", "--setup-yes"])
    assert argv[0] == "--setup"
    ns = create_argument_parser().parse_args(argv)
    assert ns.setup and ns.setup_yes and not ns.setup_no_index
