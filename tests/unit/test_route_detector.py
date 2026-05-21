"""Tests for RouteDetector — Flask, FastAPI, Django, Express, Spring detection."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from tree_sitter_analyzer._route_cache import RouteCache
from tree_sitter_analyzer.mcp.tools.route_detector_tool import RouteDetectorTool
from tree_sitter_analyzer.route_detector import RouteDetector, RouteInfo


def _write(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


@pytest.fixture
def flask_project(tmp_path: Path) -> Path:
    _write(
        tmp_path,
        "app.py",
        """\
from flask import Flask
app = Flask(__name__)

@app.route('/users/<id>', methods=['GET'])
def get_user(id):
    return {'id': id}

@app.route('/api/login', methods=['POST'])
def login():
    return {'ok': True}

@app.route('/healthz')
def healthz():
    return 'ok'
""",
    )
    return tmp_path


@pytest.fixture
def fastapi_project(tmp_path: Path) -> Path:
    _write(
        tmp_path,
        "api.py",
        """\
from fastapi import FastAPI
app = FastAPI()

@app.get('/items/{id}')
def read_item(id: int):
    return {'id': id}

@app.post('/items')
def create_item():
    return {}

@app.delete('/items/{id}')
def delete_item(id: int):
    return {}
""",
    )
    return tmp_path


@pytest.fixture
def express_project(tmp_path: Path) -> Path:
    _write(
        tmp_path,
        "routes.js",
        """\
const express = require('express');
const router = express.Router();
router.get('/users', function(req, res) { res.json([]); });
router.post('/users/:id', handleCreate);
router.delete('/users/:id', handleDelete);
""",
    )
    return tmp_path


@pytest.fixture
def spring_project(tmp_path: Path) -> Path:
    _write(
        tmp_path,
        "UserController.java",
        """\
package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api")
public class UserController {

    @GetMapping("/users/{id}")
    public User getUser(@PathVariable Long id) { return null; }

    @PostMapping("/users")
    public User createUser() { return null; }
}
""",
    )
    return tmp_path


@pytest.fixture
def multi_framework_project(
    flask_project: Path, fastapi_project: Path, express_project: Path
) -> Path:
    """flask_project is base; merge fastapi + express in."""
    api = fastapi_project / "api.py"
    routes = express_project / "routes.js"
    (flask_project / "api.py").write_text(api.read_text())
    (flask_project / "routes.js").write_text(routes.read_text())
    return flask_project


# ---------------------------------------------------------------------------
# RouteInfo dataclass
# ---------------------------------------------------------------------------


class TestRouteInfo:
    def test_to_dict_round_trip(self):
        r = RouteInfo(
            http_method="GET",
            url_pattern="/x",
            handler_name="h",
            file_path="/p",
            line_number=1,
            framework="flask",
            language="python",
        )
        d = r.to_dict()
        assert d["http_method"] == "GET"
        assert d["url_pattern"] == "/x"
        assert d["framework"] == "flask"
        assert d["language"] == "python"

    def test_to_dict_includes_extra(self):
        r = RouteInfo(
            http_method="GET",
            url_pattern="/x",
            handler_name="h",
            file_path="/p",
            line_number=1,
            framework="flask",
            language="python",
            extra={"middleware": ["auth"]},
        )
        assert r.to_dict()["middleware"] == ["auth"]


# ---------------------------------------------------------------------------
# Flask
# ---------------------------------------------------------------------------


class TestFlaskDetection:
    def test_detect_flask_routes(self, flask_project: Path):
        routes = RouteDetector(str(flask_project)).detect_all()
        assert len(routes) == 3
        urls = sorted(r.url_pattern for r in routes)
        assert urls == ["/api/login", "/healthz", "/users/<id>"]

    def test_flask_methods(self, flask_project: Path):
        routes = RouteDetector(str(flask_project)).detect_all()
        by_url = {r.url_pattern: r for r in routes}
        assert by_url["/users/<id>"].http_method == "GET"
        assert by_url["/api/login"].http_method == "POST"
        assert by_url["/healthz"].http_method == "GET"  # default

    def test_flask_handler_names(self, flask_project: Path):
        routes = RouteDetector(str(flask_project)).detect_all()
        names = {r.handler_name for r in routes}
        assert names == {"get_user", "login", "healthz"}

    def test_flask_framework_label(self, flask_project: Path):
        routes = RouteDetector(str(flask_project)).detect_all()
        assert all(r.framework == "flask" for r in routes)
        assert all(r.language == "python" for r in routes)


# ---------------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------------


class TestFastAPIDetection:
    def test_detect_fastapi_routes(self, fastapi_project: Path):
        routes = RouteDetector(str(fastapi_project)).detect_all()
        assert len(routes) == 3
        methods = sorted(r.http_method for r in routes)
        assert methods == ["DELETE", "GET", "POST"]

    def test_fastapi_framework_label(self, fastapi_project: Path):
        routes = RouteDetector(str(fastapi_project)).detect_all()
        assert all(r.framework == "fastapi" for r in routes)


# ---------------------------------------------------------------------------
# K1: Flask 2.x vs FastAPI @app.get/post disambiguation (round-24 dogfood)
# ---------------------------------------------------------------------------


class TestK1FrameworkDisambiguation:
    """``@app.get('/x')`` is identical between Flask 2.x and FastAPI — the
    detector must pick the framework from the file's imports, not from
    the decorator syntax alone (which previously defaulted to fastapi)."""

    def test_flask_2x_app_get_post_labels_as_flask(self, tmp_path: Path):
        """K1 reproducer: Flask 2.0+ shortcut decorators with ``from flask``
        import must be classified as ``framework='flask'``."""
        _write(
            tmp_path,
            "app.py",
            """\
from flask import Flask
app = Flask(__name__)
@app.get('/users')
def list_users():
    return []
@app.post('/users')
def create_user():
    return {}
""",
        )
        routes = RouteDetector(str(tmp_path)).detect_all()
        assert len(routes) == 2
        assert all(r.framework == "flask" for r in routes), (
            f"K1: Flask 2.x routes mislabelled — got {[r.framework for r in routes]}"
        )
        methods = sorted(r.http_method for r in routes)
        assert methods == ["GET", "POST"]

    def test_fastapi_app_get_post_still_labels_as_fastapi(self, tmp_path: Path):
        """K1 baseline: FastAPI imports must keep ``framework='fastapi'``."""
        _write(
            tmp_path,
            "api.py",
            """\
from fastapi import FastAPI
app = FastAPI()
@app.get('/items')
def list_items():
    return []
@app.post('/items')
def create_item():
    return {}
""",
        )
        routes = RouteDetector(str(tmp_path)).detect_all()
        assert len(routes) == 2
        assert all(r.framework == "fastapi" for r in routes)

    def test_express_app_get_unaffected_by_k1(self, tmp_path: Path):
        """K1 must not touch Express detection — receiver-shape + express
        import are the gates, not the python-only flask/fastapi check."""
        _write(
            tmp_path,
            "express_app.js",
            """\
const express = require('express');
const app = express();
app.get('/api/users', function(req, res) { res.json([]); });
""",
        )
        routes = RouteDetector(str(tmp_path)).detect_all()
        assert len(routes) == 1
        assert routes[0].framework == "express"

    def test_no_framework_imports_returns_nothing(self, tmp_path: Path):
        """K1: when neither flask nor fastapi is imported, fall through to
        ``unknown`` — which currently means we drop the route. Prevents
        the round-24 mislabel where ``@app.get('/x')`` in a config file
        with no framework import got tagged as fastapi by default."""
        _write(
            tmp_path,
            "ambiguous.py",
            """\
# No flask, no fastapi imports
@app.get('/ambiguous')
def handler():
    pass
""",
        )
        routes = RouteDetector(str(tmp_path)).detect_all()
        assert routes == [], (
            f"K1: routes emitted with no framework import — got {routes}"
        )

    def test_flask_legacy_route_decorator_still_works(self, tmp_path: Path):
        """``@app.route(...)`` is Flask-only and stays unconditional —
        confirms the K1 fix didn't accidentally gate the legacy form."""
        _write(
            tmp_path,
            "legacy.py",
            """\
from flask import Flask
app = Flask(__name__)
@app.route('/legacy', methods=['GET', 'POST'])
def legacy():
    return 'ok'
""",
        )
        routes = RouteDetector(str(tmp_path)).detect_all()
        assert len(routes) == 2
        assert all(r.framework == "flask" for r in routes)
        methods = sorted(r.http_method for r in routes)
        assert methods == ["GET", "POST"]

    def test_dual_import_uses_constructor_tiebreak(self, tmp_path: Path):
        """K1: unusual case where both flask and fastapi are imported —
        the active framework is inferred from the constructor call."""
        _write(
            tmp_path,
            "hybrid.py",
            """\
from flask import Flask
from fastapi import FastAPI
# Constructor call settles the tie:
app = FastAPI()
@app.get('/items')
def list_items():
    return []
""",
        )
        routes = RouteDetector(str(tmp_path)).detect_all()
        assert len(routes) == 1
        assert routes[0].framework == "fastapi"


# ---------------------------------------------------------------------------
# Express
# ---------------------------------------------------------------------------


class TestExpressDetection:
    def test_detect_express_routes(self, express_project: Path):
        routes = RouteDetector(str(express_project)).detect_all()
        assert len(routes) == 3
        methods = sorted(r.http_method for r in routes)
        assert methods == ["DELETE", "GET", "POST"]

    def test_express_framework_label(self, express_project: Path):
        routes = RouteDetector(str(express_project)).detect_all()
        assert all(r.framework == "express" for r in routes)
        assert all(r.language == "javascript" for r in routes)


# ---------------------------------------------------------------------------
# Finding 3: Express receiver-name filter (round-16b dogfood)
# ---------------------------------------------------------------------------


class TestExpressReceiverFilter:
    """``X.post('/x', ...)`` must not match unless X is an Express receiver."""

    def test_client_http_call_is_not_a_route(self, tmp_path: Path):
        """Custom apiClient.post('/save', ...) is a client call, not a route.

        Reproduces round-16b finding 3: round-15 RouteDetector reported
        2 Express routes from a file that doesn't even import express and
        whose ``.post(...)`` calls were against a custom ``apiClient``
        object — a common pattern in vanilla JS.
        """
        _write(
            tmp_path,
            "client.js",
            """\
const API_BASE = 'https://api.example.com';
const apiClient = {
    async post(endpoint, data) {
        return fetch(API_BASE + endpoint, {method: 'POST', body: JSON.stringify(data)});
    },
    async get(endpoint) {
        return fetch(API_BASE + endpoint);
    },
};

async function handleAction(action, element) {
    switch (action) {
        case 'save':
            await apiClient.post('/save', {data: 'example'});
            break;
        case 'delete':
            await apiClient.post('/delete', {id: element.dataset.id});
            break;
    }
}
""",
        )
        routes = RouteDetector(str(tmp_path)).detect_all()
        assert routes == [], (
            f"Finding 3: apiClient.post('/...') falsely matched as route — got {len(routes)}"
        )

    def test_express_routes_still_match_with_router_receiver(self, tmp_path: Path):
        """userRouter.post(...) with require('express') still detected."""
        _write(
            tmp_path,
            "routes.js",
            """\
const express = require('express');
const userRouter = express.Router();
userRouter.get('/users', listUsers);
userRouter.post('/users', createUser);
""",
        )
        routes = RouteDetector(str(tmp_path)).detect_all()
        assert len(routes) == 2, (
            "Custom <name>Router receivers must still match when file "
            f"imports express. Got {len(routes)} routes."
        )

    def test_app_post_without_express_import_is_skipped(self, tmp_path: Path):
        """app.post(...) is ignored unless the file imports express.

        Defends against random ``app`` namespaces in non-Express code
        (e.g. Electron's ``app``) producing false positives.
        """
        _write(
            tmp_path,
            "electron-main.js",
            """\
const { app } = require('electron');
app.post('/some-channel', () => {});
""",
        )
        routes = RouteDetector(str(tmp_path)).detect_all()
        assert routes == [], (
            f"Finding 3: non-express `app.post()` matched anyway — got {len(routes)}"
        )

    def test_es_module_express_import_still_detected(self, tmp_path: Path):
        """from 'express' should also count as an express import."""
        _write(
            tmp_path,
            "app.js",
            """\
import express from 'express';
const app = express();
app.get('/health', (req, res) => res.send('ok'));
""",
        )
        routes = RouteDetector(str(tmp_path)).detect_all()
        assert len(routes) == 1
        assert routes[0].url_pattern == "/health"


# ---------------------------------------------------------------------------
# Spring Boot
# ---------------------------------------------------------------------------


class TestSpringDetection:
    def test_detect_spring_routes(self, spring_project: Path):
        routes = RouteDetector(str(spring_project)).detect_all()
        assert len(routes) >= 2  # GetMapping + PostMapping
        methods = {r.http_method for r in routes}
        assert "GET" in methods
        assert "POST" in methods

    def test_spring_framework_label(self, spring_project: Path):
        routes = RouteDetector(str(spring_project)).detect_all()
        assert all(r.framework == "spring" for r in routes)
        assert all(r.language == "java" for r in routes)


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------


class TestSummaryAndLookup:
    def test_summary(self, multi_framework_project: Path):
        s = RouteDetector(str(multi_framework_project)).summary()
        assert s["total_routes"] >= 6
        assert "flask" in s["by_framework"]
        assert "fastapi" in s["by_framework"]
        assert "express" in s["by_framework"]
        assert s["file_count"] >= 3

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


# ---------------------------------------------------------------------------
# MCP tool layer
# ---------------------------------------------------------------------------


class TestRouteDetectorToolSchema:
    def test_get_tool_definition_name(self):
        defn = RouteDetectorTool().get_tool_definition()
        assert defn["name"] == "detect_routes"
        assert "inputSchema" in defn

    def test_validate_lookup_requires_url_pattern(self):
        with pytest.raises(ValueError, match="url_pattern"):
            RouteDetectorTool().validate_arguments({"mode": "lookup"})

    def test_validate_prefix_requires_url_pattern(self):
        with pytest.raises(ValueError, match="url_pattern"):
            RouteDetectorTool().validate_arguments({"mode": "prefix"})

    def test_validate_file_requires_file_path(self):
        with pytest.raises(ValueError, match="file_path"):
            RouteDetectorTool().validate_arguments({"mode": "file"})

    def test_validate_summary_no_args(self):
        assert RouteDetectorTool().validate_arguments({"mode": "summary"})


class TestRouteDetectorToolExecute:
    @staticmethod
    def _run(tool: RouteDetectorTool, args: dict) -> dict:
        return asyncio.run(tool.execute(args))

    def test_execute_summary_mode(self, flask_project: Path):
        tool = RouteDetectorTool(str(flask_project))
        result = self._run(tool, {"mode": "summary", "output_format": "json"})
        assert result["success"] is True
        assert result["mode"] == "summary"
        assert result["total_routes"] == 3

    def test_execute_all_mode(self, flask_project: Path):
        tool = RouteDetectorTool(str(flask_project))
        result = self._run(tool, {"mode": "all", "output_format": "json"})
        assert result["success"] is True
        assert result["route_count"] == 3
        assert len(result["routes"]) == 3

    def test_execute_all_with_framework_filter(self, multi_framework_project: Path):
        tool = RouteDetectorTool(str(multi_framework_project))
        result = self._run(
            tool,
            {"mode": "all", "framework": "flask", "output_format": "json"},
        )
        assert all(r["framework"] == "flask" for r in result["routes"])

    def test_execute_lookup_mode(self, flask_project: Path):
        tool = RouteDetectorTool(str(flask_project))
        result = self._run(
            tool,
            {"mode": "lookup", "url_pattern": "/healthz", "output_format": "json"},
        )
        assert result["match_count"] == 1
        assert result["routes"][0]["handler_name"] == "healthz"

    def test_execute_prefix_mode(self, flask_project: Path):
        tool = RouteDetectorTool(str(flask_project))
        result = self._run(
            tool,
            {"mode": "prefix", "url_pattern": "/api", "output_format": "json"},
        )
        assert result["match_count"] == 1

    def test_execute_file_mode(self, flask_project: Path):
        tool = RouteDetectorTool(str(flask_project))
        result = self._run(
            tool,
            {
                "mode": "file",
                "file_path": str(flask_project / "app.py"),
                "output_format": "json",
            },
        )
        assert result["route_count"] == 3

    def test_execute_unknown_mode_raises(self, flask_project: Path):
        tool = RouteDetectorTool(str(flask_project))
        # validate_arguments does not catch unknown modes; the dispatch in
        # execute() raises ValueError for any mode outside the documented set.
        with pytest.raises((ValueError, KeyError)):
            self._run(tool, {"mode": "bogus", "output_format": "json"})

    def test_file_mode_runs_path_through_validator(
        self, flask_project: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Security regression: file mode must route agent-supplied paths
        through BaseMCPTool.resolve_and_validate_file_path before parsing."""
        tool = RouteDetectorTool(str(flask_project))
        seen: list[str] = []
        original = tool.resolve_and_validate_file_path

        def spy(path: str) -> str:
            seen.append(path)
            return original(path)

        monkeypatch.setattr(tool, "resolve_and_validate_file_path", spy)
        self._run(
            tool,
            {
                "mode": "file",
                "file_path": str(flask_project / "app.py"),
                "output_format": "json",
            },
        )
        assert seen == [str(flask_project / "app.py")]

    def test_file_mode_rejects_path_traversal(self, flask_project: Path):
        """Security regression: file mode must reject ../ escapes."""
        tool = RouteDetectorTool(str(flask_project))
        with pytest.raises((ValueError, Exception)):
            self._run(
                tool,
                {
                    "mode": "file",
                    "file_path": "../../../etc/passwd",
                    "output_format": "json",
                },
            )

    def test_walk_skips_symlinks_outside_project(self, tmp_path: Path):
        """Security regression: rglob must not follow symlinks that escape project root."""
        import os

        project = tmp_path / "proj"
        project.mkdir()
        (project / "app.py").write_text(
            "from flask import Flask\napp = Flask(__name__)\n"
            "@app.route('/inside')\ndef inside(): pass\n"
        )
        # Sneak in a symlink pointing at a sibling tree that contains a file
        # with a fake route — must be ignored.
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "leak.py").write_text("@app.route('/leak')\ndef leak(): pass")
        try:
            os.symlink(outside, project / "data")
        except OSError:
            pytest.skip("symlinks not supported on this platform")

        routes = RouteDetector(str(project)).detect_all()
        assert all("/leak" not in r.url_pattern for r in routes)
        assert all("/outside/" not in r.file_path for r in routes)

    def test_set_project_path_resets_detector(
        self, flask_project: Path, tmp_path: Path
    ):
        tool = RouteDetectorTool(str(flask_project))
        first = self._run(tool, {"mode": "summary", "output_format": "json"})
        assert first["total_routes"] == 3
        # Repoint at empty dir; cached detector must be reset.
        empty = tmp_path / "empty"
        empty.mkdir()
        tool.set_project_path(str(empty))
        second = self._run(tool, {"mode": "summary", "output_format": "json"})
        assert second["total_routes"] == 0


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
        assert s1["misses"] >= 1
        assert s1["hits"] == 0

        d2 = RouteDetector(str(flask_project))
        second = d2.detect_all()
        s2 = d2.cache_stats()
        assert s2["hits"] >= 1
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
        assert s["hits"] >= 1
        assert s["misses"] >= 1  # the modified app.py

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

    def test_warm_pass_is_meaningfully_faster_than_cold(self, tmp_path: Path):
        """PERF-1 regression guard: the cache must produce a >=3x speedup on
        second invocation. (Real-world numbers on the analyzer's own repo
        are ~130x; a tighter ratio here would just measure jitter on a
        60-file synthetic project — but if someone removes the cache or
        breaks the fast path, the ratio collapses to ~1x and we catch it.)

        Skipped under heavily-loaded CI where wall-clock measurements are
        unreliable — set TSA_SKIP_PERF=1 to opt out.
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
        assert speedup >= 3, (
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
