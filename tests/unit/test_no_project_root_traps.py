"""Static lint: prevent the ``project_root='/tmp'`` / ``project_root=None`` test trap.

Background
----------
Five tests once silently took 9-37 seconds each because they passed
``project_root='/tmp'`` or ``project_root=None`` to ``ChangeImpactTool`` /
``_load_dependency_graph``. The mocks they had covered the gh CLI calls
but NOT the dependency-graph build, and:

- ``None`` falls back to ``'.'`` (current working directory) — when pytest
  runs from the repo root, that's the full 1100-file project. Each
  dependency-graph build scanned everything.
- ``'/tmp'`` is unpredictable. On the dev box it was empty; on CI
  boxes it can contain build artifacts and other agents' cache files
  that the project's gitignore-respecting walker still picks up.

Both make tests painfully slow AND non-deterministic (the wall time
depends on what's lying around in the cwd / /tmp).

This static test grep-scans the test tree and fails if either trap
appears in a new test. The fix at use site is always the same:
take the pytest ``tmp_path`` fixture and pass ``str(tmp_path)`` (or use
``monkeypatch.chdir(tmp_path)`` when you specifically need the
``None``-fallback path to land in an empty directory).

Companion safety net
--------------------
``tests/conftest.py::pytest_runtest_call`` enforces a per-test wall-time
budget (default 5s). Together these two checks would have caught both
of the 2026-05-23 regressions before commit:

- the static lint catches the typo at write time;
- the budget catches anything else (subprocess, sleep, real network).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TESTS_DIR = _REPO_ROOT / "tests"

# Patterns we reject anywhere under tests/. Both forms cause the same bug:
# expensive directory walks against an unrelated tree.
_TMP_PATTERN = re.compile(
    r"""project_root\s*=\s*['"]/tmp['"]""",
    re.IGNORECASE,
)
_NONE_PATTERN = re.compile(
    r"""project_root\s*=\s*None\b""",
)

# Only these tool/helper constructors build a graph against project_root —
# passing None or /tmp to anything else (FileOutputManager, formatter,
# tool registry, semantic_classify) is genuinely safe because they don't
# walk the filesystem. We narrow both lints to just the dangerous ones
# to avoid false positives that train people to ignore the message.
_GRAPH_BUILDERS_NEAR_NONE = re.compile(
    r"\b(ChangeImpactTool|"
    r"DependencyGraph|"
    r"CallGraph|"
    r"ProjectGraph|"
    r"ProjectHealthTool|"
    r"ChangeImpactRequest|"
    r"_load_dependency_graph|"
    r"_build_change_impact_result)\b",
)


def _iter_test_files() -> list[Path]:
    return sorted(p for p in _TESTS_DIR.rglob("*.py") if "__pycache__" not in p.parts)


def test_no_project_root_eq_tmp_in_tests() -> None:
    """Banner: ``project_root='/tmp'`` inside tests/ is a perf trap.

    Same narrowing as the None check — only flag when a graph-building
    name appears in a ±5-line window so we skip Mock fixture data and
    assert-called mock verifications (those don't actually scan anything).
    """
    bad: list[str] = []
    for path in _iter_test_files():
        # Skip THIS file — it documents the banned patterns by name.
        if path.samefile(Path(__file__)):
            continue
        # Skip conftest — its help text quotes the offending pattern.
        if path.name == "conftest.py":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        for lineno, line in enumerate(lines, start=1):
            if line.lstrip().startswith("#"):
                continue
            if not _TMP_PATTERN.search(line):
                continue
            # Skip mock assertions — they don't actually invoke the tool.
            if "assert_called" in line or "Mock" in line:
                continue
            # Honor escape hatch — e.g. test deliberately probes "/tmp".
            if "# allowed: tmp-string" in line:
                continue
            # Require a graph-building name nearby for it to be a real trap.
            window_start = max(0, lineno - 6)
            window_end = min(len(lines), lineno + 5)
            window = "\n".join(lines[window_start:window_end])
            if not _GRAPH_BUILDERS_NEAR_NONE.search(window):
                continue
            bad.append(f"{path.relative_to(_REPO_ROOT)}:{lineno}: {line.strip()}")

    if bad:
        offenders = "\n  ".join(bad)
        pytest.fail(
            "Found tests passing project_root='/tmp' to a graph-building tool.\n"
            "/tmp is non-deterministic — empty on a fresh dev box, full of\n"
            "build artifacts on CI — so the dependency-graph build silently\n"
            "scans whatever happens to be there (we've seen 22s on CI).\n"
            "Use the pytest tmp_path fixture instead:\n\n"
            "    def test_x(self, tmp_path):\n"
            "        tool = ChangeImpactTool(project_root=str(tmp_path))\n\n"
            f"Offenders:\n  {offenders}",
            pytrace=False,
        )


def test_no_project_root_eq_none_in_tests() -> None:
    """Banner: ``project_root=None`` in graph-building tools silently uses cwd.

    Only flags the constructors that actually walk the filesystem.
    Other tools (FileOutputManager, registry, SemanticClassifyTool) are
    None-safe and ignored here.
    """
    bad: list[str] = []
    for path in _iter_test_files():
        if path.samefile(Path(__file__)):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        for lineno, line in enumerate(lines, start=1):
            if line.lstrip().startswith("#"):
                continue
            if not _NONE_PATTERN.search(line):
                continue
            # Honor an explicit "# allowed: chdir(tmp_path)" escape.
            if "# allowed: chdir(tmp_path)" in line:
                continue
            # Only fail when a known graph-building name appears in a
            # ±5-line window around this line (call-site or constructor).
            window_start = max(0, lineno - 6)
            window_end = min(len(lines), lineno + 5)
            window = "\n".join(lines[window_start:window_end])
            if not _GRAPH_BUILDERS_NEAR_NONE.search(window):
                continue
            bad.append(f"{path.relative_to(_REPO_ROOT)}:{lineno}: {line.strip()}")

    if bad:
        offenders = "\n  ".join(bad)
        pytest.fail(
            "Found tests passing project_root=None to a tool that builds a\n"
            "DependencyGraph or CallGraph. None falls back to '.' (cwd) and\n"
            "silently scans the entire repo when pytest runs from the\n"
            "repo root — turning a unit test into a ~10s integration test.\n\n"
            "Two fixes:\n"
            "  (a) pass project_root=str(tmp_path)  — the usual answer\n"
            "  (b) if you specifically need to exercise the None-fallback\n"
            "      semantic, monkeypatch.chdir(tmp_path) FIRST, then add\n"
            "      '# allowed: chdir(tmp_path)' on the same line as None.\n\n"
            f"Offenders:\n  {offenders}",
            pytrace=False,
        )
