#!/usr/bin/env python3
"""
End-to-end integration tests for Code Intelligence Graph.

Tests the full pipeline: source code -> parsing -> indexing -> MCP tool execution.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.intelligence.architecture_metrics import ArchitectureMetrics
from tree_sitter_analyzer.intelligence.call_graph import CallGraphBuilder
from tree_sitter_analyzer.intelligence.dependency_graph import DependencyGraphBuilder
from tree_sitter_analyzer.intelligence.formatters import (
    format_architecture_report,
    format_impact_result,
    format_trace_result,
)
from tree_sitter_analyzer.intelligence.impact_analyzer import ImpactAnalyzer
from tree_sitter_analyzer.intelligence.models import (
    DependencyEdge,
    SymbolDefinition,
    SymbolReference,
)
from tree_sitter_analyzer.intelligence.symbol_index import SymbolIndex

# ---- Sample project source code for E2E tests ----

AUTH_SERVICE_CODE = """\
class AuthService:
    def __init__(self, db):
        self.db = db

    def login(self, username, password):
        user = self.db.find_user(username)
        if user and user.check_password(password):
            return self._create_token(user)
        return None

    def _create_token(self, user):
        return f"token-{user.id}"

    def logout(self, token):
        self.db.invalidate_token(token)
"""

USER_MODEL_CODE = """\
class User:
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash

    def check_password(self, password):
        return hash(password) == self.password_hash
"""

API_HANDLER_CODE = """\
from auth_service import AuthService

class APIHandler:
    def __init__(self):
        self.auth = AuthService(db=None)

    def handle_login(self, request):
        result = self.auth.login(request.username, request.password)
        if result:
            return {"token": result}
        return {"error": "invalid credentials"}

    def handle_logout(self, request):
        self.auth.logout(request.token)
        return {"status": "ok"}
"""

TEST_AUTH_CODE = """\
from auth_service import AuthService

def test_login_success():
    auth = AuthService(db=MockDB())
    token = auth.login("admin", "pass123")
    assert token is not None

def test_login_failure():
    auth = AuthService(db=MockDB())
    token = auth.login("admin", "wrong")
    assert token is None
"""


class TestEndToEndPipeline:
    """Test the full pipeline from source -> index -> query."""

    @pytest.fixture
    def indexed_project(self):
        """Set up a fully indexed sample project."""
        call_graph = CallGraphBuilder()
        dep_graph = DependencyGraphBuilder()
        symbol_index = SymbolIndex()

        # Index all source files
        call_graph.extract_calls_from_source(AUTH_SERVICE_CODE, "auth_service.py")
        call_graph.extract_calls_from_source(USER_MODEL_CODE, "user_model.py")
        call_graph.extract_calls_from_source(API_HANDLER_CODE, "api_handler.py")
        call_graph.extract_calls_from_source(TEST_AUTH_CODE, "test_auth.py")

        # Add symbol definitions
        symbol_index.add_definition(
            SymbolDefinition("AuthService", "auth_service.py", 1, 15, "class")
        )
        symbol_index.add_definition(
            SymbolDefinition("login", "auth_service.py", 5, 9, "method", parent_class="AuthService")
        )
        symbol_index.add_definition(
            SymbolDefinition("_create_token", "auth_service.py", 11, 12, "method", parent_class="AuthService")
        )
        symbol_index.add_definition(
            SymbolDefinition("logout", "auth_service.py", 14, 15, "method", parent_class="AuthService")
        )
        symbol_index.add_definition(
            SymbolDefinition("User", "user_model.py", 1, 8, "class")
        )
        symbol_index.add_definition(
            SymbolDefinition("check_password", "user_model.py", 7, 8, "method", parent_class="User")
        )
        symbol_index.add_definition(
            SymbolDefinition("APIHandler", "api_handler.py", 3, 16, "class")
        )
        symbol_index.add_definition(
            SymbolDefinition("handle_login", "api_handler.py", 7, 11, "method", parent_class="APIHandler")
        )
        symbol_index.add_definition(
            SymbolDefinition("handle_logout", "api_handler.py", 13, 15, "method", parent_class="APIHandler")
        )

        # Add symbol references
        symbol_index.add_reference(
            SymbolReference("AuthService", "api_handler.py", 1, "import")
        )
        symbol_index.add_reference(
            SymbolReference("AuthService", "api_handler.py", 5, "call", context_function="__init__")
        )
        symbol_index.add_reference(
            SymbolReference("login", "api_handler.py", 8, "call", context_function="handle_login")
        )
        symbol_index.add_reference(
            SymbolReference("logout", "api_handler.py", 14, "call", context_function="handle_logout")
        )
        symbol_index.add_reference(
            SymbolReference("AuthService", "test_auth.py", 1, "import")
        )
        symbol_index.add_reference(
            SymbolReference("login", "test_auth.py", 5, "call", context_function="test_login_success")
        )
        symbol_index.add_reference(
            SymbolReference("login", "test_auth.py", 10, "call", context_function="test_login_failure")
        )

        # Add dependency edges
        dep_graph.add_edge(DependencyEdge("api_handler.py", "auth_service.py", "auth_service", ["AuthService"]))
        dep_graph.add_edge(DependencyEdge("test_auth.py", "auth_service.py", "auth_service", ["AuthService"]))

        return call_graph, dep_graph, symbol_index

    def test_call_graph_extraction(self, indexed_project):
        """Test that calls are properly extracted from source."""
        call_graph, _, _ = indexed_project

        # AuthService.login calls find_user, check_password, _create_token
        auth_calls = call_graph.find_callees("login")
        callee_names = [c.callee_name for c in auth_calls]
        assert "find_user" in callee_names
        assert "check_password" in callee_names
        assert "_create_token" in callee_names

    def test_symbol_lookup(self, indexed_project):
        """Test symbol definition lookup."""
        _, _, symbol_index = indexed_project

        login_defs = symbol_index.lookup_definition("login")
        assert len(login_defs) == 1
        assert login_defs[0].file_path == "auth_service.py"
        assert login_defs[0].symbol_type == "method"

    def test_reference_lookup(self, indexed_project):
        """Test symbol reference lookup."""
        _, _, symbol_index = indexed_project

        login_refs = symbol_index.lookup_references("login")
        assert len(login_refs) >= 2  # api_handler + test_auth
        ref_files = [r.file_path for r in login_refs]
        assert "api_handler.py" in ref_files
        assert "test_auth.py" in ref_files

    def test_trace_symbol_full_pipeline(self, indexed_project):
        """Test full trace_symbol result formatting."""
        call_graph, _, symbol_index = indexed_project

        # Build trace data
        defs = symbol_index.lookup_definition("login")
        refs = symbol_index.lookup_references("login")
        callers = call_graph.find_callers("login")
        callees = call_graph.find_callees("login")

        trace_data = {
            "symbol": "login",
            "definitions": [d.to_dict() for d in defs],
            "usages": [r.to_dict() for r in refs],
            "call_chain": {
                "callers": [c.to_dict() for c in callers],
                "callees": [c.to_dict() for c in callees],
            },
            "inheritance": [],
        }

        # Test summary format
        summary = format_trace_result(trace_data, "summary")
        assert "login" in summary
        assert "auth_service.py" in summary

        # Test JSON format
        import json
        json_out = format_trace_result(trace_data, "json")
        parsed = json.loads(json_out)
        assert parsed["symbol"] == "login"

    def test_impact_analysis_pipeline(self, indexed_project):
        """Test full impact analysis for a symbol change."""
        call_graph, dep_graph, symbol_index = indexed_project

        analyzer = ImpactAnalyzer(call_graph, dep_graph, symbol_index)
        result = analyzer.assess("login", change_type="signature_change")

        assert result.target == "login"
        # login is called from api_handler and test_auth
        affected_files = {i.file_path for i in result.direct_impacts}
        assert len(affected_files) >= 1

        # Result should be serializable
        result_dict = result.to_dict()
        formatted = format_impact_result(result_dict, "summary")
        assert "login" in formatted

    def test_impact_analysis_with_tests(self, indexed_project):
        """Test that impact analysis finds affected test files."""
        call_graph, dep_graph, symbol_index = indexed_project

        analyzer = ImpactAnalyzer(call_graph, dep_graph, symbol_index)
        result = analyzer.assess("AuthService", change_type="signature_change", include_tests=True)

        # test_auth.py imports AuthService, so should appear
        # (either as direct impact or affected test)
        all_affected = {i.file_path for i in result.direct_impacts + result.transitive_impacts}
        all_affected.update(result.affected_tests)
        assert any("test_" in f for f in all_affected)

    def test_architecture_health_pipeline(self, indexed_project):
        """Test architecture health assessment on sample project."""
        _, dep_graph, symbol_index = indexed_project

        metrics = ArchitectureMetrics(dep_graph, symbol_index)
        report = metrics.compute_report(".")

        assert report.score > 0
        report_dict = report.to_dict()
        formatted = format_architecture_report(report_dict, "summary")
        assert "Score" in formatted

    def test_cycle_detection_real_scenario(self):
        """Test cycle detection with a realistic circular dependency."""
        dep_graph = DependencyGraphBuilder()
        dep_graph.add_edge(DependencyEdge("models/user.py", "services/auth.py", "services.auth"))
        dep_graph.add_edge(DependencyEdge("services/auth.py", "utils/crypto.py", "utils.crypto"))
        dep_graph.add_edge(DependencyEdge("utils/crypto.py", "models/user.py", "models.user"))

        symbol_index = SymbolIndex()
        metrics = ArchitectureMetrics(dep_graph, symbol_index)
        report = metrics.compute_report(".", checks=["circular_dependencies"])

        assert len(report.cycles) == 1
        assert report.cycles[0].length == 3

    def test_dead_code_detection_pipeline(self, indexed_project):
        """Test dead code detection in the sample project."""
        _, dep_graph, symbol_index = indexed_project

        metrics = ArchitectureMetrics(dep_graph, symbol_index)
        report = metrics.compute_report(".", checks=["dead_code"])

        # Some symbols should be detected as dead (no references)
        # _create_token and check_password are not in the reference index
        assert len(report.dead_symbols) >= 1


class TestMCPToolExecution:
    """Test MCP tools end-to-end (async execution)."""

    @pytest.mark.asyncio
    async def test_trace_symbol_tool_e2e(self):
        """Test trace_symbol tool with real execution."""
        from tree_sitter_analyzer.mcp.tools.trace_symbol_tool import TraceSymbolTool

        tool = TraceSymbolTool(project_root=None)
        result = await tool.execute({
            "symbol": "TestSymbol",
            "trace_type": "full",
            "output_format": "json",
        })
        assert isinstance(result, dict)
        assert "data" in result

    @pytest.mark.asyncio
    async def test_assess_change_impact_tool_e2e(self):
        """Test assess_change_impact tool with real execution."""
        from tree_sitter_analyzer.mcp.tools.assess_change_impact_tool import (
            AssessChangeImpactTool,
        )

        tool = AssessChangeImpactTool(project_root=None)
        result = await tool.execute({
            "target": "SomeFunction",
            "change_type": "behavior_change",
            "output_format": "json",
        })
        assert isinstance(result, dict)
        assert "data" in result or "error" in result

    @pytest.mark.asyncio
    async def test_check_architecture_health_tool_e2e(self):
        """Test check_architecture_health tool with real execution."""
        from tree_sitter_analyzer.mcp.tools.check_architecture_health_tool import (
            CheckArchitectureHealthTool,
        )

        tool = CheckArchitectureHealthTool(project_root=None)
        result = await tool.execute({
            "path": "src/",
            "output_format": "json",
        })
        assert isinstance(result, dict)
        assert "data" in result

    @pytest.mark.asyncio
    async def test_trace_symbol_all_formats(self):
        """Test trace_symbol with all output formats."""
        from tree_sitter_analyzer.mcp.tools.trace_symbol_tool import TraceSymbolTool

        tool = TraceSymbolTool(project_root=None)

        for fmt in ("summary", "tree", "json"):
            result = await tool.execute({
                "symbol": "test",
                "output_format": fmt,
            })
            assert isinstance(result, dict)
            assert "result" in result


class TestMCPServerRegistration:
    """Test that intelligence tools are registered in the MCP server."""

    def test_server_has_trace_symbol(self):
        """Test that the server initializes trace_symbol_tool."""
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

        server = TreeSitterAnalyzerMCPServer(project_root=None)
        assert hasattr(server, "trace_symbol_tool")
        assert server.trace_symbol_tool is not None

    def test_server_has_assess_change_impact(self):
        """Test that the server initializes assess_change_impact_tool."""
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

        server = TreeSitterAnalyzerMCPServer(project_root=None)
        assert hasattr(server, "assess_change_impact_tool")
        assert server.assess_change_impact_tool is not None

    def test_server_has_check_architecture_health(self):
        """Test that the server initializes check_architecture_health_tool."""
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

        server = TreeSitterAnalyzerMCPServer(project_root=None)
        assert hasattr(server, "check_architecture_health_tool")
        assert server.check_architecture_health_tool is not None
