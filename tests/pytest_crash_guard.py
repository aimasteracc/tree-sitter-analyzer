"""Keep a per-test timeout a normal, named test failure (#1779).

Two ways a test that overran ``--timeout`` used to take more than itself down:

* **POSIX (signal method).** pytest-timeout raises ``Failed`` from a SIGALRM
  handler. On Python 3.11+ the interrupted frame's ``tb_lineno`` can be
  ``None`` (the signal landed on an instruction with no line number), and
  pytest 8.4's ``TracebackEntry.lineno`` computes ``tb_lineno - 1``. The
  ``TypeError`` escaped ``pytest_runtest_makereport`` on the xdist worker,
  xdist turned it into ``INTERNALERROR> assert not crashitem`` and the whole
  session ended with exit code 3 (release run 39943115866, macos-latest 3.11,
  in ``test_real_repo_finds_java_plugin``).
* **Windows (thread method; no SIGALRM).** pytest-timeout dumps stacks to the
  worker's terminal, which xdist does not relay, and calls ``os._exit(1)``.
  The controller could only say ``worker 'gwN' crashed while running ...``
  (PR #1777).

This plugin:

1. makes ``TracebackEntry.lineno`` / ``Frame.lineno`` fall back to the frame's
   line (or its code object's first line) when CPython reports ``None``;
2. wraps ``pytest_runtest_makereport`` so a report that still cannot be built
   becomes a *failed* report naming the test, never an internal error;
3. replaces pytest-timeout's thread-method timer (the only method on Windows)
   with one that raises the timeout failure in the main thread instead of
   calling ``os._exit``, so the test fails (and is retried by ``--reruns``)
   like it does under the signal method. A test stuck in native code that
   never returns to the interpreter is still ended, with every thread's stack,
   by ``tests/pytest_hang_watchdog.py`` (#1638).

None of this hides a failure: every path still produces a failed report.
"""

from __future__ import annotations

import ctypes
import sys
import threading
import traceback
from typing import Any

import pytest
from _pytest._code import code as _pytest_code
from _pytest.outcomes import Failed
from _pytest.reports import TestReport

_PLUGIN_NAME = "tsa-crash-guard"
_PATCHED_FLAG = "_tsa_crash_guard_patched"


# -- 1. None-safe traceback line numbers ----------------------------------


def _frame_line(frame: Any) -> int:
    lineno = frame.f_lineno
    if lineno is None:
        lineno = frame.f_code.co_firstlineno
    return int(lineno)


def _entry_lineno(self: Any) -> int:
    raw = self._rawentry
    lineno = raw.tb_lineno
    if lineno is None:
        lineno = _frame_line(raw.tb_frame)
    return int(lineno) - 1


def _frame_lineno(self: Any) -> int:
    return _frame_line(self.raw) - 1


def patch_traceback_linenos() -> bool:
    """Make pytest's traceback line numbers tolerate ``tb_lineno is None``.

    Returns ``False`` (and changes nothing) when pytest's internals no longer
    have the expected shape, so a pytest upgrade degrades to stock behaviour.
    """
    targets = (
        (getattr(_pytest_code, "TracebackEntry", None), _entry_lineno),
        (getattr(_pytest_code, "Frame", None), _frame_lineno),
    )
    if any(
        cls is None or not isinstance(cls.__dict__.get("lineno"), property)
        for cls, _ in targets
    ):
        return False
    for cls, getter in targets:
        if not getattr(cls, _PATCHED_FLAG, False):
            cls.lineno = property(getter)  # type: ignore[union-attr]
            setattr(cls, _PATCHED_FLAG, True)
    return True


# -- 2. makereport safety net ---------------------------------------------


def _describe(excinfo: Any) -> str:
    if excinfo is None:
        return "(the test phase raised no exception)"
    try:
        return str(excinfo.exconly())
    except Exception:  # noqa: BLE001 - the description is best effort
        return repr(excinfo.value)


def fallback_report(item: pytest.Item, call: Any, error: BaseException) -> TestReport:
    """A failed report for ``item`` when pytest could not build the real one."""
    longrepr = (
        f"{_describe(call.excinfo)}\n\n"
        f"[{_PLUGIN_NAME} #1779] pytest could not render this report: "
        f"{type(error).__name__}: {error}"
    )
    return TestReport(
        nodeid=item.nodeid,
        location=item.location,
        keywords=dict.fromkeys(item.keywords, 1),
        outcome="failed",
        longrepr=longrepr,
        when=call.when,
        sections=[],
        duration=call.duration,
        start=call.start,
        stop=call.stop,
        user_properties=item.user_properties,
    )


# -- 3. in-process timeout for the thread method --------------------------


class PerTestTimeout(Failed):
    """Raised in the main thread when a test overruns its pytest-timeout."""

    message = "Timeout"

    def __init__(self, msg: str | None = None, pytrace: bool = True) -> None:
        super().__init__(msg or type(self).message, pytrace)


def _other_thread_stacks() -> str:
    main = threading.main_thread().ident
    current = threading.get_ident()
    names = {thread.ident: thread.name for thread in threading.enumerate()}
    chunks = []
    for ident, frame in sys._current_frames().items():
        if ident in (main, current):
            continue
        chunks.append(f"--- thread {names.get(ident, '<unknown>')} ({ident}) ---\n")
        chunks.append("".join(traceback.format_stack(frame)))
    return "".join(chunks)


# A private prototype: setting argtypes on ``ctypes.pythonapi``'s shared
# function object would leak into any other caller.
_SET_ASYNC_EXC = ctypes.PYFUNCTYPE(ctypes.c_int, ctypes.c_ulong, ctypes.py_object)(
    ("PyThreadState_SetAsyncExc", ctypes.pythonapi)
)


def _set_async_exc(thread_id: int, exc_type: type[BaseException] | None) -> int:
    """Raise ``exc_type`` in ``thread_id``; ``None`` clears a pending one."""
    exc = ctypes.py_object() if exc_type is None else ctypes.py_object(exc_type)
    return int(_SET_ASYNC_EXC(thread_id, exc))


def timeout_exception(timeout: float) -> type[PerTestTimeout]:
    """A ``PerTestTimeout`` subclass whose message carries the context."""
    message = f"Timeout (>{timeout}s) from pytest-timeout; raised in the main thread."
    stacks = _other_thread_stacks()
    if stacks:
        message += f"\nOther threads:\n{stacks}"
    return type("PerTestTimeout", (PerTestTimeout,), {"message": message})


def _debugging(settings: Any) -> bool:
    if getattr(settings, "disable_debugger_detection", False):
        return False
    try:
        import pytest_timeout
    except ImportError:
        return False
    return bool(pytest_timeout.is_debugging())


class CrashGuard:
    """pytest hooks registered by :func:`install`."""

    @pytest.hookimpl(wrapper=True, tryfirst=True)
    def pytest_runtest_makereport(self, item: pytest.Item, call: Any):
        try:
            return (yield)
        except Exception as error:  # noqa: BLE001 - converted to a failure
            return fallback_report(item, call, error)

    @pytest.hookimpl(tryfirst=True, optionalhook=True)
    def pytest_timeout_set_timer(self, item: pytest.Item, settings: Any) -> Any:
        main = threading.main_thread()
        if settings.method != "thread" or threading.current_thread() is not main:
            return None  # pytest-timeout's own timer handles it
        main_id = main.ident
        assert main_id is not None
        timeout = float(settings.timeout)

        def fire() -> None:
            if not _debugging(settings):
                _set_async_exc(main_id, timeout_exception(timeout))

        timer = threading.Timer(timeout, fire)
        timer.name = f"{_PLUGIN_NAME} {item.nodeid}"
        timer.daemon = True

        def cancel() -> None:
            timer.cancel()
            timer.join()
            # Drop an exception the test finished too quickly to receive, so it
            # cannot surface later inside pytest's own bookkeeping.
            _set_async_exc(main_id, None)

        item.cancel_timeout = cancel  # type: ignore[attr-defined]
        timer.start()
        return True


def install(config: pytest.Config) -> CrashGuard:
    """Register the guard for this process (controller and xdist workers)."""
    patch_traceback_linenos()
    existing = config.pluginmanager.get_plugin(_PLUGIN_NAME)
    if isinstance(existing, CrashGuard):
        return existing
    guard = CrashGuard()
    config.pluginmanager.register(guard, _PLUGIN_NAME)
    return guard
