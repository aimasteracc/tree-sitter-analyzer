"""Canonical production run specification and signed ledger identity fields."""

from __future__ import annotations

import json
import math
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from benchmarks.codegraph_compare.canary_evidence import canonical_sha256

SCHEMA_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _nonempty(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _digest(value: object, label: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(path))


@dataclass(frozen=True)
class ProductionRunSpecV1:
    manifest_hash: str
    cell_id: str
    model: str
    prompt_sha256: str
    launch_identity_sha256: str
    workspace_baseline_sha256: str
    budget_ceiling_usd: float
    token_limit: int
    request_limit: int
    nonce: str
    expires_at_unix: int
    journal_root: str
    evidence_root: str
    global_nonce_ledger_root: str
    ledger_root_device: int
    ledger_root_inode: int
    ledger_root_uid: int
    ledger_root_mode: int
    ledger_root_ctime_ns: int
    ledger_parent_device: int
    ledger_parent_inode: int
    ledger_parent_uid: int
    ledger_parent_mode: int
    ledger_parent_ctime_ns: int

    def to_wire_dict(self) -> dict[str, object]:
        return {"schema_version": SCHEMA_VERSION, **self.__dict__}

    def to_json(self) -> str:
        return json.dumps(
            self.to_wire_dict(), allow_nan=False, sort_keys=True, separators=(",", ":")
        )

    @property
    def spec_hash(self) -> str:
        validate_production_run_spec(self)
        return canonical_sha256(
            {
                "schema_version": SCHEMA_VERSION,
                "manifest_hash": self.manifest_hash,
                "cell_id": self.cell_id,
                "model": self.model,
                "prompt_sha256": self.prompt_sha256,
                "launch_identity_sha256": self.launch_identity_sha256,
                "workspace_baseline_sha256": self.workspace_baseline_sha256,
                "budget_ceiling_usd": self.budget_ceiling_usd,
                "token_limit": self.token_limit,
                "request_limit": self.request_limit,
                "nonce": self.nonce,
                "expires_at_unix": self.expires_at_unix,
                "journal_root": self.journal_root,
                "evidence_root": self.evidence_root,
                "global_nonce_ledger_root": self.global_nonce_ledger_root,
                "ledger_root_device": self.ledger_root_device,
                "ledger_root_inode": self.ledger_root_inode,
                "ledger_root_uid": self.ledger_root_uid,
                "ledger_root_mode": self.ledger_root_mode,
                "ledger_root_ctime_ns": self.ledger_root_ctime_ns,
                "ledger_parent_device": self.ledger_parent_device,
                "ledger_parent_inode": self.ledger_parent_inode,
                "ledger_parent_uid": self.ledger_parent_uid,
                "ledger_parent_mode": self.ledger_parent_mode,
                "ledger_parent_ctime_ns": self.ledger_parent_ctime_ns,
            }
        )


def load_production_run_spec_v1(data: str | bytes) -> ProductionRunSpecV1:
    """Load strict v1 JSON, rejecting duplicate and unknown fields."""

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    value = json.loads(
        data,
        object_pairs_hook=pairs,
        parse_constant=lambda item: (_ for _ in ()).throw(
            ValueError(f"non-finite number: {item}")
        ),
    )
    if type(value) is not dict or value.pop("schema_version", None) != SCHEMA_VERSION:
        raise ValueError("unsupported run spec wire schema")
    if set(value) != set(ProductionRunSpecV1.__dataclass_fields__):
        raise ValueError("run spec fields must match strict v1 schema")
    spec = ProductionRunSpecV1(**value)
    validate_production_run_spec(spec)
    canonical = json.dumps(
        {"schema_version": SCHEMA_VERSION, **value},
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    original = data.decode("utf-8") if type(data) is bytes else data
    if (
        type(original) is not str
        or spec.to_json() != canonical
        or original != canonical
    ):
        raise ValueError("run spec is not canonical")
    return spec


def validate_production_run_spec(spec: object) -> None:
    if type(spec) is not ProductionRunSpecV1:
        raise ValueError("run spec must be an exact ProductionRunSpecV1")
    _digest(spec.manifest_hash, "manifest_hash")
    _nonempty(spec.cell_id, "cell_id")
    _nonempty(spec.model, "model")
    _digest(spec.prompt_sha256, "prompt_sha256")
    _digest(spec.launch_identity_sha256, "launch_identity_sha256")
    _digest(spec.workspace_baseline_sha256, "workspace_baseline_sha256")
    if (
        type(spec.budget_ceiling_usd) is not float
        or not math.isfinite(spec.budget_ceiling_usd)
        or spec.budget_ceiling_usd <= 0
    ):
        raise ValueError("budget_ceiling_usd must be finite and positive")
    for label, value in (
        ("token_limit", spec.token_limit),
        ("request_limit", spec.request_limit),
        ("expires_at_unix", spec.expires_at_unix),
    ):
        if type(value) is not int or value <= 0:
            raise ValueError(f"{label} must be a positive integer")
    _nonempty(spec.nonce, "nonce")
    for root_label, root_value in (
        ("journal_root", spec.journal_root),
        ("evidence_root", spec.evidence_root),
        ("global_nonce_ledger_root", spec.global_nonce_ledger_root),
    ):
        _nonempty(root_value, root_label)
        path = Path(root_value)
        if not path.is_absolute() or str(_absolute_lexical(path)) != root_value:
            raise ValueError(f"{root_label} must be a canonical absolute path")
    for label in (
        "ledger_root_device",
        "ledger_root_inode",
        "ledger_root_uid",
        "ledger_root_mode",
        "ledger_root_ctime_ns",
        "ledger_parent_device",
        "ledger_parent_inode",
        "ledger_parent_uid",
        "ledger_parent_mode",
        "ledger_parent_ctime_ns",
    ):
        value = getattr(spec, label)
        if type(value) is not int or value < 0:
            raise ValueError(f"{label} must be a non-negative exact integer")
    if spec.ledger_root_inode == 0 or spec.ledger_parent_inode == 0:
        raise ValueError("ledger inode identities must be non-zero")
    if spec.ledger_root_ctime_ns == 0 or spec.ledger_parent_ctime_ns == 0:
        raise ValueError("ledger change-time identities must be non-zero")
    if not stat.S_ISDIR(spec.ledger_root_mode) or not stat.S_ISDIR(
        spec.ledger_parent_mode
    ):
        raise ValueError("ledger root and parent identities must describe directories")


def capture_ledger_identity(root: Path) -> dict[str, int]:
    """Capture the lstat identity that an operator must bind into the signed spec."""
    root_stat = os.lstat(root)
    parent_stat = os.lstat(root.parent)
    if stat.S_ISLNK(root_stat.st_mode) or stat.S_ISLNK(parent_stat.st_mode):
        raise ValueError("ledger root and parent must not be symlinks")
    if not stat.S_ISDIR(root_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
        raise ValueError("ledger root and parent must be directories")
    return {
        "ledger_root_device": root_stat.st_dev,
        "ledger_root_inode": root_stat.st_ino,
        "ledger_root_uid": root_stat.st_uid,
        "ledger_root_mode": root_stat.st_mode,
        "ledger_root_ctime_ns": root_stat.st_ctime_ns,
        "ledger_parent_device": parent_stat.st_dev,
        "ledger_parent_inode": parent_stat.st_ino,
        "ledger_parent_uid": parent_stat.st_uid,
        "ledger_parent_mode": parent_stat.st_mode,
        "ledger_parent_ctime_ns": parent_stat.st_ctime_ns,
    }
