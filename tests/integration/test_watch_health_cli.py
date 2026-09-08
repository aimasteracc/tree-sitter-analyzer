"""RED integration tests for the --watch-health CLI flag and daemon wiring.

Target surface (does NOT exist yet):
    CLI flags:
        --watch-health
        --threshold-grade {A,B,C,D,F}
        --watch-interval SECONDS
        --watch-debounce SECONDS
        --notify-channel stdout|file|webhook (comma-sep, repeatable)
        --notify-file PATH
        --on-degradation '<template>'
        --watch-cooldown SECONDS
        --history-keep N

    Runtime: the daemon reuses FileWatcherDaemon (already implemented).
    The wrapper module (does NOT exist yet) exposes a function/class that:
        - parses CLI args,
        - spawns the daemon thread,
        - installs an on_sync callback that calls
          HealthHomeostasisLoop.on_sync_callback(changed_files),
        - shuts down cleanly on SIGINT or .stop().

Wrapper module candidate paths the test will probe (importing whichever
the implementation chose — both are reasonable per the spec):
    tree_sitter_analyzer.health_homeostasis.WatchHealthRunner
    tree_sitter_analyzer.health_homeostasis.run_watch_health
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


# ------------------------------------------------------------------ lazy imports


def _create_parser():
    from tree_sitter_analyzer.cli.argument_parser_builder import (  # noqa: WPS433
        create_argument_parser,
    )

    return create_argument_parser()


def _import_runner():
    """Find the watch-health runner entrypoint.

    Per spec ambiguity, accept either a callable factory or a class.
    """
    from tree_sitter_analyzer import health_homeostasis  # noqa: WPS433

    runner_cls = getattr(health_homeostasis, "WatchHealthRunner", None)
    runner_fn = getattr(health_homeostasis, "run_watch_health", None)
    if runner_cls is None and runner_fn is None:
        pytest.fail(
            "neither WatchHealthRunner nor run_watch_health exposed in "
            "tree_sitter_analyzer.health_homeostasis"
        )
    return runner_cls or runner_fn


# ------------------------------------------------------------------ CLI flag parsing


def test_watch_health_cli_flag_parsed() -> None:
    """--watch-health and --threshold-grade are recognized by the argparse builder."""
    parser = _create_parser()

    args = parser.parse_args(["--watch-health", "--threshold-grade", "C"])

    assert getattr(args, "watch_health", False) is True
    assert getattr(args, "threshold_grade", None) == "C"


def test_watch_health_all_siblings_parsed(tmp_path: Path) -> None:
    """All --watch-health sibling flags must parse without errors."""
    parser = _create_parser()
    out = tmp_path / "events.jsonl"

    args = parser.parse_args(
        [
            "--watch-health",
            "--threshold-grade",
            "C",
            "--watch-interval",
            "5",
            "--watch-debounce",
            "0.5",
            "--notify-channel",
            "stdout,file",
            "--notify-file",
            str(out),
            "--on-degradation",
            "echo {file} {grade}",
            "--watch-cooldown",
            "30",
            "--history-keep",
            "100",
        ]
    )

    assert args.watch_health is True
    assert args.threshold_grade == "C"
    assert float(args.watch_interval) == pytest.approx(5.0)
    assert float(args.watch_debounce) == pytest.approx(0.5)
    # Comma-separated channels: accept either list-form or raw string;
    # both are valid argparse choices for this flag.
    channels = args.notify_channel
    if isinstance(channels, str):
        channels = channels.split(",")
    assert "stdout" in channels
    assert "file" in channels
    assert args.notify_file == str(out)
    assert args.on_degradation == "echo {file} {grade}"
    assert float(args.watch_cooldown) == pytest.approx(30.0)
    assert int(args.history_keep) == 100


def test_threshold_grade_rejects_invalid_values() -> None:
    """--threshold-grade must constrain to A|B|C|D|F."""
    parser = _create_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--watch-health", "--threshold-grade", "Z"])


# ------------------------------------------------------------------ daemon lifecycle


def _spawn_runner(runner_target, project_root: Path, **kwargs) -> object:
    """Instantiate the runner (class or factory) and return an object that
    exposes .start()/.stop() — or, if the entry point is a function, return
    a thin wrapper around it."""
    defaults = {
        "project_root": str(project_root),
        "threshold_grade": "C",
        "interval": 1.0,
        "debounce": 0.2,
        "cooldown": 0.0,
        "history_keep": 50,
    }
    defaults.update(kwargs)

    if isinstance(runner_target, type):
        return runner_target(**defaults)

    # Function form — wrap it.
    class _FunctionRunner:
        def __init__(self) -> None:
            self._thread: threading.Thread | None = None
            self._stop_event = threading.Event()

        def start(self) -> None:
            def _go() -> None:
                runner_target(stop_event=self._stop_event, **defaults)

            self._thread = threading.Thread(target=_go, daemon=True)
            self._thread.start()

        def stop(self, timeout: float = 5.0) -> None:
            self._stop_event.set()
            if self._thread is not None:
                self._thread.join(timeout=timeout)

    return _FunctionRunner()


def test_watch_health_daemon_starts_and_stops_clean_on_sigint(
    tmp_path: Path,
) -> None:
    """Daemon starts in a background thread, stops cleanly on .stop(),
    leaves no orphan threads within a 5s timeout."""
    runner_target = _import_runner()

    # Seed a minimal project so the daemon has something to scan.
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("def f(): pass\n")

    threads_before = {t.ident for t in threading.enumerate()}

    runner = _spawn_runner(runner_target, tmp_path)
    runner.start()
    time.sleep(0.5)  # let the watcher boot

    # Sanity: at least one extra thread exists while running.
    running_threads = {t.ident for t in threading.enumerate()} - threads_before
    assert running_threads, "runner should have spawned at least one thread"

    # Stop and verify clean shutdown.
    stop = getattr(runner, "stop", None)
    assert callable(stop), "runner must expose .stop()"
    stop(timeout=5.0) if "timeout" in stop.__code__.co_varnames else stop()

    # Give threads a moment to wind down (defensive).
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        leftover = {t.ident for t in threading.enumerate()} - threads_before
        # Filter out non-alive threads that haven't been joined yet.
        leftover = {
            tid
            for tid in leftover
            if any(t.ident == tid and t.is_alive() for t in threading.enumerate())
        }
        if not leftover:
            break
        time.sleep(0.1)

    final_leftover = {
        t.ident
        for t in threading.enumerate()
        if t.is_alive() and t.ident not in threads_before
    }
    assert not final_leftover, (
        f"orphan threads after stop: {len(final_leftover)} still alive"
    )


# ------------------------------------------------------------------ end-to-end modify


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows-specific incompatibility — tracked separately",
)
def test_file_modify_triggers_reevaluation(tmp_path: Path) -> None:
    """#1405：相同健康分数的保存也必须产生新的历史记录。"""
    from tree_sitter_analyzer.registry.health_history import HealthHistory

    src = tmp_path / "src"
    src.mkdir()
    target = src / "main.py"
    target.write_text("def hello():\n    pass\n", encoding="utf-8")
    runner = _spawn_runner(_import_runner(), tmp_path, threshold_grade="F")
    history = HealthHistory(str(tmp_path))

    def wait_for_rows(expected):
        deadline = time.monotonic() + 8
        while True:
            rows = history._conn.execute(
                "SELECT id FROM health_score_history WHERE file_path = ? ORDER BY id",
                (str(target),),
            ).fetchall()
            if len(rows) == expected or time.monotonic() >= deadline:
                return [row[0] for row in rows]
            time.sleep(0.05)

    runner.start()
    try:
        assert wait_for_rows(1) == [1]
        target.write_text(
            "def hello():\n"
            "    if True:\n"
            "        if True:\n"
            "            if True:\n"
            "                return 42\n",
            encoding="utf-8",
        )
        assert wait_for_rows(2) == [1, 2]
    finally:
        runner.stop()
        history.close()


# ------------------------------------------------------------------ cli → runner glue


def test_cli_args_flow_into_runner_config(tmp_path: Path) -> None:
    """Args parsed from CLI → runner accepts them as kwargs.

    This is a contract test: prevents future drift between argparse and runner
    constructor."""
    parser = _create_parser()
    tmp_path / "events.jsonl"
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("pass\n")

    args = parser.parse_args(
        [
            "--watch-health",
            "--threshold-grade",
            "D",
            "--watch-interval",
            "1",
            "--watch-debounce",
            "0.2",
            "--watch-cooldown",
            "0",
            "--history-keep",
            "20",
            "--notify-channel",
            "stdout",
        ]
    )

    runner_target = _import_runner()
    # The runner must accept the canonical kwarg names (interval, debounce,
    # threshold_grade, cooldown, history_keep). Build with what CLI gave us.
    runner = _spawn_runner(
        runner_target,
        tmp_path,
        threshold_grade=args.threshold_grade,
        interval=float(args.watch_interval),
        debounce=float(args.watch_debounce),
        cooldown=float(args.watch_cooldown),
        history_keep=int(args.history_keep),
    )

    runner.start()
    try:
        time.sleep(0.5)
    finally:
        stop = getattr(runner, "stop", None)
        if callable(stop):
            if "timeout" in stop.__code__.co_varnames:
                stop(timeout=5.0)
            else:
                stop()
