"""
Constants for the code_map subsystem.

Single source of truth for framework decorators and other shared constants.
"""

from __future__ import annotations

# Decorator/annotation names that indicate framework-registered functions.
# Functions decorated with these are NOT dead code (called by frameworks).
FRAMEWORK_DECORATORS: frozenset[str] = frozenset({
    # Web frameworks
    "route", "get", "post", "put", "delete", "patch", "head", "options",
    "app", "api", "router", "blueprint", "middleware", "websocket",
    # CLI frameworks
    "command", "group", "option", "argument", "click", "typer",
    # Testing
    "fixture", "parametrize", "mark", "pytest", "test",
    # Python builtins / structural
    "property", "staticmethod", "classmethod",
    "abstractmethod", "override", "overload",
    "dataclass", "dataclasses",
    # Event / Signal / Callback
    "on", "listener", "handler", "receiver", "subscribe", "callback",
    # DI / Registration
    "register", "inject", "provider", "singleton", "service",
    # Celery / async tasks
    "task", "shared_task", "periodic_task",
    # Caching / memoization
    "cache", "cached", "lru_cache", "memoize",
})

# Files whose public symbols are exempt from dead code detection
PUBLIC_API_PATTERNS: tuple[str, ...] = (
    "api.py", "__init__.py", "interface.py", "exports.py",
    "public.py", "facade.py",
)
