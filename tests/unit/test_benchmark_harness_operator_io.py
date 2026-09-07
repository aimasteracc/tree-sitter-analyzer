"""Issue #1376：test_benchmark_harness_operator_io 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
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


def test_stage_copy_file_applies_requested_mode_despite_umask(tmp_path: Path):
    # PR #1249 review 3744303005: 不同服务 UID 必须能够读取暂存输入。
    from benchmarks.codegraph_compare.stage_inputs import copy_file

    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.write_bytes(b"trusted")
    previous = os.umask(0o077)
    try:
        copy_file(source, destination, 0o444)
    finally:
        os.umask(previous)

    assert stat.S_IMODE(destination.stat().st_mode) == 0o444


def test_operator_success_state_replace_is_directory_durable(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744303001: 终态成功必须在主机掉电后仍可恢复。
    from benchmarks.codegraph_compare import qualification_operator

    output = tmp_path / "experiment"
    synced = []
    monkeypatch.setattr(qualification_operator, "_run_impl", lambda _args: 0)
    monkeypatch.setattr(
        qualification_operator, "_fsync_directory", lambda path: synced.append(path)
    )

    assert qualification_operator.run(SimpleNamespace(experiment_root=str(output))) == 0
    assert synced == [output, output, output]
    assert json.loads((output / "operator-state.json").read_bytes()) == {
        "completed_cells": 14,
        "state": "SUCCESS",
    }


def test_operator_failed_state_replace_is_directory_durable(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744303001: 终态失败必须在主机掉电后仍可恢复。
    from benchmarks.codegraph_compare import qualification_operator

    output = tmp_path / "experiment"
    synced = []

    def fail(_args):
        raise RuntimeError("failed")

    monkeypatch.setattr(qualification_operator, "_run_impl", fail)
    monkeypatch.setattr(
        qualification_operator, "_fsync_directory", lambda path: synced.append(path)
    )

    with pytest.raises(RuntimeError, match="failed"):
        qualification_operator.run(SimpleNamespace(experiment_root=str(output)))
    assert synced == [output, output, output]
    assert json.loads((output / "operator-state.json").read_bytes()) == {
        "error": "RuntimeError",
        "state": "FAILED",
    }


def test_stage_inventory_tree_uses_read_only_modes_from_git_inventory(
    tmp_path: Path,
):
    # PR #1249 review 3744439670: 暂存的可执行文件和普通 blob 都必须不可变。
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes
    from benchmarks.codegraph_compare.stage_inputs import stage_inventory_tree

    source = tmp_path / "checkout"
    source.mkdir()
    payloads = {
        "README.md": ("100644", b"fixture\n"),
        "bin/tool": ("100755", b"#!/bin/sh\n"),
    }
    records = []
    for relative, (mode, payload) in payloads.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        oid = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
        records.append(
            [relative, mode, oid, len(payload), hashlib.sha256(payload).hexdigest()]
        )
    inventory = tmp_path / "inventory.json"
    inventory.write_bytes(
        canonical_json_bytes({"eligibility": {"tracked_files": records}})
    )
    destination = tmp_path / "staged"

    stage_inventory_tree(source, destination, tmp_path / "source.tar", inventory)

    assert {
        relative: stat.S_IMODE((destination / relative).stat().st_mode)
        for relative in payloads
    } == {"README.md": 0o444, "bin/tool": 0o555}
    assert stat.S_IMODE((destination / "bin").stat().st_mode) == 0o555
    assert stat.S_IMODE(destination.stat().st_mode) == 0o555


def test_operator_write_completes_short_writes_before_fsync(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744358510: 成功写入必须保留完整的 envelope。
    from benchmarks.codegraph_compare import qualification_operator as operator

    real_write = os.write

    def short_write(descriptor, payload):
        return real_write(descriptor, payload[:3])

    monkeypatch.setattr(operator.os, "write", short_write)
    path = tmp_path / "evidence.json"
    operator._write(path, {"status": "SUCCESS"})

    assert path.read_bytes() == b'{"status":"SUCCESS"}\n'


def test_operator_write_rejects_zero_progress(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744358510: 零字节写入不能报告 operator 成功。
    from benchmarks.codegraph_compare import qualification_operator as operator

    monkeypatch.setattr(operator.os, "write", lambda *_args: 0)
    with pytest.raises(OSError, match="made no progress"):
        operator._write(tmp_path / "evidence.json", {"status": "SUCCESS"})


def test_stage_copy_file_completes_short_writes(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744482394: 短写之后，暂存仍须保留每个字节。
    from benchmarks.codegraph_compare import stage_inputs

    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.write_bytes(b"trusted-stage-bytes")
    real_write = os.write

    def short_write(descriptor, payload):
        return real_write(descriptor, payload[:3])

    monkeypatch.setattr(stage_inputs.os, "write", short_write)
    stage_inputs.copy_file(source, destination)

    assert destination.read_bytes() == b"trusted-stage-bytes"


def test_stage_copy_file_rejects_zero_progress(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744482394: 零字节写入不能暂存可信输入。
    from benchmarks.codegraph_compare import stage_inputs

    source = tmp_path / "source"
    source.write_bytes(b"trusted-stage-bytes")
    monkeypatch.setattr(stage_inputs.os, "write", lambda *_args: 0)

    with pytest.raises(OSError, match="staged input write made no progress"):
        stage_inputs.copy_file(source, tmp_path / "destination")


def test_aggregate_output_writer_retries_partial_writes(monkeypatch):
    # PR #1249 review 3744561299: 短写不能截断聚合证据。
    from benchmarks.codegraph_compare import verifier_aggregate

    observed = bytearray()

    def partial(_descriptor, payload):
        count = min(2, len(payload))
        observed.extend(payload[:count])
        return count

    monkeypatch.setattr(verifier_aggregate.os, "write", partial)
    verifier_aggregate._write_all(7, b"abcdef")

    assert bytes(observed) == b"abcdef"


def test_aggregate_output_writer_rejects_zero_progress(monkeypatch):
    # PR #1249 review 3744561299: 零进度写入必须失败关闭。
    from benchmarks.codegraph_compare import verifier_aggregate

    monkeypatch.setattr(verifier_aggregate.os, "write", lambda *_args: 0)

    with pytest.raises(OSError, match="made no progress"):
        verifier_aggregate._write_all(7, b"x")


_mark_posix_qualification_section_tests()
