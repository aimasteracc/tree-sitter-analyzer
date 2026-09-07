"""Issue #1376：test_benchmark_harness_authority_host 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import sys
from functools import partial
from pathlib import Path

import pytest

from tests.unit._benchmark_harness_platform import (
    mark_posix_qualification_section_tests,
)
from tests.unit._benchmark_harness_service_helpers import _mock_authority_cgroup_host

_POSIX_QUALIFICATION_SECTION_START = sys._getframe().f_lineno
_mark_posix_qualification_section_tests = partial(
    mark_posix_qualification_section_tests, globals()
)


def test_authority_preflight_rejects_ambiguous_mount_without_state(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744627747: 计划挂载错误必须在预留之前被发现。
    from benchmarks.codegraph_compare import audit_authority_runner as authority
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    job = tmp_path / "job"
    job.mkdir()
    plan = {
        "resource_ceilings": {"io_bytes": 1024},
        "executions": [
            {
                "id": execution_id,
                "argv": [
                    "/tool/bin",
                    execution_id,
                    "--config",
                    "/config.json",
                    *(
                        ["--source", "/source", "--source", "/source"]
                        if execution_id == "build"
                        else []
                    ),
                ],
            }
            for execution_id in ("delete", "build", "health", "symbol", "call")
        ],
    }
    (job / "plan.json").write_bytes(canonical_json_bytes(plan))
    runner = object.__new__(authority.AuthorityRunner)
    runner._artifacts = tmp_path
    runner._inputs = lambda _contract: (job, {}, {})
    runner._verify_staged = lambda *_args: 1
    monkeypatch.setattr(authority, "validate_producer_plan", lambda value: value)

    with pytest.raises(ValueError, match="source target is not exact"):
        runner.preflight({"job_id": "a" * 64})

    assert list(tmp_path.glob("*.state")) == []


def test_authority_cgroup_host_failure_precedes_running_reservation(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744853003: 确定性的主机失败不能消耗任务。
    from benchmarks.codegraph_compare import audit_authority_runner as authority

    job = tmp_path / "job"
    artifacts = tmp_path / "artifacts"
    job.mkdir()
    artifacts.mkdir()
    (job / "plan.json").write_text("{}", encoding="utf-8")
    runner = object.__new__(authority.AuthorityRunner)
    runner._artifacts = artifacts
    runner._inputs = lambda _contract: (job, {}, {})
    runner._verify_staged = lambda *_args: 1
    monkeypatch.setattr(authority, "validate_producer_plan", lambda value: value)
    monkeypatch.setattr(authority, "_authorized_output_ceiling", lambda _plan: 1)
    monkeypatch.setattr(
        authority,
        "_producer_mount_targets",
        lambda _plan: ("/source", "/tool", "/config"),
    )
    monkeypatch.setattr(
        authority,
        "_run",
        lambda *_args: b'{"CgroupVersion":"2","CgroupDriver":"systemd"}',
    )

    with pytest.raises(ValueError, match="only cgroup-v2 cgroupfs Docker"):
        runner.preflight({"job_id": "a" * 64})

    assert list(artifacts.glob("*.state")) == []


def test_authority_requires_all_available_cgroup_controllers(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744853003: 生产者需要的每个控制器都必须可用。
    authority, cgroup = _mock_authority_cgroup_host(tmp_path, monkeypatch)
    (cgroup / "cgroup.controllers").write_text("cpu memory pids", encoding="utf-8")

    with pytest.raises(ValueError, match="controllers are unavailable"):
        authority._preflight_cgroup_host()


def test_authority_requires_all_delegated_cgroup_controllers(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744853003: 生产者需要的每个控制器都必须已委派。
    authority, cgroup = _mock_authority_cgroup_host(tmp_path, monkeypatch)
    (cgroup / "cgroup.subtree_control").write_text("cpu memory pids", encoding="utf-8")

    with pytest.raises(ValueError, match="controllers are not delegated"):
        authority._preflight_cgroup_host()


def test_authority_requires_writable_cgroup_delegation(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744853003: 已委派的层级必须允许创建子节点。
    authority, _cgroup = _mock_authority_cgroup_host(tmp_path, monkeypatch)
    monkeypatch.setattr(authority.os, "access", lambda *_args: False)

    with pytest.raises(ValueError, match="delegation is not writable"):
        authority._preflight_cgroup_host()


_mark_posix_qualification_section_tests()
