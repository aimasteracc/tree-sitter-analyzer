#!/usr/bin/env python3
"""Subprocess runner for the mutation probe (RFC-0029).

Runs a single pytest test node in an isolated subprocess, optionally with
a mutated module served via a ``sys.meta_path`` finder injected through a
bootstrap script.  Never writes mutated bytes to the working tree.

Subprocess invocation (RFC §"Isolating the run"):
    uv run python <bootstrap> <node_id>
        --override-ini="addopts=--strict-markers --timeout=60"
        -p no:cacheprovider
        --tb=short -q

The ``--override-ini`` drops xdist, reruns, and the default marker filter in
one move.  ``-p no:cacheprovider`` keeps the run from writing ``.pytest_cache``.
``-p no:randomly`` is NOT used — ``pytest_randomly`` is not installed in this
repo, so the flag would be a silent no-op (RFC §"Isolating the run").
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time

from .types import FailureKind

# Bootstrap template injected into the child process.  Environment variables
# carry the module name and path to the mutated bytes file; sys.argv[1:]
# carries the pytest arguments.
_BOOTSTRAP = """\
import sys
import os
import importlib.abc
import importlib.machinery

_module_name = os.environ["_MUTATION_MODULE"]
_bytes_path = os.environ["_MUTATION_BYTES_FILE"]

with open(_bytes_path, "rb") as _fh:
    _mutated_bytes = _fh.read()


class _MutationFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname != _module_name:
            return None
        return importlib.machinery.ModuleSpec(fullname, _MutationLoader())


class _MutationLoader(importlib.abc.Loader):
    def create_module(self, spec):
        return None  # use default creation semantics

    def exec_module(self, module):
        # Preserve __package__ so relative imports resolve normally.
        parts = _module_name.rsplit(".", 1)
        module.__package__ = parts[0] if len(parts) > 1 else ""
        code = compile(
            _mutated_bytes,
            "<mutation:" + _module_name + ">",
            "exec",
        )
        exec(code, module.__dict__)  # noqa: S102


sys.meta_path.insert(0, _MutationFinder())

import pytest
sys.exit(pytest.main(sys.argv[1:]))
"""

# pytest exit codes
_PYTEST_OK = 0  # all tests passed
_PYTEST_TESTS_FAILED = 1  # at least one test failed
_PYTEST_INTERNAL_ERROR = 2  # collection/internal error
_PYTEST_NO_TESTS_RAN = 4  # no tests collected (empty run)
_PYTEST_NO_TESTS_FOUND = 5  # no tests matching node id

# Assertion-derived exception names that signal a real detection.
# pytest.fail() raises _pytest.outcomes.Failed, displayed as "Failed".
# Rewritten assert → AssertionError.
_ASSERTION_EXC_NAMES: frozenset[str] = frozenset({"AssertionError", "Failed"})

# Timeout sentinel returned as the ``output`` string.
_TIMEOUT_SENTINEL = "__TIMEOUT__"


def run_test(
    node_id: str,
    project_root: str,
    timeout_s: float = 60.0,
    mutated_module: str | None = None,
    mutated_bytes: bytes | None = None,
) -> tuple[FailureKind, float, str]:
    """Run *node_id* under pytest in a subprocess.

    Parameters
    ----------
    node_id:
        Fully-qualified pytest node id, e.g. ``tests/unit/foo.py::test_bar``.
    project_root:
        Absolute or relative path to the project root (cwd for the subprocess).
    timeout_s:
        Wall-clock budget in seconds.  Returns ``("NOT_RUN", budget*1000,
        _TIMEOUT_SENTINEL)`` on expiry.
    mutated_module:
        Fully-qualified Python module name to intercept, e.g.
        ``tree_sitter_analyzer.import_graph``.  ``None`` for baseline run.
    mutated_bytes:
        Mutated source bytes to serve via ``sys.meta_path``.
        ``None`` for baseline run.

    Returns
    -------
    tuple of (FailureKind, elapsed_ms, raw_output)
    """
    cwd = os.path.abspath(project_root)

    if mutated_bytes is not None and mutated_module is not None:
        return _run_mutated(node_id, cwd, timeout_s, mutated_module, mutated_bytes)
    return _run_plain(node_id, cwd, timeout_s)


def _pytest_args(node_id: str) -> list[str]:
    # "--" separates pytest options from file/node-id args so a node_id that
    # begins with "-" cannot be misinterpreted as a pytest flag (HIGH #2).
    return [
        "--override-ini=addopts=--strict-markers --timeout=60",
        "-p",
        "no:cacheprovider",
        "--tb=short",
        "-q",
        "--",
        node_id,
    ]


def _run_plain(
    node_id: str, cwd: str, timeout_s: float
) -> tuple[FailureKind, float, str]:
    cmd = ["uv", "run", "pytest"] + _pytest_args(node_id)
    return _execute(cmd, cwd, timeout_s, env=None)


def _run_mutated(
    node_id: str,
    cwd: str,
    timeout_s: float,
    module_name: str,
    mutated_bytes: bytes,
) -> tuple[FailureKind, float, str]:
    tmpdir = tempfile.mkdtemp(prefix="tsa_mutprobe_")
    try:
        bootstrap_path = os.path.join(tmpdir, "bootstrap.py")
        bytes_path = os.path.join(tmpdir, "mutated_src.py")

        with open(bootstrap_path, "w", encoding="utf-8") as fh:
            fh.write(_BOOTSTRAP)
        with open(bytes_path, "wb") as fh:
            fh.write(mutated_bytes)

        env = dict(os.environ)
        env["_MUTATION_MODULE"] = module_name
        env["_MUTATION_BYTES_FILE"] = bytes_path

        cmd = ["uv", "run", "python", bootstrap_path] + _pytest_args(node_id)
        return _execute(cmd, cwd, timeout_s, env=env)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _execute(
    cmd: list[str],
    cwd: str,
    timeout_s: float,
    env: dict[str, str] | None,
) -> tuple[FailureKind, float, str]:
    start = time.perf_counter()
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        output = (result.stdout or "") + (result.stderr or "")
        kind = _classify(result.returncode, output)
        return kind, elapsed_ms, output
    except subprocess.TimeoutExpired:
        elapsed_ms = timeout_s * 1000.0
        return "NOT_RUN", elapsed_ms, _TIMEOUT_SENTINEL
    except FileNotFoundError:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return "NOT_RUN", elapsed_ms, "uv not found"


def _classify(returncode: int, output: str) -> FailureKind:
    """Map pytest's exit code + output to a FailureKind."""
    if returncode == _PYTEST_OK:
        return "NONE"

    # No tests ran / no tests found / deselected by marker filter.
    if returncode in (_PYTEST_NO_TESTS_RAN, _PYTEST_NO_TESTS_FOUND):
        return "NOT_RUN"

    lower = output.lower()
    if (
        "no tests ran" in lower
        or "collected 0 items" in lower
        or "no tests were selected" in lower
    ):
        return "NOT_RUN"

    # Exit code 2 = internal error / collection error (e.g. SyntaxError at
    # import time). Treat as a non-assertion crash.
    if returncode == _PYTEST_INTERNAL_ERROR:
        return "NON_ASSERTION"

    # Exit code 1: tests ran and at least one failed. Discriminate by
    # exception type from the --tb=short output.
    return _parse_exception_type(output)


def _parse_exception_type(output: str) -> FailureKind:
    """Determine whether pytest failures are assertion-derived.

    pytest's ``--tb=short`` format includes "E   ExceptionType: message"
    lines inside failure blocks.  We look for the first such line and check
    whether the exception type is assertion-derived.

    ``constrains`` is only returned when the failure is ASSERTION.  A crash
    (ImportError, AttributeError, …) returns NON_ASSERTION so the caller
    can emit ``unknown / MUTATED_RUN_CRASHED`` — a crash is not detection.
    """
    for line in output.splitlines():
        stripped = line.strip()
        # Short-tb format: "E   ExcType: ..." or "E   ExcType"
        if not (stripped.startswith("E ") or stripped.startswith("E\t")):
            continue
        exc_part = stripped[1:].strip()
        if not exc_part:
            continue
        # Extract the exception class name (before ":" or space).
        exc_name = exc_part.split(":")[0].split()[0].strip()
        if not exc_name:
            continue
        if exc_name in _ASSERTION_EXC_NAMES:
            return "ASSERTION"
        # pytest assertion rewriting emits "E   assert X == Y" (lowercase).
        # This is still an AssertionError — treat it as assertion-derived.
        if exc_name == "assert":
            return "ASSERTION"
        # Any capitalized identifier is a Python exception class name.
        if exc_name[0].isupper() and exc_name.isidentifier():
            return "NON_ASSERTION"

    # Fallback: FAILED in output but no parseable exception line.
    # Be conservative: treat as NON_ASSERTION (→ unknown) rather than risking
    # a false-constrains verdict.
    if "FAILED" in output or "failed" in output.lower():
        return "NON_ASSERTION"
    return "NOT_RUN"


def is_timeout(output: str) -> bool:
    """True when the run sentinel indicates a timeout."""
    return output == _TIMEOUT_SENTINEL
