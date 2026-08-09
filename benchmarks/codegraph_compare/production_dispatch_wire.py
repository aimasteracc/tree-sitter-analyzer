from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.canary_evidence import (
    CanaryCellV1,
    CanaryManifestV1,
    canonical_sha256,
    validate_canary_manifest,
)
from benchmarks.codegraph_compare.production_collector import (
    _DIR_FLAGS,
    _FILE_NOFOLLOW,
    _open_parent_and_create_root,
)
from benchmarks.codegraph_compare.production_trust import (
    OperatorTrustConfigV1,
    ProductionRunSpecV1,
)


@dataclass(frozen=True)
class ProductionDispatchRequestV1:
    manifest: CanaryManifestV1
    spec: ProductionRunSpecV1
    cell_order: int
    timeout_seconds: int
    qualification_evidence_digest: str
    journal_root: Path
    evidence_root: Path

    def to_wire_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "manifest": asdict(self.manifest),
            "spec": self.spec.to_wire_dict(),
            "cell_order": self.cell_order,
            "timeout_seconds": self.timeout_seconds,
            "qualification_evidence_digest": self.qualification_evidence_digest,
            "journal_root": str(self.journal_root),
            "evidence_root": str(self.evidence_root),
        }

    def to_json(self) -> str:
        return _canonical(self.to_wire_dict()).decode()

    @property
    def envelope_hash(self) -> str:
        return canonical_sha256(
            {
                "schema_version": 1,
                "manifest_hash": self.manifest.manifest_hash,
                "spec_hash": self.spec.spec_hash,
                "cell_order": self.cell_order,
                "qualification_evidence_digest": self.qualification_evidence_digest,
                "journal_root": self.spec.journal_root,
                "evidence_root": self.spec.evidence_root,
                "global_nonce_ledger_root": self.spec.global_nonce_ledger_root,
            }
        )


@dataclass(frozen=True)
class ProviderReservationReceiptV1:
    schema_version: int
    spec_hash: str
    reservation_id: str
    request_limit: int
    token_limit: int
    budget_ceiling_usd: float
    hmac_sha256: str


def issue_provider_reservation_receipt(
    spec: ProductionRunSpecV1, reservation_id: str, key: bytes
) -> ProviderReservationReceiptV1:
    if type(reservation_id) is not str or not reservation_id or len(key) < 32:
        raise ValueError("provider reservation identity/key invalid")
    fields = {
        "schema_version": 1,
        "spec_hash": spec.spec_hash,
        "reservation_id": reservation_id,
        "request_limit": spec.request_limit,
        "token_limit": spec.token_limit,
        "budget_ceiling_usd": spec.budget_ceiling_usd,
    }
    signature = hmac.new(key, _canonical(fields), hashlib.sha256).hexdigest()
    return ProviderReservationReceiptV1(
        schema_version=1,
        spec_hash=spec.spec_hash,
        reservation_id=reservation_id,
        request_limit=spec.request_limit,
        token_limit=spec.token_limit,
        budget_ceiling_usd=spec.budget_ceiling_usd,
        hmac_sha256=signature,
    )


@dataclass(frozen=True)
class ProviderRunResult:
    provider_request_count: int
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    termination_reason: str
    transcript: bytes
    tool_receipt: bytes = b""
    provider_reservation_id: str | None = None
    kill_attempted: bool = False
    wait_completed: bool = False
    usage_complete: bool = False
    provider_reservation_receipt: ProviderReservationReceiptV1 | None = None


class ProviderRunFailure(RuntimeError):
    def __init__(self, message: str, partial: ProviderRunResult) -> None:
        super().__init__(message)
        self.partial = partial


class ProviderRequestGate:
    def __init__(
        self, provider_call: Callable[[ProductionDispatchRequestV1], ProviderRunResult]
    ) -> None:
        self._call = provider_call
        self._count = 0

    @property
    def count(self) -> int:
        return self._count

    def call(self, request: ProductionDispatchRequestV1) -> ProviderRunResult:
        if self._count != 0:
            raise RuntimeError("PROVIDER_REQUEST_LIMIT_REACHED")
        self._count = 1
        return self._call(request)


@dataclass(frozen=True)
class TrustedOfflineTestAdapter:
    run: Callable[[ProductionDispatchRequestV1], ProviderRunResult]


@dataclass(frozen=True)
class ProductionDispatchReceiptV1:
    status: str
    violations: tuple[str, ...]
    envelope_hash: str | None
    reservation_durable: bool
    terminal_durable: bool
    model_callbacks_invoked: int
    provider_requests: int | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    termination_reason: str
    evidence_digest: str | None
    evidence_level: str = "E0"
    winner: None = None
    dominance_allowed: bool = False
    publishable: bool = False
    schema_version: int = 1

    def to_wire_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return _canonical(self.to_wire_dict()).decode()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode()


def _strict_json(data: str | bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    value = json.loads(
        data,
        object_pairs_hook=pairs,
        parse_constant=lambda x: (_ for _ in ()).throw(
            ValueError(f"non-finite number: {x}")
        ),
    )
    if type(value) is not dict:
        raise ValueError("wire value must be an object")
    return value


def load_production_dispatch_request_v1(
    data: str | bytes,
) -> ProductionDispatchRequestV1:
    value = _strict_json(data)
    expected = {
        "schema_version",
        "manifest",
        "spec",
        "cell_order",
        "timeout_seconds",
        "qualification_evidence_digest",
        "journal_root",
        "evidence_root",
    }
    if (
        set(value) != expected
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
    ):
        raise ValueError("request fields must match strict v1 schema")
    from benchmarks.codegraph_compare.production_trust import (
        load_production_run_spec_v1,
    )

    spec = load_production_run_spec_v1(_canonical(value["spec"]))
    raw = value["manifest"]
    if type(raw) is not dict or set(raw) != set(CanaryManifestV1.__dataclass_fields__):
        raise ValueError("manifest fields must match strict v1 schema")
    raw = dict(raw)
    if (
        type(raw["oracle"]) is not list
        or type(raw["launch_config_hashes"]) is not list
        or type(raw["cells"]) is not list
    ):
        raise ValueError("manifest collection types invalid")
    raw["oracle"] = tuple(raw["oracle"])
    raw["launch_config_hashes"] = tuple(
        tuple(item) for item in raw["launch_config_hashes"]
    )
    raw["cells"] = tuple(CanaryCellV1(**item) for item in raw["cells"])
    manifest = CanaryManifestV1(**raw)
    validate_canary_manifest(manifest)
    for name in ("cell_order", "timeout_seconds"):
        if type(value[name]) is not int:
            raise ValueError(f"{name} must be exact integer")
    for name in ("qualification_evidence_digest", "journal_root", "evidence_root"):
        if type(value[name]) is not str:
            raise ValueError(f"{name} must be string")
    request = ProductionDispatchRequestV1(
        manifest,
        spec,
        value["cell_order"],
        value["timeout_seconds"],
        value["qualification_evidence_digest"],
        Path(value["journal_root"]),
        Path(value["evidence_root"]),
    )
    if (
        str(request.journal_root) != spec.journal_root
        or str(request.evidence_root) != spec.evidence_root
    ):
        raise ValueError("request roots do not match signed spec")
    if request.to_json() != _canonical(value).decode():
        raise ValueError("request is not canonical")
    return request


def load_journal_event_v1(data: str | bytes) -> dict[str, Any]:
    value = _strict_json(data)
    if (
        type(value.get("schema_version")) is not int
        or value["schema_version"] != 1
        or type(value.get("event")) is not str
    ):
        raise ValueError("unsupported journal event schema")
    fields = {
        "RESERVED": {"schema_version", "event", "envelope_hash", "spec_hash", "nonce"},
        "GLOBAL_CLAIM": {
            "schema_version",
            "event",
            "spec_hash",
            "nonce",
            "envelope_hash",
        },
        "TERMINAL": {
            "schema_version",
            "event",
            "status",
            "violations",
            "evidence_digest",
        },
    }
    if value["event"] not in fields or set(value) != fields[value["event"]]:
        raise ValueError("journal event fields invalid")
    if value["event"] == "TERMINAL":
        if (
            value["status"] not in ("PASS", "INVALID", "NOT_EVALUATED", "UNKNOWN")
            or type(value["violations"]) is not list
            or any(type(item) is not str for item in value["violations"])
        ):
            raise ValueError("terminal event invalid")
    return value


def load_production_dispatch_receipt_v1(
    data: str | bytes,
) -> ProductionDispatchReceiptV1:
    value = _strict_json(data)
    fields = set(ProductionDispatchReceiptV1.__dataclass_fields__)
    if set(value) != fields:
        raise ValueError("receipt fields must match strict v1 schema")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("unsupported receipt schema")
    if type(value["violations"]) is not list or any(
        type(x) is not str for x in value["violations"]
    ):
        raise ValueError("violations must be strings")
    value["violations"] = tuple(value["violations"])
    receipt = ProductionDispatchReceiptV1(**value)
    for name in (
        "reservation_durable",
        "terminal_durable",
        "dominance_allowed",
        "publishable",
    ):
        if type(getattr(receipt, name)) is not bool:
            raise ValueError(f"{name} must be boolean")
    if (
        receipt.status not in ("PASS", "INVALID", "NOT_EVALUATED")
        or receipt.evidence_level != "E0"
        or receipt.winner is not None
        or receipt.dominance_allowed
        or receipt.publishable
    ):
        raise ValueError("receipt protected fields invalid")
    if (
        type(receipt.model_callbacks_invoked) is not int
        or receipt.model_callbacks_invoked < 0
    ):
        raise ValueError("model_callbacks_invoked must be a non-negative integer")
    for name in ("provider_requests", "input_tokens", "output_tokens"):
        item = getattr(receipt, name)
        if item is not None and (type(item) is not int or item < 0):
            raise ValueError(f"{name} must be a non-negative integer or null")
    if receipt.cost_usd is not None and (
        type(receipt.cost_usd) is not float
        or not math.isfinite(receipt.cost_usd)
        or receipt.cost_usd < 0
    ):
        raise ValueError("cost_usd must be a finite non-negative float or null")
    if type(receipt.termination_reason) is not str:
        raise ValueError("termination_reason must be string")
    return receipt


class _Journal:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.parent_fd, self.fd, self.pin = _open_parent_and_create_root(root)

    def write(self, name: str, value: object) -> None:
        body = _canonical(value) + b"\n"
        fd = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _FILE_NOFOLLOW,
            0o400,
            dir_fd=self.fd,
        )
        try:
            offset = 0
            while offset < len(body):
                offset += os.write(fd, body[offset:])
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(self.fd)
        os.fsync(self.parent_fd)

    def close(self) -> None:
        for fd in (self.fd, self.parent_fd):
            try:
                os.close(fd)
            except OSError:
                pass


def _open_existing_dir(path: Path) -> int:
    absolute = path.resolve(strict=True)
    if str(absolute) != str(path):
        raise ValueError("directory must be canonical absolute")
    fd = os.open("/", _DIR_FLAGS)
    try:
        for part in absolute.parts[1:]:
            child = os.open(part, _DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except Exception:
        os.close(fd)
        raise


def _claim_global(
    request: ProductionDispatchRequestV1, config: OperatorTrustConfigV1
) -> None:
    assert config.global_nonce_ledger_root is not None
    fd = _open_existing_dir(config.global_nonce_ledger_root)
    name = (
        canonical_sha256(
            {
                "schema_version": 1,
                "spec_hash": request.spec.spec_hash,
                "nonce": request.spec.nonce,
            }
        )
        + ".claim"
    )
    body = (
        _canonical(
            {
                "schema_version": 1,
                "event": "GLOBAL_CLAIM",
                "spec_hash": request.spec.spec_hash,
                "nonce": request.spec.nonce,
                "envelope_hash": request.envelope_hash,
            }
        )
        + b"\n"
    )
    try:
        claim = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _FILE_NOFOLLOW,
            0o400,
            dir_fd=fd,
        )
        try:
            os.write(claim, body)
            os.fsync(claim)
        finally:
            os.close(claim)
        os.fsync(fd)
    finally:
        os.close(fd)
