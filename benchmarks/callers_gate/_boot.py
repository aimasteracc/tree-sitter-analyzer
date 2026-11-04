"""Subprocess entry points, run under the gate interpreter with ``-s -P``.

``python -s -P _boot.py server <pkg_dir> <project_root>``
    Start the MCP stdio server of the analyzer found on ``PYTHONPATH``.
``python -s -P _boot.py index <pkg_dir> <project_root> <out.json> <excluded.json>``
    Build the index in-process and audit which analyzer modules the build loaded.

Both refuse to start unless ``tree_sitter_analyzer`` resolves to ``<pkg_dir>``:
an editable install or a stray ``sys.path`` entry must never answer for the
code under test. Stdlib only at import time.

The import audit can only see this process. The gate therefore builds with
``TSA_INDEX_WORKERS=1`` (no spawn pool), and :func:`forbid_child_processes`
refuses any multiprocessing child or Python subprocess during the build: a
child's imports would escape the audit.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import multiprocessing.process
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

WRONG_PACKAGE = 3
EXCLUSION_VIOLATED = 4
INDEX_FAILED = 5
CHILD_PROCESS = 6
_PYTHON_STEMS = ("python", "pythonw", "py")


class ChildProcessForbidden(RuntimeError):
    """A child interpreter started during the audited index build."""


def _launches_python(args: Any, kwargs: dict[str, Any]) -> bool:
    exe = kwargs.get("executable")
    first: Any = exe
    if first is None:
        if isinstance(args, (str, bytes)):
            first = os.fsdecode(args).split()[0] if args.strip() else ""
        elif args:
            first = list(args)[0]
    name = Path(os.fsdecode(first)).name.lower() if first else ""
    stem = name[:-4] if name.endswith(".exe") else name
    same = bool(first) and os.path.normcase(os.fsdecode(first)) == os.path.normcase(
        sys.executable
    )
    return same or stem in _PYTHON_STEMS or stem.startswith("python3")


@contextlib.contextmanager
def forbid_child_processes() -> Iterator[list[str]]:
    """Refuse every multiprocessing child and Python subprocess while active.

    Yields the list of refused launches (each is also raised as
    :class:`ChildProcessForbidden` at the launch site, so a caller that
    swallows the error is still caught through the list).
    """
    started: list[str] = []
    base = multiprocessing.process.BaseProcess
    original_start = base.start
    original_init = subprocess.Popen.__init__

    def guarded_start(self: Any) -> None:
        started.append(f"multiprocessing:{type(self).__name__}")
        raise ChildProcessForbidden("the index build started a multiprocessing child")

    def guarded_init(self: Any, args: Any, *rest: Any, **kwargs: Any) -> None:
        if _launches_python(args, kwargs):
            started.append(f"subprocess:{args!r}"[:200])
            self._child_created = False  # Popen.__del__ reads it
            raise ChildProcessForbidden(f"the index build started {args!r}")
        original_init(self, args, *rest, **kwargs)

    base.start = guarded_start  # type: ignore[method-assign]
    subprocess.Popen.__init__ = guarded_init  # type: ignore[method-assign]
    try:
        yield started
    finally:
        base.start = original_start  # type: ignore[method-assign]
        subprocess.Popen.__init__ = original_init  # type: ignore[method-assign]


def _check_package(expected: str) -> None:
    import tree_sitter_analyzer

    actual = Path(tree_sitter_analyzer.__file__).resolve().parent
    if os.path.normcase(str(actual)) != os.path.normcase(str(Path(expected).resolve())):
        print(
            f"CALLERS_GATE_WRONG_PACKAGE {actual} != {expected}",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(WRONG_PACKAGE)
    print(f"CALLERS_GATE_PACKAGE {actual}", file=sys.stderr, flush=True)


def _server(pkg_dir: str, root: str) -> None:
    _check_package(pkg_dir)
    from tree_sitter_analyzer.mcp.server import main_sync

    sys.argv = [sys.argv[0], "--project-root", root]
    main_sync()


def _index(pkg_dir: str, root: str, out: str, excluded_file: str) -> None:
    _check_package(pkg_dir)
    excluded = set(json.loads(Path(excluded_file).read_text(encoding="utf-8")))
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    started = time.perf_counter()
    result: dict[str, Any] = {}
    with forbid_child_processes() as children:
        try:
            result = asyncio.run(CodeGraphFullIndexTool(root).execute({"mode": "full"}))
        except ChildProcessForbidden:
            pass  # recorded in ``children``; exits CHILD_PROCESS below
    seconds = time.perf_counter() - started
    loaded = sorted(
        name for name in sys.modules if name.startswith("tree_sitter_analyzer")
    )
    violations = sorted(excluded.intersection(loaded))
    summary = {
        "success": bool(result.get("success")),
        "verdict": result.get("verdict"),
        "summary_line": result.get("summary_line"),
        "seconds": round(seconds, 2),
        "loaded_modules": len(loaded),
        "excluded_loaded": violations,
        "child_processes": children,
        "workers_env": os.environ.get("TSA_INDEX_WORKERS"),
    }
    Path(out).write_text(json.dumps(summary, indent=1), encoding="utf-8")
    if children:
        sys.exit(CHILD_PROCESS)
    if violations:
        sys.exit(EXCLUSION_VIOLATED)
    if not summary["success"]:
        sys.exit(INDEX_FAILED)


def main() -> None:
    mode = sys.argv[1]
    if mode == "server":
        _server(sys.argv[2], sys.argv[3])
    elif mode == "index":
        _index(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
    else:
        raise SystemExit(f"unknown mode {mode!r}")


if __name__ == "__main__":
    main()
