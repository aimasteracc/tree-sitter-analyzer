"""Fresh-exec dispatcher contracts for RFC-0022 strace controls."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTROL = ROOT / "scripts/rfc0022_strace_positive_control.py"


@pytest.mark.parametrize(
    "control",
    [
        "absolute-write",
        "clean",
        "create-unlink",
        "descendant-create-unlink",
        pytest.param(
            "inherited-fd",
            marks=pytest.mark.skipif(
                os.name == "nt",
                reason="tracked: RFC-0022 Linux authority pass_fds is POSIX-only",
            ),
        ),
        "mkdir-rmdir",
        "rename-restore",
        "shared-writable-mmap",
        "sqlite-sidecar",
        "truncate-restore",
        "write-then-delete",
    ],
)
def test_positive_control_dispatcher_is_fresh_exec_and_deterministic(
    tmp_path: Path, control: str
) -> None:
    root = tmp_path / control
    root.mkdir()
    (root / "fixture.txt").write_bytes(b"fixture\n")
    command = [sys.executable, str(CONTROL), control, "--root", str(root)]
    if control == "absolute-write":
        command.extend(["--absolute-target", str(root / "absolute-created.txt")])
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert (
        result.stdout
        == json.dumps({"control": control, "status": "completed"}, sort_keys=True)
        + "\n"
    )
