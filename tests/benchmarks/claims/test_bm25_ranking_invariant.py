"""Claim invariant: BM25-ranked symbol search with relevance scores.

README claim (Key Features section):
    "BM25-ranked symbol search — results sorted by relevance score,
    not file path. relevance_score on every result (min-max normalized:
    best=1.0, weakest=0.0)"

This invariant asserts the claim's behavioral properties:
    1. Every search result carries a 'relevance_score' field.
    2. Scores are normalized to [0.0, 1.0].
    3. An exact-match result ranks first (score == 1.0 or highest).
    4. Results are sorted by relevance_score descending.

Note: Deep BM25 algorithm correctness is already tested in
tests/unit/mcp/test_fts5_bm25_ranking.py. This file tests the
*claimed user-visible behavior* from the README, not the internals.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.mcp.tools.symbol_search_tool import CodeGraphSymbolSearchTool

pytestmark = [pytest.mark.benchmark, pytest.mark.claims_benchmark]


@pytest.fixture
def indexed_project_with_symbols(tmp_path):
    """A small project where 'UserService' is the exact symbol to find."""
    (tmp_path / "service.py").write_text(
        "class UserService:\n"
        "    def get_user(self, user_id):\n"
        "        return self._find(user_id)\n"
        "\n"
        "    def _find(self, user_id):\n"
        "        pass\n"
        "\n"
        "class AdminService:\n"
        "    def get_user(self, uid):\n"
        "        pass\n"
    )
    (tmp_path / "utils.py").write_text(
        "def format_user(user):\n"
        "    return str(user)\n"
        "\n"
        "def user_count():\n"
        "    return 0\n"
    )
    cache = ASTCache(str(tmp_path))
    cache.index_project()
    cache.close()
    return tmp_path


def test_bm25_search_results_have_relevance_score(indexed_project_with_symbols):
    """Every search result must include 'relevance_score' (README claim).

    README: 'relevance_score on every result (min-max normalized: best=1.0, weakest=0.0)'
    """
    tool = CodeGraphSymbolSearchTool(str(indexed_project_with_symbols))
    result = asyncio.run(tool.execute({"query": "UserService", "output_format": "json"}))
    assert result["success"] is True
    assert result["match_count"] >= 1, "Expected at least one result for 'UserService'"  # ratchet: nondeterministic search result count

    for r in result["results"]:
        assert "relevance_score" in r, (
            f"Result {r.get('name')} is missing 'relevance_score'. "
            f"README claims BM25 relevance_score is present on every result."
        )


def test_bm25_relevance_scores_are_normalized_between_0_and_1(indexed_project_with_symbols):
    """Relevance scores must be in [0.0, 1.0] (min-max normalized per README).

    README: 'min-max normalized: best=1.0, weakest=0.0'
    """
    tool = CodeGraphSymbolSearchTool(str(indexed_project_with_symbols))
    result = asyncio.run(tool.execute({"query": "user", "output_format": "json"}))
    assert result["success"] is True

    for r in result["results"]:
        score = r.get("relevance_score", -1)
        assert 0.0 <= score <= 1.0, (
            f"relevance_score {score} for '{r.get('name')}' is outside [0.0, 1.0]. "
            f"README claims scores are min-max normalized."
        )


def test_bm25_exact_match_ranks_first(indexed_project_with_symbols):
    """An exact-match symbol must appear first in results.

    README: 'results sorted by relevance score, not file path'
    Exact name matches should always beat partial matches in BM25 ranking.
    """
    tool = CodeGraphSymbolSearchTool(str(indexed_project_with_symbols))
    result = asyncio.run(tool.execute({"query": "UserService", "output_format": "json"}))
    assert result["success"] is True
    assert result["match_count"] >= 1  # ratchet: nondeterministic search result count

    first = result["results"][0]
    assert first["name"] == "UserService", (
        f"Expected exact match 'UserService' to rank first, got '{first['name']}' "
        f"(score={first.get('relevance_score')}). "
        f"README claims results are sorted by BM25 relevance, not file path."
    )


def test_bm25_results_are_sorted_by_score_descending(indexed_project_with_symbols):
    """Results must be sorted by relevance_score in descending order.

    README: 'results sorted by relevance score, not file path'
    This is the observable guarantee: scores must be non-increasing.
    """
    tool = CodeGraphSymbolSearchTool(str(indexed_project_with_symbols))
    result = asyncio.run(tool.execute({"query": "user", "output_format": "json"}))
    assert result["success"] is True

    scores = [r.get("relevance_score", 0.0) for r in result["results"]]
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1], (
            f"Results not sorted by relevance_score descending at index {i}: "
            f"score[{i}]={scores[i]} < score[{i+1}]={scores[i+1]}. "
            f"Full scores: {scores}"
        )
