#!/usr/bin/env python3
"""
Test search_content tool description quality and structure.

Verifies the description content, structure, and token cost comparison table.
"""

import pytest
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


class TestSearchContentDescription:
    """Test class for search_content description validation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tool = SearchContentTool()
        self.tool_def = self.tool.get_tool_definition()
        self.description = self.tool_def["description"]

    def test_description_length_validity(self):
        """Test that description length is within reasonable bounds."""
        # Should be comprehensive but not excessive
        min_chars = 800   # Minimum for comprehensive guidance
        max_chars = 4000  # Maximum to prevent token bloat
        
        description_length = len(self.description)
        assert min_chars <= description_length <= max_chars, (
            f"Description length {description_length} not in valid range "
            f"{min_chars}-{max_chars} characters"
        )

    def test_section_structure_validation(self):
        """Test that description follows proper section structure."""
        lines = self.description.split('\n')
        
        # Find section headers
        section_headers = []
        for line in lines:
            if line.strip().startswith(('⚠️', '🎯', '💡')):
                section_headers.append(line.strip())
        
        # Expected section order
        expected_sections = [
            "⚠️ IMPORTANT: Token Efficiency Guide",
            "🎯 RECOMMENDED WORKFLOW (Most Efficient Approach):",
            "💡 TOKEN EFFICIENCY COMPARISON:",
            "⚠️ MUTUALLY EXCLUSIVE: Only one output format parameter can be true at a time."
        ]
        
        for expected in expected_sections:
            found = any(expected in header for header in section_headers)
            assert found, f"Missing expected section: {expected}"

    def test_token_cost_comparison_table(self):
        """Test that token cost comparison table is complete and accurate."""
        # Required format entries with token counts
        required_entries = [
            ("total_only", "~10 tokens", "MOST EFFICIENT"),
            ("count_only_matches", "~50-200 tokens", "file distribution"),
            ("summary_only", "~500-2000 tokens", "Initial investigation"),
            ("group_by_file", "~2000-10000 tokens", "organized by file"),
            ("optimize_paths", "10-30% reduction", "path compression"),
            ("Full results", "~2000-50000+ tokens", "detailed analysis")
        ]
        
        for format_name, token_range, description_key in required_entries:
            # Check that format is mentioned
            assert format_name in self.description, f"Missing format: {format_name}"
            # Check that token estimate is present
            assert token_range in self.description, f"Missing token estimate: {token_range}"
            # Check that description context is present
            assert description_key.lower() in self.description.lower(), (
                f"Missing description context: {description_key}"
            )

    def test_workflow_explanation_completeness(self):
        """Test that workflow explanation contains all necessary steps."""
        # Required workflow elements
        workflow_elements = [
            "START with total_only=true",
            "initial count validation",
            "~10 tokens",
            "IF more detail needed",
            "count_only_matches=true",
            "file distribution",
            "~50-200 tokens",
            "IF context needed",
            "summary_only=true",
            "overview",
            "~500-2000 tokens",
            "ONLY use full results",
            "specific content review",
            "~2000-50000+ tokens"
        ]
        
        for element in workflow_elements:
            assert element in self.description, f"Missing workflow element: {element}"

    def test_efficiency_ordering(self):
        """Test that formats are presented in efficiency order."""
        # Find the order of format mentions in TOKEN EFFICIENCY COMPARISON
        comparison_section_start = self.description.find("💡 TOKEN EFFICIENCY COMPARISON")
        comparison_section = self.description[comparison_section_start:comparison_section_start + 1000]
        
        formats_in_order = ["total_only", "count_only_matches", "summary_only", "group_by_file", "optimize_paths"]
        
        positions = []
        for format_name in formats_in_order:
            pos = comparison_section.find(format_name)
            if pos != -1:
                positions.append((format_name, pos))
        
        # Verify they appear in efficiency order (most efficient first)
        sorted_positions = sorted(positions, key=lambda x: x[1])
        expected_order = ["total_only", "count_only_matches", "summary_only", "group_by_file"]
        
        actual_order = [pos[0] for pos in sorted_positions if pos[0] in expected_order]
        assert actual_order == expected_order, (
            f"Formats not in efficiency order. Expected: {expected_order}, Got: {actual_order}"
        )

    def test_visual_formatting_quality(self):
        """Test that visual formatting enhances readability."""
        # Count visual elements
        emoji_count = sum(1 for char in self.description if ord(char) > 127)
        assert emoji_count >= 6, f"Insufficient visual elements: {emoji_count}"
        
        # Check for proper use of formatting
        formatting_elements = [
            "⚠️",  # Warning/important marker
            "🎯",  # Target/goal marker  
            "💡",  # Idea/tip marker
            ":",   # Proper section separators
            "\n",  # Line breaks for readability
        ]
        
        for element in formatting_elements:
            count = self.description.count(element)
            assert count > 0, f"Missing formatting element: {element}"

    def test_concrete_examples_present(self):
        """Test that description includes concrete usage examples."""
        # Should include specific token numbers and scenarios
        concrete_examples = [
            "~10 tokens",
            "~50-200 tokens", 
            "~500-2000 tokens",
            "~2000-10000 tokens",
            "10-30%",
            "count validation",
            "file distribution",
            "initial investigation"
        ]
        
        for example in concrete_examples:
            assert example in self.description, f"Missing concrete example: {example}"

    def test_guidance_actionability(self):
        """Test that guidance provides actionable instructions."""
        # Should include clear action words and decision points
        action_words = [
            "START with",
            "IF more detail needed",
            "IF context needed", 
            "ONLY use",
            "RECOMMENDED",
            "Choose",
            "minimize"
        ]
        
        action_found = 0
        for word in action_words:
            if word in self.description:
                action_found += 1
        
        assert action_found >= 5, f"Insufficient actionable guidance. Found only {action_found} action words"

    def test_warning_emphasis(self):
        """Test that warnings are properly emphasized."""
        # Important warnings should be clearly marked
        warning_indicators = [
            "⚠️ IMPORTANT",
            "⚠️ MUTUALLY EXCLUSIVE",
            "MOST EFFICIENT",
            "Cannot be combined"
        ]
        
        for warning in warning_indicators:
            assert warning in self.description, f"Missing warning emphasis: {warning}"

    def test_no_redundant_information(self):
        """Test that description avoids unnecessary repetition."""
        # Check for excessive repetition of key phrases
        key_phrases = ["token", "efficient", "format", "parameter"]
        
        for phrase in key_phrases:
            count = self.description.lower().count(phrase.lower())
            # Should be mentioned but not excessively
            assert 3 <= count <= 20, f"Phrase '{phrase}' mentioned {count} times (should be 3-20)"

    def test_compatibility_with_existing_features(self):
        """Test that description doesn't conflict with existing tool features."""
        # Should not contradict existing parameter descriptions
        schema = self.tool_def["inputSchema"]
        properties = schema["properties"]
        
        # Check that all mentioned parameters actually exist
        mentioned_params = ["total_only", "count_only_matches", "summary_only", "group_by_file", "optimize_paths"]
        
        for param in mentioned_params:
            assert param in properties, f"Description mentions non-existent parameter: {param}"
            
        # Check that parameter types are consistent
        for param in mentioned_params:
            param_type = properties[param]["type"]
            assert param_type == "boolean", f"Parameter {param} should be boolean, got {param_type}"