"""``precheck``: the CI checks a callers PR usually fails, run locally before pushing.

1. ``ruff check .`` (as CI) and ``ruff format --check`` on the changed files;
2. ``mypy`` on the changed ``tree_sitter_analyzer/`` files (CI runs mypy on the package);
3. the related tests -- changed test files plus ``tests/**/test_*<stem>*.py`` for each
   changed package module, plus ``--tests`` -- under coverage;
4. patch coverage of the changed package lines against the merge base with
   ``--base``, computed like Codecov (a partially covered branch line is not a
   hit). The target is Codecov's ``auto`` patch target: the base commit's
   project coverage from the Codecov API (``codecov.yml`` does not exist, so
   the default applies); ``--patch-target`` overrides it.

The tests here are a subset, so local patch coverage can only be lower than
CI's for the same tests run; a pass here is a strong but not a perfect proxy.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import gitutil

CODECOV_COMMIT = "https://api.codecov.io/api/v2/github/aimasteracc/repos/tree-sitter-analyzer/commits/{sha}/"
PACKAGE = "tree_sitter_analyzer"


def changed_files(head: Path, merge_base: str) -> list[str]:
    tracked = gitutil.git(
        head, "diff", "--name-only", "--diff-filter=ACMR", merge_base
    ).split()
    untracked = gitutil.git(head, "ls-files", "--others", "--exclude-standard").split()
    return sorted({p for p in tracked + untracked if (head / p).is_file()})


def changed_lines(head: Path, merge_base: str, files: list[str]) -> dict[str, set[int]]:
    """Added/changed line numbers (new side) per file, untracked files counted whole."""
    out: dict[str, set[int]] = {}
    untracked = set(
        gitutil.git(head, "ls-files", "--others", "--exclude-standard").split()
    )
    for rel in files:
        if rel in untracked:
            out[rel] = set(
                range(
                    1,
                    len(
                        (head / rel)
                        .read_text(encoding="utf-8", errors="replace")
                        .splitlines()
                    )
                    + 1,
                )
            )
            continue
        diff = gitutil.git(head, "diff", "-U0", merge_base, "--", rel)
        lines: set[int] = set()
        for m in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", diff, re.M):
            start, count = int(m.group(1)), int(m.group(2) or "1")
            lines.update(range(start, start + count))
        out[rel] = lines
    return out


def related_tests(head: Path, files: list[str]) -> list[str]:
    tests = {
        f
        for f in files
        if f.startswith("tests/")
        and Path(f).name.startswith("test_")
        and f.endswith(".py")
    }
    stems = {
        Path(f).stem
        for f in files
        if f.startswith(PACKAGE + "/")
        and f.endswith(".py")
        and Path(f).stem != "__init__"
    }
    if stems:
        all_tests = gitutil.git(head, "ls-files", "--", "tests/*test_*.py").split()
        for test in all_tests:
            name = Path(test).stem
            if any(
                re.search(rf"(^|_){re.escape(stem)}(_|$)", name[len("test_") :])
                for stem in stems
            ):
                tests.add(test)
    return sorted(tests)


def patch_coverage(
    cov: dict[str, Any], head: Path, lines: dict[str, set[int]]
) -> tuple[int, int, int, list[str]]:
    """(hits, misses, partials, uncovered 'file:line') over changed package lines."""
    by_file: dict[str, dict[str, Any]] = {}
    for path, data in cov.get("files", {}).items():
        measured = Path(path)
        if measured.is_absolute():
            measured = measured.resolve().relative_to(head)
        by_file[measured.as_posix()] = data
    hits = misses = partials = 0
    uncovered: list[str] = []
    for rel, changed in sorted(lines.items()):
        if not (rel.startswith(PACKAGE + "/") and rel.endswith(".py")):
            continue
        data = by_file.get(rel)
        if data is None:
            # never imported by the related tests: every statement line is a miss
            statements = _statement_lines(head / rel)
            for line in sorted(changed & statements):
                misses += 1
                uncovered.append(f"{rel}:{line}")
            continue
        executed = set(data.get("executed_lines", ()))
        missing = set(data.get("missing_lines", ()))
        partial_from = {int(a) for a, _b in data.get("missing_branches", ())}
        for line in sorted(changed):
            if line in missing:
                misses += 1
                uncovered.append(f"{rel}:{line}")
            elif line in executed:
                if line in partial_from:
                    partials += 1
                    uncovered.append(f"{rel}:{line} (partial)")
                else:
                    hits += 1
    return hits, misses, partials, uncovered


def _statement_lines(path: Path) -> set[int]:
    import ast

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError, UnicodeDecodeError):
        return set()
    return {node.lineno for node in ast.walk(tree) if isinstance(node, ast.stmt)}


def codecov_target(
    head: Path, merge_base: str, log: Callable[[str], None]
) -> float | None:
    """Project coverage of the nearest first-parent ancestor Codecov has (the auto patch target)."""
    commits = gitutil.git(
        head, "rev-list", "--first-parent", "-n", "15", merge_base
    ).split()
    for sha in commits:
        try:
            with urllib.request.urlopen(
                CODECOV_COMMIT.format(sha=sha), timeout=20
            ) as resp:  # noqa: S310 - fixed https host
                data = json.loads(resp.read().decode("utf-8"))
        except (OSError, ValueError) as exc:
            log(f"[precheck] codecov {sha[:10]}: {exc}")
            continue
        coverage = (data.get("totals") or {}).get("coverage")
        if isinstance(coverage, (int, float)):
            log(
                f"[precheck] patch target {coverage}% (Codecov project coverage at {sha[:10]})"
            )
            return float(coverage)
    return None


def _step(
    name: str,
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
    log: Callable[[str], None],
) -> tuple[bool, float]:
    started = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    secs = time.perf_counter() - started
    ok = proc.returncode == 0
    log(f"[precheck] {name}: {'ok' if ok else 'FAIL'} ({secs:.1f}s)")
    if not ok:
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-40:]
        for line in tail:
            print("    " + line)
    return ok, secs


def run(
    head: Path,
    python: Path,
    *,
    base: str,
    target: float | None,
    extra_tests: list[str],
    log: Callable[[str], None],
) -> int:
    started = time.perf_counter()
    merge_base = gitutil.git(head, "merge-base", base, "HEAD").strip()
    files = changed_files(head, merge_base)
    py_files = [f for f in files if f.endswith(".py")]
    log(
        f"[precheck] {len(files)} changed files vs {base} ({merge_base[:10]}), {len(py_files)} Python"
    )
    env = {**os.environ, "PYTHONPATH": str(head), "PYTHONUTF8": "1"}
    env.setdefault(
        "TSA_PYTEST_TEMP_ROOT", str(Path(tempfile.gettempdir()) / "tsa-precheck")
    )
    results: dict[str, bool] = {}
    results["ruff check"] = _step(
        "ruff check .", [str(python), "-m", "ruff", "check", "."], head, env, log
    )[0]
    if py_files:
        results["ruff format"] = _step(
            "ruff format --check",
            [str(python), "-m", "ruff", "format", "--check", *py_files],
            head,
            env,
            log,
        )[0]
    pkg = [f for f in py_files if f.startswith(PACKAGE + "/")]
    if pkg:
        results["mypy"] = _step(
            "mypy", [str(python), "-m", "mypy", *pkg], head, env, log
        )[0]
    tests = sorted(set(related_tests(head, files)) | set(extra_tests))
    lines = changed_lines(head, merge_base, files)
    if tests:
        cov_json = Path(tempfile.mkdtemp(prefix="tsa-precheck-")) / "coverage.json"
        log(f"[precheck] related tests: {len(tests)} files")
        cmd = [
            str(python),
            "-m",
            "pytest",
            "-q",
            "-o",
            "asyncio_default_fixture_loop_scope=function",
            "-p",
            "no:cacheprovider",
            f"--cov={PACKAGE}",
            "--cov-branch",
            f"--cov-report=json:{cov_json}",
            *tests,
        ]
        results["tests"] = _step("pytest (related)", cmd, head, env, log)[0]
        if cov_json.is_file():
            cov = json.loads(cov_json.read_text(encoding="utf-8"))
            results["patch coverage"] = _judge_patch(
                cov,
                head,
                lines,
                target if target is not None else codecov_target(head, merge_base, log),
                log,
            )
        elif any(f.startswith(PACKAGE + "/") for f in lines):
            log("[precheck] patch coverage: FAIL (no coverage data)")
            results["patch coverage"] = False
    elif any(f.startswith(PACKAGE + "/") and f.endswith(".py") for f in lines):
        log(
            "[precheck] patch coverage: FAIL (package code changed but no related tests found; pass --tests)"
        )
        results["patch coverage"] = False
    failed = [k for k, ok in results.items() if not ok]
    log(
        f"[precheck] {'PASS' if not failed else 'FAIL: ' + ', '.join(failed)} in {time.perf_counter() - started:.0f}s"
    )
    return 1 if failed else 0


def _judge_patch(
    cov: dict[str, Any],
    head: Path,
    lines: dict[str, set[int]],
    target: float | None,
    log: Callable[[str], None],
) -> bool:
    hits, misses, partials, uncovered = patch_coverage(cov, head, lines)
    total = hits + misses + partials
    if total == 0:
        log("[precheck] patch coverage: no coverable changed package lines")
        return True
    pct = 100.0 * hits / total
    if target is None:
        log(
            f"[precheck] patch coverage {pct:.2f}% ({hits}/{total}); no target (Codecov unreachable): FAIL, pass --patch-target"
        )
        return False
    ok = pct >= target
    log(
        f"[precheck] patch coverage {pct:.2f}% ({hits} hit, {misses} miss, {partials} partial) vs target {target:.2f}%: {'ok' if ok else 'FAIL'}"
    )
    for item in uncovered[:30]:
        print("    uncovered " + item)
    return ok
