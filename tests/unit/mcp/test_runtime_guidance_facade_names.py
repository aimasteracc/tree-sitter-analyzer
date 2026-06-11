"""Anti-regression ratchet: runtime guidance must speak 8-facade names only.

Fix for GitHub issue #440 — every tool_routing entry, next_step builder,
suggested_tool hint, and smart_workflow_hint must reference one of the 8 live
facade names (search/nav/structure/health/edit/project/index/viz) or the
``facade action=x`` call form.  Legacy pre-facade names (codegraph_*, safe_to_edit,
list_files, query_code, get_project_overview, check_project_health, ...) must
NOT appear in any guidance string shown to agents.

Coverage limits (documented):
  - Statically-reachable strings in _build_tool_routing, _health_opt_in_hint,
    _build_smart_hint, smart_prompts, error_recovery hints — covered here.
  - Runtime-built strings that embed dynamic content (file_path interpolation
    in recommended_mcp_command, safety_mcp_command) — covered by targeted
    execute-level tests below.
  - next_step strings from deep inner tools that are not directly tested here
    are covered by targeted tests per guidance surface.
"""

from __future__ import annotations

import inspect
import re

from tree_sitter_analyzer.mcp.facade_map import LEGACY_TOOL_MAP
from tree_sitter_analyzer.mcp.server_utils import error_recovery as _er
from tree_sitter_analyzer.mcp.server_utils import smart_prompts as _sp
from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
    _build_tool_routing,
    _health_opt_in_hint,
)
from tree_sitter_analyzer.mcp.tools.symbol_search_tool import CodeGraphSymbolSearchTool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Pattern that matches a bare legacy tool name used as a call in a string.
# e.g. "list_files(roots=[...])", "safe_to_edit(file_path='...')",
# "codegraph_explore(query=...)".  We match <name>( or just <name> as a
# word-boundary match, but only the exact legacy names.
_LEGACY_NAMES_SET: frozenset[str] = frozenset(LEGACY_TOOL_MAP.keys())

# A few non-LEGACY_TOOL_MAP names that still appear in old guidance strings.
# set_project_path is a live infra tool (not a facade) so it's allowed.
_EXTRA_FORBIDDEN: frozenset[str] = frozenset(
    {
        # These were never registered as legacy shims but appear in old texts:
        "get_agent_workflow",  # → project action=workflow
        "check_file_health",  # → health action=file
        "check_project_health",  # → health action=project
    }
)
_FORBIDDEN: frozenset[str] = (_LEGACY_NAMES_SET | _EXTRA_FORBIDDEN) - {
    # set_project_path is standalone infra; its name is fine to mention
    "set_project_path",
}

_CALL_RE = re.compile(r"\b([a-z][a-z0-9_]+)\s*\(")


def _forbidden_calls_in(text: str) -> list[str]:
    """Return list of forbidden legacy tool names found as call sites in text."""
    found = []
    for match in _CALL_RE.finditer(text):
        name = match.group(1)
        if name in _FORBIDDEN:
            found.append(name)
    return found


def _forbidden_words_in(
    text: str, *, extras: frozenset[str] = frozenset()
) -> list[str]:
    """Return list of forbidden legacy tool names found as bare words in text."""
    all_forbidden = _FORBIDDEN | extras
    found = []
    for name in all_forbidden:
        # word-boundary match so "list_files" doesn't match "list_files_helpers"
        if re.search(rf"\b{re.escape(name)}\b", text):
            found.append(name)
    return list(set(found))


# ---------------------------------------------------------------------------
# 1. Static tool_routing block (project_overview_tool._build_tool_routing)
# ---------------------------------------------------------------------------


class TestToolRoutingFacadeNames:
    def test_tool_routing_no_legacy_names(self) -> None:
        """Every value in _build_tool_routing() must use facade form only."""
        routing = _build_tool_routing()
        violations: list[str] = []
        for key, snippet in routing.items():
            bad = _forbidden_calls_in(snippet)
            if bad:
                violations.append(f"key={key!r} snippet={snippet!r} bad={bad}")
        assert violations == [], (
            "_build_tool_routing() contains legacy tool names:\n"
            + "\n".join(violations)
        )

    def test_tool_routing_values_use_facade_action_form(self) -> None:
        """At least the high-traffic routing keys must use facade action= form."""
        routing = _build_tool_routing()
        # Spot-check: these keys must reference the actual facade call form.
        action_form_re = re.compile(
            r"\b(search|nav|structure|health|edit|project|index|viz)\s+"
            r"action=\w+"
        )
        # Or the "facade(action=...)" positional call form used by some snippets.
        call_action_re = re.compile(
            r"\b(search|nav|structure|health|edit|project|index|viz)\("
        )
        high_traffic = [
            "project_health",
            "edit_risk",
            "find_symbol",
            "find_files",
            "call_graph",
            "agent_workflow",
        ]
        for key in high_traffic:
            if key not in routing:
                continue
            snippet = routing[key]
            # Accept either "facade action=x ..." or "facade(action=x, ...)" style
            ok = (
                action_form_re.search(snippet) is not None
                or call_action_re.search(snippet) is not None
            )
            assert ok, (
                f"tool_routing key={key!r} snippet={snippet!r} does not use "
                "facade action= form"
            )


# ---------------------------------------------------------------------------
# 2. smart_workflow_hint (_health_opt_in_hint + _build_smart_hint)
# ---------------------------------------------------------------------------


class TestSmartWorkflowHint:
    def test_health_opt_in_hint_no_legacy_names(self) -> None:
        """_health_opt_in_hint() must not teach get_project_overview."""
        hint = _health_opt_in_hint()
        bad = _forbidden_words_in(hint)
        assert bad == [], (
            f"_health_opt_in_hint() contains legacy names {bad!r}: {hint!r}"
        )

    def test_health_opt_in_hint_uses_facade_form(self) -> None:
        """_health_opt_in_hint() must reference the facade call form."""
        hint = _health_opt_in_hint()
        # Must reference the project facade
        assert "project" in hint, f"Expected 'project' facade reference: {hint!r}"

    def test_smart_prompts_no_legacy_names(self) -> None:
        """smart_prompts.py instruction templates must not teach legacy names."""
        for template_name, template in (
            ("ANALYZE", _sp._ANALYZE_INSTRUCTIONS_TEMPLATE),
            ("EXPLORE", _sp._EXPLORE_INSTRUCTIONS_TEMPLATE),
        ):
            bad = _forbidden_words_in(template)
            assert bad == [], (
                f"smart_prompts.{template_name} contains legacy names {bad!r}:\n"
                f"{template}"
            )

    def test_smart_prompts_response_builders_produce_clean_text(self) -> None:
        """build_smart_analyze_response / build_smart_explore_response facade names."""
        analyze = _sp.build_smart_analyze_response("app.py", "What does it do?")
        assert "description" in analyze
        text = analyze["messages"][0]["content"]["text"]
        bad = _forbidden_words_in(text)
        assert bad == [], (
            f"build_smart_analyze_response text contains legacy names {bad!r}"
        )
        # Must reference a facade action
        assert "action=" in text, f"Expected facade action= in analyze text: {text!r}"

        explore = _sp.build_smart_explore_response("/tmp/project")
        assert "description" in explore
        text2 = explore["messages"][0]["content"]["text"]
        bad2 = _forbidden_words_in(text2)
        assert bad2 == [], (
            f"build_smart_explore_response text contains legacy names {bad2!r}"
        )
        assert "action=" in text2, f"Expected facade action= in explore text: {text2!r}"


# ---------------------------------------------------------------------------
# 3. error_recovery suggested_tool hints
# ---------------------------------------------------------------------------


class TestErrorRecoverySuggestedTool:
    def test_file_not_found_suggested_tool_is_facade(self) -> None:
        """file_not_found recovery hint must suggest a facade name, not list_files."""
        from tree_sitter_analyzer.mcp.server_utils.error_recovery import (
            build_agent_friendly_error,
        )

        err = FileNotFoundError("file not found at /tmp/missing.py")
        result = build_agent_friendly_error("analyze_file", err)
        # Must have a suggested_tool
        assert "suggested_tool" in result
        tool = result["suggested_tool"]
        # Must be a facade name or facade action= form (not a raw legacy name)
        assert tool not in _FORBIDDEN, (
            f"suggested_tool={tool!r} is a legacy name; must be facade form"
        )

    def test_no_such_file_suggested_tool_is_facade(self) -> None:
        """'no such file' recovery hint must suggest a facade name."""
        from tree_sitter_analyzer.mcp.server_utils.error_recovery import (
            build_agent_friendly_error,
        )

        err = FileNotFoundError("no such file or directory: /tmp/missing.py")
        result = build_agent_friendly_error("analyze_file", err)
        assert "suggested_tool" in result
        tool = result["suggested_tool"]
        assert tool not in _FORBIDDEN, (
            f"suggested_tool={tool!r} is a legacy name; must be facade form"
        )

    def test_error_recovery_hint_texts_no_legacy_names(self) -> None:
        """All recovery hint text strings in _ERROR_RECOVERY_HINTS must be clean."""
        violations: list[str] = []
        for row in _er._ERROR_RECOVERY_HINTS:
            # row = (substring, error_type, recovery_hint, suggested_tool)
            _pattern, _et, hint, tool = row
            bad_hint = _forbidden_words_in(hint)
            if bad_hint:
                violations.append(f"hint={hint!r} bad={bad_hint}")
            if tool and tool in _FORBIDDEN:
                violations.append(f"suggested_tool={tool!r} is a legacy name")
        assert violations == [], (
            "_ERROR_RECOVERY_HINTS contains legacy names:\n" + "\n".join(violations)
        )


# ---------------------------------------------------------------------------
# 4. search symbol next_step — targets the specific codegraph_explore mention
# ---------------------------------------------------------------------------


class TestSearchSymbolNextStep:
    def test_symbol_search_next_step_no_legacy(self, tmp_path) -> None:
        """search action=symbol next_step must not say 'codegraph_explore'."""
        import asyncio

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text(
            "def my_function():\n    pass\n", encoding="utf-8"
        )

        tool = CodeGraphSymbolSearchTool(project_root=str(tmp_path))
        result = asyncio.run(
            tool.execute({"query": "my_function", "output_format": "json"})
        )
        # next_step may or may not be present (depends on whether results found)
        next_step = result.get("next_step", "")
        bad = _forbidden_words_in(next_step)
        assert bad == [], (
            f"symbol search next_step contains legacy names {bad!r}: {next_step!r}"
        )
        if next_step:
            # When present it must reference the facade form
            assert "structure" in next_step or "action=" in next_step, (
                f"symbol search next_step does not use facade form: {next_step!r}"
            )

    def test_symbol_search_next_step_exact_facade_form(self) -> None:
        """The next_step builder must produce the facade call form string."""
        # Inspect the source of execute() to confirm the legacy name is gone.
        # The next_step is constructed inline at the call site (not a constant),
        # so we verify via source inspection that the legacy name is absent.
        source = inspect.getsource(CodeGraphSymbolSearchTool.execute)
        # Must NOT contain the legacy name
        assert "codegraph_explore" not in source, (
            "CodeGraphSymbolSearchTool.execute still references legacy 'codegraph_explore'"
        )
        # Must reference the facade form
        assert "structure" in source, (
            "CodeGraphSymbolSearchTool.execute does not reference the 'structure' facade"
        )


# ---------------------------------------------------------------------------
# 5. project_health_tool — recommended_mcp_command and safety_mcp_command
# ---------------------------------------------------------------------------


class TestProjectHealthToolGuidance:
    def test_recommended_mcp_command_facade_form(self) -> None:
        """_file_action() must return facade form commands."""
        from tree_sitter_analyzer.mcp.tools.project_health_tool import _file_action

        class _Score:
            def __init__(self, grade, file_path, dims=None):
                self.grade = grade
                self.file_path = file_path
                self.dimensions = dims or {}

        for grade in ("D", "F"):
            cmd = _file_action(_Score(grade, "src/big.py"))
            bad = _forbidden_calls_in(cmd)
            assert bad == [], (
                f"_file_action grade={grade!r} cmd={cmd!r} has legacy names {bad!r}"
            )
            assert cmd != "", f"_file_action must return non-empty for grade {grade!r}"

        for grade in ("C",):
            cmd = _file_action(_Score(grade, "src/ok.py", {"complexity": 30.0}))
            bad = _forbidden_calls_in(cmd)
            assert bad == [], (
                f"_file_action grade={grade!r} cmd={cmd!r} has legacy names {bad!r}"
            )

    def test_safety_mcp_command_facade_form(self) -> None:
        """_build_agent_backlog_item() safety_mcp_command must use facade form."""
        from tree_sitter_analyzer.mcp.tools.project_health_tool import (
            _build_agent_backlog,
        )

        class _Score:
            def __init__(self, grade, file_path, total=50.0, dims=None):
                self.grade = grade
                self.file_path = file_path
                self.total = total
                self.dimensions = dims or {}

        backlog = _build_agent_backlog([_Score("F", "src/bad.py")], limit=1)
        assert len(backlog) == 1
        safety_cmd = backlog[0]["safety_mcp_command"]
        bad = _forbidden_calls_in(safety_cmd)
        assert bad == [], f"safety_mcp_command={safety_cmd!r} has legacy names {bad!r}"
        recommended_cmd = backlog[0]["recommended_mcp_command"]
        bad2 = _forbidden_calls_in(recommended_cmd)
        assert bad2 == [], (
            f"recommended_mcp_command={recommended_cmd!r} has legacy names {bad2!r}"
        )
