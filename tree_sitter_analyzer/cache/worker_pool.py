"""Spawn-pool plumbing for parallel extraction (#1724).

Two problems surfaced in a long-lived MCP stdio server on Windows. A full
re-extraction there started 12 pool workers, which never ran a task, and the
``tools/call`` never returned.

1. **Inherited stdin deadlock.** ``multiprocessing`` on Windows creates each
   worker with ``CreateProcess`` and no explicit ``STARTUPINFO``, so the worker
   gets the parent's current standard handles. In the MCP server, stdin is the
   JSON-RPC pipe, and the server's reader thread always has a synchronous
   ``ReadFile`` pending on it. While the worker interpreter initializes its
   standard streams, it queries that handle (``lseek`` →
   ``NtQueryInformationFile``). On a synchronous pipe, that query waits for the
   pending read to finish, but the client is waiting for the reply, so it never
   does. The py-spy stacks show every worker blocked in
   ``Py_InitializeFromConfig`` → ``lseek`` → ``NtQueryInformationFile``, and the
   parent waiting in ``Pool.imap_unordered``. A server started as
   ``tree-sitter-analyzer-mcp.exe`` hangs the same way as one started with
   ``python -P -c``. Fix: while the pool starts its workers,
   :func:`isolated_std_handles` points the process's standard input at ``NUL``
   and its standard output at standard error. Workers then never touch the
   JSON-RPC pipe, and a stray print from a worker cannot corrupt the protocol
   stream. The parent's own ``sys.stdin`` / ``sys.stdout`` keep their file
   descriptors and are unaffected.
2. **No liveness bound.** The parent waited for results without any limit.
   :func:`run_pool` bounds the wait for the first result and for each later
   result. On a stall it terminates the pool and raises
   :class:`WorkerPoolStalled` instead of hanging.
"""

from __future__ import annotations

import os
import sys
import threading
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from multiprocessing import TimeoutError as PoolTimeout
from multiprocessing import pool as _mp_pool
from multiprocessing.context import BaseContext
from typing import Any

#: Bound on the first result: worker start-up plus one chunk of files.
FIRST_RESULT_SECONDS = 180.0
#: Bound between two later results (one chunk of up to ``chunksize`` files).
RESULT_SECONDS = 600.0
#: Environment override for both bounds, in seconds.
ENV_VAR = "TSA_INDEX_POOL_TIMEOUT"

_STD_INPUT_HANDLE = -10
_STD_OUTPUT_HANDLE = -11
_STD_ERROR_HANDLE = -12
#: Serialises the process-wide standard-handle swap between concurrent pools.
_HANDLE_LOCK = threading.Lock()


class WorkerPoolStalled(RuntimeError):
    """The extraction pool produced no result within its time bound."""

    code = "INDEX_WORKER_POOL_STALLED"


def _bounds() -> tuple[float, float]:
    raw = os.environ.get(ENV_VAR, "").strip()
    if raw:
        try:
            value = float(raw)
        except ValueError:
            value = 0.0
        if value > 0:
            return value, value
    return FIRST_RESULT_SECONDS, RESULT_SECONDS


@contextmanager
def isolated_std_handles() -> Iterator[None]:
    """On Windows, give child processes created in this block a ``NUL`` stdin
    and the parent's stderr as stdout (see the module docstring). This is a
    no-op elsewhere: POSIX ``spawn`` does not query an inherited pipe that way.
    """
    if sys.platform == "win32":  # pragma: no cover - Windows only (tested there)
        with _windows_isolated_std_handles():
            yield
    else:
        yield


if sys.platform == "win32":  # pragma: no cover - Windows only (tested there)

    @contextmanager
    def _windows_isolated_std_handles() -> Iterator[None]:
        import ctypes
        import msvcrt

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetStdHandle.restype = ctypes.c_void_p
        kernel32.GetStdHandle.argtypes = [ctypes.c_ulong]
        kernel32.SetStdHandle.restype = ctypes.c_int
        kernel32.SetStdHandle.argtypes = [ctypes.c_ulong, ctypes.c_void_p]
        null_fd = os.open(os.devnull, os.O_RDONLY)
        try:
            null_handle = msvcrt.get_osfhandle(null_fd)
            with _HANDLE_LOCK:
                previous_in = kernel32.GetStdHandle(_STD_INPUT_HANDLE & 0xFFFFFFFF)
                previous_out = kernel32.GetStdHandle(_STD_OUTPUT_HANDLE & 0xFFFFFFFF)
                error = kernel32.GetStdHandle(_STD_ERROR_HANDLE & 0xFFFFFFFF)
                kernel32.SetStdHandle(_STD_INPUT_HANDLE & 0xFFFFFFFF, null_handle)
                if error:
                    kernel32.SetStdHandle(_STD_OUTPUT_HANDLE & 0xFFFFFFFF, error)
                try:
                    yield
                finally:
                    kernel32.SetStdHandle(_STD_INPUT_HANDLE & 0xFFFFFFFF, previous_in)
                    kernel32.SetStdHandle(_STD_OUTPUT_HANDLE & 0xFFFFFFFF, previous_out)
        finally:
            os.close(null_fd)


class _ConcurrentStartPool(_mp_pool.Pool):
    """``multiprocessing.pool.Pool`` that starts its workers concurrently.

    ``Pool`` starts workers one after another, and with the ``spawn`` start
    method each ``Process.start()`` returns only after the new interpreter has
    booted far enough to read its preparation data from the parent's pipe. Pool
    start-up therefore costs the *sum* of the workers' boot times. On Windows,
    where process creation is slow (slower still under real-time scanning),
    that sum dominated a cold index: 13 workers took 5.4 s to start on fastapi
    (1,191 files), out of 14.8 s for the whole extraction. Starting each worker
    from its own thread overlaps the boots, so start-up costs about one boot.

    Only the construction-time population is concurrent. ``_maintain_pool``
    replaces a dead worker through ``Pool._repopulate_pool_static`` (by class
    name) and stays sequential. The workers are the ones ``Pool`` would create:
    same ``Process`` factory, target, arguments, name and daemon flag.
    """

    @staticmethod
    def _repopulate_pool_static(
        ctx: Any,
        Process: Any,  # noqa: N803 - mirrors the CPython signature
        processes: int,
        pool: list[Any],
        inqueue: Any,
        outqueue: Any,
        initializer: Any,
        initargs: Any,
        maxtasksperchild: Any,
        wrap_exception: Any,
    ) -> None:
        workers = []
        for _ in range(processes - len(pool)):
            worker = Process(
                ctx,
                target=_mp_pool.worker,  # type: ignore[attr-defined]
                args=(
                    inqueue,
                    outqueue,
                    initializer,
                    initargs,
                    maxtasksperchild,
                    wrap_exception,
                ),
            )
            worker.name = worker.name.replace("Process", "PoolWorker")
            worker.daemon = True
            workers.append(worker)
        started, error = _start_concurrently(workers)
        # Started workers join the pool even on failure: ``Pool.__init__`` then
        # terminates and joins everything in ``pool`` before re-raising.
        pool.extend(started)
        if error is not None:
            raise error


def _start_concurrently(workers: list[Any]) -> tuple[list[Any], BaseException | None]:
    """Call ``start()`` on every worker, each from its own thread, and wait.

    Returns the workers that started (in their original order) and the first
    failure, if any.
    """
    errors: list[BaseException] = []

    def start(worker: Any) -> None:
        try:
            worker.start()
        except BaseException as exc:  # handed back to the calling thread
            errors.append(exc)

    if len(workers) <= 1:
        for worker in workers:
            start(worker)
    else:
        threads = [
            threading.Thread(target=start, args=(worker,), name="tsa-pool-start")
            for worker in workers
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    started = [worker for worker in workers if worker.pid is not None]
    return started, (errors[0] if errors else None)


def _make_pool(ctx: Any, workers: int, initializer: Callable[[], Any] | None) -> Any:
    """A concurrently started pool for a real context; ``ctx.Pool`` otherwise."""
    if isinstance(ctx, BaseContext):
        return _ConcurrentStartPool(
            processes=workers, initializer=initializer, context=ctx
        )
    return ctx.Pool(processes=workers, initializer=initializer)


def _run_chunk(task: tuple[Callable[[Any], Any], list[Any]]) -> list[Any]:
    """Worker side: apply ``func`` to one chunk of items."""
    func, chunk = task
    return [func(item) for item in chunk]


def run_pool(
    ctx: Any,
    workers: int,
    initializer: Callable[[], Any] | None,
    func: Callable[[Any], Any],
    args: Iterable[Any],
    *,
    chunksize: int = 8,
    first_result_seconds: float | None = None,
    result_seconds: float | None = None,
) -> list[Any]:
    """``Pool.imap_unordered`` with isolated standard handles and liveness bounds.

    Raises :class:`WorkerPoolStalled` (after terminating the pool) when no result
    arrives in time; results are otherwise returned in completion order.
    """
    default_first, default_next = _bounds()
    first = default_first if first_result_seconds is None else first_result_seconds
    later = default_next if result_seconds is None else result_seconds
    items = list(args)
    results: list[Any] = []
    with isolated_std_handles():
        # Workers are created in the constructor (processes=workers), inside the
        # isolated-handle window; the window closes before any task runs.
        pool = _make_pool(ctx, workers, initializer)
    try:
        # Chunks are sent as single tasks: ``imap_unordered`` with ``chunksize > 1``
        # returns a plain generator without ``next(timeout)``.
        size = max(1, chunksize)
        chunks = [(func, items[i : i + size]) for i in range(0, len(items), size)]
        iterator = pool.imap_unordered(_run_chunk, chunks, chunksize=1)
        for _ in range(len(chunks)):
            bound = first if not results else later
            try:
                results.extend(iterator.next(timeout=bound))
            except PoolTimeout:
                pool.terminate()
                raise WorkerPoolStalled(
                    f"{WorkerPoolStalled.code}: no extraction result within "
                    f"{bound:.0f} s ({len(results)}/{len(items)} files done, "
                    f"{workers} workers); set {ENV_VAR} or TSA_INDEX_WORKERS=0 "
                    "to index sequentially"
                ) from None
        pool.close()
        pool.join()
    finally:
        pool.terminate()
    return results
