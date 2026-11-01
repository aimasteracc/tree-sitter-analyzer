"""RFC-0042 P1: the loader thread never imports a module for the first time.

Python's per-module import locks raise ``_DeadlockError`` when two threads import
modules of one import cycle at the same moment. CI hit it (run 41338978132):
``tools/list`` on the event loop and the loader thread both imported the cache
stack, and ``tools/list`` failed with "deadlock detected by
_ModuleLock('tree_sitter_analyzer.cache.generation_routing')". The fix makes the
loader thread import nothing: ``loader.start`` imports its dependencies on the
calling thread (the server's event-loop thread, which also runs every request)
before the thread starts. A thread that takes no module lock cannot be part of
a lock cycle, whatever the request path imports.

The race itself is timing-dependent; this test checks the property that rules
it out, deterministically. A fresh interpreter in the state of a server at
``notifications/initialized`` (only ``tree_sitter_analyzer.mcp.server``
imported) records every module whose import starts in the loader thread
(``sys.meta_path`` is consulted only for modules not yet in ``sys.modules``),
across a real load of a Python + TypeScript index, a lease renewal and a root
without an index. Before the fix it recorded about 300 modules, 227 of them in
this package.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

import tree_sitter_analyzer

_AN_HOUR_NS = 3600 * 1_000_000_000
_SOURCES = {
    "pkg/__init__.py": "from .helper import helper\n",
    "pkg/helper.py": "def helper():\n    return 3\n\n\ndef top():\n    return helper()\n",
    "web/util.ts": (
        "export function slug(s: string): string {\n  return s.trim();\n}\n\n"
        "export function title(s: string): string {\n  return slug(s);\n}\n"
    ),
}

_PROBE = textwrap.dedent(
    """
    import json, sys, threading, time

    import tree_sitter_analyzer.mcp.server  # the server's state at `initialized`

    seen = []

    class Recorder:
        def find_spec(self, fullname, path=None, target=None):
            seen.append((threading.current_thread().name, fullname))
            return None

    sys.meta_path.insert(0, Recorder())
    from tree_sitter_analyzer import call_graph_warm, index_snapshot
    from tree_sitter_analyzer.resident import loader

    index_snapshot._TTL_SECONDS = 1.5  # let a renewal (P1b) run if present
    loader.RENEW_MARGIN_SECONDS = 0.5
    loader.MIN_RENEW_SECONDS = 0.2
    call_graph_warm.enable()
    loader.enable()
    indexed, bare = sys.argv[1], sys.argv[2]
    loader.start(indexed)
    loader.start(bare)
    loader.wait(timeout=120)
    time.sleep(2.0)
    print(json.dumps({
        "imports": sorted({m for t, m in seen if t == loader.THREAD_NAME}),
        "indexed": loader.status(indexed),
        "bare": loader.status(bare),
    }, default=str))
    loader.shutdown(timeout=10)
    """
)


async def _index(root: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    result = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert result["published"] is True


@pytest.mark.asyncio
async def test_the_loader_thread_imports_nothing(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    for rel, text in _SOURCES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    stamp = time.time_ns() - _AN_HOUR_NS
    for path in [*root.rglob("*.*"), root / "pkg", root / "web", root]:
        os.utime(path, ns=(stamp, stamp))
    await _index(root)
    bare = tmp_path / "bare"
    bare.mkdir()

    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(tree_sitter_analyzer.__file__).resolve().parents[1])
    env.pop("TSA_RESIDENT", None)
    env.pop("TSA_GRAPH_WARM", None)
    done = subprocess.run(
        [sys.executable, "-c", _PROBE, str(root), str(bare)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        env=env,
        cwd=str(tmp_path),
    )
    assert done.returncode == 0, done.stderr[-3000:]
    report = json.loads(done.stdout.strip().splitlines()[-1])
    assert report["indexed"]["state"] == "ready", report["indexed"]
    assert report["indexed"]["certified"] is None, report["indexed"]
    assert report["bare"]["state"] == "skipped", report["bare"]
    assert report["imports"] == [], (
        "the loader thread imported modules for the first time; add them to "
        "tree_sitter_analyzer.resident.loader._DEPENDENCIES"
    )
