from __future__ import annotations

import json
import math
import re
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
from benchmarks.codegraph_compare.production_authorities import (
    ProviderReservationReceiptV1,
    ProviderUsageReceiptV1,
    SupervisedTransportReceiptV1,
)
from benchmarks.codegraph_compare.production_trust import (
    OperatorTrustConfigV1,
    ProductionQualification,
    ProductionRunSpecV1,
)

_LOWER_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ProductionDispatchRequestV1:
    manifest: CanaryManifestV1
    spec: ProductionRunSpecV1
    cell_order: int
    timeout_seconds: int
    qualification_evidence_digest: str
    journal_root: Path
    evidence_root: Path
    previous_terminal_receipt_sha256: str | None = None

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
            "previous_terminal_receipt_sha256": self.previous_terminal_receipt_sha256,
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
                "previous_terminal_receipt_sha256": self.previous_terminal_receipt_sha256,
            }
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
    provider_usage_receipt: ProviderUsageReceiptV1 | None = None
    transport_receipt: SupervisedTransportReceiptV1 | None = None


class ProviderRunFailure(RuntimeError):
    def __init__(self, message: str, partial: ProviderRunResult) -> None:
        super().__init__(message)
        self.partial = partial


@dataclass(frozen=True)
class TrustedOfflineTestAdapter:
    """Marker only. Offline fakes are never executed by production dispatch."""

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
    authority_receipts: tuple[str, ...] = ()
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


def _assert_canonical_input(data: str | bytes, value: object) -> None:
    if type(data) is bytes:
        try:
            original = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("wire input must be UTF-8") from error
    elif type(data) is str:
        original = data
    else:
        raise ValueError("wire input must be string or bytes")
    if original != _canonical(value).decode("utf-8"):
        raise ValueError("wire input is not canonical")


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
        "previous_terminal_receipt_sha256",
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
    if (
        type(value["cell_order"]) is not int
        or value["cell_order"] < 0
        or value["cell_order"] >= len(manifest.cells)
    ):
        raise ValueError("cell_order must select exactly one manifest cell")
    if (
        type(value["timeout_seconds"]) is not int
        or value["timeout_seconds"] <= 0
        or value["timeout_seconds"] != manifest.timeout_seconds
    ):
        raise ValueError("timeout_seconds must be an exact positive manifest timeout")
    if (
        type(value["qualification_evidence_digest"]) is not str
        or _LOWER_SHA256.fullmatch(value["qualification_evidence_digest"]) is None
    ):
        raise ValueError("qualification_evidence_digest must be lowercase SHA-256")
    for name in ("journal_root", "evidence_root"):
        if type(value[name]) is not str:
            raise ValueError(f"{name} must be string")
    previous = value["previous_terminal_receipt_sha256"]
    if previous is not None and (
        type(previous) is not str or _LOWER_SHA256.fullmatch(previous) is None
    ):
        raise ValueError(
            "previous_terminal_receipt_sha256 must be lowercase SHA-256 or null"
        )
    if (value["cell_order"] == 0) != (previous is None):
        raise ValueError("cell 0 must be genesis and cell 1 must bind cell 0 terminal")
    request = ProductionDispatchRequestV1(
        manifest,
        spec,
        value["cell_order"],
        value["timeout_seconds"],
        value["qualification_evidence_digest"],
        Path(value["journal_root"]),
        Path(value["evidence_root"]),
        value["previous_terminal_receipt_sha256"],
    )
    if (
        str(request.journal_root) != spec.journal_root
        or str(request.evidence_root) != spec.evidence_root
    ):
        raise ValueError("request roots do not match signed spec")
    if request.to_json() != _canonical(value).decode():
        raise ValueError("request is not canonical")
    _assert_canonical_input(data, value)
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
    if value["event"] in ("RESERVED", "GLOBAL_CLAIM"):
        if any(
            type(value[name]) is not str or _LOWER_SHA256.fullmatch(value[name]) is None
            for name in ("envelope_hash", "spec_hash")
        ) or (
            type(value["nonce"]) is not str
            or not value["nonce"]
            or len(value["nonce"]) > 256
            or "/" in value["nonce"]
            or "\\" in value["nonce"]
            or ".." in value["nonce"]
        ):
            raise ValueError("reservation event identity invalid")
    else:
        if (
            type(value["status"]) is not str
            or value["status"] not in ("PASS", "INVALID", "NOT_EVALUATED", "UNKNOWN")
            or type(value["violations"]) is not list
            or any(type(item) is not str or not item for item in value["violations"])
            or (
                value["evidence_digest"] is not None
                and (
                    type(value["evidence_digest"]) is not str
                    or _LOWER_SHA256.fullmatch(value["evidence_digest"]) is None
                )
            )
            or (
                value["status"] == "PASS"
                and (value["evidence_digest"] is None or value["violations"])
            )
        ):
            raise ValueError("terminal event invalid")
    _assert_canonical_input(data, value)
    return value


def _load_production_dispatch_receipt_v1(
    data: str | bytes, *, allow_unverified_pass: bool
) -> ProductionDispatchReceiptV1:
    value = _strict_json(data)
    fields = set(ProductionDispatchReceiptV1.__dataclass_fields__)
    if set(value) != fields:
        raise ValueError("receipt fields must match strict v1 schema")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("unsupported receipt schema")
    if type(value["violations"]) is not list or any(
        type(x) is not str or not x or len(x) > 1024 for x in value["violations"]
    ):
        raise ValueError("violations must be bounded non-empty strings")
    value["violations"] = tuple(value["violations"])
    if type(value["authority_receipts"]) is not list or any(
        type(item) is not str for item in value["authority_receipts"]
    ):
        raise ValueError("authority_receipts must be canonical JSON strings")
    for item in value["authority_receipts"]:
        signed_receipt = _strict_json(item)
        _assert_canonical_input(item, signed_receipt)
        signature = signed_receipt.get("signature_ed25519")
        if type(signature) is not str or len(signature) != 128:
            raise ValueError(
                "authority receipt signature must be canonical Ed25519 hex"
            )
    value["authority_receipts"] = tuple(value["authority_receipts"])
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
        type(receipt.status) is not str
        or receipt.status not in ("PASS", "INVALID", "NOT_EVALUATED")
        or type(receipt.evidence_level) is not str
        or receipt.evidence_level not in ("E0", "E1")
        or receipt.evidence_level != "E0"
        or receipt.winner is not None
        or receipt.dominance_allowed
        or receipt.publishable
    ):
        raise ValueError("receipt protected fields invalid")
    for name in ("envelope_hash", "evidence_digest"):
        item = getattr(receipt, name)
        if item is not None and (
            type(item) is not str or _LOWER_SHA256.fullmatch(item) is None
        ):
            raise ValueError(f"{name} must be a lowercase SHA-256 digest or null")
    if type(
        receipt.model_callbacks_invoked
    ) is not int or receipt.model_callbacks_invoked not in (0, 1):
        raise ValueError("model_callbacks_invoked must be exact integer 0 or 1")
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
    if (
        type(receipt.termination_reason) is not str
        or not receipt.termination_reason
        or len(receipt.termination_reason) > 256
    ):
        raise ValueError("termination_reason must be a bounded non-empty string")
    if receipt.status == "PASS" and (
        bool(receipt.violations)
        or not receipt.reservation_durable
        or not receipt.terminal_durable
        or receipt.model_callbacks_invoked != 1
        or receipt.envelope_hash is None
        or receipt.evidence_digest is None
        or receipt.provider_requests != 1
        or receipt.input_tokens is None
        or receipt.output_tokens is None
        or receipt.cost_usd is None
        or len(receipt.authority_receipts) != 6
    ):
        raise ValueError(
            "PASS receipt durability/callback/usage/digest invariant invalid"
        )
    _assert_canonical_input(data, value)
    if receipt.status == "PASS" and not allow_unverified_pass:
        raise ValueError("PASS receipt requires trusted verification context")
    return receipt


def load_production_dispatch_receipt_v1(
    data: str | bytes,
) -> ProductionDispatchReceiptV1:
    """Strictly load non-PASS evidence; PASS needs pinned verification context."""
    return _load_production_dispatch_receipt_v1(data, allow_unverified_pass=False)


def load_verified_production_dispatch_receipt_v1(
    data: str | bytes,
    *,
    request: ProductionDispatchRequestV1,
    config: OperatorTrustConfigV1,
    qualification: ProductionQualification,
    now_unix: int,
) -> ProductionDispatchReceiptV1:
    """Load PASS only after verifying all signed receipts and outer bindings."""
    from benchmarks.codegraph_compare.production_dispatch_validation import (
        load_verified_production_dispatch_receipt_v1 as verify_load,
    )

    return verify_load(
        data,
        request=request,
        config=config,
        qualification=qualification,
        now_unix=now_unix,
    )
