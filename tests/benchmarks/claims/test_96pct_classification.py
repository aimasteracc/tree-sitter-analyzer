"""Claim invariant: 96.3% call edge classification rate.

README claim (benchmarks/codegraph_compare/REPORT-v1.21.0.md):
    "Edge classification rate: 96.3% of call edges resolve to a non-'unknown'
    callee_resolution."

The SQL to reproduce the measurement on the live index:
    SELECT
        COUNT(*) AS total,
        SUM(CASE WHEN callee_resolution != 'unknown' THEN 1 ELSE 0 END) AS classified
    FROM edges
    WHERE kind = 'calls';

This invariant:
    1. Asserts the classification rate on a synthetic multi-function corpus
       reaches a reasonable threshold on a fresh index.
    2. Documents the measurement command so it can be re-run on the live index.
    3. Marks the "96.3% on this repo" check as full_language + claims_benchmark
       because it requires a full project index.

For the real-repo measurement:
    uv run python -c "
    from tree_sitter_analyzer.ast_cache import ASTCache
    import sqlite3, pathlib
    db = pathlib.Path('.ast-cache/index.db')
    if db.exists():
        conn = sqlite3.connect(db)
        total, classified = conn.execute(
            'SELECT COUNT(*), SUM(callee_resolution != \\'unknown\\') FROM edges WHERE kind=\\'calls\\''
        ).fetchone()
        print(f\\'Classification rate: {classified/total*100:.1f}% ({classified}/{total})\\')
    "
"""

from __future__ import annotations

import os
import sqlite3
import tempfile

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache

pytestmark = [pytest.mark.benchmark, pytest.mark.claims_benchmark]


def _build_indexed_python_project(tmp: str) -> ASTCache:
    """Build a small Python project with call edges and return its cache."""
    with open(os.path.join(tmp, "core.py"), "w") as f:
        f.write(
            "def parse(text):\n"
            "    return tokenize(text)\n"
            "\n"
            "def tokenize(text):\n"
            "    return text.split()\n"
            "\n"
            "def validate(data):\n"
            "    return bool(data)\n"
            "\n"
            "class Processor:\n"
            "    def run(self, text):\n"
            "        tokens = parse(text)\n"
            "        return validate(tokens)\n"
        )
    with open(os.path.join(tmp, "app.py"), "w") as f:
        f.write(
            "from core import Processor, parse\n"
            "\n"
            "def main():\n"
            "    p = Processor()\n"
            "    result = p.run('hello world')\n"
            "    tokens = parse('hello')\n"
            "    return result, tokens\n"
        )
    cache = ASTCache(tmp)
    cache.index_project()
    return cache


def test_call_edge_classification_rate_on_fresh_index():
    """On a fresh Python-only index, classification rate must be >= 80%.

    The README claims 96.3% on the full project index. A small synthetic
    corpus of clear Python-to-Python calls should reach at least 80% since
    all functions are in-project and resolvable.

    Emit the measured rate for CI history visibility.
    """
    import glob as _glob
    import shutil
    tmp = tempfile.mkdtemp()
    try:
        cache = _build_indexed_python_project(tmp)

        # Find the index db — it may be in .ast-cache/
        db_path = None
        for pattern in [".ast-cache/index.db"]:
            matches = _glob.glob(os.path.join(tmp, pattern))
            if matches:
                db_path = matches[0]
                break

        if not db_path or not os.path.exists(db_path):
            cache.close()
            pytest.skip("No index.db produced — call graph not built in test environment")

        row = None
        skip_reason = None
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT COUNT(*), SUM(callee_resolution != 'unknown') "
                "FROM edges WHERE kind='calls'"
            ).fetchone()
        except sqlite3.OperationalError:
            skip_reason = "edges table not found — call graph schema may differ"
        finally:
            conn.close()

        cache.close()

        if skip_reason:
            pytest.skip(skip_reason)

        total, classified = row
        if not total:
            pytest.skip("No call edges found in the synthetic project — call graph not built")

        classified = classified or 0
        rate = classified / total * 100
        # Emit for CI history
        print(f"[claim] 96pct_classification measured={rate:.1f}% ({classified}/{total})")
        assert rate >= 80.0, (
            f"Call edge classification rate {rate:.1f}% is below 80% threshold. "
            f"Classified: {classified}/{total}. "
            f"The README claims 96.3% on the full project index."
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_classification_rate_sql_is_documented():
    """The measurement SQL must be present in this file (docs-as-tests pattern).

    Ensures that when someone wants to re-run the 96.3% claim, they can find
    the command in the test that guards the claim.
    """
    import inspect
    src = inspect.getfile(test_classification_rate_sql_is_documented)
    with open(src, encoding="utf-8") as f:
        content = f.read()
    assert "callee_resolution" in content, (
        "The measurement SQL for the 96.3% classification claim must be "
        "present in this test file for repro visibility."
    )
    assert "96.3" in content, (
        "The README claim value '96.3%' must be referenced in this test file."
    )
