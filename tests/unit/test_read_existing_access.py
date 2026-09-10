"""Exact behavioral tests for the shared RFC-0022 access boundary."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from tree_sitter_analyzer.read_existing_access import (
    READ_EXISTING_AUTHORITY_UNCERTIFIED,
    classify_index_access,
    read_existing_gate,
    read_existing_unavailable,
    validate_index_capability_pair,
    validate_optional_index_capability_pair,
    validate_read_existing_access,
    validate_read_existing_paths,
    validate_read_existing_schema_values,
)


@pytest.mark.parametrize("access_mode", [None, "", "READ_EXISTING", 1, True])
def test_helper_rejects_every_non_literal_access_mode(access_mode: object) -> None:
    with pytest.raises(
        ValueError, match=r"^access_mode must be the string 'read_existing'$"
    ):
        validate_read_existing_access({"access_mode": access_mode})


def test_helper_distinguishes_omission_from_explicit_read_existing() -> None:
    assert (
        validate_read_existing_access({}),
        validate_read_existing_access({"access_mode": "read_existing"}),
    ) == (False, True)


@pytest.mark.parametrize("token", ["diff_snapshot_id", "route_lease_id"])
def test_helper_preserves_legacy_p02_token_without_access_mode(token: str) -> None:
    assert validate_read_existing_access({token: "legacy_token_01"}) is False


@pytest.mark.parametrize("token", ["snapshot_id", "source_generation"])
def test_new_p01_token_requires_access_mode(token: str) -> None:
    with pytest.raises(
        ValueError, match=rf"^{token} requires access_mode=read_existing$"
    ):
        validate_read_existing_access({token: "token_01"})


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (
            {"snapshot_id": "idxsnap_01"},
            "snapshot_id and source_generation are required for access_mode=read_existing",
        ),
        (
            {"source_generation": "generation_01"},
            "snapshot_id and source_generation are required for access_mode=read_existing",
        ),
        (
            {"snapshot_id": "", "source_generation": "generation_01"},
            "snapshot_id must be a non-empty string",
        ),
        (
            {"snapshot_id": "idxsnap_01", "source_generation": 7},
            "source_generation must be a non-empty string",
        ),
    ],
)
def test_required_index_pair_rejects_invalid_tokens_exactly(
    arguments: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=rf"^{message}$"):
        validate_index_capability_pair(arguments, read_existing=True)


@pytest.mark.parametrize(
    "arguments",
    [
        {"snapshot_id": "idxsnap_01"},
        {"source_generation": "generation_01"},
    ],
)
def test_optional_index_pair_rejects_half_pairs(arguments: dict[str, object]) -> None:
    with pytest.raises(
        ValueError,
        match=r"^snapshot_id and source_generation must be supplied together$",
    ):
        validate_optional_index_capability_pair(arguments)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("snapshot_id", ""),
        ("snapshot_id", 7),
        ("source_generation", ""),
        ("source_generation", 7),
    ],
)
def test_optional_index_pair_rejects_invalid_tokens(name: str, value: object) -> None:
    with pytest.raises(ValueError, match=rf"^{name} must be a non-empty string$"):
        validate_optional_index_capability_pair({name: value})


def test_optional_index_pair_accepts_complete_non_empty_pair() -> None:
    assert (
        validate_optional_index_capability_pair(
            {
                "snapshot_id": "idxsnap_01",
                "source_generation": "generation_01",
            }
        )
        is None
    )


def test_index_access_partial_snapshot_retains_acquired_identity() -> None:
    result = classify_index_access(
        snapshot_id="idxsnap_01",
        source_generation=None,
        completeness="partial",
        reason="CALL_GRAPH_INCOMPLETE",
    )

    assert result == {
        "access_mode": "read_existing",
        "access_state": "available",
        "access_reason": None,
        "source_snapshots": [
            {
                "kind": "index",
                "snapshot_id": "idxsnap_01",
                "source_generation": None,
            }
        ],
    }


@pytest.mark.parametrize(
    ("reason", "state"),
    [
        ("MISSING_INDEX", "missing"),
        ("MISSING_PROJECT_ROOT", "missing"),
        ("INCOMPATIBLE_SCHEMA", "unknown"),
        ("CORRUPT_INDEX", "unknown"),
    ],
)
def test_index_access_without_capability_preserves_reason(
    reason: str, state: str
) -> None:
    assert classify_index_access(
        snapshot_id=None,
        source_generation=None,
        completeness="unknown",
        reason=reason,
    ) == {
        "access_mode": "read_existing",
        "access_state": state,
        "access_reason": reason,
        "source_snapshots": [],
    }


def test_unavailable_helper_is_exact_for_explicit_json_request() -> None:
    result = read_existing_unavailable(
        {"access_mode": "read_existing", "output_format": "json"},
        reason="CAPABILITY_UNAVAILABLE",
    )

    assert result == {
        "success": True,
        "verdict": "WARN",
        "access_mode": "read_existing",
        "access_state": "unknown",
        "access_reason": "CAPABILITY_UNAVAILABLE",
        "source_snapshots": [],
        "output_format": "json",
    }


def test_unavailable_helper_preserves_legacy_omission() -> None:
    assert read_existing_unavailable({"output_format": "json"}) is None


class _SchemaTool:
    project_root = "/project"

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "properties": {
                "access_mode": {"type": "string", "enum": ["read_existing"]},
                "task": {"type": "string"},
                "include_tests": {"type": "boolean"},
                "hunk_cap": {"type": "integer"},
                "scope_paths": {"type": "array", "items": {"type": "string"}},
                "output_format": {"type": "string", "enum": ["json", "toon"]},
            }
        }


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("task", 123, "task must have JSON type string"),
        ("include_tests", "yes", "include_tests must have JSON type boolean"),
        ("hunk_cap", "NaN", "hunk_cap must have JSON type integer"),
        ("scope_paths", [1], "scope_paths must contain only strings"),
        ("output_format", "yaml", r"output_format must be one of \['json', 'toon'\]"),
    ],
)
def test_explicit_schema_values_reject_wrong_types_and_enums(
    name: str, value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=rf"^{message}$"):
        validate_read_existing_schema_values(
            _SchemaTool(),
            {"access_mode": "read_existing", name: value},
        )


def test_explicit_schema_values_accept_string_array_items() -> None:
    validate_read_existing_schema_values(
        _SchemaTool(),
        {"access_mode": "read_existing", "scope_paths": ["src/app.py"]},
    )


def test_explicit_schema_values_ignore_unknown_fields_for_strict_wrapper() -> None:
    validate_read_existing_schema_values(
        _SchemaTool(),
        {"access_mode": "read_existing", "unknown": "handled by BaseMCPTool"},
    )


class _RejectingSecurityValidator:
    def validate_file_path(
        self, file_path: str, *, base_path: str | None
    ) -> tuple[bool, str]:
        assert (file_path, base_path) == ("src/app.py", "/project")
        return False, "outside project"


class _PathTool:
    project_root = "/project"
    security_validator = _RejectingSecurityValidator()


def test_path_helper_preserves_project_boundary_failure() -> None:
    with pytest.raises(
        ValueError,
        match=r"^Invalid file path: Security validation failed: outside project$",
    ):
        validate_read_existing_paths(_PathTool(), ["src/app.py"])


class _RecordingValidator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def validate_file_path(
        self, file_path: str, *, base_path: str | None
    ) -> tuple[bool, str]:
        self.calls.append((file_path, base_path))
        return True, ""


def test_path_helper_fails_closed_without_bound_project_root() -> None:
    # Codex P1 (#1257): with project_root unbound, SecurityValidator gets
    # base_path=None and its project-boundary layer is skipped, so an
    # arbitrary relative path validates. The helper must fail closed with
    # the stable MISSING_PROJECT_ROOT error and never reach the validator.
    validator = _RecordingValidator()
    tool = SimpleNamespace(project_root=None, security_validator=validator)

    with pytest.raises(ValueError) as exc_info:
        validate_read_existing_paths(tool, ["src/app.py"])

    assert str(exc_info.value) == (
        "MISSING_PROJECT_ROOT: project_root must be bound before "
        "read_existing path validation"
    )
    assert validator.calls == []


class _GateTool:
    def __init__(self) -> None:
        self.validated: list[dict[str, Any]] = []

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        self.validated.append(arguments)
        return True


def test_gate_validates_before_classified_unavailable() -> None:
    tool = _GateTool()
    arguments = {
        "access_mode": "read_existing",
        "output_format": "json",
    }

    result = read_existing_gate(
        tool,
        arguments,
        reason=READ_EXISTING_AUTHORITY_UNCERTIFIED,
    )

    assert tool.validated == [arguments]
    assert result == {
        "success": True,
        "verdict": "WARN",
        "access_mode": "read_existing",
        "access_state": "unknown",
        "access_reason": READ_EXISTING_AUTHORITY_UNCERTIFIED,
        "source_snapshots": [],
        "output_format": "json",
    }
