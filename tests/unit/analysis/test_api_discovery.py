#!/usr/bin/env python3
"""Tests for API Discovery Module."""

from __future__ import annotations

import tempfile
from pathlib import Path

from tree_sitter_analyzer.analysis.api_discovery import (
    ApiEndpoint,
    FrameworkType,
    calculate_metrics,
    discover_endpoints,
)


class TestApiEndpoint:
    """Test ApiEndpoint dataclass."""

    def test_create_endpoint(self):
        """Test creating an API endpoint."""
        endpoint = ApiEndpoint(
            framework=FrameworkType.FLASK,
            path="/api/users",
            methods=("GET", "POST"),
            handler="get_users",
            file="app.py",
            line=10,
        )
        assert endpoint.framework == FrameworkType.FLASK
        assert endpoint.path == "/api/users"
        assert endpoint.methods == ("GET", "POST")
        assert endpoint.handler == "get_users"
        assert endpoint.file == "app.py"
        assert endpoint.line == 10

    def test_to_dict(self):
        """Test converting endpoint to dictionary."""
        endpoint = ApiEndpoint(
            framework=FrameworkType.FLASK,
            path="/api/users",
            methods=("GET",),
            handler="get_users",
            file="app.py",
            line=10,
        )
        result = endpoint.to_dict()
        assert result["framework"] == "flask"
        assert result["path"] == "/api/users"
        assert result["methods"] == ["GET"]
        assert result["handler"] == "get_users"
        assert result["file"] == "app.py"
        assert result["line"] == 10


class TestFlaskDetection:
    """Test Flask route detection."""

    def test_detect_basic_route(self):
        """Test detecting basic @app.route decorator."""
        with tempfile.TemporaryDirectory() as tmpdir:
            flask_file = Path(tmpdir) / "app.py"
            flask_file.write_text("""
from flask import Flask
app = Flask(__name__)

@app.route("/api/users")
def get_users():
    return {"users": []}
""")

            endpoints = discover_endpoints(tmpdir, {FrameworkType.FLASK})
            assert len(endpoints) == 1
            assert endpoints[0].framework == FrameworkType.FLASK
            assert endpoints[0].path == "/api/users"
            assert endpoints[0].methods == ("GET",)
            assert endpoints[0].handler == "get_users"

    def test_detect_http_method_decorators(self):
        """Test detecting @app.get, @app.post decorators."""
        with tempfile.TemporaryDirectory() as tmpdir:
            flask_file = Path(tmpdir) / "app.py"
            flask_file.write_text("""
from flask import Flask
app = Flask(__name__)

@app.get("/api/users")
def list_users():
    pass

@app.post("/api/users")
def create_user():
    pass
""")

            endpoints = discover_endpoints(tmpdir, {FrameworkType.FLASK})
            assert len(endpoints) == 2

            get_endpoint = [e for e in endpoints if "GET" in e.methods][0]
            assert get_endpoint.path == "/api/users"
            assert get_endpoint.handler == "list_users"

            post_endpoint = [e for e in endpoints if "POST" in e.methods][0]
            assert post_endpoint.path == "/api/users"
            assert post_endpoint.handler == "create_user"

    def test_detect_blueprint_routes(self):
        """Test detecting Blueprint routes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            flask_file = Path(tmpdir) / "app.py"
            flask_file.write_text("""
from flask import Blueprint
bp = Blueprint("users", __name__)

@bp.route("/api/users")
def get_users():
    pass
""")

            endpoints = discover_endpoints(tmpdir, {FrameworkType.FLASK})
            assert len(endpoints) == 1
            assert endpoints[0].framework == FrameworkType.FLASK
            assert endpoints[0].path == "/api/users"
            assert endpoints[0].handler == "get_users"

    def test_detect_multiple_methods(self):
        """Test detecting route with multiple HTTP methods."""
        with tempfile.TemporaryDirectory() as tmpdir:
            flask_file = Path(tmpdir) / "app.py"
            flask_file.write_text("""
from flask import Flask
app = Flask(__name__)

@app.route("/api/users", methods=["GET", "POST"])
def users():
    pass
""")

            endpoints = discover_endpoints(tmpdir, {FrameworkType.FLASK})
            assert len(endpoints) == 1
            assert set(endpoints[0].methods) == {"GET", "POST"}

    def test_detect_router_decorator(self):
        """Test detecting @router routes (common pattern)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            flask_file = Path(tmpdir) / "app.py"
            flask_file.write_text("""
router = SomeRouter()

@router.get("/api/items")
def get_items():
    pass

@router.post("/api/items")
def create_item():
    pass
""")

            endpoints = discover_endpoints(tmpdir, {FrameworkType.FLASK})
            assert len(endpoints) == 2


class TestFastAPIDetection:
    """Test FastAPI endpoint detection."""

    def test_detect_basic_endpoints(self):
        """Test detecting basic FastAPI endpoints."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fastapi_file = Path(tmpdir) / "main.py"
            fastapi_file.write_text("""
from fastapi import FastAPI
app = FastAPI()

@app.get("/api/users")
def get_users():
    pass

@app.post("/api/users")
def create_user():
    pass
""")

            endpoints = discover_endpoints(tmpdir, {FrameworkType.FASTAPI})
            assert len(endpoints) == 2

            get_endpoint = [e for e in endpoints if "GET" in e.methods][0]
            assert get_endpoint.framework == FrameworkType.FASTAPI
            assert get_endpoint.path == "/api/users"

            post_endpoint = [e for e in endpoints if "POST" in e.methods][0]
            assert post_endpoint.path == "/api/users"

    def test_detect_router_endpoints(self):
        """Test detecting FastAPI router endpoints."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fastapi_file = Path(tmpdir) / "routes.py"
            fastapi_file.write_text("""
from fastapi import APIRouter
router = APIRouter()

@router.get("/api/items")
def get_items():
    pass

@router.post("/api/items")
def create_item():
    pass
""")

            endpoints = discover_endpoints(tmpdir, {FrameworkType.FASTAPI})
            assert len(endpoints) == 2

            for endpoint in endpoints:
                assert endpoint.framework == FrameworkType.FASTAPI
                assert endpoint.path == "/api/items"

    def test_detect_all_http_methods(self):
        """Test detecting all HTTP method decorators."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fastapi_file = Path(tmpdir) / "main.py"
            fastapi_file.write_text("""
from fastapi import FastAPI
app = FastAPI()

@app.get("/items")
@app.post("/items")
@app.put("/items")
@app.delete("/items")
@app.patch("/items")
def items():
    pass
""")

            endpoints = discover_endpoints(tmpdir, {FrameworkType.FASTAPI})
            assert len(endpoints) == 5

            methods = {e.methods[0] for e in endpoints}
            assert methods == {"GET", "POST", "PUT", "DELETE", "PATCH"}


class TestDjangoDetection:
    """Test Django URL pattern detection."""

    def test_detect_path_patterns(self):
        """Test detecting Django path() patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            django_file = Path(tmpdir) / "urls.py"
            django_file.write_text("""
from django.urls import path
from . import views

urlpatterns = [
    path("api/users/", views.user_list),
    path("api/users/<int:id>/", views.user_detail),
]
""")

            endpoints = discover_endpoints(tmpdir, {FrameworkType.DJANGO})
            assert len(endpoints) == 2

            assert "api/users/" in endpoints[0].path
            assert endpoints[0].framework == FrameworkType.DJANGO

    def test_detect_api_view_decorator(self):
        """Test detecting @api_view decorator."""
        with tempfile.TemporaryDirectory() as tmpdir:
            django_file = Path(tmpdir) / "views.py"
            django_file.write_text("""
from django.http import JsonResponse
from rest_framework.decorators import api_view

@api_view(["GET", "POST"])
def user_list(request):
    pass
""")

            endpoints = discover_endpoints(tmpdir, {FrameworkType.DJANGO})
            assert len(endpoints) == 1
            assert endpoints[0].framework == FrameworkType.DJANGO
            assert set(endpoints[0].methods) == {"GET", "POST"}
            assert endpoints[0].handler == "user_list"


class TestExpressDetection:
    """Test Express.js route detection."""

    def test_detect_basic_routes(self):
        """Test detecting basic Express routes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            express_file = Path(tmpdir) / "app.js"
            express_file.write_text("""
const express = require('express');
const app = express();

app.get('/api/users', (req, res) => {
    res.json([]);
});

app.post('/api/users', (req, res) => {
    res.json({created: true});
});
""")

            endpoints = discover_endpoints(tmpdir, {FrameworkType.EXPRESS})
            assert len(endpoints) == 2

            get_endpoint = [e for e in endpoints if "GET" in e.methods][0]
            assert get_endpoint.framework == FrameworkType.EXPRESS
            assert "/api/users" in get_endpoint.path

    def test_detect_router_routes(self):
        """Test detecting Express router routes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            express_file = Path(tmpdir) / "routes.js"
            express_file.write_text("""
const router = require('express').Router();

router.get('/items', getItem);
router.post('/items', createItem);
router.put('/items/:id', updateItem);
""")

            endpoints = discover_endpoints(tmpdir, {FrameworkType.EXPRESS})
            assert len(endpoints) >= 2

            for endpoint in endpoints:
                assert endpoint.framework == FrameworkType.EXPRESS

    def test_detect_typescript_routes(self):
        """Test detecting TypeScript Express routes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            express_file = Path(tmpdir) / "app.ts"
            express_file.write_text("""
import express from 'express';
const app = express();

app.get('/api/users', (req: Request, res: Response) => {
    res.json([]);
});
""")

            endpoints = discover_endpoints(tmpdir, {FrameworkType.EXPRESS})
            assert len(endpoints) == 1
            assert endpoints[0].framework == FrameworkType.EXPRESS


class TestSpringDetection:
    """Test Spring Boot endpoint detection."""

    def test_detect_get_mapping(self):
        """Test detecting @GetMapping annotation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            spring_file = Path(tmpdir) / "UserController.java"
            spring_file.write_text("""
@RestController
@RequestMapping("/api")
public class UserController {

    @GetMapping("/users")
    public List<User> getUsers() {
        return userService.findAll();
    }
}
""")

            endpoints = discover_endpoints(tmpdir, {FrameworkType.SPRING})
            assert len(endpoints) == 1
            assert endpoints[0].framework == FrameworkType.SPRING
            assert "/users" in endpoints[0].path
            assert "GET" in endpoints[0].methods

    def test_detect_post_mapping(self):
        """Test detecting @PostMapping annotation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            spring_file = Path(tmpdir) / "UserController.java"
            spring_file.write_text("""
@RestController
public class UserController {

    @PostMapping("/users")
    public User createUser(@RequestBody User user) {
        return userService.save(user);
    }
}
""")

            endpoints = discover_endpoints(tmpdir, {FrameworkType.SPRING})
            assert len(endpoints) == 1
            assert endpoints[0].framework == FrameworkType.SPRING
            assert "POST" in endpoints[0].methods

    def test_detect_request_mapping(self):
        """Test detecting @RequestMapping annotation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            spring_file = Path(tmpdir) / "UserController.java"
            spring_file.write_text("""
@RestController
@RequestMapping("/api/users")
public class UserController {

    @RequestMapping(method = RequestMethod.GET)
    public List<User> list() {
        return userService.findAll();
    }
}
""")

            endpoints = discover_endpoints(tmpdir, {FrameworkType.SPRING})
            assert len(endpoints) >= 1


class TestMetrics:
    """Test metrics calculation."""

    def test_calculate_basic_metrics(self):
        """Test calculating basic metrics."""
        endpoints = [
            ApiEndpoint(FrameworkType.FLASK, "/users", ("GET", "POST"), "handler1", "app.py", 1),
            ApiEndpoint(FrameworkType.FLASK, "/items", ("GET",), "handler2", "app.py", 2),
            ApiEndpoint(FrameworkType.FASTAPI, "/api/data", ("GET",), "handler3", "main.py", 3),
            ApiEndpoint(FrameworkType.EXPRESS, "/api/posts", ("GET", "POST"), "handler4", "routes.js", 4),
        ]

        metrics = calculate_metrics(endpoints)

        assert metrics["total_endpoints"] == 4
        assert metrics["by_framework"]["flask"] == 2
        assert metrics["by_framework"]["fastapi"] == 1
        assert metrics["by_framework"]["express"] == 1
        assert metrics["by_method"]["GET"] == 4
        assert metrics["by_method"]["POST"] == 2

    def test_calculate_empty_metrics(self):
        """Test calculating metrics with no endpoints."""
        metrics = calculate_metrics([])
        assert metrics["total_endpoints"] == 0
        assert metrics["by_framework"] == {}
        assert metrics["by_method"] == {}
        assert metrics["by_file"] == {}


class TestMultiFramework:
    """Test detecting multiple frameworks in same project."""

    def test_detect_flask_and_fastapi(self):
        """Test detecting both Flask and FastAPI endpoints."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Flask app
            flask_file = Path(tmpdir) / "flask_app.py"
            flask_file.write_text("""
from flask import Flask
app = Flask(__name__)

@app.route("/flask/users")
def flask_users():
    pass
""")

            # FastAPI app
            fastapi_file = Path(tmpdir) / "fastapi_app.py"
            fastapi_file.write_text("""
from fastapi import FastAPI
app = FastAPI()

@app.get("/fastapi/users")
def fastapi_users():
    pass
""")

            endpoints = discover_endpoints(tmpdir, {FrameworkType.FLASK, FrameworkType.FASTAPI})
            assert len(endpoints) == 2

            flask_endpoints = [e for e in endpoints if e.framework == FrameworkType.FLASK]
            fastapi_endpoints = [e for e in endpoints if e.framework == FrameworkType.FASTAPI]

            assert len(flask_endpoints) == 1
            assert len(fastapi_endpoints) == 1
            assert "/flask/users" in flask_endpoints[0].path
            assert "/fastapi/users" in fastapi_endpoints[0].path
