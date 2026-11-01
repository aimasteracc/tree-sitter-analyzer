"""RFC-0042 P1: load the resident state in a background thread after server start.

Profiling (RFC-0042, ``rich``) puts 70–76 % of a fresh process's first
``nav callers`` in the certified snapshot capture and 10–26 % in the graph
build or adopt. Both are work the first query does anyway. The loader does
the same work earlier, in a daemon thread started after the MCP
``initialize`` answer, with the same functions and arguments:

1. ``certified_index_read(root)`` — the capture and certification a request
   runs; the published lease stays in the snapshot registry (35 s TTL) and the
   next request reuses it under the registry's existing reuse rule.
2. ``call_graph_warm.warm_now(root)`` — the post-publish background graph
   build of #1708 (``CachedCallGraph(persist=True)``), keyed by the graph input
   digest in ``call_graph_memo``. A request on any snapshot of the same content
   computes the same digest and adopts it; a request that arrives during the
   build waits for it through the existing ``call_graph_memo.claim`` (#1708).

Trust (RFC-0042 R0/R1): the loader adds no cache and no key. Its results are
found only through the certified snapshot identity and the content digest that
today's code already checks, so a different index generation or source state
can never see them; nothing here is freshness evidence. The loader never
records a certification timeout (a request records its own), never builds an
index, and skips a root without a published index or while a full rebuild runs.

Switch ``TSA_RESIDENT``: ``background`` (default) loads after start;
``first-use`` and ``off`` keep today's lazy behaviour (P1 has no further
resident state, so the two are the same for now; ``off`` stays the kill switch
for later phases). Only processes that call :func:`enable` (the MCP server)
ever load: one-shot CLI runs and embedders keep ``first-use``.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

#: Environment switch: ``off`` | ``first-use`` | ``background`` (default).
ENV_VAR = "TSA_RESIDENT"
DEFAULT_MODE = "background"
#: Upper bound to wait for in-flight loads at server shutdown (seconds).
SHUTDOWN_SECONDS = 5.0
#: Name of the loader thread (tests and logs recognise it).
THREAD_NAME = "tsa-resident-loader"
#: Modules the first ``nav callers`` call imports; the load ends by importing them.
PRELOAD_MODULES: tuple[str, ...] = (
    "tree_sitter_analyzer.mcp.tools.nav_facade",
    "tree_sitter_analyzer.mcp.tools.callers_tool",
)

_OFF_VALUES = frozenset({"off", "0", "false", "no"})
_MODES = frozenset({"off", "first-use", "background"})

_lock = threading.Lock()
_enabled = False
_closed = False
#: Project root key -> the loader thread (running or finished).
_threads: dict[str, threading.Thread] = {}
#: Project root key -> last known state (``loading`` / ``ready`` / ``skipped`` / ``failed``).
_status: dict[str, dict[str, Any]] = {}
#: Project root key -> (event set when the capture ends, capturing thread).
_capturing: dict[str, tuple[threading.Event, threading.Thread]] = {}


def mode() -> str:
    """The resident mode from ``TSA_RESIDENT``; unknown values mean the default."""
    value = os.environ.get(ENV_VAR, "").strip().lower()
    if value in _OFF_VALUES:
        return "off"
    if value in _MODES:
        return value
    return DEFAULT_MODE


def enable() -> None:
    """Called once by the long-running MCP server; other processes never load."""
    global _enabled, _closed
    with _lock:
        _enabled = True
        _closed = False


def _key(project_root: str) -> str:
    return os.path.normcase(os.path.realpath(project_root))


def start(project_root: str | None) -> bool:
    """Start the background load for ``project_root``; never blocks, never repeats.

    Returns True only when this call started a new loader thread. Idempotent:
    the ``initialized`` notification, ``tools/list`` and every ``tools/call``
    may call it; one load runs per root and process.
    """
    if not project_root:
        return False
    current = mode()
    key = _key(project_root)
    with _lock:
        if current != "background":
            _status.setdefault(key, {"state": current})
            return False
        if not _enabled or _closed or key in _threads:
            return False
        _status[key] = {"state": "loading"}
        thread = threading.Thread(
            target=_run, args=(project_root, key), name=THREAD_NAME, daemon=True
        )
        _threads[key] = thread
        thread.start()
    return True


def _run(project_root: str, key: str) -> None:
    started = time.perf_counter()
    try:
        outcome = load(project_root)
    except Exception as exc:  # noqa: BLE001 — requests then take today's path
        logger.warning("resident load failed for %s", project_root, exc_info=True)
        outcome = {"state": "failed", "reason": type(exc).__name__}
    outcome["seconds"] = round(time.perf_counter() - started, 3)
    with _lock:
        _status[key] = outcome


def load(project_root: str) -> dict[str, Any]:
    """Run today's first-query work for ``project_root``: certified lease, then graph."""
    from ..cache.generation_routing import resolve_index_path
    from ..mcp.tools.index_rebuild_signal import is_index_rebuilding

    try:
        database = str(resolve_index_path(project_root))
    except (OSError, ValueError):
        return {"state": "skipped", "reason": "INDEX_GENERATION_SELECTOR_INVALID"}
    if not os.path.lexists(database):
        return {"state": "skipped", "reason": "MISSING_INDEX"}
    if is_index_rebuilding(project_root):
        return {"state": "skipped", "reason": "INDEX_REBUILDING"}
    outcome: dict[str, Any] = {"state": "ready", "certified": _lease(project_root)}
    from .. import call_graph_warm

    outcome["graph"] = call_graph_warm.warm_now(project_root)
    if outcome["certified"] is None:
        outcome["snapshot_graph"] = _bind_snapshot_graph(project_root)
    outcome["preloaded"] = _preload()
    return outcome


def _preload() -> list[str]:
    """Import the modules a first ``nav callers`` call imports (no object is built).

    The server builds the ``nav`` facade on its first ``tools/call`` (#1675);
    importing its modules costs about 0.3 s of that call. This runs last, after
    the server has answered ``tools/list``, so it rarely overlaps the server's
    own imports (Python's per-module import locks make an overlap safe).
    """
    import importlib

    done: list[str] = []
    for name in PRELOAD_MODULES:
        try:
            importlib.import_module(name)
        except ImportError:
            continue
        done.append(name)
    return done


def _bind_snapshot_graph(project_root: str) -> str | None:
    """Adopt the built graph once on the leased snapshot, as a request would.

    A request on the certified snapshot finds its graph by the snapshot's
    remembered input digest (#1774); a snapshot not seen before re-reads every
    call edge to compute it. Running the request's own graph code here on the
    same lease (rows read, digest computed, memo hit) records that digest, so
    the first request adopts the graph without the re-read. ``None`` when bound.
    """
    from ..call_graph import CachedCallGraph
    from ..index_snapshot import certified_index_read

    with certified_index_read(project_root) as owner:
        if owner is None:
            return "INDEX_SNAPSHOT_UNKNOWN"
        cache = owner.query_cache()
        graph = CachedCallGraph(project_root, cache=cache, fallback=False, persist=True)
        graph.build()
        if not graph._built:
            return "GRAPH_NOT_BUILT"
        cache.call_graph_built()  # per-snapshot verdict the first request checks
        return None


def _lease(project_root: str) -> str | None:
    """Take the certified snapshot lease a request would take; None when certified.

    Mirrors the request's own guards (``callers_tool.execute_batch``): no capture
    when the live index's call-graph marker already rules certification out, or
    when a capture of the same state recently exceeded its deadline (#1710).
    """
    from ..cache.live_index_probe import probe_live_index
    from ..index_snapshot import _certified_index_read_reason, certified_index_read
    from ..mcp.tools import certification_timeouts

    probe = probe_live_index(project_root)
    if probe is not None and not probe.call_graph_exact:
        return "CALL_GRAPH_INCOMPLETE"
    if certification_timeouts.should_skip(project_root):
        return "CERTIFICATION_TIMEOUT_REMEMBERED"
    with capturing(project_root):
        with certified_index_read(project_root) as owner:
            if owner is not None:
                return None
            return _certified_index_read_reason() or "INDEX_SNAPSHOT_UNKNOWN"


@contextmanager
def capturing(project_root: str) -> Iterator[None]:
    """Mark a background capture of ``project_root`` as in flight (see :func:`await_capture`)."""
    key = _key(project_root)
    event = threading.Event()
    with _lock:
        _capturing[key] = (event, threading.current_thread())
    try:
        yield
    finally:
        with _lock:
            if _capturing.get(key, (None,))[0] is event:
                del _capturing[key]
        event.set()


def await_capture(project_root: str, timeout: float) -> bool:
    """Wait for another thread's in-flight background capture of the same root.

    A request that finds no reusable lease would otherwise wait on the capture
    lock that this capture holds and then capture the same state again. True
    when a capture was in flight and finished within ``timeout``: the caller
    then retries its reuse check under the same rule, else captures itself.
    """
    with _lock:
        entry = _capturing.get(_key(project_root))
    if entry is None or entry[1] is threading.current_thread():
        return False
    return entry[0].wait(max(0.0, timeout))


def status(project_root: str) -> dict[str, Any] | None:
    """Last known loader state for ``project_root`` (``None`` if never asked)."""
    with _lock:
        state = _status.get(_key(project_root))
    return dict(state) if state is not None else None


def wait(project_root: str | None = None, timeout: float | None = None) -> bool:
    """Wait for loader threads (all, or one root); True when all have finished."""
    deadline = None if timeout is None else time.monotonic() + timeout
    with _lock:
        threads = [
            thread
            for key, thread in _threads.items()
            if project_root is None or key == _key(project_root)
        ]
    for thread in threads:
        left = None if deadline is None else max(0.0, deadline - time.monotonic())
        thread.join(left)
    return not any(thread.is_alive() for thread in threads)


def shutdown(timeout: float = SHUTDOWN_SECONDS) -> bool:
    """Server stop: start no new load and wait up to ``timeout`` for running ones.

    A load still running is abandoned in its daemon thread (it only fills
    in-process caches and the atomically replaced graph store of #1675).
    """
    global _closed
    with _lock:
        _closed = True
    finished = wait(timeout=timeout)
    if not finished:
        logger.warning("resident load still running after %.1f s at shutdown", timeout)
    return finished


def reset() -> None:
    """Forget all loader state and disable (tests; threads already running finish)."""
    global _enabled, _closed
    with _lock:
        _enabled = False
        _closed = False
        _threads.clear()
        _status.clear()
        _capturing.clear()
