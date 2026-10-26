"""#1811: index-snapshot completeness on the shared response vocabulary."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.incremental_sync_support import SyncResult
from tree_sitter_analyzer.index_completeness import (
    INDEX_BUILD_IN_PROGRESS,
    INDEX_NOT_CERTIFIED,
    INDEX_SNAPSHOT_UNAVAILABLE,
    PROJECT_ROOT_MISSING,
    snapshot_completeness_fields,
)
from tree_sitter_analyzer.mcp.tools.tool_response import (
    COMPLETENESS_STATUSES,
    envelope_violations,
    known_completeness_reasons,
)
from tree_sitter_analyzer.mcp.utils.format_helper import (
    apply_output_format_to_response,
)
from tree_sitter_analyzer.uql.errors import EMPTY_QUERY, QueryError
from tree_sitter_analyzer.uql.output import error_payload


def test_unindexed_code_matches_the_shared_vocabulary() -> None:
    from tree_sitter_analyzer.index_completeness import UNINDEXED_SOURCE_FILES
    from tree_sitter_analyzer.mcp.tools.unindexed_sources import UNINDEXED_REASON

    assert UNINDEXED_SOURCE_FILES == UNINDEXED_REASON


def test_complete_snapshot_has_no_reasons() -> None:
    assert snapshot_completeness_fields("complete", None) == {
        "completeness": "complete"
    }


@pytest.mark.parametrize(
    ("snapshot", "reason", "status", "code"),
    [
        ("partial", "NO_EXACT_FULL_INDEX_MANIFEST", "incomplete", INDEX_NOT_CERTIFIED),
        ("partial", None, "incomplete", INDEX_NOT_CERTIFIED),
        ("unknown", "MISSING_INDEX", "unknown", "MISSING_INDEX"),
        ("unknown", "CONCURRENT_WRITER", "unknown", INDEX_BUILD_IN_PROGRESS),
        ("unknown", "MISSING_PROJECT_ROOT", "unknown", PROJECT_ROOT_MISSING),
        ("unknown", "SOURCE_INDEX_MISMATCH", "unknown", "SOURCE_INDEX_MISMATCH"),
        (
            "unknown",
            "some free-form OSError text",
            "unknown",
            INDEX_SNAPSHOT_UNAVAILABLE,
        ),
        ("unknown", None, "unknown", INDEX_SNAPSHOT_UNAVAILABLE),
        (None, None, "unknown", INDEX_SNAPSHOT_UNAVAILABLE),
        ("garbage", None, "unknown", INDEX_SNAPSHOT_UNAVAILABLE),
    ],
)
def test_non_complete_snapshots_name_a_known_reason(
    snapshot: str | None, reason: str | None, status: str, code: str
) -> None:
    fields = snapshot_completeness_fields(snapshot, reason)

    # Never upgraded: ``partial`` is incomplete, anything unrecognized unknown.
    assert fields == {
        "completeness": status,
        "completeness_reason": code,
        "completeness_reasons": [code],
    }
    assert fields["completeness"] in COMPLETENESS_STATUSES
    assert code in known_completeness_reasons()
    assert envelope_violations({"success": True, **fields}) == []


def test_incomplete_sync_names_its_reason() -> None:
    payload = SyncResult(scope_complete=False).to_dict()

    assert payload["completeness"] == "incomplete"
    assert payload["completeness_reasons"] == ["INDEX_SCOPE_INCOMPLETE"]
    assert envelope_violations({"success": True, **payload}) == []
    assert "completeness_reasons" not in SyncResult().to_dict()


def test_failed_uql_query_names_its_reason() -> None:
    payload = error_payload(QueryError(EMPTY_QUERY, "empty query"), "x")

    assert payload["completeness"] == "unknown"
    assert payload["completeness_reasons"] == ["QUERY_NOT_EXECUTED"]
    assert envelope_violations(payload) == []


@pytest.mark.parametrize(
    ("summary", "verdict"),
    [
        ({"verdict": "WARN"}, "WARN"),
        ({"verdict": "n/a"}, "INFO"),
        ({"verdict": "BOGUS"}, "INFO"),
        ({}, "INFO"),
        ("text", "INFO"),
    ],
)
def test_missing_top_level_verdict_follows_agent_summary(
    summary: object, verdict: str
) -> None:
    result = apply_output_format_to_response(
        {"success": True, "agent_summary": summary}
    )

    assert result["verdict"] == verdict
