"""Tests for Go framework route detection and aggregation utilities."""

from __future__ import annotations

from pathlib import Path

from tests.unit.conftest import _write
from tree_sitter_analyzer.route_detector import RouteDetector

# ---------------------------------------------------------------------------
# Go — net/http stdlib
# ---------------------------------------------------------------------------


class TestGoNetHTTPDetection:
    def test_detect_nethttp_routes(self, go_nethttp_project: Path):
        routes = RouteDetector(str(go_nethttp_project)).detect_all()
        assert len(routes) == 3
        urls = sorted(r.url_pattern for r in routes)
        assert "/api/login" in urls
        assert "/users" in urls
        assert "/static/" in urls

    def test_nethttp_framework_label(self, go_nethttp_project: Path):
        routes = RouteDetector(str(go_nethttp_project)).detect_all()
        assert all(r.framework == "net/http" for r in routes)
        assert all(r.language == "go" for r in routes)

    def test_nethttp_handler_names(self, go_nethttp_project: Path):
        routes = RouteDetector(str(go_nethttp_project)).detect_all()
        names = {r.handler_name for r in routes}
        assert "listUsers" in names
        assert "handleLogin" in names


# ---------------------------------------------------------------------------
# Go — Gin
# ---------------------------------------------------------------------------


class TestGoGinDetection:
    def test_detect_gin_routes(self, go_gin_project: Path):
        routes = RouteDetector(str(go_gin_project)).detect_all()
        assert len(routes) == 4
        methods = sorted(r.http_method for r in routes)
        assert methods == ["DELETE", "GET", "POST", "PUT"]

    def test_gin_framework_label(self, go_gin_project: Path):
        routes = RouteDetector(str(go_gin_project)).detect_all()
        assert all(r.framework == "gin" for r in routes)
        assert all(r.language == "go" for r in routes)

    def test_gin_url_patterns(self, go_gin_project: Path):
        routes = RouteDetector(str(go_gin_project)).detect_all()
        urls = {r.url_pattern for r in routes}
        assert "/items" in urls
        assert "/items/:id" in urls


# ---------------------------------------------------------------------------
# Go — Echo
# ---------------------------------------------------------------------------


class TestGoEchoDetection:
    def test_detect_echo_routes(self, go_echo_project: Path):
        routes = RouteDetector(str(go_echo_project)).detect_all()
        assert len(routes) == 3
        methods = sorted(r.http_method for r in routes)
        assert "GET" in methods
        assert "POST" in methods
        assert "ANY" in methods

    def test_echo_framework_label(self, go_echo_project: Path):
        routes = RouteDetector(str(go_echo_project)).detect_all()
        assert all(r.framework == "echo" for r in routes)
        assert all(r.language == "go" for r in routes)


# ---------------------------------------------------------------------------
# Go — Fiber
# ---------------------------------------------------------------------------


class TestGoFiberDetection:
    def test_detect_fiber_routes(self, go_fiber_project: Path):
        routes = RouteDetector(str(go_fiber_project)).detect_all()
        assert len(routes) == 3
        methods = sorted(r.http_method for r in routes)
        assert methods == ["DELETE", "GET", "POST"]

    def test_fiber_framework_label(self, go_fiber_project: Path):
        routes = RouteDetector(str(go_fiber_project)).detect_all()
        assert all(r.framework == "fiber" for r in routes)
        assert all(r.language == "go" for r in routes)


# ---------------------------------------------------------------------------
# Go — multi-framework project
# ---------------------------------------------------------------------------


class TestGoMultiFramework:
    def test_detect_mixed_go_frameworks(self, go_multi_framework_project: Path):
        routes = RouteDetector(str(go_multi_framework_project)).detect_all()
        assert len(routes) == 4
        frameworks = {r.framework for r in routes}
        assert "net/http" in frameworks
        assert "gin" in frameworks

    def test_go_file_dispatch(self, go_gin_project: Path):
        routes = RouteDetector(str(go_gin_project)).detect_file(
            str(go_gin_project / "main.go")
        )
        assert len(routes) == 4

    def test_go_in_multi_framework_summary(self, go_multi_framework_project: Path):
        s = RouteDetector(str(go_multi_framework_project)).summary()
        assert s["total_routes"] == 4
        assert "net/http" in s["by_framework"]
        assert "gin" in s["by_framework"]


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------


class TestSummaryAndLookup:
    def test_summary(self, multi_framework_project: Path):
        s = RouteDetector(str(multi_framework_project)).summary()
        assert s["total_routes"] >= 6  # ratchet: nondeterministic
        assert "flask" in s["by_framework"]
        assert "fastapi" in s["by_framework"]
        assert "express" in s["by_framework"]
        assert s["file_count"] >= 3  # ratchet: nondeterministic

    def test_lookup_handler_exact_match(self, flask_project: Path):
        matches = RouteDetector(str(flask_project)).lookup_handler("/api/login")
        assert len(matches) == 1
        assert matches[0].handler_name == "login"

    def test_lookup_handler_no_match(self, flask_project: Path):
        assert RouteDetector(str(flask_project)).lookup_handler("/nope") == []

    def test_lookup_url_prefix_matches(self, flask_project: Path):
        matches = RouteDetector(str(flask_project)).lookup_url_prefix("/api")
        assert len(matches) == 1
        assert matches[0].url_pattern.startswith("/api")

    def test_lookup_url_prefix_normalizes_leading_slash(self, flask_project: Path):
        a = RouteDetector(str(flask_project)).lookup_url_prefix("api")
        b = RouteDetector(str(flask_project)).lookup_url_prefix("/api")
        assert {r.url_pattern for r in a} == {r.url_pattern for r in b}

    def test_detect_all_is_cached(self, flask_project: Path):
        d = RouteDetector(str(flask_project))
        first = d.detect_all()
        second = d.detect_all()
        assert first is second  # cached list identity


# ---------------------------------------------------------------------------
# r37r: summary_line grammar — singular/plural rules
# ---------------------------------------------------------------------------


class TestR37rSummaryLineGrammar:
    """r37r dogfood: ``2 routes across 1 frameworks`` is ungrammatical.

    Caught by dogfooding ``--detect-routes`` on our own project (2 routes,
    1 framework). The hardcoded template ``"{N} routes across {M} frameworks"``
    pluralized both nouns regardless of count. The fix introduces a
    ``_pluralize`` helper that applies the English ``n != 1 → plural`` rule.
    """

    def test_single_framework_uses_singular(self):
        """Summary mode with 1 framework must say 'framework' not 'frameworks'."""
        from tree_sitter_analyzer.mcp.tools.route_detector_tool import (
            _attach_route_summary,
        )

        result = {"total_routes": 2, "by_framework": {"express": 2}}
        _attach_route_summary(result, "summary")
        assert result["summary_line"] == "2 routes across 1 framework"

    def test_multiple_frameworks_uses_plural(self):
        """Summary mode with 3 frameworks keeps 'frameworks' (plural)."""
        from tree_sitter_analyzer.mcp.tools.route_detector_tool import (
            _attach_route_summary,
        )

        result = {
            "total_routes": 9,
            "by_framework": {"flask": 3, "fastapi": 3, "express": 3},
        }
        _attach_route_summary(result, "summary")
        assert result["summary_line"] == "9 routes across 3 frameworks"

    def test_single_route_uses_singular(self):
        """1 route + 1 framework → both singular."""
        from tree_sitter_analyzer.mcp.tools.route_detector_tool import (
            _attach_route_summary,
        )

        result = {"total_routes": 1, "by_framework": {"flask": 1}}
        _attach_route_summary(result, "summary")
        assert result["summary_line"] == "1 route across 1 framework"

    def test_zero_routes_uses_plural(self):
        """English convention: '0 routes' (plural) — n != 1 → plural."""
        from tree_sitter_analyzer.mcp.tools.route_detector_tool import (
            _attach_route_summary,
        )

        result = {"total_routes": 0, "by_framework": {}}
        _attach_route_summary(result, "summary")
        assert result["summary_line"] == "0 routes across 0 frameworks"

    def test_mode_all_single_route_uses_singular(self):
        """'all' mode also pluralizes by count."""
        from tree_sitter_analyzer.mcp.tools.route_detector_tool import (
            _attach_route_summary,
        )

        result = {"total_routes": 1, "by_framework": {"flask": 1}, "routes": []}
        _attach_route_summary(result, "all")
        assert result["summary_line"] == "1 route"

    def test_mode_all_multiple_routes_uses_plural(self):
        """'all' mode with 5 routes stays plural."""
        from tree_sitter_analyzer.mcp.tools.route_detector_tool import (
            _attach_route_summary,
        )

        result = {"total_routes": 5, "by_framework": {"flask": 5}, "routes": []}
        _attach_route_summary(result, "all")
        assert result["summary_line"] == "5 routes"


# ---------------------------------------------------------------------------
# detect_file: language dispatch (regression: extension lookup bug)
# ---------------------------------------------------------------------------


class TestDetectFileLanguageDispatch:
    """Regression: detect_file used to call _language_from_ext(ext) instead of
    _language_from_ext(file_path), causing it to always return None."""

    def test_python_file_dispatch(self, flask_project: Path):
        routes = RouteDetector(str(flask_project)).detect_file(
            str(flask_project / "app.py")
        )
        assert len(routes) == 3

    def test_javascript_file_dispatch(self, express_project: Path):
        routes = RouteDetector(str(express_project)).detect_file(
            str(express_project / "routes.js")
        )
        assert len(routes) == 3

    def test_unknown_extension_returns_empty(self, tmp_path: Path):
        f = tmp_path / "notes.txt"
        f.write_text("hello")
        assert RouteDetector(str(tmp_path)).detect_file(str(f)) == []


# ---------------------------------------------------------------------------
# Filesystem walk: excluded directories
# ---------------------------------------------------------------------------


class TestSourceWalk:
    def test_excludes_node_modules(self, tmp_path: Path):
        _write(
            tmp_path,
            "node_modules/express/index.js",
            "router.get('/leak', h);",
        )
        _write(
            tmp_path,
            "app.py",
            "from flask import Flask\napp = Flask(__name__)\n@app.route('/')\ndef i(): return 1\n",
        )
        routes = RouteDetector(str(tmp_path)).detect_all()
        assert all("/node_modules/" not in r.file_path for r in routes)

    def test_excludes_venv(self, tmp_path: Path):
        _write(tmp_path, ".venv/lib/x.py", "@app.route('/v')\ndef v(): pass")
        _write(tmp_path, "app.py", "@app.route('/')\ndef i(): pass")
        routes = RouteDetector(str(tmp_path)).detect_all()
        assert all("/.venv/" not in r.file_path for r in routes)

    def test_excludes_hidden_work_dirs(self, tmp_path: Path):
        _write(
            tmp_path,
            ".benchmark-repos/gin/gin_test.go",
            """\
package main

func routes(r *gin.Engine) {
    r.GET("/leak", handler)
}
""",
        )
        _write(
            tmp_path,
            "app.py",
            "from flask import Flask\napp = Flask(__name__)\n@app.route('/')\ndef i(): pass",
        )
        routes = RouteDetector(str(tmp_path)).detect_all()
        assert routes
        assert all("/.benchmark-repos/" not in r.file_path for r in routes)
