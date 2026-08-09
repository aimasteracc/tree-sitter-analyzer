"""External exact-14 verifier service and authenticated Unix client."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import stat
import struct
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from benchmarks.codegraph_compare.audit_authority_service import verify_contract
from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    strict_json_loads,
)
from benchmarks.codegraph_compare.receipt_v3_service import _paths, _verify_authority
from benchmarks.codegraph_compare.service_runtime import (
    measure_runtime,
    peer_allowed,
    read_frame,
    secure_key,
    verify_service_launch_attestation,
    wait_for_launch_release,
)
from benchmarks.codegraph_compare.setup_qualification_plan import EXPECTED_CELLS
from benchmarks.codegraph_compare.verifier import parse_public_config
from benchmarks.codegraph_compare.verifier_aggregate import (
    _validate_verdict_schema,
    aggregate_verdict,
)
from benchmarks.codegraph_compare.verifier_ledger import ChallengeLedger

MAX_FRAME = 64 * 1024 * 1024
READ_DEADLINE_SECONDS = 10
VERDICT_DOMAIN = b"NO1-008A-EXTERNAL-VERIFIER-VERDICT-V2\0"
CHALLENGE_DOMAIN = b"NO1-008A-EXTERNAL-VERIFIER-CHALLENGE-V1\0"
LEDGER_DOMAIN = b"NO1-008A-EXTERNAL-VERIFIER-LEDGER-V1\0"
_HEX = frozenset("0123456789abcdef")
MANIFEST_MAX_DEPTH = 64
MANIFEST_MAX_NODES = 4_000_000


class _PostSendTransportError(Exception):
    """A request was fully sent but its response transport did not complete."""


def _manifest_json_loads(payload: bytes) -> dict[str, Any]:
    """Parse verifier frames with protocol bounds independent of receipt limits."""
    if type(payload) is not bytes or not payload or len(payload) > MAX_FRAME:
        raise ValueError("manifest JSON byte size is invalid")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON member: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number rejected: {value}")

    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs,
            parse_constant=reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid manifest JSON") from error
    if type(value) is not dict:
        raise ValueError("manifest frame must be a JSON object")
    nodes = 0
    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MANIFEST_MAX_NODES or depth > MANIFEST_MAX_DEPTH:
            raise ValueError("manifest JSON complexity limit exceeded")
        if type(item) is str:
            if len(item.encode("utf-8")) > MAX_FRAME:
                raise ValueError("manifest JSON string limit exceeded")
        elif type(item) is list:
            stack.extend((child, depth + 1) for child in item)
        elif type(item) is dict:
            stack.extend((child, depth + 1) for child in item.values())
        elif type(item) not in (bool, int, float, type(None)):
            raise ValueError("manifest JSON value type invalid")
    return value


def _hex64(value: Any, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in _HEX for c in value):
        raise ValueError(f"{label} is not canonical SHA-256")
    return value


def _frame(
    connection: socket.socket, seconds: float = READ_DEADLINE_SECONDS
) -> dict[str, Any]:
    value = read_frame(
        connection,
        MAX_FRAME,
        seconds,
        "verifier request",
        parser=_manifest_json_loads,
    )
    if type(value) is not dict:
        raise ValueError("verifier frame must be an object")
    return value


def _send(connection: socket.socket, value: dict[str, Any]) -> None:
    payload = canonical_json_bytes(value)
    if len(payload) > MAX_FRAME:
        raise ValueError("verifier response exceeds protocol bound")
    connection.sendall(struct.pack("!I", len(payload)) + payload)


def _regular(root: Path, relative: str) -> Path:
    path = root / relative
    if path.resolve(strict=True) != path or root not in path.parents:
        raise ValueError("verifier evidence escapes authority store")
    metadata = os.lstat(path)
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("verifier evidence must be regular")
    return path


def _load_manifest(
    request: dict[str, Any],
    config: dict[str, Any],
    artifact_root: Path,
    staged_root: Path,
    temporary: Path,
) -> tuple[dict[str, Any], str, str, str, str]:
    if set(request) != {"operation", "challenge", "manifest_bytes", "manifest_sha256"}:
        raise ValueError("verifier request is not closed")
    if request["operation"] != "verify-exact-14":
        raise ValueError("verifier operation is not authorized")
    challenge = _hex64(request["challenge"], "verifier challenge")
    text = request["manifest_bytes"]
    if type(text) is not str:
        raise ValueError("manifest canonical bytes must be UTF-8 text")
    raw = text.encode("utf-8", errors="strict")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != _hex64(request["manifest_sha256"], "manifest hash"):
        raise ValueError("manifest hash mismatch")
    manifest = _manifest_json_loads(raw)
    if canonical_json_bytes(manifest) != raw:
        raise ValueError("manifest bytes are not canonical")
    if (
        type(manifest) is not dict
        or set(manifest) != {"schema_version", "correlation_nonce", "cells"}
        or manifest["schema_version"] != 2
    ):
        raise ValueError("external verifier manifest is not closed")
    correlation = _hex64(manifest["correlation_nonce"], "correlation nonce")
    cells = manifest["cells"]
    if type(cells) is not list or len(cells) != 14:
        raise ValueError("external verifier requires exact fourteen cells")
    # Authenticate the complete closed manifest before consuming the FD budget.
    validated = []
    for ordinal, item in enumerate(cells):
        if type(item) is not dict or set(item) != {
            "contract",
            "authority_response",
            "receipt",
        }:
            raise ValueError("external verifier cell is not closed")
        contract = verify_contract(
            {"operation": "run-cell", "contract": item["contract"]}
        )
        identity = EXPECTED_CELLS[ordinal]
        if (
            contract["cell"]["repo_id"],
            contract["cell"]["arm_id"],
        ) != identity or contract["nonce"] != correlation:
            raise ValueError("external verifier cell identity/order/nonce invalid")
        response = _verify_authority(item["authority_response"], config)
        if (
            response["contract_digest"]
            != hashlib.sha256(canonical_json_bytes(contract)).hexdigest()
            or response["cell"] != contract["cell"]
            or response["nonce"] != correlation
            or response["job_id"] != contract["job_id"]
        ):
            raise ValueError("authority response does not bind root contract")
        validated.append((identity, item, response))
    decision_ids = {item[1]["contract"]["decision_id"] for item in validated}
    decision_digests = {
        item[1]["contract"]["decision_contract_sha256"] for item in validated
    }
    if len(decision_ids) != 1 or len(decision_digests) != 1:
        raise ValueError(
            "exact-14 contracts must share one offline decision identity/digest"
        )
    decision_id = decision_ids.pop()
    decision_digest = decision_digests.pop()

    loaded_cells: list[dict[str, Any]] = []
    retained_fds: list[int] = []
    try:
        for ordinal, (identity, item, response) in enumerate(validated):
            paths = _paths(response, artifact_root, staged_root)
            try:
                audit = temporary / f"audit-{ordinal:02d}.json"
                audit.write_bytes(canonical_json_bytes(response["audit"]))
                os.chmod(audit, 0o400)
                plan = strict_json_loads(paths["plan.json"].read_bytes())
                inventory = strict_json_loads(paths["inventory.json"].read_bytes())
                evidence: dict[str, str] = {}
                for name in (
                    "data.img",
                    "hash.img",
                    "source-snapshot.tar",
                    "tool",
                    "config",
                    "seccomp",
                ):
                    descriptor = os.dup(int(paths[name].name))
                    retained_fds.append(descriptor)
                    evidence[name] = f"/proc/self/fd/{descriptor}"
            finally:
                paths.close()
            loaded_cells.append(
                {
                    "repo_id": identity[0],
                    "arm_id": identity[1],
                    "attempt": 1,
                    "plan": plan,
                    "inventory": inventory,
                    "receipt": item["receipt"],
                    "data_image": evidence["data.img"],
                    "hash_image": evidence["hash.img"],
                    "process_audit": str(audit),
                    "source_snapshot": evidence["source-snapshot.tar"],
                    "tool": evidence["tool"],
                    "config": evidence["config"],
                    "seccomp": evidence["seccomp"],
                }
            )
    except BaseException:
        for descriptor in retained_fds:
            os.close(descriptor)
        raise
    loaded = {
        "schema_version": 1,
        "verifier_nonce": correlation,
        "verifier_image_digest": config["trusted"]["images"]["verifier"],
        "run_contract": {
            "plan_set_hash": config["trusted"]["plan_set_hash"],
            "run_nonce": correlation,
        },
        "cells": loaded_cells,
    }
    return loaded, digest, challenge, decision_id, decision_digest


def _signed_ledger(
    value: dict[str, Any], key: Ed25519PrivateKey, config: dict[str, Any]
) -> dict[str, Any]:
    return {
        "record": value,
        "key_id": config["verifier"]["key_id"],
        "algorithm": "Ed25519",
        "signature": key.sign(LEDGER_DOMAIN + canonical_json_bytes(value)).hex(),
    }


def _verify(
    request: dict[str, Any],
    config: dict[str, Any],
    artifact_root: Path,
    staged_root: Path,
    key: Ed25519PrivateKey,
    ledger: ChallengeLedger,
    measurement: dict[str, Any],
) -> dict[str, Any]:
    digest = _hex64(request.get("manifest_sha256"), "manifest hash")
    challenge = _hex64(request.get("challenge"), "verifier challenge")
    ledger.start_verifying(digest, challenge)
    try:
        with tempfile.TemporaryDirectory(prefix="no1-008a-verifier-") as directory:
            manifest, loaded_digest, loaded_challenge, decision_id, decision_digest = (
                _load_manifest(
                    request, config, artifact_root, staged_root, Path(directory)
                )
            )
            if (loaded_digest, loaded_challenge) != (digest, challenge):
                raise ValueError("verified manifest identity changed")
            pinned = {
                int(Path(cell[name]).name)
                for cell in manifest["cells"]
                for name in (
                    "data_image",
                    "hash_image",
                    "source_snapshot",
                    "tool",
                    "config",
                    "seccomp",
                )
                if str(cell[name]).startswith("/proc/self/fd/")
            }
            try:
                verdict = aggregate_verdict(manifest, public_config=config)
            finally:
                for descriptor in pinned:
                    os.close(descriptor)
        _validate_verdict_schema(verdict)
    except BaseException:
        ledger.finish(digest, challenge, success=False)
        raise

    def build(consumption: dict[str, Any], head: dict[str, Any]) -> bytes:
        signed = {
            "manifest_sha256": digest,
            "decision_id": decision_id,
            "decision_contract_sha256": decision_digest,
            "challenge": challenge,
            "ledger_counter": consumption["counter"],
            "ledger_prev_hash": consumption["prev_hash"],
            "issued_at_ns": consumption["issued_at_ns"],
            "verdict": verdict,
            "service_identity": measurement,
            "consumption_record": _signed_ledger(consumption, key, config),
            "ledger_head": _signed_ledger(head, key, config),
        }
        envelope = {
            **signed,
            "key_id": config["verifier"]["key_id"],
            "algorithm": "Ed25519",
            "signature": key.sign(VERDICT_DOMAIN + canonical_json_bytes(signed)).hex(),
        }
        return canonical_json_bytes(envelope)

    _consumption, _head, envelope_bytes = ledger.finish_with_envelope(
        digest, challenge, build
    )
    return _manifest_json_loads(envelope_bytes)


def serve_once(
    listener: socket.socket,
    *,
    config: dict[str, Any],
    artifact_root: Path,
    staged_root: Path,
    key: Ed25519PrivateKey,
    ledger: ChallengeLedger,
    measurement: dict[str, Any],
    allowed_client_uid: int,
) -> None:
    connection, _ = listener.accept()
    try:
        peer_allowed(connection, allowed_client_uid)
        request = _frame(connection)
        if (
            set(request) == {"operation"}
            and request["operation"] == "query-ledger-head"
        ):
            reply = _signed_ledger(ledger.head(), key, config)
        elif (
            set(request) == {"operation", "manifest_sha256", "challenge"}
            and request["operation"] == "query-verdict"
        ):
            digest = _hex64(request["manifest_sha256"], "manifest hash")
            challenge = _hex64(request["challenge"], "verifier challenge")
            reply = _manifest_json_loads(ledger.verdict(digest, challenge))
        elif (
            set(request) == {"operation", "manifest_sha256"}
            and request["operation"] == "begin-exact-14"
        ):
            digest = _hex64(request["manifest_sha256"], "manifest hash")
            record = ledger.begin(digest)
            signed = {
                "manifest_sha256": digest,
                "challenge": record["challenge"],
                "ledger_counter": record["counter"],
                "ledger_prev_hash": record["prev_hash"],
                "issued_at_ns": record["issued_at_ns"],
                "service_identity": measurement,
            }
            reply = {
                **signed,
                "key_id": config["verifier"]["key_id"],
                "algorithm": "Ed25519",
                "signature": key.sign(
                    CHALLENGE_DOMAIN + canonical_json_bytes(signed)
                ).hex(),
            }
        else:
            reply = _verify(
                request, config, artifact_root, staged_root, key, ledger, measurement
            )
    except Exception as error:
        reply = {"error": type(error).__name__, "reason": str(error)}
    try:
        _send(connection, reply)
    except (TimeoutError, BrokenPipeError, ConnectionError):
        pass
    finally:
        connection.close()


def _round_trip(
    socket_path: Path, request: dict[str, Any], config: dict[str, Any], timeout: float
) -> dict[str, Any]:
    if timeout <= 0:
        raise TimeoutError("verifier overall deadline expired")
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    deadline = time.monotonic() + timeout
    try:
        client.settimeout(max(0.001, deadline - time.monotonic()))
        client.connect(str(socket_path))
        option = getattr(socket, "SO_PEERCRED", None)
        if option is None:
            raise ValueError("Unix peer credentials unavailable")
        pid, uid, _gid = struct.unpack(
            "3i", client.getsockopt(socket.SOL_SOCKET, option, 12)
        )
        if pid <= 0 or uid != config["verifier"]["peer_uid"]:
            raise ValueError("external verifier peer UID mismatch")
        _send(client, request)
        try:
            client.shutdown(socket.SHUT_WR)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("verifier overall deadline expired")
            client.settimeout(remaining)
            return _frame(client, remaining)
        except ValueError as error:
            if str(error) != "frame truncated":
                raise
            raise _PostSendTransportError(
                "verifier response frame truncated"
            ) from error
        except (TimeoutError, BrokenPipeError, ConnectionError, OSError) as error:
            raise _PostSendTransportError(
                "verifier response transport failed"
            ) from error
    finally:
        client.close()


def query_ledger_head(
    *, socket_path: Path, config: dict[str, Any], timeout: float
) -> dict[str, Any]:
    """Fetch and authenticate the verifier's current durable head."""
    reply = _round_trip(
        socket_path, {"operation": "query-ledger-head"}, config, timeout
    )
    if (
        type(reply) is not dict
        or set(reply) != {"record", "key_id", "algorithm", "signature"}
        or reply["key_id"] != config["verifier"]["key_id"]
        or reply["algorithm"] != "Ed25519"
    ):
        raise ValueError("live verifier ledger head envelope invalid")
    Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(config["verifier"]["public_key_hex"])
    ).verify(
        bytes.fromhex(reply["signature"]),
        LEDGER_DOMAIN + canonical_json_bytes(reply["record"]),
    )
    record = reply["record"]
    if type(record) is not dict or set(record) != {"counter", "record_hash"}:
        raise ValueError("live verifier ledger head invalid")
    return reply


def query_verdict(
    *,
    socket_path: Path,
    manifest_sha256: str,
    challenge: str,
    config: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    """Recover and authenticate a transactionally committed verdict envelope."""
    digest = _hex64(manifest_sha256, "manifest hash")
    challenge = _hex64(challenge, "verifier challenge")
    envelope = _round_trip(
        socket_path,
        {
            "operation": "query-verdict",
            "manifest_sha256": digest,
            "challenge": challenge,
        },
        config,
        timeout,
    )
    required = {
        "manifest_sha256",
        "decision_id",
        "decision_contract_sha256",
        "challenge",
        "ledger_counter",
        "ledger_prev_hash",
        "issued_at_ns",
        "verdict",
        "service_identity",
        "consumption_record",
        "ledger_head",
        "key_id",
        "algorithm",
        "signature",
    }
    if (
        type(envelope) is not dict
        or set(envelope) != required
        or envelope["manifest_sha256"] != digest
        or envelope["challenge"] != challenge
        or envelope["key_id"] != config["verifier"]["key_id"]
        or envelope["algorithm"] != "Ed25519"
        or envelope["service_identity"]
        != config["trusted"]["verifier_runtime"]["measurement"]
    ):
        raise ValueError("recovered verifier verdict binding mismatch")
    public = Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(config["verifier"]["public_key_hex"])
    )
    signed = {
        key: envelope[key] for key in required - {"key_id", "algorithm", "signature"}
    }
    public.verify(
        bytes.fromhex(envelope["signature"]),
        VERDICT_DOMAIN + canonical_json_bytes(signed),
    )
    consumption = envelope["consumption_record"]
    head = envelope["ledger_head"]
    for retained in (consumption, head):
        if (
            type(retained) is not dict
            or set(retained) != {"record", "key_id", "algorithm", "signature"}
            or retained["key_id"] != config["verifier"]["key_id"]
            or retained["algorithm"] != "Ed25519"
        ):
            raise ValueError("recovered signed ledger proof is invalid")
        public.verify(
            bytes.fromhex(retained["signature"]),
            LEDGER_DOMAIN + canonical_json_bytes(retained["record"]),
        )
    record = consumption["record"]
    if (
        record.get("event") != "CONSUMED"
        or record.get("manifest_sha256") != digest
        or record.get("challenge") != challenge
        or record.get("counter") != envelope["ledger_counter"]
        or head.get("record", {}).get("counter") != envelope["ledger_counter"]
    ):
        raise ValueError("recovered verifier consumption proof is not bound")
    _validate_verdict_schema(envelope["verdict"])
    return envelope


def request_verdict(
    *,
    socket_path: Path,
    manifest: dict[str, Any],
    config: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    """Obtain a service-issued challenge then consume it once for this manifest."""
    raw = canonical_json_bytes(manifest)
    digest = hashlib.sha256(raw).hexdigest()
    deadline = time.monotonic() + timeout
    begin_request = {"operation": "begin-exact-14", "manifest_sha256": digest}
    try:
        begin = _round_trip(
            socket_path, begin_request, config, deadline - time.monotonic()
        )
    except _PostSendTransportError:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise
        # begin() is manifest-idempotent while its challenge is active, so a
        # single response-loss retry returns the committed signed challenge.
        begin = _round_trip(socket_path, begin_request, config, remaining)
    begin_keys = {
        "manifest_sha256",
        "challenge",
        "ledger_counter",
        "ledger_prev_hash",
        "issued_at_ns",
        "service_identity",
        "key_id",
        "algorithm",
        "signature",
    }
    if (
        type(begin) is not dict
        or set(begin) != begin_keys
        or begin["manifest_sha256"] != digest
        or begin["service_identity"]
        != config["trusted"]["verifier_runtime"]["measurement"]
    ):
        raise ValueError("verifier challenge envelope invalid")
    begin_signed = {
        key: begin[key] for key in begin_keys - {"key_id", "algorithm", "signature"}
    }
    Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(config["verifier"]["public_key_hex"])
    ).verify(
        bytes.fromhex(begin["signature"]),
        CHALLENGE_DOMAIN + canonical_json_bytes(begin_signed),
    )
    request = {
        "operation": "verify-exact-14",
        "challenge": begin["challenge"],
        "manifest_bytes": raw.decode("utf-8"),
        "manifest_sha256": digest,
    }
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("verifier overall deadline expired")
    try:
        envelope = _round_trip(socket_path, request, config, remaining)
    except _PostSendTransportError:
        recovery_remaining = deadline - time.monotonic()
        if recovery_remaining <= 0:
            raise
        envelope = query_verdict(
            socket_path=socket_path,
            manifest_sha256=digest,
            challenge=begin["challenge"],
            config=config,
            timeout=recovery_remaining,
        )
    if type(envelope) is dict and set(envelope) == {"error", "reason"}:
        raise ValueError(f"external verifier rejected manifest: {envelope['reason']}")
    expected = {
        "manifest_sha256",
        "decision_id",
        "decision_contract_sha256",
        "challenge",
        "ledger_counter",
        "ledger_prev_hash",
        "issued_at_ns",
        "verdict",
        "service_identity",
        "consumption_record",
        "ledger_head",
        "key_id",
        "algorithm",
        "signature",
    }
    if (
        type(envelope) is not dict
        or set(envelope) != expected
        or envelope["manifest_sha256"] != digest
        or envelope["decision_id"] != manifest["cells"][0]["contract"]["decision_id"]
        or envelope["decision_contract_sha256"]
        != manifest["cells"][0]["contract"]["decision_contract_sha256"]
        or envelope["challenge"] != begin["challenge"]
        or envelope["issued_at_ns"] != begin["issued_at_ns"]
        or envelope["key_id"] != config["verifier"]["key_id"]
        or envelope["algorithm"] != "Ed25519"
        or envelope["service_identity"] != begin["service_identity"]
        or envelope["ledger_counter"] <= begin["ledger_counter"]
        or envelope["consumption_record"].get("record", {}).get("event") != "CONSUMED"
        or envelope["consumption_record"].get("record", {}).get("counter")
        != envelope["ledger_counter"]
        or envelope["ledger_head"].get("record", {}).get("counter")
        != envelope["ledger_counter"]
    ):
        raise ValueError("external verifier verdict binding mismatch")
    signed = {
        key: envelope[key] for key in expected - {"key_id", "algorithm", "signature"}
    }
    Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(config["verifier"]["public_key_hex"])
    ).verify(
        bytes.fromhex(envelope["signature"]),
        VERDICT_DOMAIN + canonical_json_bytes(signed),
    )
    for retained in (envelope["consumption_record"], envelope["ledger_head"]):
        if (
            type(retained) is not dict
            or set(retained) != {"record", "key_id", "algorithm", "signature"}
            or retained["key_id"] != config["verifier"]["key_id"]
            or retained["algorithm"] != "Ed25519"
        ):
            raise ValueError("signed ledger proof is invalid")
        Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(config["verifier"]["public_key_hex"])
        ).verify(
            bytes.fromhex(retained["signature"]),
            LEDGER_DOMAIN + canonical_json_bytes(retained["record"]),
        )
    _validate_verdict_schema(envelope["verdict"])
    return envelope


_KEY_FDS: list[int] = []


def _load_key(path: Path) -> Ed25519PrivateKey:
    fd, raw = secure_key(path, os.geteuid())
    _KEY_FDS.append(fd)
    return Ed25519PrivateKey.from_private_bytes(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--public-config", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--staged-root", required=True)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--allowed-client-uid", required=True, type=int)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--launch-attestation", required=True)
    parser.add_argument("--launch-release", required=True)
    args = parser.parse_args(argv)
    config = parse_public_config(Path(args.public_config).read_bytes())
    if os.geteuid() != config["verifier"]["peer_uid"]:
        raise SystemExit("verifier service UID does not match root-signed identity")
    launch_bytes = wait_for_launch_release(
        Path(args.launch_attestation), Path(args.launch_release)
    )
    runtime = config["trusted"]["verifier_runtime"]["measurement"]
    measurement = measure_runtime(runtime)
    verify_service_launch_attestation(
        strict_json_loads(launch_bytes),
        "verifier",
        config,
    )
    key = _load_key(Path(args.private_key))
    if (
        key.public_key().public_bytes_raw().hex()
        != config["verifier"]["public_key_hex"]
    ):
        raise SystemExit("verifier private key does not match public config")
    ledger = ChallengeLedger(Path(args.ledger))
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(args.socket)
    # Filesystem access must not preempt the exact SO_PEERCRED UID authorization.
    os.chmod(args.socket, 0o666)  # nosec B103 - local socket; peer UID is fail-closed
    listener.listen(args.workers)

    def worker() -> None:
        while True:
            serve_once(
                listener,
                config=config,
                artifact_root=Path(args.artifact_root).resolve(strict=True),
                staged_root=Path(args.staged_root).resolve(strict=True),
                key=key,
                ledger=ledger,
                measurement=measurement,
                allowed_client_uid=args.allowed_client_uid,
            )

    with ThreadPoolExecutor(
        max_workers=args.workers, thread_name_prefix="verifier"
    ) as pool:
        futures = [pool.submit(worker) for _ in range(args.workers)]
        for future in futures:
            future.result()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
