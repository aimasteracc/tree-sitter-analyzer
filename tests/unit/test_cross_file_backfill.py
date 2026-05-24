#!/usr/bin/env python3
"""Tests for cross-file call edge backfill and resolved callee persistence."""

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache


@pytest.fixture
def multi_file_project(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()

    (project / "services.py").write_text(
        "from models import User\n"
        "from utils import format_user, validate_input\n"
        "\n"
        "class UserService:\n"
        "    def get_user(self, user_id):\n"
        "        user = self._find_user(user_id)\n"
        "        return format_user(user)\n"
        "\n"
        "    def _find_user(self, user_id):\n"
        "        return User(user_id)\n"
        "\n"
        "def handle_request(request):\n"
        "    svc = UserService()\n"
        "    user = svc.get_user(1)\n"
        "    return user\n"
    )

    (project / "utils.py").write_text(
        "def format_user(user):\n"
        "    return str(user)\n"
        "\n"
        "def validate_input(data):\n"
        "    return bool(data)\n"
    )

    (project / "models.py").write_text(
        "class User:\n"
        "    def __init__(self, name):\n"
        "        self.name = name\n"
        "\n"
        "    def display(self):\n"
        "        return self.name\n"
    )

    (project / "main.py").write_text(
        "from services import handle_request\n"
        "\n"
        "def main():\n"
        "    result = handle_request({})\n"
        "    print(result)\n"
    )

    cache = ASTCache(str(project))
    cache.index_project(max_files=100)
    yield project, cache
    cache.close()


class TestBackfillCrossFileEdges:
    def test_backfill_returns_stats(self, multi_file_project):
        _project, cache = multi_file_project
        result = cache.backfill_cross_file_edges()
        assert "total" in result
        assert "resolved" in result
        assert "unchanged" in result
        assert "errors" in result
        assert result["total"] >= 0
        assert result["resolved"] >= 0

    def test_backfill_writes_resolved_file(self, multi_file_project):
        _project, cache = multi_file_project
        cache.backfill_cross_file_edges()
        conn = cache._get_conn()
        rows = conn.execute(
            "SELECT callee_name, callee_resolved_file FROM ast_call_edges "
            "WHERE callee_resolved_file != ''"
        ).fetchall()
        assert len(rows) > 0
        resolved_names = {r["callee_name"] for r in rows}
        assert "format_user" in resolved_names or "handle_request" in resolved_names

    def test_cross_file_stats_after_backfill(self, multi_file_project):
        _project, cache = multi_file_project
        cache.backfill_cross_file_edges()
        stats = cache.get_cross_file_stats()
        assert stats["total"] >= 0
        assert stats["resolved"] >= 0
        assert stats["cross_file"] >= 0
        assert "pct" in stats

    def test_query_callers_uses_resolved_file(self, multi_file_project):
        _project, cache = multi_file_project
        cache.backfill_cross_file_edges()
        callers = cache.query_callers("format_user")
        if callers:
            for c in callers:
                assert "callee_file" in c
                assert c["callee_file"] != ""

    def test_query_callees_uses_resolved_file(self, multi_file_project):
        _project, cache = multi_file_project
        cache.backfill_cross_file_edges()
        callees = cache.query_callees("get_user", caller_file="services.py")
        if callees:
            for c in callees:
                assert "callee_file" in c

    def test_index_project_auto_backfill(self, tmp_path):
        project = tmp_path / "proj2"
        project.mkdir()

        (project / "a.py").write_text(
            "from b import helper\n"
            "def main():\n"
            "    return helper()\n"
        )
        (project / "b.py").write_text(
            "def helper():\n"
            "    return 42\n"
        )

        cache = ASTCache(str(project))
        stats = cache.index_project(max_files=100)
        assert "cross_file_backfill" in stats
        bf = stats["cross_file_backfill"]
        assert bf["total"] >= 0
        cache.close()


class TestCrossFileStats:
    def test_stats_with_empty_cache(self, tmp_path):
        project = tmp_path / "empty_proj"
        project.mkdir()
        cache = ASTCache(str(project))
        stats = cache.get_cross_file_stats()
        assert stats["total"] == 0
        assert stats["pct"] == 0.0
        cache.close()

    def test_stats_after_indexing(self, multi_file_project):
        _project, cache = multi_file_project
        stats = cache.get_cross_file_stats()
        assert stats["total"] > 0
