"""Issue #1376：resource_bounds 行为组，原测试 AST 保持不变。"""

from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
import time
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.unit._benchmark_harness_platform import (
    mark_posix_qualification_section_tests,
)

_POSIX_QUALIFICATION_SECTION_START = sys._getframe().f_lineno
_mark_posix_qualification_section_tests = partial(
    mark_posix_qualification_section_tests, globals()
)


def test_qualification_index_observation_streams_canonical_bounded_records(
    tmp_path: Path,
):
    # PR #1249 review 3745026823: observations are bounded before producer success.
    from benchmarks.codegraph_compare.setup_qualification_executor import (
        _write_final_index_observation,
    )

    index = tmp_path / "index"
    raw = tmp_path / "raw"
    index.mkdir()
    raw.mkdir()
    (index / "b").write_bytes(b"bb")
    (index / "a").write_bytes(b"a")
    descriptor = _write_final_index_observation(
        index, raw, "observation", deadline_monotonic=time.monotonic() + 10
    )

    assert descriptor == {
        "path": "raw/observation",
        "size_bytes": (raw / "observation").stat().st_size,
        "sha256": hashlib.sha256((raw / "observation").read_bytes()).hexdigest(),
    }
    assert json.loads((raw / "observation").read_bytes()) == [
        {
            "path": "a",
            "sha256": hashlib.sha256(b"a").hexdigest(),
            "size_bytes": 1,
        },
        {
            "path": "b",
            "sha256": hashlib.sha256(b"bb").hexdigest(),
            "size_bytes": 2,
        },
    ]


def test_qualification_index_observation_rejects_receipt_node_overflow(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3745026823: node complexity fails before successful sealing.
    from benchmarks.codegraph_compare import setup_qualification_executor as executor

    index = tmp_path / "index"
    raw = tmp_path / "raw"
    index.mkdir()
    raw.mkdir()
    (index / "only").write_bytes(b"x")
    monkeypatch.setattr(executor, "MAX_NODES", 3)

    with pytest.raises(ValueError, match="receipt node bound"):
        executor._write_final_index_observation(
            index, raw, "observation", deadline_monotonic=time.monotonic() + 10
        )


def test_qualification_index_observation_rejects_receipt_byte_overflow(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3745026823: byte complexity fails before successful sealing.
    from benchmarks.codegraph_compare import setup_qualification_executor as executor

    index = tmp_path / "index"
    raw = tmp_path / "raw"
    index.mkdir()
    raw.mkdir()
    monkeypatch.setattr(executor, "MAX_JSON_BYTES", len(b'{"records":}'))

    with pytest.raises(ValueError, match="receipt JSON bound"):
        executor._write_final_index_observation(
            index, raw, "observation", deadline_monotonic=time.monotonic() + 10
        )


def test_sealed_read_budget_uses_named_actual_passes():
    # PR #1249 review 3745026813: budget counts signer x2 and verifier readers.
    from benchmarks.codegraph_compare.execution_budget import sealed_read_passes

    assert sealed_read_passes("executor") == sealed_read_passes("approver")
    assert {
        role: {kind: len(names) for kind, names in sealed_read_passes(role).items()}
        for role in ("executor", "approver", "verifier")
    } == {
        "executor": {"images": 4, "output": 9},
        "approver": {"images": 4, "output": 9},
        "verifier": {"images": 2, "output": 5},
    }


def test_ext4_image_sizing_rejects_large_sparse_output(tmp_path: Path):
    # PR #1249 review 3744561310: sparse logical bytes cannot bypass output ceilings.
    from benchmarks.codegraph_compare.audit_authority_runner import _ext4_image_size

    core = tmp_path / "core"
    core.mkdir()
    (core / "sparse-index").write_bytes(b"")
    os.truncate(core / "sparse-index", 128 * 1024 * 1024)

    with pytest.raises(ValueError, match="authorized output ceiling"):
        _ext4_image_size(core, 64 * 1024 * 1024)


def test_ext4_image_sizing_uses_sealed_core_usage(tmp_path: Path):
    # PR #1249 review 3744561310: small outputs no longer allocate a fixed 1 GiB.
    from benchmarks.codegraph_compare.audit_authority_runner import _ext4_image_size

    core = tmp_path / "core"
    core.mkdir()
    (core / "index").mkdir()
    (core / "index" / "data").write_bytes(b"x")

    assert _ext4_image_size(core, 128 * 1024 * 1024) == 68 * 1024 * 1024


def test_ext4_layout_reserves_exact_sealed_core_inodes(tmp_path: Path):
    # PR #1249 review 3744627741: byte sizing alone under-provisioned small-file inodes.
    from benchmarks.codegraph_compare.audit_authority_runner import _ext4_layout

    core = tmp_path / "core"
    core.mkdir()
    (core / "index").mkdir()
    (core / "one").write_bytes(b"")
    (core / "index" / "two").write_bytes(b"")

    assert _ext4_layout(core, 128 * 1024 * 1024) == (
        68 * 1024 * 1024,
        6,
        16 * 1024,
    )


def test_ext4_layout_rejects_core_above_entry_bound(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744627741: inode counting work has an authority-owned bound.
    from benchmarks.codegraph_compare import audit_authority_runner as authority

    core = tmp_path / "core"
    core.mkdir()
    (core / "one").write_bytes(b"")
    (core / "two").write_bytes(b"")
    monkeypatch.setattr(authority, "_MAX_SEALED_CORE_ENTRIES", 2)

    with pytest.raises(ValueError, match="entry count exceeds authority maximum"):
        authority._ext4_layout(core, 128 * 1024 * 1024)


def test_debugfs_timeout_scales_with_payload_and_contract_expiry(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744627743: extraction cannot inherit the fixed 120s default.
    from benchmarks.codegraph_compare import audit_authority_runner as authority

    observed = []
    monkeypatch.setattr(authority.time, "time_ns", lambda: 1_000_000_000)
    monkeypatch.setattr(authority, "_hash_tree", lambda _path: "same")
    monkeypatch.setattr(
        authority,
        "_run",
        lambda *args, timeout: observed.append((args, timeout)) or b"",
    )

    authority._assert_ext4_payload(
        tmp_path / "data.img",
        tmp_path / "core",
        payload_bytes=64 * 1024 * 1024,
        contract_expires_at_ns=33_000_000_000,
    )

    command, timeout = observed[0]
    assert command[:2] == ("debugfs", "-R")
    assert command[2].startswith("rdump / ")
    assert command[3] == str(tmp_path / "data.img")
    assert timeout == 32.0


def test_streamed_blob_descriptor_does_not_use_read_bytes(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744677888: producer evidence descriptors are streamed from disk.
    from benchmarks.codegraph_compare.setup_qualification_executor import (
        _describe_blob,
    )

    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "stdout").write_bytes(b"abc" * 1024)
    monkeypatch.setattr(Path, "read_bytes", lambda _self: pytest.fail("buffered read"))

    assert _describe_blob(raw, "stdout") == {
        "path": "raw/stdout",
        "size_bytes": 3072,
        "sha256": hashlib.sha256(b"abc" * 1024).hexdigest(),
    }


def test_core_blob_bound_uses_signed_output_ceiling_not_legacy_512mib():
    # PR #1249 review 3744728241: valid large descriptors use the signed ceiling.
    from benchmarks.codegraph_compare.verifier_recompute import _core_blob_size

    size = 513 * 1024 * 1024
    plan = {"resource_ceilings": {"io_bytes": size}}

    assert _core_blob_size(plan, size) == 537_919_488
    with pytest.raises(ValueError, match="signed output ceiling"):
        _core_blob_size(plan, size + 1)


def test_shared_verifier_debugfs_timeout_uses_image_size_and_absolute_deadline(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744728245: all receipt/verifier extraction shares this path.
    from benchmarks.codegraph_compare import execution_budget, verifier

    image = tmp_path / "data.img"
    image.write_bytes(b"")
    os.truncate(image, 16 * 1024 * 1024 * 1024)
    observed = []
    monkeypatch.setattr(execution_budget.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(
        verifier.subprocess,
        "run",
        lambda *args, **kwargs: (
            observed.append(kwargs["timeout"]) or SimpleNamespace(returncode=0)
        ),
    )

    verifier._extract_ext4(image, tmp_path / "out", deadline_monotonic=200.0)

    assert observed == [100.0]


def test_live_output_size_ignores_disappearing_entry(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744776119: mutable producer trees race live accounting.
    from benchmarks.codegraph_compare import setup_qualification_executor as executor

    output = tmp_path / "output"
    output.mkdir()
    (output / "index.db").write_bytes(b"abc")
    real_lstat = executor.os.lstat

    def vanished(path):
        if Path(path).name == "index.db":
            raise FileNotFoundError(path)
        return real_lstat(path)

    monkeypatch.setattr(executor.os, "lstat", vanished)

    assert executor._output_size(output, strict=False) == 0


def test_live_output_size_charges_allocated_blocks_and_shared_metadata(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3745125491: empty and sparse output consumes live budget.
    from benchmarks.codegraph_compare import setup_qualification_executor as executor
    from benchmarks.codegraph_compare.execution_budget import (
        OUTPUT_ENTRY_METADATA_CHARGE_BYTES,
    )

    output = tmp_path / "output"
    output.mkdir()
    item = output / "item"
    item.touch()
    real_lstat = executor.os.lstat

    def allocated(path):
        metadata = real_lstat(path)
        if Path(path) == item:
            return SimpleNamespace(st_mode=metadata.st_mode, st_blocks=2)
        return metadata

    monkeypatch.setattr(executor.os, "lstat", allocated)

    assert executor._output_size(output) == 1024 + OUTPUT_ENTRY_METADATA_CHARGE_BYTES


def test_live_output_size_rejects_entry_count_above_shared_bound(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3745125491: every mutable-tree scan has bounded work.
    from benchmarks.codegraph_compare import setup_qualification_executor as executor

    output = tmp_path / "output"
    output.mkdir()
    (output / "one").touch()
    (output / "two").touch()
    monkeypatch.setattr(executor, "_MAX_OUTPUT_ENTRIES", 1)

    with pytest.raises(ValueError, match="entry count exceeds authority maximum"):
        executor._output_size(output, ceiling=1024 * 1024)


def test_live_output_size_enforces_signed_ceiling_during_scan(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3745125491: allocated output cannot grow past signed bytes.
    from benchmarks.codegraph_compare import setup_qualification_executor as executor

    output = tmp_path / "output"
    output.mkdir()
    item = output / "item"
    item.touch()
    real_lstat = executor.os.lstat

    def allocated(path):
        metadata = real_lstat(path)
        if Path(path) == item:
            return SimpleNamespace(st_mode=metadata.st_mode, st_blocks=2)
        return metadata

    monkeypatch.setattr(executor.os, "lstat", allocated)

    with pytest.raises(ValueError, match="exceeds signed I/O ceiling"):
        executor._output_size(output, ceiling=5119)


def test_terminal_output_size_rejects_disappearing_entry(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744776119: only the stable terminal snapshot is strict.
    from benchmarks.codegraph_compare import setup_qualification_executor as executor

    output = tmp_path / "output"
    output.mkdir()
    (output / "index.db").write_bytes(b"abc")
    real_lstat = executor.os.lstat

    def vanished(path):
        if Path(path).name == "index.db":
            raise FileNotFoundError(path)
        return real_lstat(path)

    monkeypatch.setattr(executor.os, "lstat", vanished)

    with pytest.raises(FileNotFoundError):
        executor._output_size(output)


def test_verifier_server_frame_deadline_scales_to_maximum_payload(monkeypatch):
    # PR #1249 review 3744822112: 512 MiB reads must not retain a fixed 10s budget.

    from benchmarks.codegraph_compare import verifier_service

    deadlines = []

    def receive(_connection, size, deadline):
        deadlines.append(deadline)
        return struct.pack("!I", verifier_service.MAX_FRAME) if size == 4 else b"{}"

    monkeypatch.setattr(verifier_service, "recv_exact", receive)
    monkeypatch.setattr(verifier_service.time, "monotonic", lambda: 100.0)

    assert verifier_service._frame(object()) == {}
    assert deadlines == [110.0, 164.0]


def test_receipt_frame_preflight_rejects_approver_draft_ceiling(monkeypatch):
    # PR #1249 review 3744822118: all receipt frames must fit before authority use.
    from benchmarks.codegraph_compare import qualification_operator as operator

    plan = {"plan": "x"}
    inventory = {"eligibility": {"paths": ["a"]}}
    bounds = operator.preflight_receipt_service_frames(plan, inventory)
    monkeypatch.setattr(operator, "RECEIPT_MAX_MESSAGE", bounds["approver_request"] - 1)

    with pytest.raises(ValueError, match="receipt frame upper bound"):
        operator.preflight_receipt_service_frames(plan, inventory)


def test_receipt_server_frame_deadline_scales_to_maximum_payload(monkeypatch):
    # PR #1249 review 3744887360: 16 MiB reads use the declared frame size.

    from benchmarks.codegraph_compare import receipt_v3_service

    deadlines = []

    def receive(_connection, size, deadline):
        deadlines.append(deadline)
        return struct.pack("!I", receipt_v3_service.MAX_MESSAGE) if size == 4 else b"{}"

    monkeypatch.setattr(receipt_v3_service, "recv_exact", receive)
    monkeypatch.setattr(receipt_v3_service.time, "monotonic", lambda: 100.0)

    assert receipt_v3_service._frame(object()) == {}
    assert deadlines == [110.0, 116.0]


@pytest.mark.parametrize("role", ["executor", "approver"])
def test_receipt_signer_rechecks_expired_deadline_before_signature(monkeypatch, role):
    # PR #1249 review 3744915233: completed semantic work cannot sign after expiry.
    from benchmarks.codegraph_compare import receipt_v3_signer as signer

    body = {"sealed": True}
    monkeypatch.setattr(signer, "_safe_path", lambda _path: Path("/sealed.img"))
    monkeypatch.setattr(signer, "_extract_ext4", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(signer, "_build_body", lambda *_args, **_kwargs: body)
    monkeypatch.setattr(signer, "_full_semantic_verify", lambda *_args, **_kwargs: body)
    monkeypatch.setattr(signer.time, "monotonic", lambda: 5.0)
    monkeypatch.setattr(
        signer,
        "create_executor_attestation",
        lambda *_args: pytest.fail("expired executor receipt was signed"),
    )
    monkeypatch.setattr(
        signer,
        "approve_executor_attestation",
        lambda *_args: pytest.fail("expired approver receipt was signed"),
    )
    args = SimpleNamespace(data_image="/sealed.img")
    config = {role: {"key_id": role}}
    draft = {"body": body} if role == "approver" else None

    with pytest.raises(TimeoutError, match=f"{role} receipt signing deadline expired"):
        signer.sign_verified_receipt(
            role=role,
            args=args,
            config=config,
            key=b"key",
            key_id=role,
            draft=draft,
            deadline_monotonic=5.0,
        )


_mark_posix_qualification_section_tests()
