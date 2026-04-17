#!/usr/bin/env python3
"""Tests for API Discovery MCP Tool."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.api_discovery_tool import ApiDiscoveryTool


class TestApiDiscoveryToolDefinition:
    """Test the tool definition."""

    def test_tool_name(self):
        """Test tool name."""
        tool = ApiDiscoveryTool("/tmp")
        definition = tool.get_tool_definition()
        assert definition["name"] == "api_discovery"

    def test_has_description(self):
        """Test tool has a description."""
        tool = ApiDiscoveryTool("/tmp")
        definition = tool.get_tool_definition()
        assert "description" in definition
        assert len(definition["description"]) > 50

    def test_has_input_schema(self):
        """Test tool has input schema."""
        tool = ApiDiscoveryTool("/tmp")
        definition = tool.get_tool_definition()
        assert "inputSchema" in definition
        assert "properties" in definition["inputSchema"]

    def test_schema_has_project_root(self):
        """Test schema includes project_root property."""
        tool = ApiDiscoveryTool("/tmp")
        definition = tool.get_tool_definition()
        assert "project_root" in definition["inputSchema"]["properties"]

    def test_schema_has_frameworks(self):
        """Test schema includes frameworks property."""
        tool = ApiDiscoveryTool("/tmp")
        definition = tool.get_tool_definition()
        assert "frameworks" in definition["inputSchema"]["properties"]

    def test_schema_has_output_format(self):
        """Test schema includes output_format property."""
        tool = ApiDiscoveryTool("/tmp")
        definition = tool.get_tool_definition()
        assert "output_format" in definition["inputSchema"]["properties"]


class TestApiDiscoveryToolValidation:
    """Test input validation."""

    @pytest.mark.asyncio
    async def test_missing_project_root(self):
        """Test error when project_root is missing."""
        tool = ApiDiscoveryTool()
        with pytest.raises(ValueError, match="project_root is required"):
            tool.validate_arguments({})

    @pytest.mark.asyncio
    async def test_invalid_framework(self):
        """Test error with invalid framework name."""
        tool = ApiDiscoveryTool()
        with pytest.raises(ValueError, match="Invalid framework"):
            tool.validate_arguments({
                "project_root": "/tmp",
                "frameworks": ["invalid_framework"],
            })

    @pytest.mark.asyncio
    async def test_invalid_output_format(self):
        """Test error with invalid output format."""
        tool = ApiDiscoveryTool()
        with pytest.raises(ValueError, match="output_format must be"):
            tool.validate_arguments({
                "project_root": "/tmp",
                "output_format": "xml",
            })

    @pytest.mark.asyncio
    async def test_invalid_include_metrics(self):
        """Test error with non-boolean include_metrics."""
        tool = ApiDiscoveryTool()
        with pytest.raises(ValueError, match="include_metrics must be a boolean"):
            tool.validate_arguments({
                "project_root": "/tmp",
                "include_metrics": "true",
            })

    @pytest.mark.asyncio
    async def test_valid_arguments(self):
        """Test valid arguments pass validation."""
        tool = ApiDiscoveryTool()
        assert tool.validate_arguments({"project_root": "/tmp"}) is True


class TestApiDiscoveryToolExecution:
    """Test tool execution."""

    @pytest.mark.asyncio
    async def test_discover_flask_endpoints(self):
        """Test discovering Flask endpoints."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create Flask app
            flask_file = Path(tmpdir) / "app.py"
            flask_file.write_text("""
from flask import Flask
app = Flask(__name__)

@app.route("/api/users")
def get_users():
    return {"users": []}

@app.post("/api/users")
def create_user():
    return {"created": True}
""")

            tool = ApiDiscoveryTool()
            result = await tool.execute({
                "project_root": tmpdir,
                "frameworks": ["flask"],
            })

            assert "error" not in result
            assert "data" in result
            assert "endpoints" in result["data"]
            assert len(result["data"]["endpoints"]) == 2

            # Verify metrics
            assert "metrics" in result["data"]
            assert result["data"]["metrics"]["total_endpoints"] == 2
            assert result["data"]["metrics"]["by_framework"]["flask"] == 2

    @pytest.mark.asyncio
    async def test_discover_fastapi_endpoints(self):
        """Test discovering FastAPI endpoints."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create FastAPI app
            fastapi_file = Path(tmpdir) / "main.py"
            fastapi_file.write_text("""
from fastapi import FastAPI
app = FastAPI()

@app.get("/items")
def get_items():
    pass

@app.post("/items")
def create_item():
    pass
""")

            tool = ApiDiscoveryTool()
            result = await tool.execute({
                "project_root": tmpdir,
                "frameworks": ["fastapi"],
            })

            assert "error" not in result
            assert "data" in result
            assert "endpoints" in result["data"]
            assert len(result["data"]["endpoints"]) == 2

            # Check first endpoint
            endpoint = result["data"]["endpoints"][0]
            assert endpoint["framework"] == "fastapi"
            assert "items" in endpoint["path"]

    @pytest.mark.asyncio
    async def test_discover_all_frameworks(self):
        """Test discovering endpoints from all frameworks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create Flask app
            (Path(tmpdir) / "flask_app.py").write_text("""
from flask import Flask
app = Flask(__name__)

@app.route("/flask/test")
def flask_test():
    pass
""")

            # Create FastAPI app
            (Path(tmpdir) / "fastapi_app.py").write_text("""
from fastapi import FastAPI
app = FastAPI()

@app.get("/fastapi/test")
def fastapi_test():
    pass
""")

            tool = ApiDiscoveryTool()
            result = await tool.execute({"project_root": tmpdir})

            assert "error" not in result
            assert "data" in result
            assert "endpoints" in result["data"]
            assert len(result["data"]["endpoints"]) == 2

            # Verify metrics
            assert result["data"]["metrics"]["by_framework"]["flask"] == 1
            assert result["data"]["metrics"]["by_framework"]["fastapi"] == 1

    @pytest.mark.asyncio
    async def test_exclude_metrics(self):
        """Test excluding metrics from output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            flask_file = Path(tmpdir) / "app.py"
            flask_file.write_text("""
from flask import Flask
app = Flask(__name__)

@app.route("/test")
def test():
    pass
""")

            tool = ApiDiscoveryTool()
            result = await tool.execute({
                "project_root": tmpdir,
                "include_metrics": False,
            })

            assert "error" not in result
            assert "data" in result
            assert "endpoints" in result["data"]
            assert "metrics" not in result["data"]

    @pytest.mark.asyncio
    async def test_empty_project(self):
        """Test behavior with project containing no API endpoints."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create empty Python file
            (Path(tmpdir) / "utils.py").write_text("""
def helper_function():
    pass
""")

            tool = ApiDiscoveryTool()
            result = await tool.execute({"project_root": tmpdir})

            assert "error" not in result
            assert "data" in result
            assert "endpoints" in result["data"]
            assert len(result["data"]["endpoints"]) == 0

            # Metrics should still be present
            assert result["data"]["metrics"]["total_endpoints"] == 0

    @pytest.mark.asyncio
    async def test_endpoint_data_structure(self):
        """Test that endpoint data has all required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            flask_file = Path(tmpdir) / "app.py"
            flask_file.write_text("""
from flask import Flask
app = Flask(__name__)

@app.route("/api/users", methods=["GET", "POST"])
def handle_users():
    pass
""")

            tool = ApiDiscoveryTool()
            result = await tool.execute({"project_root": tmpdir})

            assert "error" not in result
            endpoint = result["data"]["endpoints"][0]

            # Required fields
            assert "framework" in endpoint
            assert "path" in endpoint
            assert "methods" in endpoint
            assert "handler" in endpoint
            assert "file" in endpoint
            assert "line" in endpoint

            # Check values
            assert endpoint["framework"] == "flask"
            assert endpoint["path"] == "/api/users"
            assert set(endpoint["methods"]) == {"GET", "POST"}
            assert endpoint["handler"] == "handle_users"

    @pytest.mark.asyncio
    async def test_django_detection(self):
        """Test discovering Django endpoints."""
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

            tool = ApiDiscoveryTool()
            result = await tool.execute({
                "project_root": tmpdir,
                "frameworks": ["django"],
            })

            assert "error" not in result
            assert "data" in result
            assert "endpoints" in result["data"]
            assert len(result["data"]["endpoints"]) >= 1

    @pytest.mark.asyncio
    async def test_express_detection(self):
        """Test discovering Express.js endpoints."""
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

            tool = ApiDiscoveryTool()
            result = await tool.execute({
                "project_root": tmpdir,
                "frameworks": ["express"],
            })

            assert "error" not in result
            assert "data" in result
            assert "endpoints" in result["data"]
            assert len(result["data"]["endpoints"]) >= 1

    @pytest.mark.asyncio
    async def test_spring_detection(self):
        """Test discovering Spring Boot endpoints."""
        with tempfile.TemporaryDirectory() as tmpdir:
            spring_file = Path(tmpdir) / "UserController.java"
            spring_file.write_text("""
@RestController
public class UserController {

    @GetMapping("/users")
    public List<User> getUsers() {
        return userService.findAll();
    }

    @PostMapping("/users")
    public User createUser(@RequestBody User user) {
        return userService.save(user);
    }
}
""")

            tool = ApiDiscoveryTool()
            result = await tool.execute({
                "project_root": tmpdir,
                "frameworks": ["spring"],
            })

            assert "error" not in result
            assert "data" in result
            assert "endpoints" in result["data"]
            assert len(result["data"]["endpoints"]) >= 1


class TestApiDiscoveryToolToonOutput:
    """Test TOON output format."""

    @pytest.mark.asyncio
    async def test_toon_format(self):
        """Test TOON compressed output format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            flask_file = Path(tmpdir) / "app.py"
            flask_file.write_text("""
from flask import Flask
app = Flask(__name__)

@app.route("/test")
def test():
    pass
""")

            tool = ApiDiscoveryTool()
            result = await tool.execute({
                "project_root": tmpdir,
                "output_format": "toon",
            })

            assert "format" in result
            assert result["format"] == "toon"
            assert "toon" in result
            assert len(result["toon"]) > 0

    @pytest.mark.asyncio
    async def test_toon_error_format(self):
        """Test TOON format for errors."""
        tool = ApiDiscoveryTool()
        result = await tool.execute({
            "project_root": "/nonexistent",
            "output_format": "toon",
        })

        assert "error" in result
        assert "format" in result
        assert result["format"] == "toon"


class TestApiDiscoveryToolMetrics:
    """Test metrics calculation."""

    @pytest.mark.asyncio
    async def test_metrics_by_framework(self):
        """Test metrics grouped by framework."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Flask app
            (Path(tmpdir) / "flask_app.py").write_text("""
from flask import Flask
app = Flask(__name__)

@app.route("/test1")
def test1():
    pass
""")

            # FastAPI app
            (Path(tmpdir) / "fastapi_app.py").write_text("""
from fastapi import FastAPI
app = FastAPI()

@app.get("/test2")
def test2():
    pass
""")

            tool = ApiDiscoveryTool()
            result = await tool.execute({"project_root": tmpdir})

            assert "error" not in result
            metrics = result["data"]["metrics"]

            assert metrics["by_framework"]["flask"] == 1
            assert metrics["by_framework"]["fastapi"] == 1
            assert metrics["total_endpoints"] == 2

    @pytest.mark.asyncio
    async def test_metrics_by_method(self):
        """Test metrics grouped by HTTP method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            flask_file = Path(tmpdir) / "app.py"
            flask_file.write_text("""
from flask import Flask
app = Flask(__name__)

@app.route("/users", methods=["GET", "POST"])
def users():
    pass

@app.delete("/users/<int:id>")
def delete_user():
    pass
""")

            tool = ApiDiscoveryTool()
            result = await tool.execute({"project_root": tmpdir})

            assert "error" not in result
            metrics = result["data"]["metrics"]

            assert metrics["by_method"]["GET"] >= 1
            assert metrics["by_method"]["POST"] >= 1
            assert metrics["by_method"]["DELETE"] >= 1

    @pytest.mark.asyncio
    async def test_metrics_by_file(self):
        """Test metrics grouped by file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            flask_file = Path(tmpdir) / "app.py"
            flask_file.write_text("""
from flask import Flask
app = Flask(__name__)

@app.route("/test1")
def test1():
    pass

@app.route("/test2")
def test2():
    pass
""")

            tool = ApiDiscoveryTool()
            result = await tool.execute({"project_root": tmpdir})

            assert "error" not in result
            metrics = result["data"]["metrics"]

            assert "app.py" in metrics["by_file"]
            assert metrics["by_file"]["app.py"] == 2
