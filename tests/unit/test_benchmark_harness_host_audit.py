"""Issue #1376：test_benchmark_harness_host_audit 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import os
import sys
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.unit._benchmark_harness_platform import (
    mark_posix_qualification_section_tests,
)
from tests.unit._benchmark_harness_service_helpers import _diagnostic_authority_server

_POSIX_QUALIFICATION_SECTION_START = sys._getframe().f_lineno
_mark_posix_qualification_section_tests = partial(
    mark_posix_qualification_section_tests, globals()
)


def test_qualification_external_audit_protocol_verifies_exact_signed_request(
    tmp_path: Path, monkeypatch
):
    # Mutation 5 (2026-08-10): 只有外部 Unix authority 可以授权审计。
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import audit_authority_client
    from benchmarks.codegraph_compare.host_auditor import DOMAIN, _authority

    monkeypatch.setattr(
        audit_authority_client,
        "_peer_credentials",
        lambda client: (1, os.getuid(), os.getgid()),
    )
    key = b"\x33" * 32
    socket_path = Path("/tmp") / f"tsa-audit-{os.getpid()}-{tmp_path.name[-6:]}.sock"
    thread = _diagnostic_authority_server(socket_path, key)
    authority = {
        "key_id": "auditor",
        "public_key_hex": Ed25519PrivateKey.from_private_bytes(key)
        .public_key()
        .public_bytes_raw()
        .hex(),
        "peer_uid": os.getuid(),
    }
    request = {
        "protocol": "no1-008a-audit-v1",
        "phase": "terminal",
        "service_measurement": "d" * 64,
        "audit": {"producer_container_id": "immutable-id"},
    }
    envelope = _authority(request, socket_path, authority, DOMAIN)
    thread.join(timeout=5)
    assert envelope["audit"] == request


def test_qualification_external_audit_accepts_early_response_close(
    tmp_path: Path, monkeypatch
):
    # GH-1253：authority 关闭响应后，macOS 可能报告 ENOTCONN。
    import errno
    import socket

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import audit_authority_client
    from benchmarks.codegraph_compare.host_auditor import DOMAIN, _authority

    monkeypatch.setattr(
        audit_authority_client,
        "_peer_credentials",
        lambda client: (1, os.getuid(), os.getgid()),
    )
    key = b"\x33" * 32
    socket_path = Path("/tmp") / f"tsa-early-{os.getpid()}-{tmp_path.name[-6:]}.sock"
    thread = _diagnostic_authority_server(socket_path, key)
    real_socket = socket.socket

    class ShutdownRaceSocket:
        def __init__(self, *args, **kwargs):
            self._socket = real_socket(*args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._socket, name)

        def shutdown(self, _how):
            raise OSError(errno.ENOTCONN, "authority already closed")

    monkeypatch.setattr(audit_authority_client.socket, "socket", ShutdownRaceSocket)
    authority = {
        "key_id": "auditor",
        "public_key_hex": Ed25519PrivateKey.from_private_bytes(key)
        .public_key()
        .public_bytes_raw()
        .hex(),
        "peer_uid": os.getuid(),
    }
    request = {
        "protocol": "no1-008a-audit-v1",
        "phase": "terminal",
        "service_measurement": "d" * 64,
        "audit": {"producer_container_id": "immutable-id"},
    }

    envelope = _authority(request, socket_path, authority, DOMAIN)
    thread.join(timeout=5)

    assert envelope["audit"] == request


def test_qualification_external_audit_protocol_rejects_forged_reply(
    tmp_path: Path, monkeypatch
):
    # Mutation 5 (2026-08-10): 没有固定密钥的 socket 端点不具备授权能力。
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import audit_authority_client
    from benchmarks.codegraph_compare.host_auditor import DOMAIN, _authority

    monkeypatch.setattr(
        audit_authority_client,
        "_peer_credentials",
        lambda client: (1, os.getuid(), os.getgid()),
    )
    socket_path = Path("/tmp") / f"tsa-forge-{os.getpid()}-{tmp_path.name[-6:]}.sock"
    thread = _diagnostic_authority_server(socket_path, b"\x55" * 32)
    authority = {
        "key_id": "auditor",
        "public_key_hex": Ed25519PrivateKey.from_private_bytes(b"\x33" * 32)
        .public_key()
        .public_bytes_raw()
        .hex(),
        "peer_uid": os.getuid(),
    }
    request = {
        "protocol": "no1-008a-audit-v1",
        "phase": "terminal",
        "service_measurement": "d" * 64,
        "audit": {},
    }
    with pytest.raises(ValueError, match="signature mismatch"):
        _authority(request, socket_path, authority, DOMAIN)
    thread.join(timeout=5)


def test_qualification_host_auditor_rejects_local_private_key_cli():
    # Mutation 5 (2026-08-10): 生产环境没有本地 auditor 密钥的兼容路径。
    from benchmarks.codegraph_compare.host_auditor import main

    with pytest.raises(SystemExit) as error:
        main(
            [
                "launch",
                "--container",
                "container",
                "--seccomp",
                "/seccomp",
                "--expected-image",
                "image@sha256:" + "1" * 64,
                "--authority-socket",
                "/authority.sock",
                "--public-config",
                "/config.json",
                "--since",
                "1",
                "--run-nonce",
                "2" * 64,
                "--private-key",
                "/local/auditor.key",
            ]
        )
    assert error.value.code == 2


def test_qualification_host_auditor_checks_root_pinned_top_level_image_id():
    # Mutation 5 (2026-08-10): 仅凭 Config.Image 不能授权容器。
    from benchmarks.codegraph_compare.host_auditor import _docker_facts

    inspected = {
        "Image": "sha256:" + "9" * 64,
        "Config": {"Image": "producer@sha256:" + "1" * 64, "User": "65532:65532"},
        "HostConfig": {
            "ReadonlyRootfs": True,
            "CapDrop": ["ALL"],
            "NetworkMode": "none",
            "SecurityOpt": ["no-new-privileges", "seccomp=/trusted/seccomp"],
            "PidsLimit": 64,
            "Memory": 4294967296,
            "NanoCpus": 1000000000,
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=64m"},
        },
    }
    with pytest.raises(ValueError, match="top-level Image ID"):
        _docker_facts(
            inspected,
            "producer@sha256:" + "1" * 64,
            "sha256:" + "8" * 64,
            Path("/trusted/seccomp"),
        )


def test_qualification_host_auditor_preserves_exact_observed_security_options():
    # PR #1249 review 3745026819: 终态证据来自观测，而不是合成。
    from benchmarks.codegraph_compare.host_auditor import (
        PRODUCER_GATE_TARGET,
        PRODUCER_GATE_WRAPPER,
        _docker_facts,
    )

    image = "producer@sha256:" + "1" * 64
    image_id = "sha256:" + "8" * 64
    inspected = {
        "Image": image_id,
        "Config": {
            "Image": image,
            "User": "65532:65532",
            "Entrypoint": ["/bin/sh"],
            "Cmd": [
                "-c",
                PRODUCER_GATE_WRAPPER,
                "no1-008a-gate",
                PRODUCER_GATE_TARGET,
                "--plan",
                "/plan/cell-plan.json",
                "--out",
                "/out",
            ],
        },
        "HostConfig": {
            "ReadonlyRootfs": True,
            "CapDrop": ["ALL"],
            "NetworkMode": "none",
            "SecurityOpt": ["no-new-privileges", "seccomp=/trusted/seccomp"],
            "PidsLimit": 64,
            "Memory": 4294967296,
            "NanoCpus": 1000000000,
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=64m"},
        },
    }

    assert _docker_facts(inspected, image, image_id, Path("/trusted/seccomp"))[
        "security_opt"
    ] == ["no-new-privileges", "seccomp=/trusted/seccomp"]


def test_qualification_host_auditor_rejects_extra_security_option():
    # PR #1249 review 3745026819: 未请求的 Docker 隔离选项必须失败关闭。
    from benchmarks.codegraph_compare.host_auditor import (
        PRODUCER_GATE_TARGET,
        PRODUCER_GATE_WRAPPER,
        _docker_facts,
    )

    image = "producer@sha256:" + "1" * 64
    inspected = {
        "Image": "sha256:" + "8" * 64,
        "Config": {
            "Image": image,
            "User": "65532:65532",
            "Entrypoint": ["/bin/sh"],
            "Cmd": [
                "-c",
                PRODUCER_GATE_WRAPPER,
                "no1-008a-gate",
                PRODUCER_GATE_TARGET,
                "--plan",
                "/plan/cell-plan.json",
                "--out",
                "/out",
            ],
        },
        "HostConfig": {
            "ReadonlyRootfs": True,
            "CapDrop": ["ALL"],
            "NetworkMode": "none",
            "SecurityOpt": [
                "no-new-privileges",
                "seccomp=/trusted/seccomp",
                "label=disable",
            ],
            "PidsLimit": 64,
            "Memory": 4294967296,
            "NanoCpus": 1000000000,
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=64m"},
        },
    }

    with pytest.raises(ValueError, match="security facts mismatch"):
        _docker_facts(
            inspected,
            image,
            "sha256:" + "8" * 64,
            Path("/trusted/seccomp"),
        )


def test_host_auditor_accepts_only_all_eight_exact_producer_bind_mounts(
    tmp_path: Path,
    monkeypatch,
):
    # PR #1249 review 3744261017: 经过认证的工具、配置和 seccomp 挂载都是必需的。
    from benchmarks.codegraph_compare.host_auditor import _mounts
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    staged = tmp_path / "staged"
    artifact = tmp_path / "artifact"
    staged.mkdir()
    artifact.mkdir()
    source = artifact / "source"
    output = artifact / "producer-output"
    gate = artifact / "producer-launch-gate"
    source.mkdir()
    output.mkdir()
    os.mkfifo(gate, mode=0o444)
    plan = {
        "executions": [
            {
                "id": name,
                "argv": [
                    "/tool/bin",
                    name,
                    "--config",
                    "/config/pinned.json",
                    *(["--source", "/source"] if name == "build" else []),
                ],
            }
            for name in ("delete", "build", "health", "symbol", "call")
        ]
    }
    sources = {
        "/source": source,
        "/tool/bin": staged / "tool",
        "/config/pinned.json": staged / "config",
        "/plan/seccomp.json": staged / "seccomp",
        "/plan/cell-plan.json": staged / "plan.json",
        "/plan/inventory.json": staged / "inventory.json",
        "/run/no1-008a-launch-gate": gate,
        "/out": output,
    }
    for target in sources.values():
        if not target.exists():
            target.write_bytes(b"x")
    sources["/plan/cell-plan.json"].write_bytes(canonical_json_bytes(plan))
    inspected = {
        "Mounts": [
            {
                "Type": "bind",
                "Source": str(source_path),
                "Destination": target,
                "RW": target == "/out",
                "Propagation": "rprivate",
            }
            for target, source_path in sources.items()
        ]
    }

    real_lstat = os.lstat

    def authority_lstat(path):
        metadata = real_lstat(path)
        if Path(path) == gate:
            return SimpleNamespace(
                st_mode=metadata.st_mode, st_uid=0, st_nlink=metadata.st_nlink
            )
        return metadata

    monkeypatch.setattr(
        "benchmarks.codegraph_compare.host_auditor.os.lstat", authority_lstat
    )
    assert set(_mounts(inspected)) == set(sources)
    inspected["Mounts"][1]["Source"] = str(staged / "config")
    with pytest.raises(ValueError, match="authenticated mount source mismatch"):
        _mounts(inspected)


_mark_posix_qualification_section_tests()
