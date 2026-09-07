"""Issue #1376：authority lifecycle 行为组，保留测试逻辑，文本 I/O 显式使用 UTF-8。"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.unit._benchmark_harness_platform import (
    mark_posix_qualification_section_tests,
)
from tests.unit._benchmark_harness_service_helpers import _mock_authority_cgroup_host

_POSIX_QUALIFICATION_SECTION_START = sys._getframe().f_lineno
_mark_posix_qualification_section_tests = partial(
    mark_posix_qualification_section_tests, globals()
)


def test_operator_gives_authority_aggregate_remaining_timeout(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744178822: sealing time must not consume producer wall budget.
    from benchmarks.codegraph_compare import qualification_operator
    from benchmarks.codegraph_compare.receipt_v3 import (
        canonical_json_bytes,
        canonical_plan_hash,
    )
    from benchmarks.codegraph_compare.setup_qualification_plan import EXPECTED_CELLS

    contracts_dir = tmp_path / "contracts"
    staged_root = tmp_path / "staged"
    contracts_dir.mkdir()
    staged_root.mkdir()
    plans = []
    contracts = []
    for ordinal, (repo, arm) in enumerate(EXPECTED_CELLS):
        plan = {
            "cell": {"repo_id": repo, "arm_id": arm, "attempt": 1},
            "wall_timeout_seconds": 10,
            "resource_ceilings": {"io_bytes": 32 * 1024 * 1024},
        }
        plan["plan_hash"] = canonical_plan_hash(plan)
        plans.append(plan)
        job_id = f"{ordinal + 1:064x}"
        contract = {
            "job_id": job_id,
            "cell": plan["cell"],
            "nonce": "a" * 64,
            "decision_id": "b" * 64,
            "expires_at_ns": 10**30,
        }
        contracts.append(contract)
        (contracts_dir / f"{ordinal}.json").write_bytes(canonical_json_bytes(contract))
        job = staged_root / job_id
        job.mkdir()
        (job / "plan.json").write_bytes(canonical_json_bytes(plan))
        (job / "inventory.json").write_bytes(canonical_json_bytes({"repo_id": repo}))
    decision = {
        "decision_id": "b" * 64,
        "expires_at_ns": 10**30,
        "plan_set_hash": "c" * 64,
        "cells": [
            {
                "repo_id": repo,
                "arm_id": arm,
                "plan_sha256": canonical_plan_hash(plan),
            }
            for (repo, arm), plan in zip(EXPECTED_CELLS, plans, strict=True)
        ],
    }
    decision_path = tmp_path / "decision.json"
    decision_path.write_bytes(canonical_json_bytes(decision))
    digest = hashlib.sha256(canonical_json_bytes(decision)).hexdigest()
    for contract in contracts:
        contract["decision_contract_sha256"] = digest
    # Rewrite after adding the common decision digest.
    for ordinal, contract in enumerate(contracts):
        (contracts_dir / f"{ordinal}.json").write_bytes(canonical_json_bytes(contract))
    public_config = tmp_path / "public.json"
    public_config.write_bytes(b"{}")
    monkeypatch.setattr(
        qualification_operator,
        "parse_public_config",
        lambda _raw: {
            "auditor": {"peer_uid": 0},
            "trusted": {
                "plan_set_hash": "c" * 64,
                "inventory_sha256": {
                    repo: hashlib.sha256(
                        canonical_json_bytes({"repo_id": repo})
                    ).hexdigest()
                    for repo, _arm in EXPECTED_CELLS
                },
                "verifier_runtime": {"measurement": {}},
            },
        },
    )
    monkeypatch.setattr(
        qualification_operator, "verify_decision_contract", lambda value: value
    )
    monkeypatch.setattr(
        qualification_operator, "verify_configured_plan_set", lambda *_args: None
    )
    monkeypatch.setattr(
        qualification_operator, "validate_producer_plan", lambda value: value
    )
    monkeypatch.setattr(
        qualification_operator, "validate_receipt_inventory", lambda value: value
    )
    monkeypatch.setattr(
        qualification_operator,
        "verify_contract",
        lambda request: request["contract"],
    )
    ticks = iter((100.0, 101.0))
    monkeypatch.setattr(
        qualification_operator,
        "time",
        SimpleNamespace(
            monotonic=lambda: next(ticks), time_ns=__import__("time").time_ns
        ),
    )
    observed = []

    def stop_after_authority(_contract, _socket, authority):
        observed.append(authority["wall_timeout_seconds"])
        raise RuntimeError("observed authority timeout")

    monkeypatch.setattr(qualification_operator, "run_cell", stop_after_authority)
    args = SimpleNamespace(
        public_config=str(public_config),
        contracts_dir=str(contracts_dir),
        decision_contract=str(decision_path),
        staged_root=str(staged_root),
        authority_socket=str(tmp_path / "authority.sock"),
    )

    with pytest.raises(RuntimeError, match="observed authority timeout"):
        qualification_operator._run_impl(args)

    assert observed == [1932]
    assert plans[0]["wall_timeout_seconds"] == 10


def test_authority_deadline_subtracts_docker_start_rpc_and_audit_time(monkeypatch):
    # PR #1249 review 3744261033: producer budget is Docker StartedAt-to-FinishedAt.
    from benchmarks.codegraph_compare import audit_authority_runner as runner

    clock = SimpleNamespace(
        time=lambda: 1_003.0,
        monotonic=lambda: 500.0,
        time_ns=lambda: 1_000_000_000,
    )
    monkeypatch.setattr(runner, "time", clock)
    process_timeouts = []

    class ImmediateProcess:
        returncode = 0

        def __init__(self, args):
            self.args = args

        def communicate(self, timeout):
            process_timeouts.append((tuple(self.args), timeout))
            return b"0\n", b""

    monkeypatch.setattr(
        runner.subprocess,
        "Popen",
        lambda args, **_kwargs: ImmediateProcess(args),
    )

    deadline = runner._docker_wall_deadline("1970-01-01T00:16:40Z", 10)
    exit_code = runner._wait_container("producer", deadline)
    runner._run("seal-command")

    extraction_calls = []
    monkeypatch.setattr(runner, "_hash_tree", lambda _path: "same")
    monkeypatch.setattr(
        runner,
        "_run",
        lambda *args, timeout: extraction_calls.append((args, timeout)) or b"",
    )
    runner._assert_ext4_payload(
        Path("data.img"),
        Path("core"),
        payload_bytes=64 * 1024 * 1024,
        contract_expires_at_ns=33_000_000_000,
    )

    assert deadline == 507.0
    assert exit_code == "0"
    assert process_timeouts == [
        (("docker", "wait", "producer"), 7.0),
        (("seal-command",), 120),
    ]
    extraction_command, extraction_timeout = extraction_calls[0]
    assert extraction_command[:2] == ("debugfs", "-R")
    assert extraction_command[2].startswith("rdump / ")
    assert extraction_command[3] == "data.img"
    assert extraction_timeout == 32.0


def test_producer_gate_readiness_timeout_is_terminal(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744358517: a missing gate reader cannot hang the reservation.
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
        runner, "_run", lambda *_args, **_kwargs: b'[{"State":{"Running":true}}]'
    )
    calls = iter((0.0,))
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(calls, 11.0))
    with pytest.raises(TimeoutError, match="gate readiness expired"):
        runner._release_producer_gate(gate, "container", 10**30)


def test_operator_rejects_short_common_lifetime_before_first_cell(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744588269: closed serial budget failure consumes no job.
    from benchmarks.codegraph_compare import qualification_operator as operator
    from benchmarks.codegraph_compare.receipt_v3 import (
        canonical_json_bytes,
        canonical_plan_hash,
    )
    from benchmarks.codegraph_compare.setup_qualification_plan import EXPECTED_CELLS

    now = 1_000_000_000_000
    expiry = now + 7_898 * 1_000_000_000 - 1
    contracts_dir = tmp_path / "contracts"
    staged_root = tmp_path / "staged"
    contracts_dir.mkdir()
    staged_root.mkdir()
    plans = []
    contracts = []
    for ordinal, (repo, arm) in enumerate(EXPECTED_CELLS):
        plan = {
            "cell": {"repo_id": repo, "arm_id": arm, "attempt": 1},
            "wall_timeout_seconds": 10,
            "resource_ceilings": {"io_bytes": 32 * 1024 * 1024},
        }
        plan["plan_hash"] = canonical_plan_hash(plan)
        plans.append(plan)
        job_id = f"{ordinal + 1:064x}"
        contract = {
            "job_id": job_id,
            "cell": plan["cell"],
            "nonce": "a" * 64,
            "decision_id": "b" * 64,
            "expires_at_ns": expiry,
        }
        contracts.append(contract)
        job = staged_root / job_id
        job.mkdir()
        (job / "plan.json").write_bytes(canonical_json_bytes(plan))
        (job / "inventory.json").write_bytes(canonical_json_bytes({"repo_id": repo}))
    decision = {
        "decision_id": "b" * 64,
        "expires_at_ns": expiry,
        "plan_set_hash": "c" * 64,
        "cells": [
            {
                "repo_id": repo,
                "arm_id": arm,
                "plan_sha256": canonical_plan_hash(plan),
            }
            for (repo, arm), plan in zip(EXPECTED_CELLS, plans, strict=True)
        ],
    }
    decision_path = tmp_path / "decision.json"
    decision_path.write_bytes(canonical_json_bytes(decision))
    digest = hashlib.sha256(canonical_json_bytes(decision)).hexdigest()
    for ordinal, contract in enumerate(contracts):
        contract["decision_contract_sha256"] = digest
        (contracts_dir / f"{ordinal}.json").write_bytes(canonical_json_bytes(contract))
    config_path = tmp_path / "public.json"
    config_path.write_bytes(b"{}")
    monkeypatch.setattr(
        operator,
        "parse_public_config",
        lambda _raw: {
            "auditor": {"peer_uid": 0},
            "trusted": {
                "plan_set_hash": "c" * 64,
                "inventory_sha256": {
                    repo: hashlib.sha256(
                        canonical_json_bytes({"repo_id": repo})
                    ).hexdigest()
                    for repo, _arm in EXPECTED_CELLS
                },
                "verifier_runtime": {"measurement": {}},
            },
        },
    )
    monkeypatch.setattr(operator, "verify_decision_contract", lambda value: value)
    monkeypatch.setattr(operator, "verify_configured_plan_set", lambda *_args: None)
    monkeypatch.setattr(operator, "validate_producer_plan", lambda value: value)
    monkeypatch.setattr(operator, "validate_receipt_inventory", lambda value: value)
    monkeypatch.setattr(
        operator, "verify_contract", lambda request: request["contract"]
    )
    monkeypatch.setattr(operator.time, "time_ns", lambda: now)
    callbacks = []
    monkeypatch.setattr(operator, "run_cell", lambda *_args: callbacks.append("cell"))
    args = SimpleNamespace(
        public_config=str(config_path),
        contracts_dir=str(contracts_dir),
        decision_contract=str(decision_path),
        staged_root=str(staged_root),
        authority_socket=str(tmp_path / "authority.sock"),
    )

    with pytest.raises(TimeoutError, match="closed serial budget"):
        operator._run_impl(args)

    assert callbacks == []


def test_authority_preflight_rejects_ambiguous_mount_without_state(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744627747: plan mount errors must precede reservation.
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
    # PR #1249 review 3744853003: deterministic host failures cannot consume a job.
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
    # PR #1249 review 3744853003: every producer controller must be available.
    authority, cgroup = _mock_authority_cgroup_host(tmp_path, monkeypatch)
    (cgroup / "cgroup.controllers").write_text("cpu memory pids", encoding="utf-8")

    with pytest.raises(ValueError, match="controllers are unavailable"):
        authority._preflight_cgroup_host()


def test_authority_requires_all_delegated_cgroup_controllers(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744853003: every producer controller must be delegated.
    authority, cgroup = _mock_authority_cgroup_host(tmp_path, monkeypatch)
    (cgroup / "cgroup.subtree_control").write_text("cpu memory pids", encoding="utf-8")

    with pytest.raises(ValueError, match="controllers are not delegated"):
        authority._preflight_cgroup_host()


def test_authority_requires_writable_cgroup_delegation(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744853003: the delegated hierarchy must accept a child.
    authority, _cgroup = _mock_authority_cgroup_host(tmp_path, monkeypatch)
    monkeypatch.setattr(authority.os, "access", lambda *_args: False)

    with pytest.raises(ValueError, match="delegation is not writable"):
        authority._preflight_cgroup_host()


def test_authority_response_recovery_uses_original_absolute_deadline(monkeypatch):
    # PR #1249 review 3744677879: recovery cannot renew a consumed request budget.
    from benchmarks.codegraph_compare import audit_authority_client as client

    observed = []
    ticks = iter((100.0, 101.0, 105.0))
    monkeypatch.setattr(client, "time", SimpleNamespace(monotonic=lambda: next(ticks)))

    def request(_request, _socket, _authority, timeout):
        observed.append(timeout)
        if len(observed) == 1:
            raise client._PostSendTransportError("lost")
        raise RuntimeError("recovery observed")

    monkeypatch.setattr(client, "_request_response", request)

    with pytest.raises(RuntimeError, match="recovery observed"):
        client.run_cell(
            {"job_id": "a" * 64},
            Path("/authority.sock"),
            {"wall_timeout_seconds": 10},
        )

    assert observed == [9.0, 5.0]


def test_authority_budget_includes_all_bounded_post_processing():
    # PR #1249 review 3744677882: preflight covers work after producer exit.
    from benchmarks.codegraph_compare.execution_budget import (
        authority_cell_budget_seconds,
    )

    assert (
        authority_cell_budget_seconds(
            {
                "wall_timeout_seconds": 10,
                "resource_ceilings": {"io_bytes": 32 * 1024 * 1024},
            }
        )
        == 1932
    )


@pytest.mark.parametrize("failure", ["connect", "send"])
def test_authority_retries_transport_failure_under_original_deadline(
    monkeypatch, failure: str
):
    # PR #1249 reviews 3744915224: no authority retry may renew the cell budget.
    from benchmarks.codegraph_compare import audit_authority_client as client

    observed: list[tuple[str, float]] = []
    ticks = iter((100.0, 101.0, 105.0))
    monkeypatch.setattr(client, "time", SimpleNamespace(monotonic=lambda: next(ticks)))

    def request(payload, _socket, _authority, timeout):
        observed.append((payload["operation"], timeout))
        if len(observed) == 1:
            error = (
                client._PreSendTransportError("not connected")
                if failure == "connect"
                else client._SendTransportError("ambiguous send")
            )
            raise error
        raise RuntimeError("bounded retry observed")

    monkeypatch.setattr(client, "_request_response", request)

    with pytest.raises(RuntimeError, match="bounded retry observed"):
        client.run_cell(
            {"job_id": "a" * 64},
            Path("/authority.sock"),
            {"wall_timeout_seconds": 10},
        )

    expected_operation = "run-cell" if failure == "connect" else "query-job-response"
    assert observed == [("run-cell", 9.0), (expected_operation, 5.0)]


def test_authority_cleanup_recovers_only_after_confirmed_absence(monkeypatch):
    # PR #1249 review 3744944754: ambiguous rm requires Docker+cgroup confirmation.
    from benchmarks.codegraph_compare import audit_authority_runner as authority

    calls = []

    def run(command, **_kwargs):
        calls.append(command)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(command, 120)
        return SimpleNamespace(
            returncode=1,
            stdout=b"",
            stderr=b"Error: No such object: producer",
        )

    monkeypatch.setattr(authority.subprocess, "run", run)

    authority._cleanup_producer("producer", Path("/missing/cgroup"))

    assert calls == [
        ["docker", "rm", "-f", "producer"],
        ["docker", "inspect", "producer"],
    ]


def test_authority_cleanup_unknown_state_is_process_fatal(monkeypatch):
    # PR #1249 review 3744944754: unconfirmed cleanup must fail-stop the service.
    from benchmarks.codegraph_compare import audit_authority_runner as authority

    ticks = iter((0.0, 0.0, 1.0, 1.0))
    monkeypatch.setattr(authority, "AUTHORITY_COMMAND_TIMEOUT_SECONDS", 0.5)
    monkeypatch.setattr(
        authority,
        "time",
        SimpleNamespace(
            monotonic=lambda: next(ticks),
            sleep=lambda _seconds: None,
        ),
    )
    monkeypatch.setattr(authority, "_docker_container_absent", lambda *_args: False)
    monkeypatch.setattr(
        authority.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1),
    )

    with pytest.raises(
        authority.AuthorityCleanupFatal,
        match="could not confirm Docker/cgroup absence",
    ):
        authority._cleanup_producer("producer", Path("/missing/cgroup"))


_mark_posix_qualification_section_tests()
