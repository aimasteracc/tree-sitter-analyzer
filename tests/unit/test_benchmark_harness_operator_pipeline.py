"""Issue #1376：test_benchmark_harness_operator_pipeline 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from functools import partial
from pathlib import Path

import pytest

from tests.unit._benchmark_harness_platform import (
    mark_posix_qualification_section_tests,
)

_POSIX_QUALIFICATION_SECTION_START = sys._getframe().f_lineno
_mark_posix_qualification_section_tests = partial(
    mark_posix_qualification_section_tests, globals()
)


def test_producer_refuses_self_reported_collector_evidence():
    import pytest

    from benchmarks.codegraph_compare.setup_qualification import produce_strict_cell

    with pytest.raises(RuntimeError, match="NOT_EVALUATED"):
        produce_strict_cell(collector=object())


def test_qualification_operator_contract_is_exact_closed_service_pipeline():
    completed = subprocess.run(
        ["bash", "scripts/no1_008a_operator.sh", "contract"],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert result == {
        "schema_version": 1,
        "cells": 14,
        "attempts_per_cell": 1,
        "max_concurrency": 1,
        "roles": [
            "producer",
            "auditor",
            "executor",
            "approver",
            "verifier",
            "decision-consumer",
        ],
        "qualification": "production-verifier-exact-14-only",
    }


def test_qualification_operator_dry_run_emits_each_cell_once():
    completed = subprocess.run(
        ["bash", "scripts/no1_008a_operator.sh", "dry-run"],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = [json.loads(line) for line in completed.stdout.splitlines()]
    identities = [(row["repo_id"], row["arm_id"], row["attempt"]) for row in rows]
    from benchmarks.codegraph_compare.setup_qualification import EXPECTED_CELLS

    assert identities == [(repo, arm, 1) for repo, arm in EXPECTED_CELLS]


def test_qualification_seccomp_denies_exact_network_syscall_set():
    profile = json.loads(
        Path("scripts/no1_008a_no_network_seccomp.json").read_text(encoding="utf-8")
    )
    assert profile["syscalls"] == [
        {
            "names": [
                "socket",
                "socketpair",
                "connect",
                "bind",
                "listen",
                "accept",
                "accept4",
                "sendto",
                "sendmsg",
                "recvfrom",
                "recvmsg",
            ],
            "action": "SCMP_ACT_ERRNO",
            "errnoRet": 1,
        }
    ]


def test_all_service_sockets_defer_access_control_to_peer_uid():
    # PR #1249 review 3744303010: 服务的主组与 operator 的主组不同。
    sources = {
        path: Path(path).read_text(encoding="utf-8")
        for path in (
            "benchmarks/codegraph_compare/audit_authority_service.py",
            "benchmarks/codegraph_compare/receipt_v3_service.py",
            "benchmarks/codegraph_compare/verifier_service.py",
            "benchmarks/codegraph_compare/decision_consumer_service.py",
        )
    }

    assert {
        path: (source.count("0o666"), source.count("peer_allowed("))
        for path, source in sources.items()
    } == {
        "benchmarks/codegraph_compare/audit_authority_service.py": (1, 1),
        "benchmarks/codegraph_compare/receipt_v3_service.py": (1, 1),
        "benchmarks/codegraph_compare/verifier_service.py": (1, 1),
        "benchmarks/codegraph_compare/decision_consumer_service.py": (1, 1),
    }


def test_no1_008a_wrapper_forwards_decision_service_inputs(tmp_path: Path):
    # PR #1249 review 3744178808: 文档中的包装脚本丢弃了必需输入。
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "argv"
    python = fake_bin / "python3"
    python.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = - ]; then cat >/dev/null; exit 0; fi\n'
        'printf \'%s\\n\' "$@" > "$CAPTURE"\n',
        encoding="utf-8",
    )
    python.chmod(0o755)
    realpath = fake_bin / "realpath"
    realpath.write_text(
        "#!/bin/sh\n"
        '[ "$1" = -e ] && shift\n'
        '[ "$1" = -- ] && shift\n'
        "printf '%s\\n' \"$1\"\n",
        encoding="utf-8",
    )
    realpath.chmod(0o755)
    paths = {}
    for name in ("contracts", "staged"):
        paths[name] = tmp_path / name
        paths[name].mkdir()
    for name in (
        "authority.sock",
        "executor.sock",
        "approver.sock",
        "verifier.sock",
        "decision.sock",
        "decision.json",
        "config.json",
    ):
        paths[name] = tmp_path / name
        paths[name].write_bytes(b"{}")
    command = [
        "bash",
        "scripts/no1_008a_operator.sh",
        "run",
        "--contracts-dir",
        str(paths["contracts"]),
        "--authority-socket",
        str(paths["authority.sock"]),
        "--executor-socket",
        str(paths["executor.sock"]),
        "--approver-socket",
        str(paths["approver.sock"]),
        "--verifier-socket",
        str(paths["verifier.sock"]),
        "--decision-consumer-socket",
        str(paths["decision.sock"]),
        "--decision-contract",
        str(paths["decision.json"]),
        "--public-config",
        str(paths["config.json"]),
        "--staged-root",
        str(paths["staged"]),
        "--experiment-root",
        str(tmp_path / "experiment"),
    ]
    environment = {**os.environ, "CAPTURE": str(capture)}
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"

    result = subprocess.run(command, env=environment, capture_output=True, text=True)

    assert result.returncode == 0
    argv = capture.read_text(encoding="utf-8").splitlines()
    assert argv[argv.index("--decision-consumer-socket") + 1] == str(
        paths["decision.sock"]
    )
    assert argv[argv.index("--decision-contract") + 1] == str(paths["decision.json"])


def test_no1_008a_dockerfile_has_independent_decision_consumer_target():
    # PR #1249 review 3744178814: 最终 decision 服务曾无法构建。
    dockerfile = Path("benchmarks/codegraph_compare/Dockerfile.no1-008a").read_text(
        encoding="utf-8"
    )
    target = dockerfile.split("FROM runtime AS decision-consumer\n", 1)[1]
    assert 'org.tree-sitter-analyzer.no1-008a.role="decision-consumer"' in target
    assert "USER 904:904" in target
    assert (
        'ENTRYPOINT ["python", "-m", '
        '"benchmarks.codegraph_compare.decision_consumer_service"]'
    ) in target


def test_receipt_image_provenance_excludes_post_decision_consumer():
    # PR #1249 review 3744178824: receipt-v3 精确签署决策前的五个角色。
    from benchmarks.codegraph_compare.verifier_evidence import _receipt_images

    images = {
        role: f"sha256:{number:064x}"
        for number, role in enumerate(
            (
                "producer",
                "executor",
                "approver",
                "auditor",
                "verifier",
                "decision_consumer",
            ),
            start=1,
        )
    }

    assert _receipt_images({"images": images}) == {
        role: images[role]
        for role in ("producer", "executor", "approver", "auditor", "verifier")
    }


def test_launch_attestation_handoff_uses_private_role_owned_paths(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744358508: 不同服务 UID 只能读取各自的产物。
    from benchmarks.codegraph_compare import service_runtime

    output = tmp_path / "handoff"
    public = tmp_path / "public.json"
    public.write_bytes(b"{}")
    descriptor = os.open(os.devnull, os.O_RDONLY)
    monkeypatch.setattr(service_runtime.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        service_runtime, "secure_key", lambda *_args: (descriptor, b"\x31" * 32)
    )
    monkeypatch.setattr(
        "benchmarks.codegraph_compare.verifier.parse_public_config", lambda _raw: {}
    )
    monkeypatch.setattr(
        service_runtime,
        "create_service_launch_attestation",
        lambda _container, role, *_args: {"role": role},
    )
    directory_owners = []
    file_owners = []
    monkeypatch.setattr(
        service_runtime.os,
        "chown",
        lambda path, uid, gid: directory_owners.append((Path(path).name, uid, gid)),
    )
    monkeypatch.setattr(
        service_runtime.os,
        "fchown",
        lambda _fd, uid, gid: file_owners.append((uid, gid)),
    )
    mappings = [
        item
        for role in ("executor", "approver", "auditor", "verifier", "decision_consumer")
        for item in ("--container", f"{role}=container-{role}")
    ]
    assert (
        service_runtime.main(
            [
                "attest-launch",
                "--public-config",
                str(public),
                "--private-key",
                "key",
                "--key-id",
                "launcher",
                "--output-dir",
                str(output),
                *mappings,
            ]
        )
        == 0
    )

    expected = {
        "executor": 901,
        "approver": 902,
        "auditor": 0,
        "verifier": 903,
        "decision_consumer": 904,
    }
    assert stat.S_IMODE(output.stat().st_mode) == 0o711
    assert {
        name: stat.S_IMODE((output / name).stat().st_mode) for name in expected
    } == dict.fromkeys(expected, 448)
    assert {
        name: stat.S_IMODE((output / name / "launch-attestation.json").stat().st_mode)
        for name in expected
    } == dict.fromkeys(expected, 256)
    assert directory_owners == [
        (name, expected[name], expected[name]) for name in sorted(expected)
    ]
    assert {
        name: stat.S_IMODE((output / name / "RELEASE").stat().st_mode)
        for name in expected
    } == dict.fromkeys(expected, 256)
    assert sorted(file_owners) == sorted(
        (uid, uid) for uid in expected.values() for _artifact in range(2)
    )


def test_exact14_manifest_preflight_counts_outer_json_escaping_and_rejects_ceiling(
    monkeypatch,
):
    # PR #1249 review 3744728248: 帧检查失败必须先于首个 cell。
    from benchmarks.codegraph_compare import verifier_service

    cells = [({"p": '"'}, {"i": "\\"}, {"c": 1}) for _ in range(14)]

    assert verifier_service.exact14_manifest_preflight_bound(cells) == 29_364_798
    monkeypatch.setattr(verifier_service, "MAX_FRAME", 29_364_797)
    with pytest.raises(ValueError, match="protocol ceiling"):
        verifier_service.preflight_exact14_manifest(cells)


def test_exact14_budget_uses_sealed_image_extractions_not_producer_wall():
    # PR #1249 review 3744776113: authority 之后的服务工作使用镜像界限。
    from benchmarks.codegraph_compare.execution_budget import (
        exact14_execution_budget_seconds,
    )

    plans = {
        ("repo", "arm"): {
            "wall_timeout_seconds": 1,
            "resource_ceilings": {"io_bytes": 16 * 1024 * 1024},
        }
    }

    assert exact14_execution_budget_seconds(plans) == 3120


def test_exact14_manifest_preflight_rejects_node_budget_before_wire(monkeypatch):
    # PR #1249 review 3744822109: 满足字节限制的 manifest 仍需要精确节点计量。
    from benchmarks.codegraph_compare import verifier_service

    cells = [({"p": 1}, {"i": 1}, {"c": 1}) for _ in range(14)]
    monkeypatch.setattr(verifier_service, "MANIFEST_MAX_NODES", 1_400_101)

    with pytest.raises(ValueError, match="complexity exceeds protocol ceiling"):
        verifier_service.preflight_exact14_manifest(cells)


def test_operator_recomputes_configured_plan_set_before_authority_calls():
    # PR #1249 review 3744915238: 过期的聚合哈希必须在消耗 cell 前失败。
    source = Path("benchmarks/codegraph_compare/qualification_operator.py").read_text(
        encoding="utf-8"
    )

    assert source.count("verify_configured_plan_set(decision_contract, config)") == 1
    assert source.index(
        "verify_configured_plan_set(decision_contract, config)"
    ) < source.index("authority = run_cell(")


_mark_posix_qualification_section_tests()
