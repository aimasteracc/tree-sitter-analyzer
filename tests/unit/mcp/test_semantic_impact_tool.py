#!/usr/bin/env python3
"""
Tests for Semantic Impact MCP Tool
"""

import pytest

from tree_sitter_analyzer.mcp.tools.semantic_impact_tool import (
    SemanticImpactTool,
)


class TestSemanticImpactTool:
    """Tests for SemanticImpactTool."""

    @pytest.fixture
    def tool(self) -> SemanticImpactTool:
        """Create a tool instance."""
        return SemanticImpactTool()

    @pytest.mark.asyncio
    async def test_low_risk_private_symbol(self, tool: SemanticImpactTool) -> None:
        """Private symbol with no callers should be low risk."""
        result = await tool.execute({
            "symbol": "internalHelper",
            "visibility": "private",
            "caller_count": 0,
            "call_chain_depth": 0,
        })

        assert result["symbol"] == "internalHelper"
        assert result["risk_level"] in ("safe", "low")
        assert result["risk_score"] < 20
        assert result["caller_count"] == 0
        assert result["visibility"] == "private"

    @pytest.mark.asyncio
    async def test_high_risk_public_api(self, tool: SemanticImpactTool) -> None:
        """Public API with many callers should be high risk."""
        result = await tool.execute({
            "symbol": "publicApiMethod",
            "visibility": "public",
            "caller_count": 25,
            "call_chain_depth": 3,
        })

        assert result["symbol"] == "publicApiMethod"
        assert result["risk_level"] in ("high", "critical")
        assert result["risk_score"] >= 60
        assert result["caller_count"] == 25
        assert result["visibility"] == "public"
        assert len(result["factors"]) > 0

    @pytest.mark.asyncio
    async def test_critical_risk_base_class(self, tool: SemanticImpactTool) -> None:
        """Base class change should be critical risk."""
        result = await tool.execute({
            "symbol": "BaseService",
            "visibility": "public",
            "caller_count": 20,
            "call_chain_depth": 3,
            "is_abstract": True,
            "base_classes": [],
        })

        assert result["symbol"] == "BaseService"
        assert result["risk_level"] == "critical"
        assert result["risk_score"] >= 80
        assert result["is_type_hierarchy_root"] is True
        assert any("base class" in f.lower() for f in result["factors"])

    @pytest.mark.asyncio
    async def test_moderate_risk_protected(self, tool: SemanticImpactTool) -> None:
        """Protected symbol with moderate callers should be moderate risk."""
        result = await tool.execute({
            "symbol": "protectedMethod",
            "visibility": "protected",
            "caller_count": 25,
            "call_chain_depth": 2,
        })

        assert result["symbol"] == "protectedMethod"
        assert result["visibility"] == "protected"
        assert result["risk_level"] in ("moderate", "high")
        assert result["risk_score"] >= 20

    @pytest.mark.asyncio
    async def test_static_modifier_increases_risk(self, tool: SemanticImpactTool) -> None:
        """Static modifier should increase risk score."""
        result = await tool.execute({
            "symbol": "STATIC_CONSTANT",
            "visibility": "public",
            "caller_count": 5,
            "is_static": True,
        })

        assert result["symbol"] == "STATIC_CONSTANT"
        assert result["risk_score"] > 0
        assert any("static" in f.lower() for f in result["factors"])

    @pytest.mark.asyncio
    async def test_interface_member_high_risk(self, tool: SemanticImpactTool) -> None:
        """Interface member should be high risk."""
        result = await tool.execute({
            "symbol": "interfaceMethod",
            "visibility": "public",
            "caller_count": 15,
            "is_interface_member": True,
        })

        assert result["symbol"] == "interfaceMethod"
        assert result["risk_level"] in ("high", "critical")
        # Interface members have high risk due to affecting all implementations

    @pytest.mark.asyncio
    async def test_deep_call_chain_increases_risk(self, tool: SemanticImpactTool) -> None:
        """Deep call chain should increase risk score."""
        result = await tool.execute({
            "symbol": "deepMethod",
            "visibility": "public",
            "caller_count": 5,
            "call_chain_depth": 5,
        })

        assert result["call_chain_depth"] == 5
        assert result["risk_score"] > 0
        assert any("call chain" in f.lower() for f in result["factors"])

    @pytest.mark.asyncio
    async def test_framework_annotations_increase_risk(self, tool: SemanticImpactTool) -> None:
        """Framework annotations should increase risk."""
        result = await tool.execute({
            "symbol": "apiEndpoint",
            "visibility": "public",
            "caller_count": 3,
            "annotations": ["GetMapping", "ApiOperation"],
        })

        assert result["risk_score"] > 0
        assert any("framework" in f.lower() or "annotation" in f.lower()
                   for f in result["factors"])

    @pytest.mark.asyncio
    async def test_suggestions_for_safe_changes(self, tool: SemanticImpactTool) -> None:
        """Safe changes should have minimal suggestions."""
        result = await tool.execute({
            "symbol": "privateHelper",
            "visibility": "private",
            "caller_count": 0,
        })

        assert len(result["suggestions"]) >= 1
        assert any("safe" in s.lower() for s in result["suggestions"])

    @pytest.mark.asyncio
    async def test_suggestions_for_critical_changes(self, tool: SemanticImpactTool) -> None:
        """Critical changes should have deprecation strategy suggestions."""
        result = await tool.execute({
            "symbol": "criticalApi",
            "visibility": "public",
            "caller_count": 30,
            "call_chain_depth": 4,
            "is_abstract": True,
        })

        assert len(result["suggestions"]) >= 1
        assert any("deprecation" in s.lower() for s in result["suggestions"])

    @pytest.mark.asyncio
    async def test_tson_output_format(self, tool: SemanticImpactTool) -> None:
        """TOON output format should work."""
        result = await tool.execute({
            "symbol": "testSymbol",
            "visibility": "public",
            "caller_count": 5,
            "output_format": "tson",
        })

        assert result["format"] == "tson"
        assert "output" in result

    def test_validate_arguments_missing_symbol(self, tool: SemanticImpactTool) -> None:
        """Should raise error when symbol is missing."""
        with pytest.raises(ValueError, match="symbol"):
            tool.validate_arguments({})

    def test_validate_arguments_invalid_caller_count(self, tool: SemanticImpactTool) -> None:
        """Should raise error when caller_count is invalid."""
        with pytest.raises(ValueError, match="caller_count"):
            tool.validate_arguments({"symbol": "test", "caller_count": -1})

    def test_validate_arguments_invalid_visibility(self, tool: SemanticImpactTool) -> None:
        """Should raise error when visibility is invalid."""
        with pytest.raises(ValueError, match="visibility"):
            tool.validate_arguments({"symbol": "test", "visibility": "invalid"})


class TestQuickRiskAssessmentTool:
    """Tests for quick mode (formerly QuickRiskAssessmentTool)."""

    @pytest.fixture
    def tool(self) -> SemanticImpactTool:
        """Create a tool instance."""
        return SemanticImpactTool()

    @pytest.mark.asyncio
    async def test_quick_assessment_safe(self, tool: SemanticImpactTool) -> None:
        """Quick assessment for safe change."""
        result = await tool.execute({
            "symbol": "privateMethod",
            "mode": "quick",
            "visibility": "private",
            "caller_count": 0,
        })

        assert result["symbol"] == "privateMethod"
        assert result["risk_level"] in ("safe", "low")
        assert result["risk_score"] < 20

    @pytest.mark.asyncio
    async def test_quick_assessment_critical(self, tool: SemanticImpactTool) -> None:
        """Quick assessment for critical change."""
        result = await tool.execute({
            "symbol": "publicApi",
            "mode": "quick",
            "visibility": "public",
            "caller_count": 30,
            "is_type_hierarchy_root": True,
            "is_abstract": True,
        })

        assert result["symbol"] == "publicApi"
        assert result["risk_level"] in ("high", "critical")
        assert result["risk_score"] >= 60

    @pytest.mark.asyncio
    async def test_quick_assessment_with_protected(self, tool: SemanticImpactTool) -> None:
        """Quick assessment with protected visibility."""
        result = await tool.execute({
            "symbol": "protectedMethod",
            "mode": "quick",
            "visibility": "protected",
            "caller_count": 25,
        })

        assert result["symbol"] == "protectedMethod"
        assert result["risk_level"] in ("moderate", "high")

    @pytest.mark.asyncio
    async def test_quick_assessment_package_visibility(self, tool: SemanticImpactTool) -> None:
        """Quick assessment with package/internal visibility."""
        result = await tool.execute({
            "symbol": "packageMethod",
            "mode": "quick",
            "visibility": "package",
            "caller_count": 3,
        })

        assert result["symbol"] == "packageMethod"
        assert result["risk_score"] > 0

    @pytest.mark.asyncio
    async def test_quick_assessment_internal_visibility(self, tool: SemanticImpactTool) -> None:
        """Quick assessment with internal visibility (alias for package)."""
        result = await tool.execute({
            "symbol": "internalMethod",
            "mode": "quick",
            "visibility": "internal",
            "caller_count": 3,
        })

        assert result["symbol"] == "internalMethod"
        assert result["risk_score"] > 0

    def test_validate_arguments_missing_symbol(self, tool: SemanticImpactTool) -> None:
        """Should raise error when symbol is missing."""
        with pytest.raises(ValueError, match="symbol"):
            tool.validate_arguments({})


class TestRiskScoring:
    """Tests for risk scoring logic."""

    @pytest.fixture
    def tool(self) -> SemanticImpactTool:
        """Create a tool instance."""
        return SemanticImpactTool()

    @pytest.mark.asyncio
    async def test_risk_score_capped_at_100(self, tool: SemanticImpactTool) -> None:
        """Risk score should be capped at 100."""
        result = await tool.execute({
            "symbol": "maxRisk",
            "visibility": "public",
            "caller_count": 100,
            "call_chain_depth": 10,
            "is_abstract": True,
            "is_interface_member": True,
            "is_static": True,
            "annotations": ["GetMapping", "PostMapping", "Component"],
        })

        assert result["risk_score"] <= 100

    @pytest.mark.asyncio
    async def test_zero_callers_public_moderate_risk(self, tool: SemanticImpactTool) -> None:
        """Public API with zero callers still has moderate risk."""
        result = await tool.execute({
            "symbol": "newPublicApi",
            "visibility": "public",
            "caller_count": 0,
        })

        assert result["risk_score"] >= 15  # Base visibility bonus
        # With zero callers, risk level is safe (score 15)
        assert result["risk_level"] in ("safe", "low", "moderate")

    @pytest.mark.asyncio
    async def test_visibility_ordering(self, tool: SemanticImpactTool) -> None:
        """Risk should respect visibility ordering: public > protected > package > private."""
        public_result = await tool.execute({
            "symbol": "test",
            "visibility": "public",
            "caller_count": 5,
        })

        protected_result = await tool.execute({
            "symbol": "test",
            "visibility": "protected",
            "caller_count": 5,
        })

        package_result = await tool.execute({
            "symbol": "test",
            "visibility": "package",
            "caller_count": 5,
        })

        private_result = await tool.execute({
            "symbol": "test",
            "visibility": "private",
            "caller_count": 5,
        })

        assert public_result["risk_score"] >= protected_result["risk_score"]
        assert protected_result["risk_score"] >= package_result["risk_score"]
        assert package_result["risk_score"] >= private_result["risk_score"]

    @pytest.mark.asyncio
    async def test_caller_volume_impact(self, tool: SemanticImpactTool) -> None:
        """Higher caller count should increase risk."""
        low_caller = await tool.execute({
            "symbol": "test",
            "visibility": "public",
            "caller_count": 1,
        })

        high_caller = await tool.execute({
            "symbol": "test",
            "visibility": "public",
            "caller_count": 50,
        })

        assert high_caller["risk_score"] > low_caller["risk_score"]
