"""Subprocess entry points, run under the gate interpreter with ``-s -P``.

``python -s -P _boot.py server <pkg_dir> <project_root>``
    Start the MCP stdio server of the analyzer found on ``PYTHONPATH``.
``python -s -P _boot.py index <pkg_dir> <project_root> <out.json> <excluded.json>``
    Build the index in-process and audit which analyzer modules the build loaded.

Both refuse to start unless ``tree_sitter_analyzer`` resolves to ``<pkg_dir>``:
an editable install or a stray ``sys.path`` entry must never answer for the
code under test. Stdlib only at import time.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

WRONG_PACKAGE = 3
EXCLUSION_VIOLATED = 4
INDEX_FAILED = 5


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
    result = asyncio.run(CodeGraphFullIndexTool(root).execute({"mode": "full"}))
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
    }
    Path(out).write_text(json.dumps(summary, indent=1), encoding="utf-8")
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
