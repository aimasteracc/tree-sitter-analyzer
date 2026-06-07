#!/usr/bin/env python3
"""FacadeTool — the P0 geode-layer dispatcher for the 62 -> 6 consolidation.

A ``FacadeTool`` is a single MCP tool that fans an ``action`` parameter out
to one of many *inner* tools, without changing the inner tools' logic,
output, or verdict envelope. It is the foundation every Wave-B facade
(``nav`` / ``structure`` / ``search`` / ``health`` / ``edit`` / ``project``)
builds on.

Design constraints distilled from the engineering review
(``.recon/review-engineering.md``) and PRD §0 Errata:

F4 (Landmine A) — strict-param projection
    ``BaseMCPTool.__init_subclass__`` wraps every tool's ``execute`` with
    ``enforce_strict_params`` (``additionalProperties: False`` by default).
    An inner tool therefore raises ``ValueError: unknown parameter 'action'``
    if the facade forwards the merged dict verbatim. The facade MUST project
    the caller's args down to each inner tool's own ``inputSchema.properties``
    whitelist before delegating: strip facade control keys (``action`` /
    ``scope`` / ``mode`` when the inner doesn't declare them) AND drop
    sibling-action params.

F5 — bespoke routing
    Three production routes bypass ``registry[name].execute()``:
    ``analyze_code_structure`` -> ``table_format_tool``,
    ``extract_code_section`` -> ``handle_extract_code_section`` (batch
    reshaping), and ``search_content`` / ``find_and_grep`` whose
    ``execute`` returns ``dict | int`` (bare int = exit code when
    ``suppress_output=True``). These register as ``bespoke_map`` callables;
    the facade forwards the cleaned args (control keys stripped) but does
    NOT project them to an inner schema — the bespoke callable owns its own
    arg handling — and tolerates a non-dict return.

R3 — symbol / function_name normalize
    Some inner tools read ``function_name`` (callers/callees), others read
    ``symbol`` (navigate/resolve). The facade copies ``symbol`` ->
    ``function_name`` (when the target inner declares ``function_name`` and
    the caller didn't set it) BEFORE projection, else the canonical
    ``symbol`` would be stripped before it could be copied.

G3 — rebind propagation
    ``server.set_project_path`` loops ``_tools.values()`` calling
    ``set_project_path`` on each. The facade does NOT override
    ``set_project_path`` (forbidden by
    ``test_no_mcp_tool_overrides_set_project_path``); instead it forwards the
    new root to every held inner instance via the allowed
    ``_on_project_root_changed`` hook.

The facade never re-wraps the inner's response: ``verdict`` / ``agent_summary``
/ ``toon_content`` stay verbatim so the centralised envelope in
``base_tool.py`` and the MCP dispatch normaliser remain the single source of
truth.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from .base_tool import BaseMCPTool

# A bespoke route may return ``dict`` (normal envelope) or ``int`` (exit code
# when suppress_output=True, mirroring search_content / find_and_grep).
BespokeHandler = Callable[[dict[str, Any]], Awaitable[Any]]

# Facade control keys that are never forwarded to an inner tool unless the
# inner explicitly declares them in its own schema. ``action`` selects the
# route; ``scope`` / ``mode`` are facade-level discriminators (PRD R2/R4/R5)
# whose meaning is action-scoped and whose legal set the inner validates.
_FACADE_CONTROL_KEYS: frozenset[str] = frozenset({"action"})

# Core high-frequency parameters surfaced explicitly on EVERY facade's public
# inputSchema. Wave D (tool-def token diet): the facade no longer unions every
# inner param verbatim into its public schema — that re-imported ~50 ripgrep
# flags into ``search`` alone and blew the tool-def token budget. Instead the
# public schema declares only these shared, cross-action params plus
# ``additionalProperties: True``; any inner-specific param (e.g. an rg flag) is
# accepted via additionalProperties and projected internally by ``_project_args``
# against the inner's REAL schema whitelist (so F4 strict-param projection is
# unaffected — it reads ``inner.get_tool_definition()``, never this public
# schema). Per-action param discovery is carried in the facade ``description``
# (description-as-discovery, à la Rhizome), not in the schema body.
#
# Descriptions are deliberately terse: per-action semantics live in the facade
# ``description`` text (description-as-discovery), so repeating a long blurb on
# every core param across all 8 facades is pure token waste. One short clause
# each keeps the schema body small while still typing the common surface.
_CORE_FACADE_PARAMS: dict[str, dict[str, Any]] = {
    "scope": {
        "type": "string",
        "description": "Action discriminator (e.g. point|graph).",
    },
    "mode": {"type": "string", "description": "Action sub-mode (e.g. summary|cycles)."},
    "file_path": {"type": "string", "description": "Target file path."},
    "symbol": {"type": "string", "description": "Symbol/function name."},
    "function_name": {
        "type": "string",
        "description": "Function name (alias of symbol).",
    },
    "query": {"type": "string", "description": "Search query/pattern."},
    "language": {"type": "string", "description": "Language hint (usually auto)."},
    "limit": {"type": "integer", "description": "Max results."},
    "output_format": {"type": "string", "description": "Output format (toon|json)."},
}


class FacadeTool(BaseMCPTool):
    """One MCP tool fanning ``action`` out to many inner tools.

    Parameters
    ----------
    facade_name:
        Public MCP tool name (e.g. ``"search"``).
    action_map:
        ``{action_name: inner_tool_instance}``. Each inner is a live
        ``BaseMCPTool`` whose ``execute`` is routed to after arg projection.
    bespoke_map:
        Optional ``{action_name: async callable}`` for F5 routes that bypass
        the registry. The callable receives the cleaned args (control keys
        stripped, R3-normalized) and owns its own arg handling. Its return
        may be a ``dict`` or a bare ``int``; the facade forwards it as-is.
    description:
        Optional facade description used in ``get_tool_definition``.
    annotations:
        Optional MCP annotations dict. A facade spanning read + mutating
        actions cannot honestly declare a single ``readOnlyHint``; callers
        pass the honest (usually non-read-only) set or omit it.
    """

    def __init__(
        self,
        facade_name: str,
        action_map: dict[str, BaseMCPTool],
        bespoke_map: dict[str, BespokeHandler] | None = None,
        *,
        description: str = "",
        annotations: dict[str, Any] | None = None,
        project_root: str | None = None,
    ) -> None:
        self.facade_name = facade_name
        self.action_map: dict[str, BaseMCPTool] = dict(action_map)
        self.bespoke_map: dict[str, BespokeHandler] = dict(bespoke_map or {})
        # Inner instances reachable only through a bespoke closure (F5). They
        # are not in ``action_map`` but still need G3 rebind propagation, so
        # callers register them via ``register_bespoke_inner``.
        self._bespoke_inners: list[BaseMCPTool] = []
        self._description = description
        self._annotations = annotations
        # BaseMCPTool.__init__ wires security/path resolver + fires
        # _on_project_root_changed (which forwards to inner instances).
        super().__init__(project_root)

    # -- rebind propagation (G3) -------------------------------------------

    def register_bespoke_inner(self, inner: BaseMCPTool) -> None:
        """Register an inner instance reachable only via a bespoke closure (F5).

        Such an instance is not in ``action_map`` but still needs to be
        rebound when the project root changes. We rebind it immediately to the
        facade's current root so it is consistent from the moment of
        registration, then keep it for future rebinds.
        """
        self._bespoke_inners.append(inner)
        root = self.project_root
        if root is None:
            return
        try:
            inner.set_project_path(root)
        except Exception:  # noqa: BLE001
            pass

    def _on_project_root_changed(self, project_root: str | None) -> None:
        """Forward the new project root to every held inner instance.

        Called from both ``__init__`` and ``set_project_path`` (via
        ``_apply_project_root``) in BaseMCPTool. We never override
        ``set_project_path`` itself — that is forbidden by
        ``test_no_mcp_tool_overrides_set_project_path``.
        """
        # ``action_map`` / ``_bespoke_inners`` are assigned before
        # super().__init__() in our __init__, so they are present by the time
        # the init-time hook fires — but guard anyway for subclasses that init
        # differently.
        if project_root is None:
            return
        inners = list(getattr(self, "action_map", {}).values())
        inners.extend(getattr(self, "_bespoke_inners", []))
        for inner in inners:
            try:
                inner.set_project_path(project_root)
            except Exception:  # noqa: BLE001 — one bad inner must not abort rebind
                pass

    # -- arg projection (F4) + normalize (R3) ------------------------------

    @staticmethod
    def _inner_property_names(inner: BaseMCPTool) -> set[str]:
        """Return the inner tool's declared top-level schema property names."""
        try:
            definition = inner.get_tool_definition()
        except Exception:  # noqa: BLE001
            return set()
        schema = definition.get("inputSchema") if isinstance(definition, dict) else None
        if not isinstance(schema, dict):
            return set()
        props = schema.get("properties")
        if not isinstance(props, dict):
            return set()
        return set(props.keys())

    def _project_args(self, inner: BaseMCPTool, args: dict[str, Any]) -> dict[str, Any]:
        """Project caller args onto the inner tool's schema whitelist.

        Steps:
        1. Strip facade control keys (``action``).
        2. R3 normalize: copy ``symbol`` -> ``function_name`` when the inner
           declares ``function_name`` and the caller didn't set it. Done
           BEFORE the whitelist filter so ``symbol`` isn't dropped first.
        3. Filter to the inner's declared properties (drops sibling-action
           params + control keys the inner doesn't accept) — required because
           the inner's strict-param guard rejects unknown keys.
        """
        cleaned = {k: v for k, v in args.items() if k not in _FACADE_CONTROL_KEYS}
        inner_props = self._inner_property_names(inner)

        # R3 normalize — before the whitelist filter.
        if (
            "function_name" in inner_props
            and not cleaned.get("function_name")
            and cleaned.get("symbol")
        ):
            cleaned["function_name"] = cleaned["symbol"]

        if not inner_props:
            # Inner declared no properties — cannot whitelist; forward as-is
            # minus control keys (the inner's own guard skips empty schemas).
            return cleaned
        return {k: v for k, v in cleaned.items() if k in inner_props}

    @staticmethod
    def _clean_bespoke_args(args: dict[str, Any]) -> dict[str, Any]:
        """Strip facade control keys for a bespoke route (no schema projection).

        Bespoke handlers (F5) own their own arg validation, so we only remove
        the facade's own control keys and apply R3 normalize defensively.
        """
        cleaned = {k: v for k, v in args.items() if k not in _FACADE_CONTROL_KEYS}
        if not cleaned.get("function_name") and cleaned.get("symbol"):
            # Defensive R3 copy; harmless for bespoke handlers that ignore it.
            cleaned["function_name"] = cleaned["symbol"]
        return cleaned

    # -- error envelope ----------------------------------------------------

    def _available_actions(self) -> list[str]:
        return sorted(set(self.action_map) | set(self.bespoke_map))

    def _action_error(self, message: str) -> dict[str, Any]:
        """Return a canonical error envelope listing available actions."""
        available = self._available_actions()
        summary_line = f"{self.facade_name}: {message}"
        next_step = (
            f"Set action to one of: {', '.join(available)}."
            if available
            else "No actions are registered on this facade."
        )
        return {
            "success": False,
            "verdict": "ERROR",
            "error_type": "validation",
            "error": message,
            "facade": self.facade_name,
            "available_actions": available,
            "summary_line": summary_line,
            "agent_summary": {
                "verdict": "ERROR",
                "summary_line": summary_line,
                "next_step": next_step,
            },
        }

    # -- dispatch ----------------------------------------------------------

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Route ``arguments['action']`` to the matching inner / bespoke route.

        Returns the inner/bespoke result verbatim (``dict`` or, for F5
        bespoke routes, possibly a bare ``int``). Never re-wraps the verdict
        envelope.
        """
        action = arguments.get("action")
        if not action or not isinstance(action, str):
            return self._action_error("missing required parameter 'action'")

        # Bespoke routes (F5) take precedence and bypass schema projection.
        if action in self.bespoke_map:
            handler = self.bespoke_map[action]
            cleaned = self._clean_bespoke_args(arguments)
            return await handler(cleaned)

        if action in self.action_map:
            inner = self.action_map[action]
            projected = self._project_args(inner, arguments)
            return await inner.execute(projected)

        available = self._available_actions()
        valid = ", ".join(available) if available else "(none registered)"
        return self._action_error(
            f"unknown action {action!r}; valid actions are: {valid}"
        )

    # -- schema / definition ----------------------------------------------

    def get_tool_schema(self) -> dict[str, Any]:
        """Slim public facade schema: ``action`` (required) + core shared params.

        Wave D tool-def token diet. The public schema deliberately does NOT
        union every inner tool's parameters. Unioning re-imported ~50 ripgrep
        flags into the ``search`` facade alone and pushed the 8-facade tool-def
        payload to only -56.6% vs the PRD's ~84% target. Instead:

        * ``action`` (required, enum of every routable action) selects the route.
        * A curated set of high-frequency, cross-action params
          (``_CORE_FACADE_PARAMS``: scope/mode/file_path/symbol/function_name/
          query/language/limit/output_format) is declared explicitly so the
          common surface stays typed and discoverable.
        * ``additionalProperties: True`` accepts any inner-specific param
          (e.g. an rg flag, ``mode``-driven sub-param) without listing it.
        * Per-action parameter discovery lives in the facade ``description``
          (description-as-discovery), not in the schema body.

        F4 is unaffected: ``_project_args`` projects the caller's args against
        ``inner.get_tool_definition()`` (the inner's REAL schema), never against
        this public schema — so slimming the public surface cannot mis-project
        or leak sibling-action params. The inner tools keep their own strict
        schemas; per-action correctness is enforced there.
        """
        properties: dict[str, Any] = {
            "action": {
                "type": "string",
                "enum": self._available_actions(),
                "description": (
                    "Which capability to invoke. One of: "
                    + ", ".join(self._available_actions())
                ),
            },
        }
        # Core shared params — copy specs so callers can't mutate our constants.
        for key, spec in _CORE_FACADE_PARAMS.items():
            properties[key] = dict(spec)

        return {
            "type": "object",
            "properties": properties,
            "required": ["action"],
            # Lenient on purpose: inner-specific params arrive here and are
            # projected internally against the inner's real schema. Inner tools
            # remain strict. Self-rejection here would defeat the facade.
            "additionalProperties": True,
        }

    def get_tool_definition(self) -> dict[str, Any]:
        definition: dict[str, Any] = {
            "name": self.facade_name,
            "description": self._description
            or f"Facade dispatching {len(self._available_actions())} actions "
            f"via the 'action' parameter: {', '.join(self._available_actions())}.",
            "inputSchema": self.get_tool_schema(),
        }
        if self._annotations is not None:
            definition["annotations"] = self._annotations
        return definition

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """A facade only requires a known ``action``; inner tools validate the
        rest. Returns True / raises ValueError (BaseMCPTool contract)."""
        action = arguments.get("action")
        if not action or not isinstance(action, str):
            raise ValueError("missing required parameter 'action'")
        if action not in self.action_map and action not in self.bespoke_map:
            raise ValueError(
                f"unknown action {action!r}; expected one of "
                f"{self._available_actions()}"
            )
        return True
