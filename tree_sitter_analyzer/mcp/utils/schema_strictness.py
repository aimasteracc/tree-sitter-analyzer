"""F5 — strict JSON Schema parameter validation for MCP tools.

JSON Schema defaults to allowing additional properties. Round-16b dogfood
showed that typo'd parameters (e.g. ``max_suggestion`` instead of
``max_suggestions``) pass through silently — the schema validates, the
typo'd key is dropped, and the tool runs with the default value. The
caller never learns their input was ignored.

This module provides ``enforce_strict_params`` — a single function that:

* Treats every MCP tool's input schema as strict by default
  (``additionalProperties: False``), even if the schema literal omits it.
  An opt-out is supported by explicitly setting ``additionalProperties: True``
  on a schema that legitimately needs to accept extras.
* When unknown keys are found, raises ``ValueError`` whose message includes
  a *did-you-mean* hint generated via :func:`difflib.get_close_matches`.

The function is called from two places:

1. ``BaseMCPTool.__init_subclass__`` wraps every subclass's ``execute``
   coroutine with this check — catches both MCP-routed dispatch and
   direct ``await tool.execute(args)`` calls used by tests / CLI bridges.
2. ``server_utils.tool_registration._dispatch_tool`` for legacy
   non-BaseMCPTool dispatch paths (``set_project_path``,
   ``extract_code_section``).

Centralising the check here keeps all 25+ tools consistent without
sprinkling ``additionalProperties: False`` into every helper module.
"""

from __future__ import annotations

import difflib
from typing import Any


def enforce_strict_params(
    tool_name: str,
    schema: dict[str, Any] | None,
    arguments: dict[str, Any] | None,
) -> None:
    """Reject unknown top-level parameters with a did-you-mean hint.

    Parameters
    ----------
    tool_name:
        Public tool name; used only in error messages.
    schema:
        The tool's ``inputSchema`` dict. If ``None`` or missing the
        ``properties`` key, validation is skipped — there is no way to
        know what is "known".
    arguments:
        The caller's argument dict. If ``None`` or empty, nothing to do.

    Behaviour
    ---------
    * If ``schema["additionalProperties"]`` is explicitly ``True``, the
      check is skipped — that schema has opted out of strict mode.
    * Otherwise (the default, including when the key is missing), any
      key in ``arguments`` that is not in ``schema["properties"]`` is
      treated as unknown.
    * The first unknown key triggers a ``ValueError`` whose message
      reads ``"unknown parameter 'X'"`` plus an optional
      ``" - did you mean 'Y'?"`` clause when difflib finds a close
      match against the schema's known property names.

    The check intentionally only inspects top-level keys. Nested
    objects (e.g. each item inside a ``requests`` list) are validated
    by per-tool logic; sweeping that into a generic helper would be
    too invasive for F5's scope.
    """
    if not isinstance(schema, dict) or not isinstance(arguments, dict):
        return
    if not arguments:
        return

    properties = schema.get("properties")
    if not isinstance(properties, dict):
        # No declared properties — cannot know what's "known".
        return

    # Explicit opt-out: a schema that says ``additionalProperties: True``
    # means the tool wants to accept arbitrary keys (e.g. pass-through
    # to a subprocess). Honour it.
    if schema.get("additionalProperties") is True:
        return

    known: list[str] = list(properties.keys())
    unknown = [key for key in arguments if key not in properties]
    if not unknown:
        return

    bad = sorted(unknown)[0]
    suggestions = difflib.get_close_matches(bad, known, n=1, cutoff=0.6)
    hint = f" — did you mean '{suggestions[0]}'?" if suggestions else ""
    raise ValueError(f"unknown parameter '{bad}' for tool '{tool_name}'{hint}")


def schema_known_properties(schema: dict[str, Any] | None) -> list[str]:
    """Return the declared property names from a schema (defensive helper).

    Used by tests and tooling that want to introspect a tool's schema
    without re-implementing the dict access pattern. Returns an empty
    list when the schema is missing or malformed.
    """
    if not isinstance(schema, dict):
        return []
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    return list(properties.keys())
