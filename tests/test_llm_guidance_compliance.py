#!/usr/bin/env python3
"""
Test LLM guidance compliance in search_content tool.

Verifies that the tool definition contains required guidance sections and markers
for efficient LLM usage.
"""

from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


class TestLLMGuidanceCompliance:
    """Test class for LLM guidance compliance verification."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tool = SearchContentTool()
        self.tool_def = self.tool.get_tool_definition()

    def test_tool_definition_structure(self):
        """Test that tool definition has required structure."""
        assert "name" in self.tool_def
        assert "description" in self.tool_def
        assert "inputSchema" in self.tool_def
        assert self.tool_def["name"] == "search_content"

    def test_required_guidance_sections_exist(self):
        """Test that all required guidance sections are present in description."""
        description = self.tool_def["description"]

        # Required section markers
        required_sections = [
            "⚠️ IMPORTANT: Token Efficiency Guide",
            "🎯 RECOMMENDED WORKFLOW",
            "💡 TOKEN EFFICIENCY COMPARISON",
            "⚠️ MUTUALLY EXCLUSIVE",
        ]

        for section in required_sections:
            assert section in description, f"Missing required section: {section}"

    def test_workflow_guidance_completeness(self):
        """Test that workflow guidance contains all steps."""
        description = self.tool_def["description"]

        # Required workflow steps
        workflow_steps = [
            "START with total_only=true",
            "IF more detail needed, use count_only_matches=true",
            "IF context needed, use summary_only=true",
            "ONLY use full results when specific content review",
        ]

        for step in workflow_steps:
            assert step in description, f"Missing workflow step: {step}"

    def test_token_efficiency_comparison_exists(self):
        """Test that token efficiency comparison table is present."""
        description = self.tool_def["description"]

        # Required efficiency entries
        efficiency_entries = [
            "total_only: ~10 tokens",
            "count_only_matches: ~50-200 tokens",
            "summary_only: ~500-2000 tokens",
            "group_by_file: ~2000-10000 tokens",
            "optimize_paths: 10-30% reduction",
        ]

        for entry in efficiency_entries:
            assert entry in description, f"Missing efficiency entry: {entry}"

    def test_parameter_exclusive_markers(self):
        """Test that all output format parameters have exclusive markers."""
        input_schema = self.tool_def["inputSchema"]
        properties = input_schema["properties"]

        exclusive_params = [
            "total_only",
            "count_only_matches",
            "summary_only",
            "group_by_file",
            "optimize_paths",
        ]

        for param in exclusive_params:
            assert param in properties, f"Missing parameter: {param}"
            param_desc = properties[param]["description"]
            assert "⚠️ EXCLUSIVE:" in param_desc, f"Missing exclusive marker in {param}"
            assert (
                "RECOMMENDED for:" in param_desc
            ), f"Missing recommendation in {param}"
            assert (
                "Cannot be combined" in param_desc
            ), f"Missing combination warning in {param}"

    def test_parameter_token_estimates(self):
        """Test that parameters include token usage estimates."""
        input_schema = self.tool_def["inputSchema"]
        properties = input_schema["properties"]

        token_estimates = {
            "total_only": "~10 tokens",
            "count_only_matches": "~50-200 tokens",
            "summary_only": "~500-2000 tokens",
            "group_by_file": "~2000-10000 tokens",
            "optimize_paths": "10-30%",
        }

        for param, estimate in token_estimates.items():
            param_desc = properties[param]["description"]
            assert (
                estimate in param_desc
            ), f"Missing token estimate '{estimate}' in {param}"

    def test_parameter_recommendations(self):
        """Test that parameters include usage recommendations."""
        input_schema = self.tool_def["inputSchema"]
        properties = input_schema["properties"]

        recommendations = {
            "total_only": "Count validation",
            "count_only_matches": "File distribution",
            "summary_only": "Initial investigation",
            "group_by_file": "Context-aware review",
            "optimize_paths": "Deep directory structures",
        }

        for param, recommendation in recommendations.items():
            param_desc = properties[param]["description"]
            # Check for recommendation keyword (case insensitive)
            assert (
                recommendation.lower() in param_desc.lower()
            ), f"Missing recommendation '{recommendation}' in {param}"

    def test_description_length_reasonable(self):
        """Test that description is comprehensive but not excessively long."""
        description = self.tool_def["description"]

        # Should be substantial enough to provide guidance but not overwhelming
        min_length = 500  # Minimum for comprehensive guidance
        max_length = 5000  # Maximum to avoid token bloat

        assert (
            min_length <= len(description) <= max_length
        ), f"Description length {len(description)} not in range {min_length}-{max_length}"

    def test_unicode_markers_present(self):
        """Test that visual markers are used effectively."""
        description = self.tool_def["description"]

        # Required visual markers
        visual_markers = ["⚠️", "🎯", "💡"]

        for marker in visual_markers:
            assert marker in description, f"Missing visual marker: {marker}"
            # Each marker should appear at least once
            assert (
                description.count(marker) >= 1
            ), f"Insufficient usage of marker: {marker}"

    def test_mutually_exclusive_warning(self):
        """Test that mutual exclusion is clearly communicated."""
        description = self.tool_def["description"]

        # Should clearly state mutual exclusion
        exclusion_phrases = [
            "MUTUALLY EXCLUSIVE",
            "one output format parameter",
            "at a time",
        ]

        exclusion_found = False
        for phrase in exclusion_phrases:
            if phrase.lower() in description.lower():
                exclusion_found = True
                break

        assert exclusion_found, "Mutual exclusion warning not clearly stated"
