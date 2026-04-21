"""Shared tool registration helpers."""
from collections.abc import Callable
from typing import Any


def _make_handler(
    tool: Any, method_name: str = "execute"
) -> Callable[..., Any]:
    """
    Create a handler function that calls the tool's method.

    Args:
        tool: The tool instance
        method_name: Name of the method to call

    Returns:
        Async handler function
    """

    async def handler(**kwargs: Any) -> Any:
        tool_instance = tool
        method = getattr(tool_instance, method_name)
        if hasattr(method, "__self__"):
            # It's a bound method, call it directly
            return await method(kwargs)
        else:
            # It's an unbound method, pass self
            return await method(tool_instance, kwargs)

    return handler

