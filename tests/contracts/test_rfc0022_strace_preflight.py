"""Pinned runtime and binary provenance contracts for RFC-0022 strace."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import rfc0022_strace_authority as authority  # noqa: E402
import rfc0022_strace_preflight as preflight  # noqa: E402
from rfc0022_strace_authority import (  # noqa: E402
    main as authority_main,
)
from rfc0022_strace_model import AuthorityError  # noqa: E402
from rfc0022_strace_preflight import strace_preflight  # noqa: E402

POLICY_PATH = ROOT / "config/rfc0022-linux-strace-policy.json"


def test_preflight_subprocesses_are_bounded_and_package_owned() -> None:
    source = (ROOT / "scripts/rfc0022_strace_preflight.py").read_text(encoding="utf-8")
    assert "PREFLIGHT_TIMEOUT_SECONDS = 15" in source
    assert source.count("timeout=PREFLIGHT_TIMEOUT_SECONDS") == 3
    assert '[os.fspath(dpkg_query), "-L", "strace"]' in source


def test_preflight_fails_closed_when_strace_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "")
    with pytest.raises(AuthorityError, match="strace is absent"):
        strace_preflight("6.8")


def test_run_setup_failure_writes_normalized_error_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(preflight.shutil, "which", lambda _executable: None)
    report_path = tmp_path / "report.json"
    code = authority_main(
        [
            "run",
            "--policy",
            str(POLICY_PATH),
            "--trace-dir",
            str(tmp_path / "trace"),
            "--report",
            str(report_path),
            "--monitor-root",
            str(tmp_path),
            "--target-cwd",
            str(tmp_path),
            "--",
            "/bin/true",
        ]
    )
    assert code == 2
    assert json.loads(report_path.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "authority_id": "rfc0022-linux-strace-v1",
        "authority_status": "error",
        "outcome": "indeterminate",
        "errors": ["strace is absent"],
        "policy": {"path": str(POLICY_PATH.resolve())},
        "raw_trace_files": [],
        "target_identity": None,
        "trace_files": [],
        "violations": [],
        "target": {
            "argv": ["/bin/true"],
            "expected_returncode": 0,
            "returncode": None,
        },
    }


def test_root_runtime_rejects_site_enabled_python(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(preflight.os, "geteuid", lambda: 0, raising=False)
    with pytest.raises(AuthorityError, match="Python flags -I -S -B"):
        preflight.require_isolated_root_runtime()


def test_run_authority_pins_system_strace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: list[tuple[str, str]] = []

    def reject_after_capture(minimum: str, executable: str) -> dict[str, str | None]:
        observed.append((minimum, executable))
        raise AuthorityError("captured pinned preflight")

    monkeypatch.setattr(authority, "require_isolated_root_runtime", lambda: None)
    monkeypatch.setattr(authority, "strace_preflight", reject_after_capture)
    with pytest.raises(AuthorityError, match="captured pinned preflight"):
        authority.run_authority(
            policy_path=POLICY_PATH,
            trace_dir=tmp_path / "trace",
            report_path=tmp_path / "report.json",
            monitor_roots=[tmp_path],
            target_cwd=tmp_path,
            target=[sys.executable],
            timeout=1,
        )
    assert observed == [("6.8", "/usr/bin/strace")]


def test_preflight_command_pins_system_strace(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    observed: list[tuple[str, str]] = []

    def capture(minimum: str, executable: str) -> dict[str, str | None]:
        observed.append((minimum, executable))
        return {"executable": executable}

    monkeypatch.setattr(authority, "strace_preflight", capture)
    assert authority.main(["preflight", "--policy", str(POLICY_PATH)]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "authority_id": "rfc0022-linux-strace-v1",
        "status": "available",
        "strace": {"executable": "/usr/bin/strace"},
    }
    assert observed == [("6.8", "/usr/bin/strace")]


@pytest.mark.skipif(
    os.name == "nt",
    reason="tracked: RFC-0022 Linux preflight requires POSIX ownership",
)
def test_pinned_preflight_rejects_writable_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "strace"
    executable.write_text(
        "#!/bin/sh\nprintf 'strace -- version 6.8\n'\n", encoding="utf-8"
    )
    executable.chmod(0o777)
    monkeypatch.setattr(preflight, "PINNED_STRACE_EXECUTABLE", str(executable))
    with pytest.raises(AuthorityError, match="protected root-owned executable"):
        preflight.strace_preflight("6.8", str(executable))


@pytest.mark.skipif(
    os.name == "nt",
    reason="tracked: RFC-0022 Linux preflight requires POSIX exec",
)
def test_preflight_records_exact_binary_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "strace"
    executable.write_text(
        "#!/bin/sh\nprintf 'strace -- version 6.8\n'\n", encoding="utf-8"
    )
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert strace_preflight("6.8", str(executable)) == {
        "version": "6.8",
        "executable": str(executable.resolve()),
        "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "package": None,
    }
