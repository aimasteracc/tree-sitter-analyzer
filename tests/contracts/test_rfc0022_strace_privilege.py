"""Privilege boundary contracts for the RFC-0022 Linux authority."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import rfc0022_strace_privilege as privilege  # noqa: E402
import rfc0022_strace_target_launcher as target_launcher  # noqa: E402
from rfc0022_strace_model import AuthorityError  # noqa: E402


def test_target_launcher_python_disables_site_and_environment() -> None:
    launcher = ROOT / "scripts/rfc0022_strace_target_launcher.py"
    invocation = privilege.build_invocation(
        "/usr/bin/strace",
        {"target_user": "rfc0022-target", "trace_arguments": ["-ff"]},
        Path("/evidence/trace"),
        launcher,
        ["/bin/true"],
    )
    assert invocation == [
        "/usr/bin/strace",
        "-u",
        "rfc0022-target",
        "-ff",
        "-o",
        os.fspath(Path("/evidence/trace")),
        "--",
        os.path.realpath(sys.executable),
        "-I",
        "-S",
        "-B",
        str(launcher),
        "--",
        "/bin/true",
    ]


def test_privilege_separation_identity_and_launcher_are_digest_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Record:
        pw_uid = 1234
        pw_gid = 1235

    directories = tuple(tmp_path / name for name in ("home", "cache"))
    for directory in directories:
        directory.mkdir()
    chowns: list[tuple[Path, int, int]] = []
    monkeypatch.setattr(privilege.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(
        privilege.os, "getgrouplist", lambda _user, gid: [gid], raising=False
    )
    monkeypatch.setattr(
        privilege.os,
        "chown",
        lambda path, uid, gid: chowns.append((path, uid, gid)),
        raising=False,
    )

    class FakePwd:
        @staticmethod
        def getpwnam(_user: str) -> Record:
            return Record()

    monkeypatch.setattr(privilege, "pwd", FakePwd)
    launcher = ROOT / "scripts/rfc0022_strace_target_launcher.py"
    identity = privilege.prepare_target_identity(
        "rfc0022-target", directories, launcher
    )
    assert identity == {
        "gid": 1235,
        "groups": [1235],
        "launcher": {
            "path": str(launcher.resolve()),
            "python": {
                "path": os.path.realpath(sys.executable),
                "sha256": hashlib.sha256(
                    Path(os.path.realpath(sys.executable)).read_bytes()
                ).hexdigest(),
            },
            "sha256": privilege.TARGET_LAUNCHER_SHA256,
        },
        "no_new_privs": True,
        "uid": 1234,
        "user": "rfc0022-target",
    }
    assert chowns == [(directory, 1234, 1235) for directory in directories]
    if os.name != "nt":
        assert [directory.stat().st_mode & 0o777 for directory in directories] == [
            0o700,
            0o700,
        ]


def test_privilege_separation_rejects_non_root_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(privilege.os, "geteuid", lambda: 501, raising=False)
    with pytest.raises(AuthorityError, match="requires root privilege separation"):
        privilege.prepare_target_identity(
            "rfc0022-target",
            (tmp_path,),
            ROOT / "scripts/rfc0022_strace_target_launcher.py",
        )


def test_target_launcher_requires_zero_linux_capabilities(tmp_path: Path) -> None:
    status = tmp_path / "status"
    status.write_text(
        "CapInh:\t0000000000000000\n"
        "CapPrm:\t0000000000000000\n"
        "CapEff:\t0000000000000000\n"
        "CapAmb:\t0000000000000000\n",
        encoding="utf-8",
    )
    target_launcher._assert_no_linux_capabilities(status)
    status.write_text(
        status.read_text(encoding="utf-8").replace(
            "CapEff:\t0000000000000000", "CapEff:\t0000000000000001"
        ),
        encoding="utf-8",
    )
    with pytest.raises(PermissionError, match="inherited Linux capabilities"):
        target_launcher._assert_no_linux_capabilities(status)


def test_target_launcher_rejects_missing_capability_evidence(tmp_path: Path) -> None:
    status = tmp_path / "status"
    status.write_text("CapEff:\t0000000000000000\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="inspect every Linux capability set"):
        target_launcher._assert_no_linux_capabilities(status)


def test_target_launcher_source_locks_no_new_privileges() -> None:
    source = (ROOT / "scripts/rfc0022_strace_target_launcher.py").read_text(
        encoding="utf-8"
    )
    required = {
        "PR_SET_NO_NEW_PRIVS = 38",
        'getattr(os, "getresuid", None)',
        'getattr(os, "getresgid", None)',
        "os.getgroups()",
        'Path("/proc/self/status")',
        'required = {"CapAmb", "CapEff", "CapInh", "CapPrm"}',
        "os.execv(",
    }
    assert {item for item in required if item in source} == required
