"""
Integration tests for context optimizer MCP tool.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.analysis.context_optimizer import (
    CodeElement,
    calculate_compression_ratio,
    filter_by_importance,
    optimize_for_llm,
    parse_toon_elements,
    score_importance,
)
from tree_sitter_analyzer.mcp.tools.context_optimizer_tool import ContextOptimizerTool


class TestContextOptimizerTool:
    """Integration tests for ContextOptimizerTool."""

    @pytest.fixture
    def tool(self) -> ContextOptimizerTool:
        """Create context optimizer tool instance."""
        return ContextOptimizerTool()

    def test_tool_name(self, tool: ContextOptimizerTool) -> None:
        """Should have correct tool name."""
        assert tool.get_name() == "context_optimizer"

    def test_tool_definition(self, tool: ContextOptimizerTool) -> None:
        """Should have correct tool definition."""
        definition = tool.get_tool_definition()

        assert definition["name"] == "context_optimizer"
        assert "toon_output" in definition["inputSchema"]["properties"]
        assert "threshold" in definition["inputSchema"]["properties"]

    def test_get_parameters(self, tool: ContextOptimizerTool) -> None:
        """Should return correct parameters schema."""
        params = tool.get_parameters()

        assert "properties" in params
        assert "toon_output" in params["properties"]
        assert "threshold" in params["properties"]
        assert "required" in params
        assert "toon_output" in params["required"]

    def test_execute_basic(self, tool: ContextOptimizerTool) -> None:
        """Should execute basic optimization."""
        toon_output = """
my_function() [complexity: 5]
simple_helper() [complexity: 1]
complex_processor() [complexity: 15]
"""

        result = tool.execute({"toon_output": toon_output})

        assert "# Context Optimized Output" in result
        assert "Compression:" in result
        assert "complex_processor" in result or "my_function" in result

    def test_execute_with_threshold(self, tool: ContextOptimizerTool) -> None:
        """Should respect threshold parameter."""
        toon_output = """
function_a() [complexity: 10]
function_b() [complexity: 5]
function_c() [complexity: 1]
"""

        result = tool.execute({"toon_output": toon_output, "threshold": 0.3})

        assert "# Context Optimized Output" in result
        assert "Threshold: 30" in result  # Match 30.0% or 30%

    def test_execute_with_dependency_data(self, tool: ContextOptimizerTool) -> None:
        """Should use dependency count data when provided."""
        toon_output = """
dependent_func() [complexity: 5]
standalone_func() [complexity: 5]
"""

        dependency_counts = {
            "dependent_func": 10,
            "standalone_func": 0,
        }

        result = tool.execute({
            "toon_output": toon_output,
            "dependency_counts": dependency_counts,
        })

        assert "dependent_func" in result or "standalone_func" in result

    def test_execute_empty_input(self, tool: ContextOptimizerTool) -> None:
        """Should handle empty input gracefully."""
        result = tool.execute({"toon_output": ""})

        assert "# Context Optimized Output" in result

    def test_get_description(self, tool: ContextOptimizerTool) -> None:
        """Should return description."""
        description = tool.get_description()
        assert "context" in description.lower()
        assert "optimize" in description.lower() or "optimization" in description.lower()


class TestEndToEndOptimization:
    """End-to-end tests for context optimization."""

    def test_full_optimization_pipeline(self) -> None:
        """Should complete full optimization pipeline."""
        toon_output = """
complex_api_handler() [complexity: 20]
simple_getter() [complexity: 1]
data_validator() [complexity: 8]
utility_helper() [complexity: 2]
business_logic() [complexity: 15]
"""

        dependency_counts = {
            "complex_api_handler": 15,
            "simple_getter": 1,
            "data_validator": 5,
            "utility_helper": 0,
            "business_logic": 10,
        }

        call_frequencies = {
            "complex_api_handler": 50,
            "simple_getter": 100,
            "data_validator": 20,
            "utility_helper": 5,
            "business_logic": 30,
        }

        # Parse elements
        elements = parse_toon_elements(toon_output)
        assert len(elements) == 5

        # Score elements
        scored = [(el, score_importance(el)) for el in elements]
        scored.sort(key=lambda x: x[1], reverse=True)

        # Highest score should be complex_api_handler (high complexity + high deps + high calls)
        assert scored[0][0].name == "complex_api_handler"

        # Filter to top 40%
        filtered = filter_by_importance(elements, threshold=0.4)
        assert len(filtered) <= len(elements)

        # Optimize
        optimized = optimize_for_llm(
            toon_output,
            threshold=0.4,
            dependency_counts=dependency_counts,
            call_frequencies=call_frequencies,
        )

        # Calculate compression
        ratio = calculate_compression_ratio(toon_output, optimized)
        assert 0.0 <= ratio <= 1.0

    def test_compression_calculation(self) -> None:
        """Should calculate compression ratio correctly."""
        original = "a" * 1000
        optimized = "a" * 500

        ratio = calculate_compression_ratio(original, optimized)
        assert ratio == 0.5  # 50% reduction

    def test_preserves_important_elements(self) -> None:
        """Should preserve important elements even with aggressive filtering."""
        elements = [
            CodeElement(
                name="critical_core",
                element_type="function",
                complexity=100,
                dependency_count=50,
                call_frequency=100,
            ),
            CodeElement(
                name="trivial_helper",
                element_type="function",
                complexity=1,
                dependency_count=0,
                call_frequency=1,
            ),
        ]

        # Even with 10% threshold, should keep critical_core
        filtered = filter_by_importance(elements, threshold=0.1, min_elements=1)
        assert len(filtered) >= 1
        assert filtered[0].name == "critical_core"

    def test_mcp_tool_integration(self) -> None:
        """Should work as MCP tool."""
        tool = ContextOptimizerTool()

        toon_output = """
high_value_func() [complexity: 15]
low_value_func() [complexity: 2]
"""

        result = tool.execute({
            "toon_output": toon_output,
            "threshold": 0.5,
        })

        assert "# Context Optimized Output" in result
        assert "Compression:" in result
