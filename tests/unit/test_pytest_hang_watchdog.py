"""Hard per-test hang watchdog (#1638): a stuck test fails fast with stacks."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests import pytest_hang_watchdog as watchdog

REPO_ROOT = Path(__file__).resolve().parents[2]

_CONFTEST = """\
from tests import pytest_hang_watchdog


def pytest_addoption(parser):
    pytest_hang_watchdog.add_options(parser)


def pytest_configure(config):
    pytest_hang_watchdog.install(config)
"""

_HANGING_TESTS = """\
import time


def test_quick():
    assert True


def test_hangs():
    time.sleep(120)
"""


@pytest.mark.parametrize(
    ("base", "soft", "expected"),
    [
        (120.0, 30.0, 120.0),
        (120.0, 300.0, 600.0),
        (120.0, 0.0, 120.0),
        (0.0, 30.0, 0.0),
    ],
)
def test_deadline_lets_the_soft_timeout_act_first(base, soft, expected):
    assert watchdog.hang_deadline(base, soft) == expected


def _item(marker_args=None, cli=None, ini=None):
    marker = (
        None if marker_args is None else SimpleNamespace(args=marker_args, kwargs={})
    )
    options = {"timeout": cli}
    inis = {"timeout": ini}
    config = SimpleNamespace(
        getoption=lambda name: options[name],
        getini=lambda name: inis[name],
    )
    return SimpleNamespace(get_closest_marker=lambda name: marker, config=config)


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        (_item(marker_args=(300,), cli=30.0), 300.0),
        (_item(cli=30.0, ini="10"), 30.0),
        (_item(cli=None, ini="10"), 10.0),
        (_item(cli=None, ini=""), 0.0),
    ],
)
def test_soft_timeout_follows_pytest_timeout_precedence(item, expected):
    assert watchdog.soft_timeout(item) == expected


def test_invalid_hang_timeout_is_rejected(monkeypatch):
    monkeypatch.setenv(watchdog.HANG_TIMEOUT_ENV, "nope")
    config = SimpleNamespace(getoption=lambda name: None)
    with pytest.raises(pytest.UsageError, match=watchdog.HANG_TIMEOUT_ENV):
        watchdog.configured_base(config)
    config = SimpleNamespace(getoption=lambda name: -1.0)
    with pytest.raises(pytest.UsageError, match=">= 0"):
        watchdog.configured_base(config)


def _run_hanging_session(
    tmp_path: Path, *args: str, timeout: float = 25
) -> tuple[int, str, float]:
    project = tmp_path / "project"
    project.mkdir()
    (project / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (project / "conftest.py").write_text(_CONFTEST, encoding="utf-8")
    (project / "test_hang.py").write_text(_HANGING_TESTS, encoding="utf-8")
    log = tmp_path / "session.log"
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            [str(REPO_ROOT), os.environ.get("PYTHONPATH", "")]
        ),
    }
    env.pop(watchdog.HANG_TIMEOUT_ENV, None)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-c",
        str(project / "pytest.ini"),
        "--rootdir",
        str(project),
        "-p",
        "no:cacheprovider",
        "-p",
        "no:randomly",
        "-q",
        "--timeout=0",
        "--hang-timeout=2",
        *args,
        str(project),
    ]
    started = time.monotonic()
    # A file, not a pipe: a leaked grandchild holding a pipe would hang here.
    with log.open("wb") as handle:
        completed = subprocess.run(  # noqa: S603 - fixed interpreter and arguments
            command,
            cwd=project,
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    return (
        completed.returncode,
        log.read_text(encoding="utf-8", errors="replace"),
        (time.monotonic() - started),
    )


@pytest.mark.slow_ok  # Spawns a pytest session that must hang for the deadline.
def test_single_process_hang_dumps_stacks_and_exits(tmp_path):
    returncode, output, elapsed = _run_hanging_session(tmp_path, "-p", "no:xdist")
    assert returncode != 0
    assert "Timeout (0:00:02)!" in output
    assert "test_hangs" in output
    assert elapsed < 20


# Starts xdist workers and waits out the deadline twice, so it runs in the
# slow lane with a matching budget.
@pytest.mark.slow
@pytest.mark.slow_ok
@pytest.mark.timeout(120)
def test_xdist_hang_fails_the_session_even_after_a_rerun(tmp_path):
    returncode, output, _ = _run_hanging_session(
        tmp_path, "-n", "1", "--reruns=1", timeout=100
    )
    assert returncode == 1
    assert "hang watchdog: test_hang.py::test_hangs exceeded 2s" in output
    assert "Timeout (0:00:02)!" in output
    assert (
        "test_hangs" in output.split("hang watchdog: test exceeded hard deadline")[-1]
    )
