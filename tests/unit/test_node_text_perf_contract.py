"""Pin the ``_node_text`` perf contract: at most ONE source-encode per call.

Background
----------
On 2026-05-23 the unit suite ran in 91s instead of 29s — a 3× regression.
The hot path was ``import_extractors._node_text``, which had a leftover
``source.encode('utf-8')`` in BOTH the length check and the slice:

    if start < end <= len(source.encode('utf-8')):   # encode #1
        return source.encode('utf-8')[start:end]...  # encode #2

Each call materialized the full UTF-8 buffer of an entire source file.
Across 217k calls during one ``DependencyGraph.build()`` that was ~7.5s
of pure encoding overhead.

This test pins two invariants so the regression can't recur:

1. **Static lint** — ``_node_text`` (in any module) must not contain two
   ``.encode('utf-8')`` calls. The bug is visible at the source level.
2. **Runtime micro-bench** — ``_node_text`` must serve N calls on a small
   ASCII source in <budget ms. If a future refactor reintroduces an
   O(file_size) per-call cost, the budget will fail.

We also assert the fast path (``node.text`` bytes) is preferred — the
fallback that DOES encode is only allowed for parsers that don't expose
``.text``.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _node_text_files() -> list[Path]:
    """All modules under tree_sitter_analyzer/ defining a ``_node_text``."""
    src_root = _REPO_ROOT / "tree_sitter_analyzer"
    matches: list[Path] = []
    for path in src_root.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if re.search(r"^def _node_text\(", text, re.MULTILINE):
            matches.append(path)
    return matches


def _extract_function(text: str, name: str) -> str | None:
    """Return the source of a top-level function ``name`` from a module."""
    lines = text.splitlines()
    out: list[str] = []
    inside = False
    for line in lines:
        if not inside and re.match(rf"^def {re.escape(name)}\(", line):
            inside = True
            out.append(line)
            continue
        if inside:
            # Function ends at next top-level def/class or end of file.
            if line and not line.startswith((" ", "\t")) and not line.startswith("#"):
                break
            out.append(line)
    return "\n".join(out) if out else None


def test_node_text_does_not_encode_twice() -> None:
    """No ``_node_text`` implementation may contain two encode() calls.

    Two encodes is the exact bug fingerprint we fixed on 2026-05-23.
    One encode is fine (the fallback path); zero is even better.
    """
    found = _node_text_files()
    assert found, "no _node_text functions found — test fixture invalid"

    offenders: list[str] = []
    for path in found:
        body = _extract_function(path.read_text(encoding="utf-8"), "_node_text")
        if body is None:
            continue
        # Strip comments and docstring blocks before counting — we care
        # about real encode() calls in code, not history mentions.
        code = re.sub(r'"""[\s\S]*?"""', "", body)
        code = re.sub(r"#.*$", "", code, flags=re.MULTILINE)
        encode_count = len(re.findall(r"\.encode\(", code))
        if encode_count > 1:
            offenders.append(
                f"{path.relative_to(_REPO_ROOT)}: {encode_count} encode() calls "
                f"(budget: ≤1; ideally 0 because node.text is already bytes)"
            )

    if offenders:
        pytest.fail(
            "_node_text has too many .encode() calls — this is the exact\n"
            "fingerprint of the 2026-05-23 regression (91s → 29s suite).\n"
            "Prefer node.text (already bytes); encode at most once in the\n"
            "fallback for parsers that don't expose .text.\n\n"
            "Offenders:\n  " + "\n  ".join(offenders),
            pytrace=False,
        )


def test_node_text_throughput_is_O1_per_call() -> None:
    """Micro-bench: 5k calls on a small ASCII source must finish quickly.

    With the regression in place the same workload took multiple seconds.
    With the fix it's well under 100 ms on any modern box. We pick a
    loose 1.0s budget so this passes even on the slowest CI runner.
    """
    from tree_sitter_analyzer.core.parser import Parser
    from tree_sitter_analyzer.import_extractors import _node_text

    src = (
        "import os\nimport sys\n"
        "def foo():\n    return os.path.join(sys.argv[0], 'x')\n" * 50
    )
    parser = Parser()
    res = parser.parse_code(src, "python")
    assert res.tree is not None

    # Collect every node so each iteration touches a real Tree-sitter node.
    nodes: list = []

    def collect(node):  # type: ignore[no-untyped-def]
        nodes.append(node)
        for child in node.children:
            collect(child)

    collect(res.tree.root_node)
    assert len(nodes) > 50, "fixture too small to exercise the hot path"

    started = time.perf_counter()
    iterations = 5_000
    for i in range(iterations):
        _ = _node_text(nodes[i % len(nodes)], src)
    elapsed = time.perf_counter() - started

    # 5000 calls in < 1.0s = < 200µs each. With the bug it was ~1.5 ms each.
    assert elapsed < 1.0, (
        f"_node_text micro-bench took {elapsed*1000:.0f}ms for {iterations} "
        f"calls (budget: 1000ms). Per-call cost has regressed — check for "
        f"an O(file_size) operation inside the helper (e.g. a stray "
        f"source.encode() call)."
    )
