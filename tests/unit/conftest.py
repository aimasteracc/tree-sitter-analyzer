"""Shared fixtures for tests/unit/test_route_detector_* test modules."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.cache.schema import (
    SCHEMA_SYMBOL_ROWS,
    SCHEMA_V1,
    SCHEMA_V4_IMPORTS,
    SCHEMA_V5_ACTIVATION,
    SCHEMA_V6_VIOLATIONS,
    SCHEMA_V14_COMMENTS,
    SCHEMA_V15_LSP_CACHE,
)
from tree_sitter_analyzer.embeddings.pipeline import _SCHEMA_SYMBOL_VECTORS
from tree_sitter_analyzer.graph.edge_store import EDGE_STORE_SCHEMA


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


# ---------------------------------------------------------------------------
# Step 1: ast_cache_conn — in-memory SQLite with full TSA schema
# ---------------------------------------------------------------------------

@pytest.fixture
def ast_cache_conn():
    """Function-scoped in-memory SQLite connection with all TSA DDL applied.

    DDL is applied in FK-safe order:
      ast_index (no FK) → ast_symbol_rows → edges → ast_imports →
      ast_symbol_activation → ast_constraint_violations →
      ast_symbol_comments → lsp_resolution_cache → symbol_embeddings
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # SCHEMA_V1 creates ast_index (no FK deps); required by query_pulse CTE.
    conn.executescript(SCHEMA_V1)
    # Core symbol table.
    conn.executescript(SCHEMA_SYMBOL_ROWS)
    # Unified edge store (no FK deps on ast_symbol_rows).
    conn.executescript(EDGE_STORE_SCHEMA)
    # Dependent tables (no FK on symbol_rows, but logical dependency).
    conn.executescript(SCHEMA_V4_IMPORTS)
    conn.executescript(SCHEMA_V5_ACTIVATION)
    conn.executescript(SCHEMA_V6_VIOLATIONS)
    # Tables that REFERENCE ast_symbol_rows(id).
    conn.executescript(SCHEMA_V14_COMMENTS)
    # Table that REFERENCES both ast_symbol_rows(id) and edges(id).
    conn.executescript(SCHEMA_V15_LSP_CACHE)
    # Embeddings table — REFERENCES ast_symbol_rows(id).
    conn.executescript(_SCHEMA_SYMBOL_VECTORS)
    conn.commit()
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Step 8a: mock_embed_models — patches embed functions in pipeline + tool
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_embed_models(monkeypatch):
    """Patch _embed_with_openai and _embed_with_unixcoder in both modules.

    Yields (mock_openai, mock_unixcoder) so tests can override return_value
    or side_effect as needed.
    """
    mock_openai = MagicMock(return_value=[[0.1, 0.2, 0.3]])
    mock_unixcoder = MagicMock(return_value=[[0.4, 0.5, 0.6]])
    monkeypatch.setattr(
        "tree_sitter_analyzer.embeddings.pipeline._embed_with_openai",
        mock_openai,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.embeddings.pipeline._embed_with_unixcoder",
        mock_unixcoder,
    )
    yield (mock_openai, mock_unixcoder)


# ---------------------------------------------------------------------------
# Step 9a: fake_lsp_process — async subprocess double
# ---------------------------------------------------------------------------

@pytest.fixture
async def fake_lsp_process():
    """Fake LSP subprocess double with drivable stdout/stdin.

    Async so asyncio.StreamReader() is created with a running event loop
    (required on Python 3.13+ where get_running_loop() is used internally).
    """
    reader = asyncio.StreamReader()
    stdin_mock = MagicMock()
    stdin_mock.write = MagicMock()

    class _FakeLspProcess:
        stdout = reader
        stdin = stdin_mock
        returncode = None  # simulate running process

    return _FakeLspProcess()
