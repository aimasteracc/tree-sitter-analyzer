"""full_index_grammar：缺少可选语法时的发布说明（#1562）。"""

from __future__ import annotations

from tree_sitter_analyzer.mcp.tools.full_index_grammar import (
    missing_grammar_failures,
    missing_grammar_next_step,
)

_REASON = "Swift grammar not installed"


def _phase(*files: str) -> dict[str, object]:
    return {"error_details": [{"file": f, "reason": _REASON} for f in files]}


def test_failures_skip_non_dict_phases_and_dedupe_files() -> None:
    # Issue #1562: ast_cache and incremental_sync report the same file twice.
    phases = {"fts5": "ok", "ast_cache": _phase("b.swift"), "sync": _phase("b.swift")}
    assert missing_grammar_failures(phases) == [("b.swift", _REASON)]


def test_next_step_caps_the_listed_files_and_counts_the_rest() -> None:
    # Issue #1562: a repo with many swift files must keep next_step bounded.
    phases = {"ast_cache": _phase("a.swift", "b.swift", "c.swift", "d.swift")}
    assert missing_grammar_next_step(phases) == (
        "Published without 4 file(s) whose optional grammar is not installed "
        f"(a.swift: {_REASON}; b.swift: {_REASON}; c.swift: {_REASON}; and 1 more). "
        "Install the extra and re-run index action=full; graph answers about "
        "those files stay incomplete until then."
    )
