"""A per-test timeout stays a normal, named test failure (#1779)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from _pytest._code.code import Frame, TracebackEntry

from tests import pytest_crash_guard as guard

REPO_ROOT = Path(__file__).resolve().parents[2]

_GUARD_CONFTEST = """\
from tests import pytest_crash_guard


def pytest_configure(config):
    pytest_crash_guard.install(config)
"""

# Mimics the release-run failure: an old-style makereport hookwrapper (there,
# pytest-rerunfailures) re-raising the TypeError that pytest's traceback
# rendering hit, which xdist escalated to ``INTERNALERROR`` / exit 3.
_REPORT_CRASH_PLUGIN = """\
import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    if item.name == "test_boom" and call.when == "call":
        raise TypeError("unsupported operand type(s) for -: 'NoneType' and 'int'")
"""

_REPORT_CRASH_TESTS = """\
def test_boom():
    assert False, "the real failure"


def test_fine():
    assert True
"""

_BUSY_TESTS = """\
import time


def test_spins_past_the_timeout():
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        pass


def test_after_the_timeout():
    assert True
"""


def test_traceback_lineno_tolerates_a_missing_tb_lineno():
    assert guard.patch_traceback_linenos() is True
    frame = sys._getframe()
    entry = TracebackEntry(SimpleNamespace(tb_lineno=None, tb_frame=frame))
    assert entry.lineno == frame.f_lineno - 1
    real = TracebackEntry(SimpleNamespace(tb_lineno=42, tb_frame=frame))
    assert real.lineno == 41


def test_frame_lineno_tolerates_a_missing_f_lineno():
    assert guard.patch_traceback_linenos() is True
    code = test_frame_lineno_tolerates_a_missing_f_lineno.__code__
    frame = Frame(SimpleNamespace(f_lineno=None, f_code=code))
    assert frame.lineno == code.co_firstlineno - 1


def test_fallback_report_is_a_named_failure():
    item = SimpleNamespace(
        nodeid="tests/test_x.py::test_x",
        location=("tests/test_x.py", 3, "test_x"),
        keywords={"test_x": 1},
        user_properties=[],
    )
    excinfo = SimpleNamespace(exconly=lambda: "Failed: Timeout (>30.0s)")
    call = SimpleNamespace(
        excinfo=excinfo, when="call", duration=31.0, start=1.0, stop=32.0
    )
    report = guard.fallback_report(item, call, TypeError("boom"))
    assert report.failed
    assert report.nodeid == "tests/test_x.py::test_x"
    assert "Failed: Timeout (>30.0s)" in str(report.longrepr)
    assert "TypeError: boom" in str(report.longrepr)


def _run_session(
    tmp_path: Path,
    files: dict[str, str],
    *args: str,
    with_guard: bool = True,
) -> tuple[int, str]:
    project = tmp_path / ("guarded" if with_guard else "unguarded")
    project.mkdir()
    (project / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (project / "conftest.py").write_text(
        _GUARD_CONFTEST if with_guard else "", encoding="utf-8"
    )
    for name, content in files.items():
        (project / name).write_text(content, encoding="utf-8")
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            [str(project), str(REPO_ROOT), os.environ.get("PYTHONPATH", "")]
        ),
    }
    log = tmp_path / f"{project.name}.log"
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
        "-n",
        "1",
        "-rf",
        *args,
        str(project),
    ]
    # A file, not a pipe: a leaked grandchild holding a pipe would hang here.
    with log.open("wb") as handle:
        completed = subprocess.run(  # noqa: S603 - fixed interpreter and arguments
            command,
            cwd=project,
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            timeout=90,
            check=False,
        )
    return completed.returncode, log.read_text(encoding="utf-8", errors="replace")


# Each case starts one or two xdist sessions in a subprocess.
@pytest.mark.slow_ok
def test_unrenderable_report_fails_the_test_not_the_session(tmp_path):
    files = {
        "crash_plugin.py": _REPORT_CRASH_PLUGIN,
        "test_report.py": _REPORT_CRASH_TESTS,
    }
    returncode, output = _run_session(
        tmp_path, files, "-p", "crash_plugin", with_guard=False
    )
    assert returncode == pytest.ExitCode.INTERNAL_ERROR, output
    assert "INTERNALERROR" in output

    returncode, output = _run_session(tmp_path, files, "-p", "crash_plugin")
    assert returncode == pytest.ExitCode.TESTS_FAILED, output
    assert "INTERNALERROR" not in output
    assert "FAILED test_report.py::test_boom" in output
    assert "the real failure" in output
    assert "could not render this report" in output
    assert "1 failed, 1 passed" in output


@pytest.mark.slow_ok
def test_thread_method_timeout_fails_the_test_and_keeps_the_worker(tmp_path):
    returncode, output = _run_session(
        tmp_path,
        {"test_busy.py": _BUSY_TESTS},
        "--timeout=1",
        "--timeout-method=thread",
    )
    assert returncode == pytest.ExitCode.TESTS_FAILED, output
    assert "crashed" not in output
    assert "FAILED test_busy.py::test_spins_past_the_timeout" in output
    assert "Timeout (>1.0s) from pytest-timeout" in output
    assert "1 failed, 1 passed" in output
