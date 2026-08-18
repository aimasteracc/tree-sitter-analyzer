"""P1 edit-safe causal-envelope completion contract."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.slow_ok  # indexes a real fixture and captures a certified snapshot
@pytest.mark.skipif(
    not sys.platform.startswith("linux") or not os.path.exists("/dev/fd"),
    reason="tracked: RFC-0025 P1 read_existing authority is Linux-only",
)
def test_causal_envelope_dogfood_needs_one_analyzer_call(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text("def answer():\n    return 42\n", encoding="utf-8")
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.index_snapshot import stamp_full_index_manifest

    cache = ASTCache(str(tmp_path))
    cache.index_project(max_files=20)
    stamp_full_index_manifest(cache.get_conn(), str(tmp_path))
    cache.close()
    script = Path("scripts/check_causal_envelope.py").resolve()

    completed = subprocess.run(  # nosec B603 — fixed interpreter/script argv
        [
            sys.executable,
            str(script),
            "app.py",
            "--project-root",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["success"] is True
    assert report["analyzer_calls"] == 1
    assert report["separate_causality_queries"] == 0
    assert report["certified_snapshot"] is True
    assert report["missing_fields"] == []
