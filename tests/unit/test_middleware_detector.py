#!/usr/bin/env python3
"""Tests for middleware_detector and detect_middleware MCP tool."""

import sys
import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.middleware_detector_tool import (
    MiddlewareDetectorTool,
)
from tree_sitter_analyzer.middleware_detector import (
    MiddlewareDetector,
    MiddlewareInfo,
)

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "middleware"


@pytest.fixture(autouse=True)
def _setup_fixtures(tmp_path):
    _FIXTURES.mkdir(parents=True, exist_ok=True)


def _write_fixture(tmp_path, rel_path: str, content: str) -> str:
    p = tmp_path / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content))
    return str(p)


@pytest.fixture
def tool():
    return MiddlewareDetectorTool(_PROJECT_ROOT)


class TestMiddlewareInfo:
    def test_to_dict_roundtrip(self):
        mw = MiddlewareInfo(
            http_method="*",
            url_pattern="/api/*",
            middleware_name="auth_check",
            middleware_type="use_middleware",
            file_path="app.js",
            line_number=10,
            framework="express",
            language="javascript",
            extra={"order": 1},
        )
        d = mw.to_dict()
        assert d["middleware_name"] == "auth_check"
        assert d["framework"] == "express"
        assert d["order"] == 1


class TestFlaskMiddleware:
    def test_before_request(self, tmp_path):
        _write_fixture(
            tmp_path,
            "app.py",
            """\
            from flask import Flask
            app = Flask(__name__)

            @app.before_request
            def check_auth():
                pass
        """,
        )
        det = MiddlewareDetector(str(tmp_path))
        mws = det.detect_all()
        assert len(mws) == 1
        assert mws[0].middleware_name == "check_auth"
        assert mws[0].middleware_type == "before_request"
        assert mws[0].framework == "flask"

    def test_after_request(self, tmp_path):
        _write_fixture(
            tmp_path,
            "app.py",
            """\
            from flask import Flask
            app = Flask(__name__)

            @app.after_request
            def log_response(response):
                return response
        """,
        )
        det = MiddlewareDetector(str(tmp_path))
        mws = det.detect_all()
        assert len(mws) == 1
        assert mws[0].middleware_type == "after_request"

    def test_errorhandler(self, tmp_path):
        _write_fixture(
            tmp_path,
            "app.py",
            """\
            from flask import Flask
            app = Flask(__name__)

            @app.errorhandler(404)
            def not_found(e):
                return "Not found", 404
        """,
        )
        det = MiddlewareDetector(str(tmp_path))
        mws = det.detect_all()
        assert len(mws) == 1
        assert mws[0].middleware_type == "errorhandler"
        assert mws[0].extra.get("status_code") == "404"


class TestDjangoMiddleware:
    def test_settings_middleware(self, tmp_path):
        _write_fixture(
            tmp_path,
            "settings.py",
            """\
            MIDDLEWARE = [
                'django.middleware.security.SecurityMiddleware',
                'django.middleware.common.CommonMiddleware',
                'django.middleware.csrf.CsrfViewMiddleware',
            ]
        """,
        )
        det = MiddlewareDetector(str(tmp_path))
        mws = det.detect_all()
        assert len(mws) == 3
        names = [m.middleware_name for m in mws]
        assert "SecurityMiddleware" in names
        assert "CsrfViewMiddleware" in names
        assert all(m.framework == "django" for m in mws)


class TestFastAPIMiddleware:
    def test_middleware_decorator(self, tmp_path):
        _write_fixture(
            tmp_path,
            "main.py",
            """\
            from fastapi import FastAPI
            app = FastAPI()

            @app.middleware("http")
            async def add_timing(request, call_next):
                response = await call_next(request)
                return response
        """,
        )
        det = MiddlewareDetector(str(tmp_path))
        mws = det.detect_all()
        assert len(mws) == 1
        assert mws[0].middleware_name == "add_timing"
        assert mws[0].middleware_type == "middleware"
        assert mws[0].framework == "fastapi"


class TestExpressMiddleware:
    def test_app_use_with_path(self, tmp_path):
        _write_fixture(
            tmp_path,
            "app.js",
            """\
            const express = require('express');
            const app = express();

            app.use('/api', authMiddleware);
            app.use(logger());
        """,
        )
        det = MiddlewareDetector(str(tmp_path))
        mws = det.detect_all()
        assert len(mws) == 2
        with_path = [m for m in mws if m.url_pattern == "/api"]
        assert len(with_path) == 1
        assert with_path[0].middleware_name == "authMiddleware"
        assert mws[1].middleware_name == "logger()"

    def test_router_use(self, tmp_path):
        _write_fixture(
            tmp_path,
            "routes.js",
            """\
            const router = require('express').Router();
            router.use(corsMiddleware);
        """,
        )
        det = MiddlewareDetector(str(tmp_path))
        mws = det.detect_all()
        assert len(mws) == 1
        assert mws[0].middleware_name == "corsMiddleware"


class TestSummary:
    def test_summary(self, tmp_path):
        _write_fixture(
            tmp_path,
            "app.py",
            """\
            from flask import Flask
            app = Flask(__name__)

            @app.before_request
            def auth():
                pass

            @app.after_request
            def log(resp):
                return resp
        """,
        )
        det = MiddlewareDetector(str(tmp_path))
        s = det.summary()
        assert s["total_middlewares"] == 2
        assert s["by_framework"]["flask"] == 2
        assert s["by_type"]["before_request"] == 1


class TestLookup:
    def test_lookup_by_url_prefix(self, tmp_path):
        _write_fixture(
            tmp_path,
            "app.js",
            """\
            const app = require('express')();
            app.use('/api', apiAuth);
            app.use('/web', webAuth);
        """,
        )
        det = MiddlewareDetector(str(tmp_path))
        mws = det.lookup_by_url_prefix("/api")
        assert len(mws) == 1
        assert mws[0].middleware_name == "apiAuth"


class TestMiddlewareDetectorTool:
    def test_tool_definition(self, tool):
        defn = tool.get_tool_definition()
        assert defn["name"] == "detect_middleware"
        assert "middleware" in defn["description"].lower()

    def test_validate_arguments(self, tool):
        assert tool.validate_arguments({})

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Windows-specific incompatibility — tracked separately",
    )
    async def test_execute_all(self, tool):
        result = await tool.execute({"mode": "all", "output_format": "json"})
        assert result["success"] is True
        assert "middlewares" in result
        assert "middleware_count" in result

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Windows-specific incompatibility — tracked separately",
    )
    async def test_execute_summary(self, tool):
        result = await tool.execute({"mode": "summary", "output_format": "json"})
        assert result["success"] is True
        assert "total_middlewares" in result
        assert "by_framework" in result

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Windows-specific incompatibility — tracked separately",
    )
    async def test_execute_toon_format(self, tool):
        result = await tool.execute({"mode": "all", "output_format": "toon"})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_no_project_root_raises(self):
        t = MiddlewareDetectorTool(None)
        with pytest.raises(ValueError, match="Project root not set"):
            await t.execute({"mode": "all"})

    def test_project_root_change_resets_cache(self, tool):
        tool._get_detector()
        assert tool._detector is not None
        tool._on_project_root_changed(None)
        assert tool._detector is None
