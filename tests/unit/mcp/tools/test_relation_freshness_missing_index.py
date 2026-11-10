"""#1943: an answer computed without an index names the index-build command first."""

from __future__ import annotations

from tree_sitter_analyzer.mcp.tools.relation_freshness import (
    INDEX_BUILD_STEP,
    apply_source_evidence,
)

_MISSING = {"freshness": "missing", "reason": "MISSING_INDEX"}


def _answer(**overrides: object) -> dict:
    base = {
        "verdict": "INFO",
        "completeness": "unknown",
        "agent_summary": {
            "summary_line": "callers: 'f' has 5 caller(s)",
            "verdict": "INFO",
            "next_step": "Review callers above.",
        },
    }
    return {**base, **overrides}


def test_missing_index_puts_the_build_step_first() -> None:
    result = _answer()
    apply_source_evidence(result, dict(_MISSING), [])
    assert result["next_step"] == INDEX_BUILD_STEP
    assert result["agent_summary"]["next_step"] == (
        f"{INDEX_BUILD_STEP} Review callers above."
    )
    assert INDEX_BUILD_STEP.startswith("No index for this project")
    assert "`--autoindex --autoindex-mode warm`" in INDEX_BUILD_STEP
    assert "`index action=auto mode=warm`" in INDEX_BUILD_STEP


def test_missing_index_keeps_verdict_completeness_and_evidence() -> None:
    result = _answer()
    apply_source_evidence(result, dict(_MISSING), [])
    assert result["verdict"] == "INFO"
    assert result["agent_summary"]["verdict"] == "INFO"
    assert result["completeness"] == "unknown"
    assert result["source_evidence"] == _MISSING
    assert "stale" not in result


def test_missing_index_prefixes_an_existing_top_level_step_once() -> None:
    result = _answer(next_step="Read rich/live.py:113.")
    apply_source_evidence(result, dict(_MISSING), [])
    apply_source_evidence(result, dict(_MISSING), [])
    assert result["next_step"] == f"{INDEX_BUILD_STEP} Read rich/live.py:113."
    assert result["agent_summary"]["next_step"].count(INDEX_BUILD_STEP) == 1


def test_complete_answer_gets_no_build_step() -> None:
    result = _answer(completeness="complete")
    apply_source_evidence(result, dict(_MISSING), [])
    assert "next_step" not in result
    assert result["agent_summary"]["next_step"] == "Review callers above."


def test_fresh_index_answer_is_unchanged() -> None:
    result = _answer()
    apply_source_evidence(
        result, {"freshness": "fresh", "reason": None, "snapshot_id": "s"}, []
    )
    assert "next_step" not in result
    assert result["agent_summary"]["next_step"] == "Review callers above."
