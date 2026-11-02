"""The MCP SDK's ``tools/call`` argument validation, with the schema check done once.

The low-level SDK server (``mcp`` 1.x) validates every call's arguments with
``jsonschema.validate(instance=arguments, schema=tool.inputSchema)``. That
function first checks the *schema* against its metaschema, on every call: about
6 ms per ``nav`` call measured (#1855), more than the rest of the MCP layer.

When the SDK allows it, the server registers its handler with
``validate_input=False`` and runs the same validation here, before the tool
runs, with the schema check and the validator kept per schema object:

* the same tool definition: the SDK's own ``_tool_cache``, which it fills (from
  ``tools/list``) before it calls the handler, whatever ``validate_input`` is;
* the same steps as ``jsonschema.validate``: ``validator_for``, ``check_schema``,
  ``best_match(validator.iter_errors(arguments))``; a schema that fails its check
  is checked again on the next call (only a passed check is kept);
* the same answer: the SDK turns a ``ValidationError`` into an error result
  ``"Input validation error: <message>"`` and any other exception into an error
  result ``str(exc)``. :class:`InputValidationError` carries exactly that
  message, so the SDK's catch-all produces the identical result.

Any other SDK (no ``_tool_cache`` dict, or no ``validate_input`` keyword, e.g.
the MCP 2.x adapter) keeps its own validation unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

#: Validators kept at most (one per tool schema object; the server has 9 tools).
MAX_VALIDATORS = 64


class InputValidationError(Exception):
    """Arguments rejected by the tool's ``inputSchema`` (the SDK's message)."""


class ToolInputValidator:
    """Validates ``tools/call`` arguments against the SDK's cached tool definitions."""

    def __init__(self, tool_cache: dict[str, Any]) -> None:
        self._tool_cache = tool_cache
        #: ``id(schema)`` -> (schema, validator); the schema reference keeps the id unique.
        self._validators: dict[int, tuple[Any, Any]] = {}

    def _validator(self, schema: Any) -> Any:
        entry = self._validators.get(id(schema))
        if entry is not None and entry[0] is schema:
            return entry[1]
        from jsonschema.validators import validator_for

        cls = validator_for(schema)
        cls.check_schema(schema)  # raises SchemaError: nothing is kept
        validator = cls(schema)
        if len(self._validators) >= MAX_VALIDATORS:
            self._validators.clear()
        self._validators[id(schema)] = (schema, validator)
        return validator

    def validate(self, name: str, arguments: dict[str, Any]) -> None:
        """Raise :class:`InputValidationError` where the SDK would reject ``arguments``."""
        tool = self._tool_cache.get(name)
        if tool is None:
            return  # the SDK validates nothing for a tool it has not listed
        from jsonschema.exceptions import best_match

        error = best_match(self._validator(tool.inputSchema).iter_errors(arguments))
        if error is not None:
            raise InputValidationError(f"Input validation error: {error.message}")

    def prepare(self, name: str) -> None:
        """Check ``name``'s schema now, so its first call does not (best effort)."""
        tool = self._tool_cache.get(name)
        if tool is None:
            return
        try:
            self._validator(tool.inputSchema)
        except Exception:  # noqa: BLE001 — the call itself reports a bad schema
            return


def call_tool_registration(
    server: Any,
) -> tuple[Callable[[Any], Any], ToolInputValidator | None]:
    """The ``tools/call`` decorator, and the validator the handler must run (or None).

    ``None`` means the SDK validates, exactly as before.
    """
    tool_cache = getattr(server, "_tool_cache", None)
    if isinstance(tool_cache, dict):
        try:
            decorator = server.call_tool(validate_input=False)
        except TypeError:
            pass
        else:
            return decorator, ToolInputValidator(tool_cache)
    return server.call_tool(), None
