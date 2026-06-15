#!/usr/bin/env python3
"""Generate ``docs/api/facade-actions.md`` — per-facade action parameter reference.

Issue #519: agents calling ``nav action=test_map`` etc. had no document
specifying, per facade action, the accepted params / required ones / response
surface / CLI twin. This script generates that reference from the source of
truth so it can never drift (a CI test regenerates and diffs — see
``tests/unit/docs/test_facade_actions_doc_drift.py``).

Sources of truth
----------------
* **Facade routing** — ``tree_sitter_analyzer.mcp._tool_registry.create_tool_registry``
  builds the 8 live ``FacadeTool`` instances; each carries ``action_map``
  (action -> inner tool) and ``bespoke_map`` (action -> closure).
* **Per-action params** — ``inner.get_tool_definition()["inputSchema"]``: the
  exact schema the runtime strict-param guard enforces
  (``BaseMCPTool._guard_strict_parameters`` -> ``enforce_strict_params``), plus
  the facade's mechanical ``symbol`` aliasing (``FacadeTool._project_args`` R3:
  ``symbol`` -> ``function_name`` / ``class_name``).
* **Response keys** — ``inner.get_output_schema()``: the statically declared
  ToolResponse envelope. Action-specific payload keys are additive
  (``additionalProperties: true``) and are NOT statically declared anywhere,
  so they are honestly summarised as "+ action payload" instead of guessed.
* **CLI twins** — ``facade_map.LEGACY_TOOL_MAP`` + ``facade_map.NEW_ACTION_PARITY``
  crosswalked with the ``tool_to_cli`` parity table asserted by
  ``tests/unit/test_agent_contracts.py::test_registered_mcp_tools_have_cli_parity``
  (extracted via AST from the test source so it cannot be hand-copied stale).
  Actions with no authoritative mapping get an explicit em-dash gap — never a
  hand-written guess.
* **Bespoke routes** — closures own their args, so there is no schema to walk.
  ``BESPOKE_ROUTE_SPECS`` below pins each one with file provenance; generation
  FAILS LOUDLY if the live ``bespoke_map`` and the spec disagree, so adding or
  removing a bespoke action forces a conscious spec update.

Usage::

    uv run python scripts/generate_facade_actions_doc.py
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = PROJECT_ROOT / "docs" / "api" / "facade-actions.md"
CONTRACTS_TEST_PATH = PROJECT_ROOT / "tests" / "unit" / "test_agent_contracts.py"
REGEN_COMMAND = "uv run python scripts/generate_facade_actions_doc.py"
DRIFT_TEST = "tests/unit/docs/test_facade_actions_doc_drift.py"

#: Rendered CLI-twin cell when no authoritative mapping exists.
NO_CLI_TWIN = "—"

# ---------------------------------------------------------------------------
# Bespoke route specs — params pinned with provenance (closures own their args)
# ---------------------------------------------------------------------------
# Two shapes:
#   {"params": "<rendered cell>", "source": "<file>::<closure>"}
#       Hand-pinned param list mirroring the closure's key handling.
#   {"schema_from": ("<module>", "<ClassName>"), "source": ...}
#       The closure forwards args VERBATIM to one inner tool whose strict
#       schema therefore IS the param contract — derived live, zero drift.
# Conditional requirements enforced in runtime validation code, invisible to
# JSON-schema ``required`` (Codex P2 on #602). Keyed (facade, action); the
# note is appended to the params cell. Provenance pinned per entry; a key
# naming a nonexistent action fails generation (loud-fail, same philosophy
# as BESPOKE_ROUTE_SPECS).
CONDITIONAL_PARAM_NOTES: dict[tuple[str, str], str] = {
    # QueryTool._dispatch (query_tool.py): file_path-or-symbol gate;
    # _validate_query_arguments: exactly one of query_key/query_string
    # for file-scoped queries.
    ("search", "query"): (
        "requires `file_path` or `symbol`; file-scoped queries take "
        "exactly one of `query_key`/`query_string`"
    ),
}

BESPOKE_ROUTE_SPECS: dict[tuple[str, str], dict[str, Any]] = {
    ("nav", "context"): {
        "params": (
            "`task`* (or `symbol`/`query` as alias), `max_nodes`, "
            "`max_code_blocks`, `include_graph`, `output_format`"
        ),
        "source": "nav_facade.py::_context_route",
    },
    ("nav", "callers"): {
        "params": (
            "`function_name`* (or `symbol` as alias), `scope` (point|graph, "
            "default point), `file_path`, `limit` (scope=point), "
            "`depth` (scope=graph), `output_format`"
        ),
        "source": "nav_facade.py::_callers_route",
    },
    ("nav", "callees"): {
        "params": (
            "`function_name`* (or `symbol` as alias), `scope` (point|graph, "
            "default point), `file_path`, `limit` (scope=point), "
            "`depth` (scope=graph), `output_format`"
        ),
        "source": "nav_facade.py::_callees_route",
    },
    ("nav", "test_map"): {
        "params": "`symbol`* (or `function_name` as alias), `file_path`, `output_format`",
        "source": "nav_facade.py::_test_map_route",
    },
    ("nav", "co_change"): {
        "params": (
            "`symbol` or `file_path` (one required), `max_commits` (default 500), "
            "`min_shared` (default 3), `max_results` (default 20), `output_format`"
        ),
        "source": "nav_facade.py::_co_change_route",
    },
    ("search", "content"): {
        # _content_route forwards args verbatim to SearchContentTool.execute,
        # so the inner's strict schema is the authoritative param contract.
        "schema_from": (
            "tree_sitter_analyzer.mcp.tools.search_content_tool",
            "SearchContentTool",
        ),
        "source": "search_facade.py::_content_route",
    },
    ("structure", "read"): {
        "params": (
            "single: `file_path`* + `start_line`* [+ `end_line`, `start_column`, "
            "`end_column`, `format`, `output_file`, `suppress_output`, "
            "`output_format`, `allow_truncate`, `fail_fast`]; "
            "batch: `requests`*"
        ),
        "source": "structure_facade.py::_read_route",
    },
    ("structure", "signatures"): {
        "params": "`file_path`*, `language`, `output_format`",
        "source": "structure_facade.py::_signatures_route",
    },
    ("structure", "class_detail"): {
        "params": (
            "`class_name`* (or `query`/`symbol` as alias), `language`, `output_format`"
        ),
        "source": "structure_facade.py::_class_detail_route",
    },
}


@dataclass(frozen=True)
class ActionRow:
    """One rendered table row: a routable (facade, action) pair."""

    action: str
    params: str
    response_keys: str
    cli_twin: str


# ---------------------------------------------------------------------------
# CLI twin crosswalk
# ---------------------------------------------------------------------------


def _load_tool_to_cli() -> dict[str, tuple[str, str]]:
    """Extract the ``tool_to_cli`` parity table from the agent-contracts test.

    The table is the project's authoritative legacy-capability -> CLI mapping
    (asserted against the real argparse parser by
    ``test_registered_mcp_tools_have_cli_parity``). It is a literal dict, so
    AST extraction keeps this generator in lock-step with the test source.
    """
    tree = ast.parse(CONTRACTS_TEST_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "tool_to_cli"
        ):
            value = ast.literal_eval(node.value)
            if not isinstance(value, dict) or not value:
                break
            return value
    raise SystemExit(
        f"could not extract the 'tool_to_cli' literal from {CONTRACTS_TEST_PATH} — "
        "the CLI-parity source of truth moved; update _load_tool_to_cli()."
    )


def _render_cli_entry(kind: str, name: str) -> str:
    """Render one CLI parity entry (main flag vs console script)."""
    if kind == "script":
        return f"`{name}` (console script)"
    return f"`{name}`"


def _cli_twin_map() -> dict[tuple[str, str], str]:
    """Build ``{(facade, action): rendered CLI twin cell}`` from the crosswalk."""
    from tree_sitter_analyzer.mcp.facade_map import (
        LEGACY_TOOL_MAP,
        NEW_ACTION_PARITY,
    )

    tool_to_cli = _load_tool_to_cli()
    twins: dict[tuple[str, str], list[str]] = {}
    for legacy_name, (facade, action) in LEGACY_TOOL_MAP.items():
        if legacy_name not in tool_to_cli:
            continue
        kind, cli_name = tool_to_cli[legacy_name]
        rendered = _render_cli_entry(kind, cli_name)
        cell = twins.setdefault((facade, action), [])
        if rendered not in cell:
            cell.append(rendered)
    for _key, (facade, action, cli_flag) in NEW_ACTION_PARITY.items():
        rendered = _render_cli_entry("main", cli_flag)
        cell = twins.setdefault((facade, action), [])
        if rendered not in cell:
            cell.append(rendered)
    return {key: ", ".join(sorted(entries)) for key, entries in twins.items()}


# ---------------------------------------------------------------------------
# Schema -> cell rendering
# ---------------------------------------------------------------------------


def _input_schema_of(tool: Any) -> dict[str, Any]:
    definition = tool.get_tool_definition()
    schema = definition.get("inputSchema") if isinstance(definition, dict) else None
    return schema if isinstance(schema, dict) else {}


def _params_cell_from_schema(schema: dict[str, Any]) -> str:
    """Render the params cell: required first (marked ``*``), then optional.

    Mirrors the facade's mechanical R3 aliasing (``FacadeTool._project_args``):
    when the inner declares ``function_name`` / ``class_name`` but not
    ``symbol``, the facade copies ``symbol`` into it — surfaced as an alias
    note so agents can use the canonical ``symbol`` everywhere.
    """
    props = schema.get("properties")
    props = props if isinstance(props, dict) else {}
    required = schema.get("required")
    required_set = set(required) if isinstance(required, list) else set()

    if not props:
        return "(none)"

    parts: list[str] = []
    for name in sorted(props, key=lambda p: (p not in required_set, p)):
        rendered = f"`{name}`*" if name in required_set else f"`{name}`"
        if name in ("function_name", "class_name") and "symbol" not in props:
            rendered += f" (`symbol` aliases `{name}`)"
        parts.append(rendered)
    return ", ".join(parts)


def _response_cell(tool: Any) -> str:
    """Render the statically-declared response surface (ToolResponse envelope).

    ``get_output_schema()`` is the only static declaration of response shape;
    payload keys are additive (``additionalProperties: true``) and live only in
    each action's runtime output, so they are summarised, not guessed.
    """
    schema = tool.get_output_schema()
    props = schema.get("properties")
    props = props if isinstance(props, dict) else {}
    required = schema.get("required")
    required_set = set(required) if isinstance(required, list) else set()

    parts = [
        f"`{name}`*" if name in required_set else f"`{name}`"
        for name in sorted(props, key=lambda p: (p not in required_set, p))
    ]
    cell = ", ".join(parts) if parts else "(undeclared)"
    if schema.get("additionalProperties", False):
        cell += " + action payload"
    return cell


def _bespoke_params_cell(facade_name: str, action: str, spec: dict[str, Any]) -> str:
    """Render a bespoke route's params cell from its pinned spec."""
    if "schema_from" in spec:
        module_name, class_name = spec["schema_from"]
        import importlib

        tool_cls = getattr(importlib.import_module(module_name), class_name)
        return _params_cell_from_schema(_input_schema_of(tool_cls(str(PROJECT_ROOT))))
    params = spec.get("params")
    if not isinstance(params, str) or not params:
        raise SystemExit(
            f"BESPOKE_ROUTE_SPECS[({facade_name!r}, {action!r})] has neither "
            "'params' nor 'schema_from' — fix the spec."
        )
    return params


# ---------------------------------------------------------------------------
# Row collection + markdown emission
# ---------------------------------------------------------------------------


def collect_rows() -> dict[str, list[ActionRow]]:
    """Walk the live facade registry into ``{facade: [ActionRow, ...]}``."""
    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

    facades, _lookup = create_tool_registry(str(PROJECT_ROOT))
    cli_twins = _cli_twin_map()

    live_bespoke = {
        (facade_name, action)
        for facade_name, facade in facades
        for action in facade.bespoke_map
    }
    if live_bespoke != set(BESPOKE_ROUTE_SPECS):
        raise SystemExit(
            "bespoke route drift: live bespoke_map actions != BESPOKE_ROUTE_SPECS.\n"
            f"  live only: {sorted(live_bespoke - set(BESPOKE_ROUTE_SPECS))}\n"
            f"  spec only: {sorted(set(BESPOKE_ROUTE_SPECS) - live_bespoke)}\n"
            "Update BESPOKE_ROUTE_SPECS in scripts/generate_facade_actions_doc.py "
            "(params come from the closure's key handling — cite the source)."
        )

    rows_by_facade: dict[str, list[ActionRow]] = {}
    for facade_name, facade in facades:
        rows: list[ActionRow] = []
        for action in facade._available_actions():
            if action in facade.bespoke_map:
                params = _bespoke_params_cell(
                    facade_name, action, BESPOKE_ROUTE_SPECS[(facade_name, action)]
                )
                response = _response_cell(facade)
            else:
                inner = facade.action_map[action]
                params = _params_cell_from_schema(_input_schema_of(inner))
                response = _response_cell(inner)
            note = CONDITIONAL_PARAM_NOTES.get((facade_name, action))
            if note:
                params = f"{params} — {note}"
            cli_twin = cli_twins.get((facade_name, action), NO_CLI_TWIN)
            rows.append(
                ActionRow(
                    action=action,
                    params=params,
                    response_keys=response,
                    cli_twin=cli_twin,
                )
            )
        rows_by_facade[facade_name] = rows
    all_actions = {
        (fname, row.action) for fname, frows in rows_by_facade.items() for row in frows
    }
    stale_notes = set(CONDITIONAL_PARAM_NOTES) - all_actions
    if stale_notes:
        raise SystemExit(
            f"CONDITIONAL_PARAM_NOTES names nonexistent actions: {sorted(stale_notes)}"
        )
    return rows_by_facade


def _escape_cell(text: str) -> str:
    """Escape pipes so cells never break the markdown table."""
    return text.replace("|", "\\|")


def generate_markdown() -> str:
    """Render the full reference document as a string (deterministic)."""
    rows_by_facade = collect_rows()
    total_actions = sum(len(rows) for rows in rows_by_facade.values())
    gap_count = sum(
        1
        for rows in rows_by_facade.values()
        for row in rows
        if row.cli_twin == NO_CLI_TWIN
    )

    lines: list[str] = [
        "# MCP Facade Action Reference",
        "",
        f"> **AUTO-GENERATED — do not edit by hand.** Regenerate with `{REGEN_COMMAND}`.",
        f"> Drift-gated by `{DRIFT_TEST}` (regenerates in-memory and diffs).",
        "",
        f"The MCP server exposes **{len(rows_by_facade)} facade tools** routing "
        f"**{total_actions} actions** via the `action` parameter. This reference is "
        "generated from the live facade registry "
        "(`tree_sitter_analyzer/mcp/_tool_registry.py`) and each inner tool's "
        "`inputSchema` — the same schema the runtime strict-parameter guard "
        "enforces, so a wrong param guess in this table would fail at runtime "
        "too (and vice versa).",
        "",
        "Reading the tables:",
        "",
        "- **Params** — accepted top-level parameters; `*` marks required ones. "
        "Facades mechanically alias the canonical `symbol` onto inner "
        "`function_name`/`class_name` params (noted inline). Every facade also "
        "accepts `action` (required) itself.",
        "- **Response keys** — the statically declared `ToolResponse` envelope "
        "(`get_output_schema()`); `*` marks guaranteed keys. `error` appears on "
        'failures. "+ action payload" means the action layers its own '
        "result keys on top (`additionalProperties: true`); payload shapes are "
        "not statically declared, so they are not listed here — see the facade "
        "description for per-action semantics.",
        "- **CLI twin** — the CLI flag (or console script) covering the same "
        f"capability, from the CLI-parity contract. {gap_count} actions have no "
        f"authoritative CLI mapping and show {NO_CLI_TWIN} (honest gap, not an "
        "omission).",
        "- *Bespoke routes* (closures with hand-rolled arg handling, e.g. "
        "`nav action=test_map`) have their params pinned in the generator with "
        "source provenance; the generator fails if the live route set drifts "
        "from those pins.",
        "",
    ]

    for facade_name, rows in rows_by_facade.items():
        lines.append(f"## `{facade_name}` — {len(rows)} actions")
        lines.append("")
        lines.append(
            "| Action | Params (required `*`) | Response keys (top-level) | CLI twin |"
        )
        lines.append("| --- | --- | --- | --- |")
        for row in rows:
            lines.append(
                f"| `{row.action}` "
                f"| {_escape_cell(row.params)} "
                f"| {_escape_cell(row.response_keys)} "
                f"| {_escape_cell(row.cli_twin)} |"
            )
        lines.append("")

    markdown = "\n".join(lines)
    if str(PROJECT_ROOT) in markdown:
        raise SystemExit(
            "generated markdown leaks the local project root path — the doc "
            "would not be reproducible on CI; fix the offending schema/cell."
        )
    return markdown


def main() -> int:
    markdown = generate_markdown()
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8", newline="\n")
    print(f"wrote {DOC_PATH.relative_to(PROJECT_ROOT)} ({len(markdown)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
