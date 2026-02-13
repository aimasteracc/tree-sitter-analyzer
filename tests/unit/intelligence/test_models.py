#!/usr/bin/env python3
"""Tests for Code Intelligence Graph data models."""

import pytest
from tree_sitter_analyzer.intelligence.models import (
    ArchitectureReport,
    CallSite,
    DependencyCycle,
    DependencyEdge,
    GodClassInfo,
    ImpactItem,
    ImpactResult,
    LayerViolation,
    ModuleMetrics,
    ResolvedImport,
    SymbolDefinition,
    SymbolReference,
)


class TestCallSite:
    """Test CallSite data model."""

    def test_create_simple_call(self):
        cs = CallSite(
            caller_file="src/main.py",
            caller_function="main",
            callee_name="print",
            callee_object=None,
            line=10,
            raw_text='print("hello")',
        )
        assert cs.caller_file == "src/main.py"
        assert cs.callee_name == "print"
        assert cs.callee_object is None

    def test_create_method_call(self):
        cs = CallSite(
            caller_file="src/auth.py",
            caller_function="login",
            callee_name="validate",
            callee_object="self",
            line=25,
            raw_text="self.validate(data)",
        )
        assert cs.callee_object == "self"
        assert cs.callee_name == "validate"

    def test_to_dict(self):
        cs = CallSite(
            caller_file="a.py",
            caller_function="f",
            callee_name="g",
            callee_object=None,
            line=1,
            raw_text="g()",
        )
        d = cs.to_dict()
        assert d["caller_file"] == "a.py"
        assert d["callee_name"] == "g"
        assert "line" in d


class TestSymbolDefinition:
    """Test SymbolDefinition data model."""

    def test_create_function_definition(self):
        sd = SymbolDefinition(
            name="login",
            file_path="src/auth.py",
            line=15,
            end_line=45,
            symbol_type="function",
            parameters=["user", "password"],
            return_type="bool",
            parent_class=None,
            docstring="Authenticate user",
            modifiers=[],
        )
        assert sd.name == "login"
        assert sd.symbol_type == "function"
        assert sd.parameters == ["user", "password"]

    def test_create_method_definition(self):
        sd = SymbolDefinition(
            name="validate",
            file_path="src/auth.py",
            line=50,
            end_line=60,
            symbol_type="method",
            parameters=["self", "data"],
            return_type=None,
            parent_class="AuthService",
            docstring=None,
            modifiers=["public"],
        )
        assert sd.parent_class == "AuthService"

    def test_create_class_definition(self):
        sd = SymbolDefinition(
            name="AuthService",
            file_path="src/auth.py",
            line=10,
            end_line=100,
            symbol_type="class",
            parameters=[],
            return_type=None,
            parent_class=None,
            docstring="Auth service",
            modifiers=["public"],
        )
        assert sd.symbol_type == "class"

    def test_to_dict(self):
        sd = SymbolDefinition(
            name="foo",
            file_path="a.py",
            line=1,
            end_line=5,
            symbol_type="function",
        )
        d = sd.to_dict()
        assert d["name"] == "foo"
        assert d["symbol_type"] == "function"


class TestSymbolReference:
    """Test SymbolReference data model."""

    def test_create_call_reference(self):
        sr = SymbolReference(
            symbol_name="login",
            file_path="src/api.py",
            line=30,
            ref_type="call",
            context_function="handle_request",
        )
        assert sr.ref_type == "call"

    def test_create_import_reference(self):
        sr = SymbolReference(
            symbol_name="AuthService",
            file_path="src/api.py",
            line=1,
            ref_type="import",
            context_function=None,
        )
        assert sr.ref_type == "import"

    def test_create_inheritance_reference(self):
        sr = SymbolReference(
            symbol_name="BaseService",
            file_path="src/auth.py",
            line=10,
            ref_type="inheritance",
            context_function=None,
        )
        assert sr.ref_type == "inheritance"

    def test_to_dict(self):
        sr = SymbolReference(
            symbol_name="foo",
            file_path="a.py",
            line=1,
            ref_type="call",
        )
        d = sr.to_dict()
        assert d["ref_type"] == "call"


class TestDependencyEdge:
    """Test DependencyEdge data model."""

    def test_create_internal_edge(self):
        de = DependencyEdge(
            source_file="src/auth.py",
            target_file="src/models/user.py",
            target_module="src.models.user",
            imported_names=["User", "UserRole"],
            is_external=False,
            line=3,
        )
        assert not de.is_external
        assert de.imported_names == ["User", "UserRole"]

    def test_create_external_edge(self):
        de = DependencyEdge(
            source_file="src/auth.py",
            target_file="",
            target_module="fastapi",
            imported_names=["Depends"],
            is_external=True,
            line=1,
        )
        assert de.is_external

    def test_to_dict(self):
        de = DependencyEdge(
            source_file="a.py",
            target_file="b.py",
            target_module="b",
            imported_names=["X"],
            is_external=False,
            line=1,
        )
        d = de.to_dict()
        assert d["source_file"] == "a.py"
        assert d["target_file"] == "b.py"


class TestResolvedImport:
    """Test ResolvedImport data model."""

    def test_resolved_internal(self):
        ri = ResolvedImport(
            module_name="src.auth.service",
            resolved_path="src/auth/service.py",
            imported_names=["AuthService"],
            is_external=False,
            is_resolved=True,
        )
        assert ri.is_resolved
        assert not ri.is_external

    def test_resolved_external(self):
        ri = ResolvedImport(
            module_name="fastapi",
            resolved_path="",
            imported_names=["FastAPI"],
            is_external=True,
            is_resolved=True,
        )
        assert ri.is_external

    def test_unresolved(self):
        ri = ResolvedImport(
            module_name="unknown.module",
            resolved_path="",
            imported_names=[],
            is_external=False,
            is_resolved=False,
        )
        assert not ri.is_resolved


class TestDependencyCycle:
    """Test DependencyCycle data model."""

    def test_create_cycle(self):
        dc = DependencyCycle(
            files=["a.py", "b.py", "a.py"],
            length=2,
            severity="warning",
        )
        assert dc.length == 2
        assert dc.severity == "warning"


class TestModuleMetrics:
    """Test ModuleMetrics data model."""

    def test_compute_instability(self):
        mm = ModuleMetrics(
            path="src/auth/",
            file_count=4,
            afferent_coupling=1,
            efferent_coupling=2,
            abstractness=0.3,
        )
        assert mm.instability == pytest.approx(2 / 3, rel=1e-2)

    def test_zero_coupling_instability(self):
        mm = ModuleMetrics(
            path="src/utils/",
            file_count=2,
            afferent_coupling=0,
            efferent_coupling=0,
            abstractness=0.0,
        )
        assert mm.instability == 0.0

    def test_distance_from_main_sequence(self):
        mm = ModuleMetrics(
            path="src/auth/",
            file_count=4,
            afferent_coupling=1,
            efferent_coupling=2,
            abstractness=0.3,
        )
        # D = |A + I - 1|
        expected = abs(0.3 + 2 / 3 - 1)
        assert mm.distance_from_main_sequence == pytest.approx(expected, rel=1e-2)


class TestImpactItem:
    """Test ImpactItem data model."""

    def test_create_impact_item(self):
        ii = ImpactItem(
            file_path="src/api.py",
            symbol_name="login_endpoint",
            line=34,
            impact_type="direct_caller",
            depth=1,
        )
        assert ii.impact_type == "direct_caller"
        assert ii.depth == 1


class TestImpactResult:
    """Test ImpactResult data model."""

    def test_create_impact_result(self):
        ir = ImpactResult(
            target="create_token",
            change_type="signature_change",
            direct_impacts=[],
            transitive_impacts=[],
            affected_tests=[],
            risk_level="low",
            total_affected_files=0,
        )
        assert ir.risk_level == "low"

    def test_to_dict(self):
        ir = ImpactResult(
            target="foo",
            change_type="behavior_change",
            direct_impacts=[
                ImpactItem("a.py", "bar", 10, "direct_caller", 1)
            ],
            transitive_impacts=[],
            affected_tests=["test_a.py"],
            risk_level="medium",
            total_affected_files=2,
        )
        d = ir.to_dict()
        assert d["target"] == "foo"
        assert len(d["direct_impacts"]) == 1
        assert d["affected_tests"] == ["test_a.py"]


class TestLayerViolation:
    """Test LayerViolation data model."""

    def test_create_violation(self):
        lv = LayerViolation(
            source_file="models/user.py",
            target_file="services/auth.py",
            source_layer="models",
            target_layer="services",
            description="models should not depend on services",
        )
        assert lv.source_layer == "models"


class TestGodClassInfo:
    """Test GodClassInfo data model."""

    def test_create_god_class(self):
        gc = GodClassInfo(
            class_name="UserService",
            file_path="src/services/user.py",
            method_count=34,
            line_count=890,
            fan_out=15,
        )
        assert gc.method_count == 34


class TestArchitectureReport:
    """Test ArchitectureReport data model."""

    def test_create_report(self):
        ar = ArchitectureReport(
            path="src/",
            score=72,
            module_metrics={},
            cycles=[],
            layer_violations=[],
            god_classes=[],
            dead_symbols=[],
            coupling_matrix={},
        )
        assert ar.score == 72

    def test_to_dict(self):
        ar = ArchitectureReport(
            path="src/",
            score=85,
            module_metrics={},
            cycles=[],
            layer_violations=[],
            god_classes=[],
            dead_symbols=[],
            coupling_matrix={},
        )
        d = ar.to_dict()
        assert d["score"] == 85
        assert "module_metrics" in d
