"""Shared fixtures for tests/unit/test_route_detector_* test modules."""

from __future__ import annotations

from pathlib import Path

import pytest


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
def go_nethttp_project(tmp_path: Path) -> Path:
    _write(
        tmp_path,
        "main.go",
        """\
package main

import (
    "net/http"
)

func main() {
    http.HandleFunc("/users", listUsers)
    http.HandleFunc("/api/login", handleLogin)
    http.Handle("/static/", http.FileServer(nil))
}
""",
    )
    return tmp_path


@pytest.fixture
def go_gin_project(tmp_path: Path) -> Path:
    _write(
        tmp_path,
        "main.go",
        """\
package main

import "github.com/gin-gonic/gin"

func main() {
    r := gin.Default()
    r.GET("/items", listItems)
    r.POST("/items", createItem)
    r.DELETE("/items/:id", deleteItem)
    r.PUT("/items/:id", updateItem)
}
""",
    )
    return tmp_path


@pytest.fixture
def go_echo_project(tmp_path: Path) -> Path:
    _write(
        tmp_path,
        "main.go",
        """\
package main

import "github.com/labstack/echo"

func main() {
    e := echo.New()
    e.GET("/products", listProducts)
    e.POST("/products", createProduct)
    e.Any("/health", healthCheck)
}
""",
    )
    return tmp_path


@pytest.fixture
def go_fiber_project(tmp_path: Path) -> Path:
    _write(
        tmp_path,
        "main.go",
        """\
package main

import "github.com/gofiber/fiber"

func main() {
    app := fiber.New()
    app.Get("/orders", listOrders)
    app.Post("/orders", createOrder)
    app.Delete("/orders/:id", deleteOrder)
}
""",
    )
    return tmp_path


@pytest.fixture
def go_multi_framework_project(tmp_path: Path) -> Path:
    _write(
        tmp_path,
        "http_handlers.go",
        """\
package main

import "net/http"

func setupRoutes() {
    http.HandleFunc("/ping", pingHandler)
    http.HandleFunc("/api/status", statusHandler)
}
""",
    )
    _write(
        tmp_path,
        "gin_routes.go",
        """\
package main

import "github.com/gin-gonic/gin"

func ginRoutes(r *gin.Engine) {
    r.GET("/api/v2/data", getData)
    r.POST("/api/v2/data", postData)
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
