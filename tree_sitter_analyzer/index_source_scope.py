"""Canonical full-index source-scope descriptors and validation."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from .indexing_limits import DEFAULT_INDEX_MAX_FILES

_DEFAULT_EXCLUDES = frozenset({"tests/golden/corpus_*"})
_SOURCE_DISCOVERY_POLICY = "tsa-full-index-walk"
_SOURCE_DISCOVERY_POLICY_VERSION = 2
SOURCE_SCOPE_DESCRIPTOR_BYTE_BUDGET = 64 * 1024


@dataclass(frozen=True, slots=True)
class SourceScopeDescriptor:
    """Canonical, replayable source-selection policy certified by a build."""

    roots: tuple[str, ...]
    no_default_excludes: bool
    exclude_patterns: tuple[str, ...]
    certification_max_files: int
    discovery_policy: str = _SOURCE_DISCOVERY_POLICY
    discovery_policy_version: int = _SOURCE_DISCOVERY_POLICY_VERSION

    def __post_init__(self) -> None:
        if len(_encode_source_scope_descriptor(self).encode("ascii")) > (
            SOURCE_SCOPE_DESCRIPTOR_BYTE_BUDGET
        ):
            raise ValueError("SOURCE_SCOPE_DESCRIPTOR_TOO_LARGE")

    @property
    def effective_excludes(self) -> frozenset[str]:
        extras = frozenset(self.exclude_patterns)
        return extras if self.no_default_excludes else _DEFAULT_EXCLUDES | extras


def make_source_scope_descriptor(
    *,
    roots: tuple[str, ...] = (".",),
    no_default_excludes: bool = False,
    exclude_patterns: tuple[str, ...] = (),
    certification_max_files: int = DEFAULT_INDEX_MAX_FILES,
) -> SourceScopeDescriptor:
    """Build a normalized full-index scope descriptor."""
    descriptor = SourceScopeDescriptor(
        tuple(roots),
        no_default_excludes,
        tuple(sorted(set(exclude_patterns))),
        certification_max_files,
    )
    return parse_source_scope_descriptor(canonical_source_scope_descriptor(descriptor))


def _encode_source_scope_descriptor(scope: SourceScopeDescriptor) -> str:
    return json.dumps(
        {
            "certification_max_files": scope.certification_max_files,
            "discovery_policy": scope.discovery_policy,
            "discovery_policy_version": scope.discovery_policy_version,
            "exclude_patterns": list(scope.exclude_patterns),
            "no_default_excludes": scope.no_default_excludes,
            "roots": list(scope.roots),
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_source_scope_descriptor(scope: SourceScopeDescriptor) -> str:
    """Serialize a scope within the shared manifest reader/writer budget."""
    encoded = _encode_source_scope_descriptor(scope)
    if len(encoded.encode("ascii")) > SOURCE_SCOPE_DESCRIPTOR_BYTE_BUDGET:
        raise ValueError("SOURCE_SCOPE_DESCRIPTOR_TOO_LARGE")
    return encoded


def parse_source_scope_descriptor(raw: str) -> SourceScopeDescriptor:
    """Validate a persisted descriptor strictly enough for safe replay."""
    try:
        value: Any = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("SOURCE_SCOPE_DESCRIPTOR_INVALID") from exc
    expected = {
        "certification_max_files",
        "discovery_policy",
        "discovery_policy_version",
        "exclude_patterns",
        "no_default_excludes",
        "roots",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("SOURCE_SCOPE_DESCRIPTOR_INVALID")
    roots = value["roots"]
    patterns = value["exclude_patterns"]
    if (
        value["discovery_policy"] != _SOURCE_DISCOVERY_POLICY
        or not isinstance(value["certification_max_files"], int)
        or isinstance(value["certification_max_files"], bool)
        or value["certification_max_files"] <= 0
        or value["discovery_policy_version"] != _SOURCE_DISCOVERY_POLICY_VERSION
        or not isinstance(value["no_default_excludes"], bool)
        or not isinstance(roots, list)
        or not roots
        or not isinstance(patterns, list)
        or any(not isinstance(item, str) for item in roots + patterns)
    ):
        raise ValueError("SOURCE_SCOPE_DESCRIPTOR_INVALID")
    normalize = (
        (lambda item: item.replace("\\", "/"))
        if os.name == "nt"
        else (lambda item: item)
    )
    normalized_roots = tuple(dict.fromkeys(normalize(item) for item in roots))
    normalized_patterns = tuple(sorted({normalize(item) for item in patterns}))
    if any(
        not item
        or os.path.isabs(item)
        or item == ".."
        or item.startswith("../")
        or "/../" in item
        for item in normalized_roots
    ):
        raise ValueError("SOURCE_SCOPE_DESCRIPTOR_INVALID")
    descriptor = SourceScopeDescriptor(
        normalized_roots,
        value["no_default_excludes"],
        normalized_patterns,
        value["certification_max_files"],
    )
    if raw != canonical_source_scope_descriptor(descriptor):
        raise ValueError("SOURCE_SCOPE_DESCRIPTOR_INVALID")
    return descriptor


def validate_full_index_source_scope(
    scope: SourceScopeDescriptor,
    effective_excludes: frozenset[str],
    max_files: int | None = None,
) -> None:
    """Reject descriptors that do not describe the walk being executed."""
    normalized = frozenset(
        item.replace("\\", "/") if os.name == "nt" else item
        for item in effective_excludes
    )
    if (
        scope.roots != (".",)
        or scope.effective_excludes != normalized
        or (max_files is not None and scope.certification_max_files != max_files)
    ):
        raise ValueError("SOURCE_SCOPE_DESCRIPTOR_MISMATCH")
