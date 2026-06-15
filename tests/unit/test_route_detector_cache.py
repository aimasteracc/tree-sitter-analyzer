"""Tests for route cache persistence, handler-name quality, envelope consistency, and version invalidation."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from tree_sitter_analyzer._route_cache import RouteCache
from tree_sitter_analyzer.mcp.tools.route_detector_tool import RouteDetectorTool
from tree_sitter_analyzer.route_detector import RouteDetector

# ---------------------------------------------------------------------------
# PERF-1: content-hash route cache
# ---------------------------------------------------------------------------


class TestRouteCachePersistence:
    """The content-hash cache must survive across RouteDetector instances
    and avoid re-parsing files whose mtime+content are unchanged."""

    def test_warm_pass_uses_cache(self, flask_project: Path):
        d1 = RouteDetector(str(flask_project))
        first = d1.detect_all()
        s1 = d1.cache_stats()
        assert s1["misses"] == 1
        assert s1["hits"] == 0

        d2 = RouteDetector(str(flask_project))
        second = d2.detect_all()
        s2 = d2.cache_stats()
        assert s2["hits"] == 1
        assert s2["misses"] == 0
        # Same URL pattern set across runs.
        assert sorted(r.url_pattern for r in first) == sorted(
            r.url_pattern for r in second
        )

    def test_cache_invalidates_on_content_change(self, multi_framework_project: Path):
        d1 = RouteDetector(str(multi_framework_project))
        d1.detect_all()

        # Modify app.py to add a new route — mtime + content both change.
        # Other files (api.py, routes.js) must stay as cache hits.
        app = multi_framework_project / "app.py"
        app.write_text(
            app.read_text() + "\n@app.route('/new')\ndef brand_new():\n    return 'x'\n"
        )

        d2 = RouteDetector(str(multi_framework_project))
        routes = d2.detect_all()
        urls = {r.url_pattern for r in routes}
        assert "/new" in urls
        # The two unchanged files should still be cache hits.
        s = d2.cache_stats()
        assert s["hits"] == 2
        assert s["misses"] == 1  # the modified app.py

    def test_cache_disabled_flag(self, flask_project: Path):
        d = RouteDetector(str(flask_project), cache_enabled=False)
        d.detect_all()
        s = d.cache_stats()
        assert s["enabled"] is False
        assert s["hits"] == 0
        assert s["misses"] == 0

    def test_results_identical_with_and_without_cache(self, flask_project: Path):
        cached = RouteDetector(str(flask_project)).detect_all()
        # Re-instantiate after caching to force going through cache path.
        cached_via_db = RouteDetector(str(flask_project)).detect_all()
        no_cache = RouteDetector(str(flask_project), cache_enabled=False).detect_all()

        def key(rs: list) -> list:
            return sorted(
                (r.http_method, r.url_pattern, r.handler_name, r.framework) for r in rs
            )

        assert key(cached) == key(cached_via_db) == key(no_cache)

    @pytest.mark.flaky(reruns=2, reruns_delay=0)
    def test_warm_pass_is_meaningfully_faster_than_cold(self, tmp_path: Path):
        """PERF-1 regression guard: the cache must produce a >=3x speedup on
        second invocation. (Real-world numbers on the analyzer's own repo
        are ~130x; a tighter ratio here would just measure jitter on a
        60-file synthetic project — but if someone removes the cache or
        breaks the fast path, the ratio collapses to ~1x and we catch it.)

        Skipped under heavily-loaded CI where wall-clock measurements are
        unreliable — set TSA_SKIP_PERF=1 to opt out.
        Marked flaky(reruns=2) — timing is sensitive to xdist CPU contention.
        """
        import os as _os

        if _os.environ.get("TSA_SKIP_PERF"):
            pytest.skip("TSA_SKIP_PERF set")

        # Generate a project of 60 Flask files (each with 3 routes).
        project = tmp_path / "perf_project"
        project.mkdir()
        for i in range(60):
            (project / f"app_{i}.py").write_text(
                "from flask import Flask\n"
                f"app = Flask('m{i}')\n"
                + "".join(
                    f"@app.route('/r{i}_{j}')\ndef h_{i}_{j}():\n    return 'x'\n\n"
                    for j in range(3)
                )
            )

        # Prime the cache so subsequent warm runs are real cache hits.
        primed = RouteDetector(str(project)).detect_all()
        assert len(primed) == 60 * 3

        from tree_sitter_analyzer.core.parser import Parser as _Parser

        def trial() -> tuple[float, float]:
            # Clear Parser._cache so the "cold" path actually pays the parse
            # cost. Otherwise PERF-2's class-level parser cache makes both
            # cold and warm fast, and the ratio collapses.
            _Parser.cache_clear()
            d_cold = RouteDetector(str(project), cache_enabled=False)
            t0 = time.perf_counter()
            d_cold.detect_all()
            cold = time.perf_counter() - t0

            d_warm = RouteDetector(str(project), cache_enabled=True)
            t1 = time.perf_counter()
            d_warm.detect_all()
            warm = time.perf_counter() - t1
            return cold, warm

        results = sorted(trial() for _ in range(3))
        cold_med, warm_med = results[1]
        speedup = cold_med / max(warm_med, 1e-6)
        assert (
            speedup >= 3
        ), (  # ratchet: nondeterministic wall-clock timing, marked flaky(reruns=2)
            f"Expected >=3x speedup, got {speedup:.1f}x "
            f"(cold={cold_med * 1000:.1f}ms warm={warm_med * 1000:.1f}ms). "
            "PERF-1 contract regressed — cache may be disabled or fast path broken."
        )

    def test_route_cache_creates_db_file(self, flask_project: Path, tmp_path: Path):
        db = tmp_path / "subdir" / "routes.db"
        cache = RouteCache(db)
        assert db.exists()
        stats = cache.stats()
        assert stats == {"file_count": 0, "total_bytes": 0}

    def test_route_cache_round_trip(self, tmp_path: Path):
        db = tmp_path / "routes.db"
        cache = RouteCache(db)
        sample = [
            {
                "http_method": "GET",
                "url_pattern": "/x",
                "handler_name": "h",
                "file_path": "/p",
                "line_number": 1,
                "framework": "flask",
                "language": "python",
            }
        ]
        cache.put("/p", "deadbeef", 12345, sample)
        assert cache.get("/p", "deadbeef") == sample
        # Wrong hash → miss.
        assert cache.get("/p", "0badcafe") is None
        # Stat hit.
        assert cache.get_by_stat("/p", 12345) == sample
        assert cache.get_by_stat("/p", 99999) is None
        # Bulk hit.
        bulk = cache.bulk_get_by_stat([("/p", 12345), ("/missing", 0)])
        assert bulk == {"/p": sample}


# ---------------------------------------------------------------------------
# Finding F4: handler-name quality for non-callable second args
# ---------------------------------------------------------------------------


class TestHandlerNameQuality:
    """``handler_name`` must never silently be the URL pattern or a junk
    arg-spec when the call's callable slot holds something that is not a
    function reference (object literal, middleware array, etc.).

    Round-17 finding F4: ``app.post('/x', { fn: handler })`` used to report
    ``handler_name == '/x'`` because the extractor fell back to ``args[0]``
    after failing to match the second arg. We now return ``<object>`` for
    object-literal slots and ``<inline>`` for inline function expressions.
    """

    @staticmethod
    def _handlers_by_url(project: Path) -> dict[str, str]:
        # Cache stores prior results by content hash — bypass it so we
        # measure the *current* extractor, not last round's cached output.
        routes = RouteDetector(str(project), cache_enabled=False).detect_all()
        return {r.url_pattern: r.handler_name for r in routes}

    def test_inline_arrow_function_returns_inline(self, tmp_path: Path):
        from tests.unit.conftest import _write

        _write(
            tmp_path,
            "arrow.js",
            """\
const express = require('express');
const app = express();
app.get('/health', (req, res) => res.send('ok'));
app.post('/users', async (req, res) => { res.json({}); });
""",
        )
        handlers = self._handlers_by_url(tmp_path)
        assert handlers["/health"] == "<inline>", (
            f"F4: arrow-function callback must surface as '<inline>', "
            f"got {handlers['/health']!r}"
        )
        assert handlers["/users"] == "<inline>"

    def test_named_function_reference_returns_identifier(self, tmp_path: Path):
        from tests.unit.conftest import _write

        _write(
            tmp_path,
            "named.js",
            """\
const express = require('express');
const app = express();
app.get('/users', listUsers);
app.post('/users/:id', userCtrl.create);
app.delete('/users/:id', wrap(removeUser));
""",
        )
        handlers = self._handlers_by_url(tmp_path)
        # Bare identifier.
        assert handlers["/users"] == "listUsers"
        # Member expression — keep the chain so callers can resolve it.
        assert handlers["/users/:id"] in ("userCtrl.create", "wrap(removeUser)"), (
            "F4: named-reference handler shape regressed; "
            f"got {handlers['/users/:id']!r}"
        )

    def test_object_literal_handler_returns_object_marker(self, tmp_path: Path):
        """The big bug: an object literal callback slot must NOT surface
        the URL pattern as ``handler_name``."""
        from tests.unit.conftest import _write

        _write(
            tmp_path,
            "object.js",
            """\
const express = require('express');
const app = express();
app.post('/save', { method: 'GET', fn: handler });
app.put('/update', { handler: doUpdate, schema: schema });
""",
        )
        handlers = self._handlers_by_url(tmp_path)
        assert handlers["/save"] == "<object>", (
            f"F4: object-literal slot must surface as '<object>', "
            f"not as URL pattern. Got {handlers['/save']!r}"
        )
        assert handlers["/update"] == "<object>"
        # Crucial negative assertion: handler must NEVER equal the URL
        # itself (the bug we are fixing).
        assert handlers["/save"] != "/save"
        assert handlers["/update"] != "/update"

    def test_middleware_array_skipped_real_handler_wins(self, tmp_path: Path):
        """``app.get('/x', [mw1, mw2], realHandler)`` — handler must be the
        final callable, not the middleware array."""
        from tests.unit.conftest import _write

        _write(
            tmp_path,
            "with_mw.js",
            """\
const express = require('express');
const app = express();
app.get('/with-array', ['mw1', 'mw2'], finalHandler);
""",
        )
        handlers = self._handlers_by_url(tmp_path)
        assert handlers["/with-array"] == "finalHandler", (
            f"F4: middleware-array slot must be skipped; "
            f"final identifier should win. Got {handlers['/with-array']!r}"
        )
        # Belt-and-braces: never the URL.
        assert handlers["/with-array"] != "/with-array"

    def test_handler_never_starts_with_slash(self, tmp_path: Path):
        """Whatever the callback slot looks like, the handler name must
        never be a URL pattern (regression-guard for the whole class)."""
        from tests.unit.conftest import _write

        _write(
            tmp_path,
            "mixed.js",
            """\
const express = require('express');
const app = express();
app.get('/a', { obj: 1 });
app.post('/b', ['mw'], cb);
app.put('/c', (req, res) => {});
app.delete('/d', namedHandler);
""",
        )
        handlers = self._handlers_by_url(tmp_path)
        for url, handler in handlers.items():
            assert not handler.startswith("/"), (
                f"F4: handler_name {handler!r} for {url!r} looks like a URL — "
                "extractor fell back to the wrong arg."
            )


# ---------------------------------------------------------------------------
# r37f7-F4: envelope self-consistency + cache version invalidation
# ---------------------------------------------------------------------------


class TestRouteEnvelopeConsistency:
    """r37f7-F4: ``mode=summary`` used to return ``total_routes=N`` next to
    ``routes: []`` for N>0 — a self-contradicting envelope. The fix
    populates ``routes`` from the same ``detect_all()`` result that powers
    the aggregate counts so ``len(routes) == total_routes`` and
    ``len(by_framework) == 0 ⇔ total_routes == 0`` always hold.
    """

    @staticmethod
    def _run(tool: RouteDetectorTool, args: dict) -> dict:
        return asyncio.run(tool.execute(args))

    def test_summary_envelope_is_internally_consistent_on_empty_project(
        self, tmp_path: Path
    ):
        """A project with no web-framework code must produce a fully
        consistent envelope: empty routes list, zero total, empty
        ``by_framework`` dict, and a summary_line that names zeros.
        """
        (tmp_path / "lib.py").write_text(
            "def add(a, b):\n    return a + b\n",
            encoding="utf-8",
        )
        tool = RouteDetectorTool(str(tmp_path))
        result = self._run(tool, {"mode": "summary", "output_format": "json"})
        assert result["routes"] == []
        assert result["total_routes"] == 0
        assert result["by_framework"] == {}
        assert result["by_method"] == {}
        # F4 contract: routes/total_routes invariant.
        assert len(result["routes"]) == result["total_routes"]
        # F4 contract: total==0 ⇔ no frameworks.
        assert (result["total_routes"] == 0) == (len(result["by_framework"]) == 0)
        assert result["summary_line"] == "0 routes across 0 frameworks"

    def test_summary_envelope_routes_match_total_on_populated_project(
        self, flask_project: Path
    ):
        """When ``total_routes > 0`` the ``routes`` list must contain the
        actual route entries — not an empty placeholder that lies about the
        count.
        """
        tool = RouteDetectorTool(str(flask_project))
        result = self._run(tool, {"mode": "summary", "output_format": "json"})
        assert result["total_routes"] == 3
        # The critical F4 invariant: list length matches the count claim.
        assert len(result["routes"]) == result["total_routes"]
        # Aggregates derived from the same list so their cardinality matches.
        frameworks = set(result["by_framework"].keys())
        frameworks_from_routes = {r["framework"] for r in result["routes"]}
        assert frameworks == frameworks_from_routes

    def test_tree_sitter_analyzer_project_reports_zero_routes(self):
        """Regression guard for the original F4 reproducer: running the
        tool against this repo (which has no Flask/Django/FastAPI/Express/
        Spring code) must return ``total_routes==0`` and an empty
        ``routes`` list.

        Before the fix, a stale ``.ast-cache/routes.db`` produced by an
        earlier (looser) version of ``scan_express_routes`` kept returning
        ``apiClient.post('/save')`` as an Express route — the cache was
        keyed by content hash only, so a scanner-logic change couldn't
        invalidate it. The fix adds a ``scanner_version`` meta row that
        wipes pre-tightening rows on init.
        """
        import os as _os

        # Walk up to the repo root (containing pyproject.toml).
        here = Path(__file__).resolve()
        repo_root = next(
            (p for p in here.parents if (p / "pyproject.toml").exists()),
            None,
        )
        if repo_root is None or not (repo_root / "tree_sitter_analyzer").is_dir():
            pytest.skip("tree-sitter-analyzer repo root not found from this test file")
        if _os.environ.get("TSA_SKIP_REPO_DOGFOOD"):
            pytest.skip("TSA_SKIP_REPO_DOGFOOD set")
        tool = RouteDetectorTool(str(repo_root))
        result = self._run(tool, {"mode": "summary", "output_format": "json"})
        assert result["total_routes"] == 0, (
            f"tree-sitter-analyzer has no web frameworks; "
            f"got total_routes={result['total_routes']!r}, "
            f"routes={result['routes']!r}"
        )
        assert result["routes"] == []
        assert result["by_framework"] == {}


class TestRouteCacheVersionInvalidation:
    """r37f7-F4: bumping ``_SCANNER_VERSION`` must wipe stale rows so a
    scanner-logic change (e.g. tightening the express receiver whitelist)
    propagates to warm-cache callers.

    Prior to F4, the cache was keyed by ``(file_path, content_hash)``
    only. A file that yielded a false-positive route under v1 of the
    scanner would keep returning that false positive on every warm pass
    because the file content was unchanged.
    """

    def test_version_mismatch_clears_cache(self, tmp_path: Path):
        from tree_sitter_analyzer import _route_cache as cache_module

        db_path = tmp_path / "routes.db"
        # Seed the cache with one row at the current scanner version.
        cache = cache_module.RouteCache(db_path)
        cache.put(
            "/fake/path.py",
            "deadbeef",
            123456789,
            [
                {
                    "http_method": "GET",
                    "url_pattern": "/legacy",
                    "handler_name": "h",
                    "file_path": "/fake/path.py",
                    "line_number": 1,
                    "framework": "express",
                    "language": "javascript",
                }
            ],
        )
        # Sanity: the row is present.
        assert cache.get("/fake/path.py", "deadbeef") is not None

        # Simulate a scanner-logic bump by re-opening the cache under a
        # newer SCANNER_VERSION. The old row must be evicted.
        new_version = cache_module._SCANNER_VERSION + 1
        monkey_version_attr = "_SCANNER_VERSION"
        original = getattr(cache_module, monkey_version_attr)
        try:
            setattr(cache_module, monkey_version_attr, new_version)
            cache2 = cache_module.RouteCache(db_path)
        finally:
            setattr(cache_module, monkey_version_attr, original)
        assert cache2.get("/fake/path.py", "deadbeef") is None, (
            "Cache row produced by an older scanner version must be evicted "
            "when SCANNER_VERSION increases — otherwise scanner tightenings "
            "never reach warm-cache callers."
        )

    def test_version_match_preserves_cache(self, tmp_path: Path):
        from tree_sitter_analyzer import _route_cache as cache_module

        db_path = tmp_path / "routes.db"
        cache = cache_module.RouteCache(db_path)
        cache.put(
            "/fake/keep.py",
            "cafef00d",
            42,
            [],
        )
        # Reopen at the *same* version — row must survive.
        cache2 = cache_module.RouteCache(db_path)
        assert cache2.get("/fake/keep.py", "cafef00d") == []
