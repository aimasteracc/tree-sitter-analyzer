"""Tests for RouteDetector — Flask, FastAPI, Django, Express, Spring detection."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

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

    def test_set_project_path_resets_detector(self, flask_project: Path, tmp_path: Path):
        tool = RouteDetectorTool(str(flask_project))
        first = self._run(tool, {"mode": "summary", "output_format": "json"})
        assert first["total_routes"] == 3
        # Repoint at empty dir; cached detector must be reset.
        empty = tmp_path / "empty"
        empty.mkdir()
        tool.set_project_path(str(empty))
        second = self._run(tool, {"mode": "summary", "output_format": "json"})
        assert second["total_routes"] == 0
