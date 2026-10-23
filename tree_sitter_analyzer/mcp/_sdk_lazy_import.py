"""Import the MCP SDK's low-level server without its eager package inits (#1675).

``import mcp.server.lowlevel`` first executes ``mcp/__init__.py`` and
``mcp/server/__init__.py``. Those re-export the whole SDK: the client session,
FastMCP, the SSE / streamable-HTTP transports, and with them starlette,
uvicorn, pydantic-settings, rich, click and pygments. That is about 190 modules
a stdio server never uses, and on a loaded Windows machine each one is a file
open that costs a cold MCP process seconds before it can answer ``initialize``.

``httpx`` (imported by ``mcp.shared.session``) does the same with its CLI:
its ``__init__`` imports click, rich and pygments.

:func:`defer_sdk_package_inits` registers ``mcp``, ``mcp.server`` and
``httpx`` as real package modules (their ``__path__``/``__spec__`` are set, so submodule imports
work) whose ``__init__`` has not run yet. The first access to a name the
``__init__`` would have defined (``from mcp import ClientSession``,
``mcp.server.FastMCP``) imports the matching submodule if there is one, and
otherwise runs the real ``__init__`` once and answers from it. The deferral
therefore changes when the SDK's package code runs, never what any name
resolves to.

It is a no-op when ``mcp`` is already imported (tests, embedding hosts) or the
SDK is not installed.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import threading
from types import ModuleType
from typing import Any

#: Packages whose ``__init__`` is deferred, parent first. ``httpx`` is reached
#: only through ``mcp.shared.session`` (for ``httpx.codes`` on a timeout); its
#: ``__init__`` imports its CLI, and with it click, rich and pygments.
DEFERRED_PACKAGES: tuple[str, ...] = ("mcp", "mcp.server", "httpx")

_LOCK = threading.RLock()


def defer_sdk_package_inits(packages: tuple[str, ...] = DEFERRED_PACKAGES) -> bool:
    """Defer the package inits; True when the deferral was installed.

    Does nothing once the first package (``mcp``) is imported: the SDK's own
    ``__init__`` has then already imported everything this would defer.
    """
    with _LOCK:
        if not packages or packages[0] in sys.modules:
            return False
        installed = False
        for name in packages:
            parent, _, child = name.rpartition(".")
            if name in sys.modules or (parent and parent not in sys.modules):
                continue
            try:
                spec = importlib.util.find_spec(name)
            except (ImportError, ValueError):
                continue
            if not _is_package(spec):
                continue
            module = _install(spec)
            if parent:
                setattr(sys.modules[parent], child, module)
            installed = True
        return installed


def _is_package(spec: Any) -> bool:
    return (
        spec is not None
        and spec.loader is not None
        and spec.submodule_search_locations is not None
    )


def _install(spec: Any) -> ModuleType:
    module = importlib.util.module_from_spec(spec)
    name = spec.name

    def __getattr__(attr: str) -> Any:
        # Dunder lookups (``__wrapped__``, ``__path__`` probes, ...) must not
        # run the package init; ``__all__`` is a real public name of it.
        if attr.startswith("__") and attr != "__all__":
            raise AttributeError(f"module {name!r} has no attribute {attr!r}")
        submodule = f"{name}.{attr}"
        try:
            if importlib.util.find_spec(submodule) is not None:
                return importlib.import_module(submodule)
        except (ImportError, ValueError):
            pass
        _run_package_init(module, spec)
        try:
            return module.__dict__[attr]
        except KeyError:
            raise AttributeError(f"module {name!r} has no attribute {attr!r}") from None

    # PEP 562 module ``__getattr__``: consulted only for names not yet defined.
    setattr(module, "__getattr__", __getattr__)  # noqa: B010
    sys.modules[name] = module
    return module


def _run_package_init(module: ModuleType, spec: Any) -> None:
    """Run the real ``__init__`` exactly once (reentrant-safe)."""
    with _LOCK:
        if module.__dict__.pop("__getattr__", None) is None:
            return
        spec.loader.exec_module(module)
