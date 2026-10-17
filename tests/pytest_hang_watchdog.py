"""Per-test hard hang watchdog (#1638).

pytest-timeout (``--timeout=30``, signal method) raises ``Failed`` in the main
thread, but that does not always end a stuck test: a teardown that blocks after
the alarm fired, C code that never returns to the interpreter, or a cleanup path
that waits on a thread or child with no deadline all keep the worker alive. On
2026-10-15 (run 38744393660) one xdist worker sat in such a state until the
15-minute step limit, and ``-q`` output could not say which test it was.

This plugin arms ``faulthandler.dump_traceback_later(exit=True)`` around each
test attempt (setup through teardown). The C watchdog thread needs no GIL, so it
fires even if the main thread is stuck in native code. When it fires it writes
the stacks of every thread and ends the process:

* xdist worker: the dump goes to a per-worker file headed by the node id. xdist
  reports the crashed worker and replaces it; the controller prints every dump
  in the terminal summary and fails the session, so a rerun that passes cannot
  hide the hang.
* single process (``-n 0``): the dump goes to the real stderr and the process
  exits with status 1.

The deadline is ``max(--hang-timeout, 2 * the pytest-timeout limit)`` so it only
fires after the soft timeout has had its chance to end the test.
"""

from __future__ import annotations

import faulthandler
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

DEFAULT_HANG_TIMEOUT_S = 120.0
HANG_TIMEOUT_ENV = "TSA_TEST_HANG_TIMEOUT"
_WORKERINPUT_KEY = "tsa_hang_dump_dir"
_PLUGIN_NAME = "tsa-hang-watchdog"
# faulthandler.dump_traceback_later writes this prefix before the stacks.
_DUMP_MARKER = b"Timeout ("


def add_options(parser: pytest.Parser) -> None:
    parser.addoption(
        "--hang-timeout",
        type=float,
        default=None,
        help=(
            "Hard per-test deadline in seconds; when exceeded, dump all thread "
            "stacks and end the process (#1638). 0 disables. Default: "
            f"${HANG_TIMEOUT_ENV} or {DEFAULT_HANG_TIMEOUT_S:g}."
        ),
    )


def configured_base(config: pytest.Config) -> float:
    value = config.getoption("--hang-timeout")
    if value is None:
        raw = os.environ.get(HANG_TIMEOUT_ENV, "")
        try:
            value = float(raw) if raw else DEFAULT_HANG_TIMEOUT_S
        except ValueError as exc:
            raise pytest.UsageError(
                f"{HANG_TIMEOUT_ENV} must be a number of seconds, got {raw!r}"
            ) from exc
    if value < 0:
        raise pytest.UsageError("--hang-timeout must be >= 0")
    return float(value)


def soft_timeout(item: pytest.Item) -> float:
    """Return pytest-timeout's limit for ``item`` (marker, then CLI/ini)."""
    marker = item.get_closest_marker("timeout")
    if marker is not None:
        value = marker.args[0] if marker.args else marker.kwargs.get("timeout")
        if value is not None:
            return float(value)
    config = item.config
    for getter in (config.getoption, config.getini):
        try:
            value = getter("timeout")
        except ValueError:
            continue
        if value not in (None, ""):
            return float(value)
    return 0.0


def hang_deadline(base: float, soft: float) -> float:
    """Deadline that lets the soft timeout act first: ``max(base, 2 * soft)``."""
    if base <= 0:
        return 0.0
    return max(base, 2 * soft) if soft > 0 else base


class HangWatchdog:
    """Arms one faulthandler deadline per test attempt in this process."""

    def __init__(self, config: pytest.Config, base: float) -> None:
        self._config = config
        self._base = base
        self._is_worker = getattr(config, "workerinput", None) is not None
        self._dump_dir: Path | None = None
        self._fd: int | None = None
        self.dumps: list[str] = []

    def start(self) -> None:
        if self._is_worker:
            dump_dir = self._config.workerinput.get(_WORKERINPUT_KEY)
            if dump_dir:
                worker = self._config.workerinput.get("workerid", "gw")
                path = Path(dump_dir) / f"{worker}-{os.getpid()}.txt"
                self._fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_TRUNC, 0o600)
            return
        # Controller or single process. Duplicate fd 2 now, while global
        # capture is suspended, so a dump reaches the real stderr rather than
        # a per-test capture file.
        self._fd = os.dup(sys.stderr.fileno())
        if self._config.pluginmanager.hasplugin("xdist"):
            self._dump_dir = Path(tempfile.mkdtemp(prefix="tsa-hang-"))

    # -- xdist controller ----------------------------------------------
    def configure_node(self, node: Any) -> None:
        if self._dump_dir is not None:
            node.workerinput[_WORKERINPUT_KEY] = str(self._dump_dir)

    def _collect_dumps(self) -> list[str]:
        if self._dump_dir is None or not self._dump_dir.is_dir():
            return []
        dumps = []
        for path in sorted(self._dump_dir.iterdir()):
            data = path.read_bytes()
            if _DUMP_MARKER in data:
                dumps.append(data.decode("utf-8", errors="replace"))
        return dumps

    @pytest.hookimpl(tryfirst=True)
    def pytest_sessionfinish(self, session: pytest.Session) -> None:
        # A worker this watchdog ended must fail the session even if
        # pytest-rerunfailures re-ran the crashed test and it passed.
        self.dumps = self._collect_dumps()
        if self.dumps:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def pytest_terminal_summary(self, terminalreporter: Any) -> None:
        for dump in self.dumps:
            terminalreporter.write_sep(
                "!", "hang watchdog: test exceeded hard deadline"
            )
            terminalreporter.write_line(dump.rstrip())

    # -- per test attempt ----------------------------------------------
    @pytest.hookimpl(wrapper=True, tryfirst=True)
    def pytest_runtest_setup(self, item: pytest.Item):
        self._arm(item)
        return (yield)

    @pytest.hookimpl(wrapper=True, tryfirst=True)
    def pytest_runtest_teardown(self, item: pytest.Item):
        try:
            return (yield)
        finally:
            faulthandler.cancel_dump_traceback_later()

    def _arm(self, item: pytest.Item) -> None:
        if self._fd is None:
            return
        deadline = hang_deadline(self._base, soft_timeout(item))
        if deadline <= 0:
            return
        if self._is_worker:
            header = (
                f"hang watchdog: {item.nodeid} exceeded {deadline:g}s "
                f"(pid {os.getpid()})\n"
            ).encode("utf-8", errors="replace")
            os.lseek(self._fd, 0, os.SEEK_SET)
            os.write(self._fd, header)
            os.ftruncate(self._fd, len(header))
        faulthandler.dump_traceback_later(deadline, exit=True, file=self._fd)

    # -- teardown ------------------------------------------------------
    @pytest.hookimpl(trylast=True)
    def pytest_unconfigure(self) -> None:
        faulthandler.cancel_dump_traceback_later()
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        if self._dump_dir is not None:
            shutil.rmtree(self._dump_dir, ignore_errors=True)
            self._dump_dir = None


def install(config: pytest.Config) -> HangWatchdog | None:
    """Register the watchdog for this process unless disabled or debugging."""
    base = configured_base(config)
    debugging = config.getoption("usepdb", False) or config.getoption("trace", False)
    if base <= 0 or debugging:
        return None
    watchdog = HangWatchdog(config, base)
    watchdog.start()
    config.pluginmanager.register(watchdog, _PLUGIN_NAME)
    if not hasattr(config, "workerinput") and config.pluginmanager.hasplugin("xdist"):
        config.pluginmanager.register(_XdistBridge(watchdog), f"{_PLUGIN_NAME}-xdist")
    return watchdog


class _XdistBridge:
    """Hand the controller's dump directory to each worker (xdist-only hook)."""

    def __init__(self, watchdog: HangWatchdog) -> None:
        self._watchdog = watchdog

    def pytest_configure_node(self, node: Any) -> None:
        self._watchdog.configure_node(node)
