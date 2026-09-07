"""Issue #1376：test_benchmark_harness_service_runtime_schema 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import hashlib
import json
import os as os
import struct
import subprocess
import sys
from functools import partial
from pathlib import Path

import pytest

from tests.unit._benchmark_harness_platform import (
    mark_posix_qualification_section_tests,
)
from tests.unit._benchmark_harness_service_helpers import (
    _qualification_v3_body,
    _qualification_v3_public_config,
    _qualification_v3_receipt,
)

_POSIX_QUALIFICATION_SECTION_START = sys._getframe().f_lineno
_mark_posix_qualification_section_tests = partial(
    mark_posix_qualification_section_tests, globals()
)


def test_qualification_v3_verity_command_binds_both_image_hashes(tmp_path: Path):
    # Audit 2026-08-09 B3: 全新的 verifier 必须自行认证数据镜像和哈希镜像。
    from benchmarks.codegraph_compare.verifier import _verify_verity

    data = tmp_path / "data.img"
    hashes = tmp_path / "hash.img"
    data.write_bytes(b"data")
    hashes.write_bytes(b"hash")
    body = _qualification_v3_body()
    snapshot = body["snapshot"]
    snapshot.update(
        {
            "data_image_size": 4,
            "data_image_sha256": hashlib.sha256(b"data").hexdigest(),
            "hash_image_size": 4,
            "hash_image_sha256": hashlib.sha256(b"hash").hexdigest(),
        }
    )
    commands = []

    def runner(command):
        commands.append(list(command))
        return subprocess.CompletedProcess(command, 0, b"", b"")

    _verify_verity(
        body,
        {"data_image": str(data.resolve()), "hash_image": str(hashes.resolve())},
        runner,
    )
    normalized = [
        [
            "/proc/self/fd/<open>" if part.startswith("/proc/self/fd/") else part
            for part in command
        ]
        for command in commands
    ]
    assert normalized == [
        [
            "veritysetup",
            "verify",
            "/proc/self/fd/<open>",
            "/proc/self/fd/<open>",
            "0" * 64,
            "--hash",
            "sha256",
            "--salt",
            "1" * 64,
            "--data-block-size",
            "4096",
            "--hash-block-size",
            "4096",
            "--data-blocks",
            "1",
        ]
    ]


def test_qualification_v3_verity_rejects_mutated_hash_image(tmp_path: Path):
    # Audit 2026-08-09 B3: 任一镜像被修改，都必须在提取前失败。
    from benchmarks.codegraph_compare.verifier import _verify_verity

    data = tmp_path / "data.img"
    hashes = tmp_path / "hash.img"
    data.write_bytes(b"data")
    hashes.write_bytes(b"mutated")
    body = _qualification_v3_body()
    body["snapshot"].update(
        {
            "data_image_size": 4,
            "data_image_sha256": hashlib.sha256(b"data").hexdigest(),
            "hash_image_size": 4,
            "hash_image_sha256": hashlib.sha256(b"hash").hexdigest(),
        }
    )
    with pytest.raises(ValueError, match="image digest"):
        _verify_verity(
            body,
            {"data_image": str(data.resolve()), "hash_image": str(hashes.resolve())},
            lambda command: subprocess.CompletedProcess(command, 0, b"", b""),
        )


def test_qualification_v3_run_correlation_requires_process_isolation():
    # Audit 2026-08-09 P1.3: 退出码绝不能作为进程身份。
    from benchmarks.codegraph_compare.verifier import verify_cell

    receipt = _qualification_v3_receipt()
    body = receipt["body"]
    failures = verify_cell(
        receipt,
        public_config=_qualification_v3_public_config(),
        plan={},
        inventory={},
        evidence={},
        verifier_nonce="a" * 64,
        verifier_image_digest=body["process_audit"]["image_digest"],
        process_identity="fresh-process",
        diagnostic_mode=True,
        diagnostic_root_public_key=__import__(
            "cryptography.hazmat.primitives.asymmetric.ed25519",
            fromlist=["Ed25519PrivateKey"],
        )
        .Ed25519PrivateKey.from_private_bytes(b"\x44" * 32)
        .public_key()
        .public_bytes_raw(),
    )
    assert failures == (
        "CELL_EVIDENCE_INVALID:verifier process is not isolated from producer",
    )


def test_qualification_v3_runtime_requires_exact_five_execution_order():
    # Audit 2026-08-09 P2.1: 运行时与 schema 固定完全相同的执行数量。
    from benchmarks.codegraph_compare.receipt_v3 import validate_body

    body = _qualification_v3_body()
    body["executions"].pop()
    with pytest.raises(ValueError, match="exact delete"):
        validate_body(body)


def test_qualification_v3_decision_commit_disconnect_queries_original_receipt(
    monkeypatch,
):
    # Audit 2026-08-09 B2: 提交后的 EOF 必须走幂等查询路径。
    import json

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import decision_consumer_service as consumer
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    config = _qualification_v3_public_config()
    contract = {"decision_id": "d" * 64, "issued_at_ns": 0, "expires_at_ns": 2}
    envelope = {"manifest_sha256": "e" * 64}
    body = {
        "schema_version": 1,
        "decision_id": contract["decision_id"],
        "decision_contract_sha256": hashlib.sha256(
            canonical_json_bytes(contract)
        ).hexdigest(),
        "manifest_sha256": envelope["manifest_sha256"],
        "verdict_status": "SETUP_QUALIFIED",
        "consumed_at_ns": 1,
        "service_identity": config["trusted"]["decision_consumer_runtime"][
            "measurement"
        ],
    }
    receipt = {
        "receipt": body,
        "key_id": config["decision_consumer"]["key_id"],
        "algorithm": "Ed25519",
        "signature": Ed25519PrivateKey.from_private_bytes(b"\x66" * 32)
        .sign(consumer.RECEIPT_DOMAIN + canonical_json_bytes(body))
        .hex(),
    }
    requests = []

    class FakeSocket:
        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            pass

        def getsockopt(self, _level, _option, _size):
            return struct.pack("3i", 123, config["decision_consumer"]["peer_uid"], 123)

        def send(self, framed):
            requests.append(json.loads(framed[4:]))
            return len(framed)

        def shutdown(self, _how):
            pass

        def close(self):
            pass

    replies = iter(
        (ValueError("frame truncated"), {"status": "consumed", "receipt": receipt})
    )

    def read_reply(*_args):
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(consumer.socket, "SO_PEERCRED", 1, raising=False)
    monkeypatch.setattr(consumer.socket, "socket", lambda *_args: FakeSocket())
    monkeypatch.setattr(consumer, "read_frame", read_reply)

    assert (
        consumer.request_decision(
            socket_path=Path("/unused"),
            contract=contract,
            envelope=envelope,
            config=config,
            timeout=1,
        )
        == receipt
    )
    assert [request["operation"] for request in requests] == [
        "consume-decision",
        "query-decision",
    ]
    assert requests[1]["decision_id"] == contract["decision_id"]


def test_qualification_v3_runtime_schema_acceptance_parity():
    # Audit 2026-08-09 P2.1: 已发布 schema 与运行时必须接受同一份实际生成的 receipt。
    from benchmarks.codegraph_compare.receipt_v3 import validate_receipt_shape

    receipt = _qualification_v3_receipt()
    validate_receipt_shape(receipt)


def test_qualification_v3_runtime_schema_mutation_contract():
    # Audit 2026-08-09 P2.1: 代表性的结构变异必须得到完全一致的解析结果。
    import copy

    from jsonschema import Draft202012Validator

    from benchmarks.codegraph_compare.receipt_v3 import (
        _published_schema,
        validate_receipt_shape,
    )

    schema, registry = _published_schema()
    validator = Draft202012Validator(schema, registry=registry)
    mutations = []
    missing = copy.deepcopy(_qualification_v3_receipt())
    del missing["body"]["run_nonce"]
    mutations.append(missing)
    extra = copy.deepcopy(_qualification_v3_receipt())
    extra["body"]["snapshot"]["mount_flags"] = ["ro"]
    mutations.append(extra)
    order = copy.deepcopy(_qualification_v3_receipt())
    order["body"]["executions"][0]["id"] = "health"
    mutations.append(order)
    duplicate = copy.deepcopy(_qualification_v3_receipt())
    duplicate["body"]["index_partition"]["indexed_paths"] *= 2
    mutations.append(duplicate)
    outcomes = []
    for receipt in mutations:
        try:
            validate_receipt_shape(receipt)
            runtime = True
        except ValueError:
            runtime = False
        schema_valid = not tuple(validator.iter_errors(receipt))
        outcomes.append((runtime, schema_valid))
    assert outcomes == [(False, False), (False, False), (False, False), (False, False)]


def test_receipt_v3_rejects_an_eighth_mount_with_wrong_target():
    # PR #1249 review 3744439666: 启动 gate 精确创建八个目标。
    from benchmarks.codegraph_compare.receipt_v3 import validate_receipt_shape

    receipt = _qualification_v3_receipt()
    receipt["body"]["process_audit"]["mounts"][6][1] = "/unexpected"

    with pytest.raises(ValueError, match="mount"):
        validate_receipt_shape(receipt)


def test_receipt_v3_rejects_writable_non_output_mount():
    # PR #1249 review 3744302996: 只有生产者输出挂载可写。
    from benchmarks.codegraph_compare.receipt_v3 import validate_receipt_shape

    receipt = _qualification_v3_receipt()
    receipt["body"]["process_audit"]["mounts"][0][2] = False

    with pytest.raises(ValueError, match="mount"):
        validate_receipt_shape(receipt)


def test_receipt_v3_docker_context_allows_only_five_schema_refs():
    # PR #1249 review 3744303008: 运行时 schema 的 COPY 必须具有精确的依赖闭包。
    negations = [
        line
        for line in Path(".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.startswith("!rfcs")
    ]

    assert negations == [
        "!rfcs/",
        "!rfcs/schemas/",
        "!rfcs/schemas/no1-008a-cell-receipt-v3.schema.json",
        "!rfcs/schemas/no1-008a-cell-receipt-v3-body.schema.json",
        "!rfcs/schemas/no1-008a-cell-receipt-v3-common.schema.json",
        "!rfcs/schemas/no1-008a-cell-receipt-v3-fields-a.schema.json",
        "!rfcs/schemas/no1-008a-cell-receipt-v3-fields-b.schema.json",
    ]


def test_public_config_v6_published_schema_accepts_runtime_config():
    # PR #1249 review 3744482399: 两种接口中的 trusted 都是同一个封闭对象。
    from jsonschema import Draft202012Validator

    schema = json.loads(
        Path(
            "benchmarks/codegraph_compare/published_schemas/public-config-v6.schema.json"
        ).read_bytes()
    )
    config = _qualification_v3_public_config()

    assert list(Draft202012Validator(schema).iter_errors(config)) == []


def test_public_config_v6_schema_and_runtime_reject_extra_trusted_field():
    # PR #1249 review 3744482399: schema 和解析器都不允许 trusted 扩展字段。
    import copy

    from jsonschema import Draft202012Validator

    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes
    from benchmarks.codegraph_compare.verifier import parse_public_config

    schema = json.loads(
        Path(
            "benchmarks/codegraph_compare/published_schemas/public-config-v6.schema.json"
        ).read_bytes()
    )
    config = copy.deepcopy(_qualification_v3_public_config())
    config["trusted"]["untrusted_extension"] = "0" * 64
    diagnostic = copy.deepcopy(config)
    diagnostic.pop("root_signature")

    with pytest.raises(
        ValueError, match="trusted config has unknown or missing fields"
    ):
        parse_public_config(canonical_json_bytes(diagnostic), diagnostic_mode=True)
    assert len(list(Draft202012Validator(schema).iter_errors(config))) == 1


def test_service_launch_schema_matches_process_identity_shape():
    # PR #1249 review 3744516431: 发布的进程字段必须匹配 _proc_identity()。
    from jsonschema import Draft202012Validator

    schema = json.loads(
        Path(
            "benchmarks/codegraph_compare/published_schemas/service-launch-v1.schema.json"
        ).read_bytes()
    )
    process = {
        "host_pid": 123,
        "container_pid": 1,
        "starttime": "456",
        "cgroup": "0::/container",
        "executable": "/usr/bin/python3",
        "executable_sha256": "a" * 64,
        "cmdline": ["python", "-m", "service"],
        "namespaces": {
            name: f"{name}:[1]"
            for name in ("mnt", "pid", "net", "user", "uts", "ipc", "cgroup")
        },
        "capabilities": dict.fromkeys(
            ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"),
            "0000000000000000",
        ),
        "no_new_privs": "1",
        "seccomp": "2",
        "seccomp_filters": "1",
    }
    attestation = {
        "container_id": "b" * 64,
        "role": "verifier",
        "image_id": "sha256:" + "c" * 64,
        "cmd": ["python"],
        "entrypoint": None,
        "user": "903",
        "readonly_rootfs": True,
        "mounts": [],
        "network_mode": "none",
        "security_opt": [],
        "process": process,
    }
    envelope = {
        "attestation": attestation,
        "key_id": "auditor",
        "algorithm": "Ed25519",
        "signature": "d" * 128,
    }

    assert list(Draft202012Validator(schema).iter_errors(envelope)) == []


_mark_posix_qualification_section_tests()
