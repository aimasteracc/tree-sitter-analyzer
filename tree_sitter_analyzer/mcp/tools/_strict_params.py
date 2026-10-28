"""F5 strict-params enforcement helpers for BaseMCPTool subclasses.

Extracted from ``base_tool.py`` (F5 round-16b) to give the sentinel and
wrapping logic a dedicated home without pulling in the full ``BaseMCPTool``
class definition.

``base_tool.py`` imports :data:`_F5_WRAPPED_ATTR` and
:func:`wrap_execute_with_strict_params` from here; nothing else in the
package needs to import this module directly unless it is building its own
tool-dispatch layer.
"""

from __future__ import annotations

import functools
import inspect
from typing import TYPE_CHECKING, Any

from tree_sitter_analyzer.mcp.utils.schema_strictness import enforce_strict_params

if TYPE_CHECKING:
    # Avoid a circular import at runtime: base_tool imports this module,
    # and BaseMCPTool is defined in base_tool. The type annotation is only
    # needed for the type checker.
    from .base_tool import BaseMCPTool

#: Sentinel attribute name set on an ``execute`` coroutine to mark it as
#: already wrapped by :func:`wrap_execute_with_strict_params`. This prevents
#: double-wrapping when a concrete subclass inherits ``execute`` from an
#: intermediate class that was already processed by ``__init_subclass__``.
_F5_WRAPPED_ATTR = "_f5_strict_params_wrapped"


def wrap_execute_with_strict_params(cls_execute: Any) -> Any:
    """Wrap an ``execute`` coroutine with strict-parameter pre-checking.

    Args:
        cls_execute: The raw (unwrapped) async ``execute`` method from a
            concrete ``BaseMCPTool`` subclass.

    Returns:
        A new coroutine function that calls
        ``self._guard_strict_parameters(arguments)`` before delegating to
        ``cls_execute``. The wrapper has the :data:`_F5_WRAPPED_ATTR`
        sentinel set to ``True`` so a deeper subclass does not double-wrap.

    The returned wrapper has the same ``__name__``, ``__doc__``, and
    ``__wrapped__`` as the original (via :func:`functools.wraps`).
    """
    if not inspect.iscoroutinefunction(cls_execute):
        # Non-async execute deviates from the protocol. Leave it alone — the
        # central dispatcher fallback still catches MCP-routed calls.
        return cls_execute

    @functools.wraps(cls_execute)
    async def _wrapped(self: BaseMCPTool, arguments: dict[str, Any]) -> dict[str, Any]:
        self._guard_strict_parameters(arguments)
        from ...cache.generation_reads import generation_read_scope

        with generation_read_scope():
            result = await cls_execute(self, arguments)
        if isinstance(result, dict) and result.get("success") is False:
            # #1808/#1809: every failure leaves the tool with an ``error``
            # and a machine code, for direct callers as well as MCP clients.
            from ..server_utils.error_recovery import ensure_failure_identity

            ensure_failure_identity(result, _tool_name(self))
        return result  # type: ignore[no-any-return]

    setattr(_wrapped, _F5_WRAPPED_ATTR, True)
    return _wrapped


def _tool_name(tool: Any) -> str:
    """The tool's MCP name for a failure message; the class name as fallback."""
    try:
        name = tool.get_tool_definition().get("name")
    except Exception:  # noqa: BLE001 - the name only labels a message
        name = None
    return name if isinstance(name, str) and name else type(tool).__name__


__all__ = [
    "_F5_WRAPPED_ATTR",
    "enforce_strict_params",
    "wrap_execute_with_strict_params",
]
