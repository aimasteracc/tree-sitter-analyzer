"""P1 edit-safe causal-envelope completion contract."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_causal_envelope_dogfood_needs_one_analyzer_call(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text("def answer():\n    return 42\n", encoding="utf-8")
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
    assert report["missing_fields"] == []
