from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import stat
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


PROVIDER_RECEIPT_ROLE = "provider-budget-gateway"
DEFAULT_PROVIDER_RECEIPT_KEY_ID = "legacy-provider-receipt-key"
_LOWER_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CANONICAL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


@dataclass(frozen=True)
class ProviderReservationReceiptV1:
    schema_version: int
    spec_hash: str
    reservation_id: str
    request_limit: int
    token_limit: int
    budget_ceiling_usd: float
    issuer_role: str
    key_id: str
    hmac_sha256: str


def validate_provider_reservation_receipt_v1(receipt: object) -> None:
    """Enforce the exact provider receipt schema before any HMAC operation."""
    if type(receipt) is not ProviderReservationReceiptV1:
        raise ValueError("provider receipt must be exact ProviderReservationReceiptV1")
    if type(receipt.schema_version) is not int or receipt.schema_version != 1:
        raise ValueError("provider receipt schema_version must be exact integer 1")
    if (
        type(receipt.spec_hash) is not str
        or _LOWER_SHA256.fullmatch(receipt.spec_hash) is None
    ):
        raise ValueError("provider receipt spec_hash must be lowercase SHA-256")
    for label in ("reservation_id", "issuer_role", "key_id"):
        value = getattr(receipt, label)
        if (
            type(value) is not str
            or _CANONICAL_ID.fullmatch(value) is None
            or ".." in value
        ):
            raise ValueError(f"provider receipt {label} must be a bounded canonical id")
    for label in ("request_limit", "token_limit"):
        value = getattr(receipt, label)
        if type(value) is not int or value <= 0:
            raise ValueError(
                f"provider receipt {label} must be a positive exact integer"
            )
    if (
        type(receipt.budget_ceiling_usd) is not float
        or not math.isfinite(receipt.budget_ceiling_usd)
        or receipt.budget_ceiling_usd <= 0
    ):
        raise ValueError("provider receipt budget must be a positive finite float")
    if (
        type(receipt.hmac_sha256) is not str
        or _LOWER_SHA256.fullmatch(receipt.hmac_sha256) is None
    ):
        raise ValueError("provider receipt HMAC must be lowercase SHA-256")


def issue_provider_reservation_receipt(
    spec: ProductionRunSpecV1,
    reservation_id: str,
    key: bytes,
    *,
    issuer_role: str = PROVIDER_RECEIPT_ROLE,
    key_id: str = DEFAULT_PROVIDER_RECEIPT_KEY_ID,
) -> ProviderReservationReceiptV1:
    if (
        type(key) is not bytes
        or len(key) < 32
        or type(reservation_id) is not str
        or _CANONICAL_ID.fullmatch(reservation_id) is None
        or ".." in reservation_id
        or type(issuer_role) is not str
        or _CANONICAL_ID.fullmatch(issuer_role) is None
        or ".." in issuer_role
        or type(key_id) is not str
        or _CANONICAL_ID.fullmatch(key_id) is None
        or ".." in key_id
    ):
        raise ValueError("provider reservation identity/key invalid")
    fields = {
        "schema_version": 1,
        "spec_hash": spec.spec_hash,
        "reservation_id": reservation_id,
        "request_limit": spec.request_limit,
        "token_limit": spec.token_limit,
        "budget_ceiling_usd": spec.budget_ceiling_usd,
        "issuer_role": issuer_role,
        "key_id": key_id,
    }
    signature = hmac.new(key, _canonical(fields), hashlib.sha256).hexdigest()
    return ProviderReservationReceiptV1(
        schema_version=1,
        spec_hash=spec.spec_hash,
        reservation_id=reservation_id,
        request_limit=spec.request_limit,
        token_limit=spec.token_limit,
        budget_ceiling_usd=spec.budget_ceiling_usd,
        issuer_role=issuer_role,
        key_id=key_id,
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
        self,
        provider_call: Callable[[ProductionDispatchRequestV1], ProviderRunResult],
        *,
        before_call: Callable[[], None] | None = None,
    ) -> None:
        self._call = provider_call
        self._before_call = before_call
        self._count = 0

    @property
    def count(self) -> int:
        return self._count

    def call(self, request: ProductionDispatchRequestV1) -> ProviderRunResult:
        if self._count != 0:
            raise RuntimeError("PROVIDER_REQUEST_LIMIT_REACHED")
        if self._before_call is not None:
            self._before_call()
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
            or (value["status"] == "PASS" and value["evidence_digest"] is None)
        ):
            raise ValueError("terminal event invalid")
    _assert_canonical_input(data, value)
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
        type(x) is not str or not x or len(x) > 1024 for x in value["violations"]
    ):
        raise ValueError("violations must be bounded non-empty strings")
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
        type(receipt.status) is not str
        or receipt.status not in ("PASS", "INVALID", "NOT_EVALUATED")
        or type(receipt.evidence_level) is not str
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
        not receipt.reservation_durable
        or not receipt.terminal_durable
        or receipt.model_callbacks_invoked != 1
        or receipt.envelope_hash is None
        or receipt.evidence_digest is None
        or receipt.provider_requests != 1
        or receipt.input_tokens is None
        or receipt.output_tokens is None
        or receipt.cost_usd is None
    ):
        raise ValueError(
            "PASS receipt durability/callback/usage/digest invariant invalid"
        )
    _assert_canonical_input(data, value)
    return receipt


class _Journal:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.parent_fd, self.fd, self.pin = _open_parent_and_create_root(root)
        parent_st = os.fstat(self.parent_fd)
        self.parent_pin = (parent_st.st_dev, parent_st.st_ino)

    def assert_pin(self) -> None:
        """Prove the signed path still names the pinned journal and parent."""
        try:
            parent_st = os.stat(self.root.parent, follow_symlinks=False)
            root_st = os.stat(
                self.root.name, dir_fd=self.parent_fd, follow_symlinks=False
            )
            signed_st = os.stat(self.root, follow_symlinks=False)
            parent_fd_st = os.fstat(self.parent_fd)
            root_fd_st = os.fstat(self.fd)
        except OSError as error:
            raise RuntimeError("Journal signed path is no longer reachable") from error
        if (
            stat.S_ISLNK(parent_st.st_mode)
            or (
                parent_st.st_dev,
                parent_st.st_ino,
            )
            != self.parent_pin
        ):
            raise RuntimeError("Journal parent inode changed")
        if (parent_fd_st.st_dev, parent_fd_st.st_ino) != self.parent_pin:
            raise RuntimeError("Journal parent descriptor changed")
        for candidate in (root_st, signed_st, root_fd_st):
            if (
                stat.S_ISLNK(candidate.st_mode)
                or (
                    candidate.st_dev,
                    candidate.st_ino,
                )
                != self.pin
            ):
                raise RuntimeError("Journal root inode changed")

    def _write_pinned(self, name: str, value: object) -> None:
        body = _canonical(value)
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

    def write(self, name: str, value: object) -> None:
        self.assert_pin()
        self._write_pinned(name, value)
        self.assert_pin()

    def write_unknown_to_pin(self, name: str, value: object) -> None:
        """Best-effort forensic record; never establishes signed-path durability."""
        self._write_pinned(name, value)

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


class _OperatorLedger:
    """Pinned operator-precreated ledger root and parent identity."""

    def __init__(
        self, request: ProductionDispatchRequestV1, config: OperatorTrustConfigV1
    ) -> None:
        root = config.global_nonce_ledger_root
        if root is None or str(root) != request.spec.global_nonce_ledger_root:
            raise ValueError("operator ledger path does not match signed spec")
        self.root = root
        self.parent_fd = _open_existing_dir(root.parent)
        try:
            self.fd = os.open(root.name, _DIR_FLAGS, dir_fd=self.parent_fd)
        except Exception:
            os.close(self.parent_fd)
            raise
        self.expected_root = (
            request.spec.ledger_root_device,
            request.spec.ledger_root_inode,
            request.spec.ledger_root_uid,
            request.spec.ledger_root_mode,
        )
        self.expected_parent = (
            request.spec.ledger_parent_device,
            request.spec.ledger_parent_inode,
            request.spec.ledger_parent_uid,
            request.spec.ledger_parent_mode,
        )
        self.assert_identity()

    @staticmethod
    def _identity(value: os.stat_result) -> tuple[int, int, int, int]:
        return value.st_dev, value.st_ino, value.st_uid, value.st_mode

    def assert_identity(self) -> None:
        try:
            parent_path = os.lstat(self.root.parent)
            root_path = os.lstat(self.root)
            parent_fd = os.fstat(self.parent_fd)
            root_fd = os.fstat(self.fd)
            root_at = os.stat(
                self.root.name, dir_fd=self.parent_fd, follow_symlinks=False
            )
        except OSError as error:
            raise RuntimeError("operator ledger identity unavailable") from error
        if any(
            stat.S_ISLNK(item.st_mode)
            for item in (parent_path, root_path, parent_fd, root_fd, root_at)
        ):
            raise RuntimeError("operator ledger identity contains symlink")
        if any(
            self._identity(item) != self.expected_parent
            for item in (parent_path, parent_fd)
        ):
            raise RuntimeError("operator ledger parent identity changed")
        if any(
            self._identity(item) != self.expected_root
            for item in (root_path, root_fd, root_at)
        ):
            raise RuntimeError("operator ledger root identity changed")

    def close(self) -> None:
        os.close(self.fd)
        os.close(self.parent_fd)


def _claim_global(
    request: ProductionDispatchRequestV1, ledger: _OperatorLedger
) -> None:
    ledger.assert_identity()
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
    body = _canonical(
        {
            "schema_version": 1,
            "event": "GLOBAL_CLAIM",
            "spec_hash": request.spec.spec_hash,
            "nonce": request.spec.nonce,
            "envelope_hash": request.envelope_hash,
        }
    )
    try:
        claim = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _FILE_NOFOLLOW,
            0o400,
            dir_fd=ledger.fd,
        )
        try:
            offset = 0
            while offset < len(body):
                offset += os.write(claim, body[offset:])
            os.fsync(claim)
        finally:
            os.close(claim)
        os.fsync(ledger.fd)
        os.fsync(ledger.parent_fd)
    finally:
        ledger.assert_identity()
