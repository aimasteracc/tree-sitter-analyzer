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

        return self._action_error(f"unknown action {action!r}")

    # -- schema / definition ----------------------------------------------

    def get_tool_schema(self) -> dict[str, Any]:
        """Merged facade schema: ``action`` (required) + control keys + union.

        F4 / R2: the facade-level schema is intentionally lenient
        (``additionalProperties: True``). It MUST allow ``action`` / ``scope``
        / ``mode`` and the union of every inner param so the facade's own
        strict-param guard (from ``__init_subclass__``) does not self-reject a
        valid action's params. The inner tools keep their own strict schemas;
        per-action correctness is enforced there. ``mode`` / ``scope`` are
        free strings — their legal set is action-scoped and only the inner
        ``validate_arguments`` can honestly enumerate it.
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
            "scope": {
                "type": "string",
                "description": (
                    "Action-scoped discriminator (e.g. point|graph). "
                    "Legal values depend on action; the inner tool validates."
                ),
            },
            "mode": {
                "type": "string",
                "description": (
                    "Action-scoped sub-mode (e.g. summary|cycles|blast). "
                    "Legal values depend on action; the inner tool validates."
                ),
            },
        }

        # Union of every inner tool's declared params (F4: agents need the
        # merged surface; inner strict guards enforce per-action correctness).
        for inner in self.action_map.values():
            try:
                definition = inner.get_tool_definition()
            except Exception:  # noqa: BLE001
                continue
            schema = (
                definition.get("inputSchema") if isinstance(definition, dict) else None
            )
            if not isinstance(schema, dict):
                continue
            props = schema.get("properties")
            if not isinstance(props, dict):
                continue
            for key, spec in props.items():
                # First declaration wins; do not clobber the control keys.
                if key not in properties:
                    properties[key] = spec

        return {
            "type": "object",
            "properties": properties,
            "required": ["action"],
            # Lenient on purpose: the union cannot capture every possible
            # bespoke-route param, and self-rejection here would defeat the
            # facade. Inner tools remain strict.
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
