"""Issue #1376：authority storage 行为组，保留测试逻辑，文本 I/O 显式使用 UTF-8。"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import time
from functools import partial
from pathlib import Path

import pytest

from tests.unit._benchmark_harness_platform import (
    mark_posix_qualification_section_tests,
)
from tests.unit._benchmark_harness_service_helpers import _authority_runner_for_test

_POSIX_QUALIFICATION_SECTION_START = sys._getframe().f_lineno
_mark_posix_qualification_section_tests = partial(
    mark_posix_qualification_section_tests, globals()
)


def test_authority_materialized_source_is_immutable_and_producer_readable(
    tmp_path: Path,
):
    # PR #1249 review 3744178810: UID 65532 could not traverse root-only snapshots.
    import io
    import tarfile

    from benchmarks.codegraph_compare.audit_authority_storage import (
        _materialize_source,
    )

    snapshot = tmp_path / "source.tar"
    payloads = {
        "pkg/main.py": ("100644", b"print('ok')\n"),
        "pkg/run.sh": ("100755", b"#!/bin/sh\nexit 0\n"),
    }
    with tarfile.open(snapshot, "w") as archive:
        for relative, (git_mode, payload) in payloads.items():
            info = tarfile.TarInfo(relative)
            info.size = len(payload)
            info.uid = info.gid = 0
            info.mode = 0o755 if git_mode == "100755" else 0o644
            archive.addfile(info, io.BytesIO(payload))
    destination = tmp_path / "source"
    inventory = json.dumps(
        {
            "eligibility": {
                "tracked_files": [
                    [
                        relative,
                        git_mode,
                        hashlib.sha1(
                            f"blob {len(payload)}\0".encode() + payload
                        ).hexdigest(),
                        len(payload),
                        hashlib.sha256(payload).hexdigest(),
                    ]
                    for relative, (git_mode, payload) in payloads.items()
                ]
            }
        }
    ).encode()

    _materialize_source(
        snapshot,
        destination,
        inventory_payload=inventory,
        ceiling=snapshot.stat().st_size,
    )

    assert {
        relative: stat.S_IMODE((destination / relative).stat().st_mode)
        for relative in payloads
    } == {"pkg/main.py": 0o444, "pkg/run.sh": 0o555}
    assert stat.S_IMODE((destination / "pkg").stat().st_mode) == 0o555
    assert stat.S_IMODE(destination.stat().st_mode) == 0o555


def test_authority_serializes_distinct_signed_jobs(tmp_path: Path):
    # PR #1249 review 3744178818: direct clients bypassed max_concurrency=1.
    import threading

    runner = _authority_runner_for_test(tmp_path)
    runner._sync_sealed_job = lambda _job_id, _result: None
    guard = threading.Lock()
    active = 0
    maximum = 0

    def execute(_contract):
        nonlocal active, maximum
        with guard:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.05)
        with guard:
            active -= 1
        return {"ok": True}

    runner._execute = execute
    threads = [
        threading.Thread(target=runner, args=({"job_id": digit * 64},))
        for digit in ("1", "2")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert maximum == 1
    assert [
        (tmp_path / f"{digit * 64}.state").read_bytes() for digit in ("1", "2")
    ] == [b"SUCCESS\n", b"SUCCESS\n"]


def test_authority_fsyncs_parent_after_reservation_and_terminal_replace(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744178821: file fsync alone did not persist directory entries.
    from benchmarks.codegraph_compare import audit_authority_runner

    runner = _authority_runner_for_test(tmp_path)
    runner._execute = lambda _contract: {"ok": True}
    runner._sync_sealed_job = lambda _job_id, _result: None
    synced = []
    monkeypatch.setattr(
        audit_authority_runner, "_fsync_directory", lambda path: synced.append(path)
    )

    runner({"job_id": "3" * 64})

    assert synced == [tmp_path, tmp_path]


def test_authority_mounts_authenticated_plan_inputs_at_exact_read_only_targets():
    # PR #1249 review 3744178826: staged tool/config bytes must reach plan argv paths.
    from benchmarks.codegraph_compare.audit_authority_storage import (
        _producer_mount_targets,
    )

    plan = {
        "executions": [
            {
                "id": execution_id,
                "argv": [
                    "/tool/bin",
                    execution_id,
                    "--config",
                    "/config/pinned.json",
                    *(["--source", "/source"] if execution_id == "build" else []),
                ],
            }
            for execution_id in ("delete", "build", "health", "symbol", "call")
        ]
    }
    runner_source = Path(
        "benchmarks/codegraph_compare/audit_authority_runner.py"
    ).read_text(encoding="utf-8")

    assert _producer_mount_targets(plan) == (
        "/source",
        "/tool/bin",
        "/config/pinned.json",
    )
    assert '(job / "tool", tool_target, True)' in runner_source
    assert '(job / "config", config_target, True)' in runner_source
    assert '(job / "seccomp", "/plan/seccomp.json", True)' in runner_source


def test_authority_removes_ext4_lost_found_and_checks_payload_before_verity():
    # PR #1249 review 3744439674: mkfs lost+found must not alter the signed tree hash.
    source = Path("benchmarks/codegraph_compare/audit_authority_runner.py").read_text(
        encoding="utf-8"
    )

    commands = [
        '"mkfs.ext4",',
        '_run("debugfs", "-w", "-R", "rmdir lost+found", str(data))',
        "_assert_ext4_payload(",
        '"veritysetup", "format", str(data), str(hashes)',
    ]

    sealing = source[source.index("data_size, inode_count, payload_bytes =") :]
    assert [sealing.index(command) for command in commands] == sorted(
        sealing.index(command) for command in commands
    )


def test_authority_streams_repository_sized_source_archive_under_inventory_ceiling(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744261021: source snapshots are not receipt-sized messages.
    import io
    import tarfile

    from benchmarks.codegraph_compare import audit_authority_storage as storage
    from benchmarks.codegraph_compare.audit_authority_storage import (
        _materialize_source,
        _sha,
        _source_archive_ceiling,
    )
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    payload = b"x" * (17 * 1024 * 1024)
    inventory = canonical_json_bytes(
        {
            "eligibility": {
                "tracked_files": [
                    [
                        "large.bin",
                        "100644",
                        hashlib.sha1(
                            f"blob {len(payload)}\0".encode() + payload
                        ).hexdigest(),
                        len(payload),
                        hashlib.sha256(payload).hexdigest(),
                    ]
                ]
            }
        }
    )
    ceiling = _source_archive_ceiling(inventory)
    snapshot = tmp_path / "source.tar"
    with tarfile.open(snapshot, "w", format=tarfile.USTAR_FORMAT) as archive:
        info = tarfile.TarInfo("large.bin")
        info.size = len(payload)
        info.uid = info.gid = 0
        info.mode = 0o644
        archive.addfile(info, io.BytesIO(payload))

    destination = tmp_path / "source"
    monkeypatch.setattr(
        storage,
        "_read",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("source archive was buffered through _read")
        ),
    )
    digest = _sha(snapshot, limit=ceiling)
    _materialize_source(
        snapshot, destination, inventory_payload=inventory, ceiling=ceiling
    )

    assert digest == hashlib.sha256(snapshot.read_bytes()).hexdigest()
    assert (destination / "large.bin").stat().st_size == 17 * 1024 * 1024


def test_producer_gate_releases_only_exact_signal(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744358517: producer commands wait for authority release.
    import threading

    from benchmarks.codegraph_compare import audit_authority_runner as runner

    gate = tmp_path / "gate"
    os.mkfifo(gate, mode=0o444)
    os.chmod(gate, 0o644)
    received = []
    reader = threading.Thread(target=lambda: received.append(gate.read_bytes()))
    reader.start()
    monkeypatch.setattr(
        runner, "_run", lambda *_args, **_kwargs: b'[{"State":{"Running":true}}]'
    )
    runner._release_producer_gate(gate, "container", __import__("time").monotonic() + 2)
    reader.join(timeout=2)

    assert received == [b"RELEASE\n"]


def test_producer_gate_fails_if_container_exits_before_release(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744358517: exit-before-gate is a terminal authority failure.
    import errno

    from benchmarks.codegraph_compare import audit_authority_runner as runner

    gate = tmp_path / "gate"
    os.mkfifo(gate, mode=0o444)
    monkeypatch.setattr(
        runner.os,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError(errno.ENXIO, "no reader")
        ),
    )
    monkeypatch.setattr(
        runner, "_run", lambda *_args, **_kwargs: b'[{"State":{"Running":false}}]'
    )
    with pytest.raises(ValueError, match="exited before launch gate"):
        runner._release_producer_gate(gate, "container", 10**30)


def test_service_launch_release_is_blocked_until_private_release_exists(tmp_path: Path):
    # PR #1249 review 3744400323: services start blocked before exact-five attestation.
    import threading

    from benchmarks.codegraph_compare.service_runtime import wait_for_launch_release

    attestation = tmp_path / "launch-attestation.json"
    release = tmp_path / "RELEASE"
    attestation.write_bytes(b"{}")
    attestation.chmod(0o400)
    observed = []
    waiter = threading.Thread(
        target=lambda: observed.append(
            wait_for_launch_release(attestation, release, timeout_seconds=2)
        )
    )
    waiter.start()
    time.sleep(0.05)
    assert observed == []
    staged_release = tmp_path / "RELEASE.pending"
    staged_release.write_bytes(b"RELEASE\n")
    staged_release.chmod(0o400)
    os.replace(staged_release, release)
    waiter.join(timeout=2)
    assert observed == [b"{}"]


def test_authority_runner_persists_response_before_success(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744482397: SUCCESS never precedes the durable signed response.
    runner = _authority_runner_for_test(tmp_path)
    runner._execute = lambda _contract: {"audit": {}, "artifacts": {}}
    runner._sync_sealed_job = lambda _job_id, _result: None
    job_id = "8" * 64
    events = []
    persist = runner._persist_response
    terminal = runner._terminal_state

    def record_persist(job, response):
        persist(job, response)
        events.append("response-fsync")

    def record_terminal(job, state, payload):
        events.append("success-replace")
        terminal(job, state, payload)

    monkeypatch.setattr(runner, "_persist_response", record_persist)
    monkeypatch.setattr(runner, "_terminal_state", record_terminal)
    reply = {"response": {"job_id": job_id}, "signature": "a" * 128}

    assert runner.run_transaction({"job_id": job_id}, lambda _result: reply) == reply
    assert events == ["response-fsync", "success-replace"]
    assert runner.query_response({"job_id": job_id}) == reply


def test_authority_mount_plan_rejects_nonexact_oracle_execution_id():
    # PR #1249 review 3744561306: receipt-v3 IDs are fixed before reservation.
    from benchmarks.codegraph_compare.audit_authority_storage import (
        _producer_mount_targets,
    )

    plan = {
        "executions": [
            {
                "id": execution_id,
                "argv": [
                    "/tool/bin",
                    execution_id,
                    "--config",
                    "/config/pinned.json",
                    *(["--source", "/source"] if execution_id == "build" else []),
                ],
            }
            for execution_id in ("delete", "build", "health", "symbol-query", "call")
        ]
    }

    with pytest.raises(ValueError, match="execution IDs are not exact"):
        _producer_mount_targets(plan)


_mark_posix_qualification_section_tests()
