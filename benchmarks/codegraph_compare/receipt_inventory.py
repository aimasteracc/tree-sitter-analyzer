"""Shared receipt inventory validation for the closed NO1-008A pipeline."""

from __future__ import annotations

import re
from typing import Any

ELIGIBILITY_KEYS = frozenset(
    {
        "repo_id",
        "source_rules_hash",
        "commit",
        "tracked_regular_paths",
        "tracked_entries",
        "root_tree_id",
        "tracked_files",
        "eligible_paths",
        "prefilter_exclusions",
        "tracked_inventory_hash",
        "eligible_paths_hash",
        "repo_fingerprint",
    }
)
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_MODES = frozenset({"100644", "100755", "120000", "160000"})


def _path(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or not value
        or value.startswith("/")
        or "\\" in value
        or "//" in value
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise ValueError(f"{label} is not a canonical relative path")
    return value


def _hex(value: Any, label: str, pattern: re.Pattern[str] = _HEX64) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise ValueError(f"{label} must be lowercase hexadecimal")
    return value


def validate_receipt_inventory(inventory: Any) -> dict[str, Any]:
    """Return the eligibility tree after validating every receipt-used field."""
    if type(inventory) is not dict:
        raise ValueError("receipt inventory must be an object")
    eligibility = inventory.get("eligibility", inventory)
    if type(eligibility) is not dict or frozenset(eligibility) != ELIGIBILITY_KEYS:
        raise ValueError("receipt eligibility has unknown or missing fields")
    if type(eligibility["repo_id"]) is not str or not eligibility["repo_id"]:
        raise ValueError("eligibility.repo_id must be a non-empty string")
    _hex(eligibility["commit"], "eligibility.commit", _HEX40)
    root_tree = eligibility["root_tree_id"]
    if (
        type(root_tree) is not str
        or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", root_tree) is None
    ):
        raise ValueError("eligibility.root_tree_id must be a Git object ID")
    for name in (
        "source_rules_hash",
        "tracked_inventory_hash",
        "eligible_paths_hash",
        "repo_fingerprint",
    ):
        _hex(eligibility[name], f"eligibility.{name}")

    for name in ("tracked_regular_paths", "eligible_paths"):
        paths = eligibility[name]
        if type(paths) is not list or paths != sorted(set(paths)):
            raise ValueError(f"eligibility.{name} must be sorted and unique")
        for path in paths:
            _path(path, f"eligibility.{name}")

    entries = eligibility["tracked_entries"]
    if type(entries) is not list or entries != sorted(entries):
        raise ValueError("eligibility.tracked_entries must be sorted")
    for item in entries:
        if type(item) is not list or len(item) != 3:
            raise ValueError("eligibility.tracked_entries must be Git triples")
        _path(item[0], "eligibility.tracked_entries.path")
        if item[1] not in _GIT_MODES:
            raise ValueError("eligibility.tracked_entries mode is invalid")
        _hex(item[2], "eligibility.tracked_entries.object_id", _HEX40)

    files = eligibility["tracked_files"]
    if type(files) is not list or files != sorted(files):
        raise ValueError("eligibility.tracked_files must be sorted")
    for item in files:
        if type(item) is not list or len(item) != 5:
            raise ValueError(
                "eligibility.tracked_files must bind path, mode, object, size, and hash"
            )
        _path(item[0], "eligibility.tracked_files.path")
        if (
            item[1] not in {"100644", "100755"}
            or type(item[3]) is not int
            or item[3] < 0
        ):
            raise ValueError("eligibility.tracked_files metadata is invalid")
        _hex(item[2], "eligibility.tracked_files.object_id", _HEX40)
        _hex(item[4], "eligibility.tracked_files.sha256")
    if [item[0] for item in files] != eligibility["tracked_regular_paths"]:
        raise ValueError("tracked files do not bind the tracked regular path partition")

    exclusions = eligibility["prefilter_exclusions"]
    if type(exclusions) is not list or exclusions != sorted(exclusions):
        raise ValueError("eligibility.prefilter_exclusions must be sorted")
    for item in exclusions:
        if type(item) is not list or len(item) != 2:
            raise ValueError("eligibility.prefilter_exclusions must be pairs")
        _path(item[0], "eligibility.prefilter_exclusions.path")
        if type(item[1]) is not str or not item[1]:
            raise ValueError("eligibility.prefilter_exclusions reason is invalid")
    eligible = set(eligibility["eligible_paths"])
    excluded = {item[0] for item in exclusions}
    tracked = set(eligibility["tracked_regular_paths"])
    if eligible & excluded or eligible | (excluded & tracked) != tracked:
        raise ValueError("eligibility paths do not form the tracked source partition")
    return dict(eligibility)
