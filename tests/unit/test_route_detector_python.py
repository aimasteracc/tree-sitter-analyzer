"""Tests for Python framework route detection: RouteInfo, Flask, FastAPI, K1 disambiguation."""

from __future__ import annotations

from pathlib import Path

from tests.unit.conftest import _write
from tree_sitter_analyzer.route_detector import RouteDetector, RouteInfo

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
