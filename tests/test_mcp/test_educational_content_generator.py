#!/usr/bin/env python3
"""
Test suite for Educational Content Generator

This module contains comprehensive tests for the educational content generator tool,
including integration tests with the multi-agent system.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

from tree_sitter_analyzer.mcp.tools.educational_content_generator import EducationalContentGenerator
from tree_sitter_analyzer.mcp.agents.prompt_manager import (
    ProjectContext,
    LearningContext,
    LearningLevel,
    ContentType
)


class TestEducationalContentGenerator:
    """Test suite for EducationalContentGenerator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.generator = EducationalContentGenerator(self.temp_dir)
        
        # Create test files
        self.sample_python_file = os.path.join(self.temp_dir, "sample.py")
        with open(self.sample_python_file, 'w') as f:
            f.write('''
class WebApplication:
    """A simple web application example."""
    
    def __init__(self, name):
        self.name = name
        self.routes = {}
    
    def add_route(self, path, handler):
        """Add a route to the application."""
        self.routes[path] = handler
    
    def handle_request(self, path):
        """Handle incoming requests."""
        if path in self.routes:
            return self.routes[path]()
        return "404 Not Found"
    
    def run(self, host="localhost", port=8080):
        """Run the web application."""
        print(f"Running {self.name} on {host}:{port}")
''')

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_tool_schema(self):
        """Test tool schema definition."""
        schema = self.generator.get_tool_schema()
        
        assert schema["type"] == "object"
        assert "project_path" in schema["properties"]
        assert "target_audience" in schema["properties"]
        assert "content_type" in schema["properties"]
        assert "learning_objectives" in schema["properties"]
        assert "content_depth" in schema["properties"]
        assert "include_exercises" in schema["properties"]
        assert "include_assessments" in schema["properties"]
        assert "output_format" in schema["properties"]
        assert schema["required"] == ["project_path"]

    @pytest.mark.asyncio
    async def test_basic_content_generation(self):
        """Test basic educational content generation."""
        arguments = {
            "project_path": self.sample_python_file,
            "target_audience": "intermediate",
            "content_type": "tutorial",
            "learning_objectives": [
                "Understand class structure",
                "Learn method implementation"
            ],
            "content_depth": "detailed",
            "include_exercises": True,
            "include_assessments": True,
            "output_format": "structured"
        }
        
        result = await self.generator.execute(arguments)
        
        assert result["success"] is True
        assert result["project_path"] == self.sample_python_file
        assert result["target_audience"] == "intermediate"
        assert result["content_type"] == "tutorial"
        assert "project_analysis" in result
        assert "complexity_analysis" in result
        assert "generated_content" in result
        assert "metadata" in result

    @pytest.mark.asyncio
    async def test_different_target_audiences(self):
        """Test content generation for different target audiences."""
        base_args = {
            "project_path": self.sample_python_file,
            "content_type": "tutorial",
            "content_depth": "detailed"
        }
        
        for audience in ["beginner", "intermediate", "advanced", "expert"]:
            args = {**base_args, "target_audience": audience}
            result = await self.generator.execute(args)
            
            assert result["success"] is True
            assert result["target_audience"] == audience
            
            # Different audiences should have different complexity assessments
            complexity = result["complexity_analysis"]["learning_difficulty"]
            assert "adjusted_score" in complexity
            assert "difficulty_level" in complexity

    @pytest.mark.asyncio
    async def test_different_content_types(self):
        """Test content generation for different content types."""
        base_args = {
            "project_path": self.sample_python_file,
            "target_audience": "intermediate",
            "content_depth": "detailed"
        }
        
        content_types = ["overview", "tutorial", "example", "exercise", "project", "reference"]
        
        for content_type in content_types:
            args = {**base_args, "content_type": content_type}
            result = await self.generator.execute(args)
            
            assert result["success"] is True
            assert result["content_type"] == content_type

    @pytest.mark.asyncio
    async def test_different_output_formats(self):
        """Test different output formats."""
        base_args = {
            "project_path": self.sample_python_file,
            "target_audience": "intermediate",
            "content_type": "tutorial"
        }
        
        formats = ["markdown", "html", "json", "structured"]
        
        for output_format in formats:
            args = {**base_args, "output_format": output_format}
            result = await self.generator.execute(args)
            
            assert result["success"] is True
            content = result["generated_content"]
            assert content["format"] == output_format
            assert "content" in content

    @pytest.mark.asyncio
    async def test_content_depth_levels(self):
        """Test different content depth levels."""
        base_args = {
            "project_path": self.sample_python_file,
            "target_audience": "intermediate",
            "content_type": "tutorial"
        }
        
        for depth in ["basic", "detailed", "comprehensive"]:
            args = {**base_args, "content_depth": depth}
            result = await self.generator.execute(args)
            
            assert result["success"] is True
            
            # More comprehensive analysis should have more detailed metrics
            project_analysis = result["project_analysis"]
            if depth == "comprehensive":
                assert "dependencies" in project_analysis
                assert "architecture_patterns" in project_analysis

    @pytest.mark.asyncio
    async def test_learning_objectives_integration(self):
        """Test integration of custom learning objectives."""
        custom_objectives = [
            "Master object-oriented programming concepts",
            "Implement web application routing",
            "Handle HTTP requests effectively",
            "Apply software design principles"
        ]
        
        arguments = {
            "project_path": self.sample_python_file,
            "target_audience": "advanced",
            "content_type": "tutorial",
            "learning_objectives": custom_objectives,
            "content_depth": "detailed"
        }
        
        result = await self.generator.execute(arguments)
        
        assert result["success"] is True
        
        # Check if objectives are reflected in the collaboration result
        collaboration_result = result["collaboration_result"]
        if isinstance(collaboration_result, str):
            # If it's a string representation, check for keywords
            for objective in custom_objectives:
                keywords = objective.lower().split()
                assert any(keyword in collaboration_result.lower() for keyword in keywords[:2])

    @pytest.mark.asyncio
    async def test_project_analysis_components(self):
        """Test project analysis components."""
        arguments = {
            "project_path": self.sample_python_file,
            "target_audience": "intermediate",
            "content_depth": "detailed"
        }
        
        result = await self.generator.execute(arguments)
        
        assert result["success"] is True
        
        project_analysis = result["project_analysis"]
        assert "language" in project_analysis
        assert "file_path" in project_analysis
        assert "structure" in project_analysis
        assert "complexity_metrics" in project_analysis
        assert "key_concepts" in project_analysis
        assert "architecture_patterns" in project_analysis
        
        assert project_analysis["language"] == "python"
        assert project_analysis["file_path"] == self.sample_python_file

    @pytest.mark.asyncio
    async def test_complexity_analysis_components(self):
        """Test complexity analysis components."""
        arguments = {
            "project_path": self.sample_python_file,
            "target_audience": "beginner",
            "content_depth": "comprehensive"
        }
        
        result = await self.generator.execute(arguments)
        
        assert result["success"] is True
        
        complexity_analysis = result["complexity_analysis"]
        assert "learning_difficulty" in complexity_analysis
        assert "complexity_metrics" in complexity_analysis
        assert "recommendations" in complexity_analysis
        
        difficulty = complexity_analysis["learning_difficulty"]
        assert "difficulty_level" in difficulty
        assert "adjusted_score" in difficulty
        assert "confidence" in difficulty

    @pytest.mark.asyncio
    async def test_structured_content_format(self):
        """Test structured content format output."""
        arguments = {
            "project_path": self.sample_python_file,
            "target_audience": "intermediate",
            "content_type": "tutorial",
            "output_format": "structured",
            "include_exercises": True,
            "include_assessments": True
        }
        
        result = await self.generator.execute(arguments)
        
        assert result["success"] is True
        
        content = result["generated_content"]["content"]
        assert "course_outline" in content
        assert "learning_materials" in content
        assert "quality_metrics" in content
        assert "implementation_guide" in content
        assert "exercises" in content
        assert "assessments" in content
        
        # Check course outline structure
        outline = content["course_outline"]
        assert "title" in outline
        assert "description" in outline
        assert "learning_objectives" in outline
        assert "modules" in outline

    @pytest.mark.asyncio
    async def test_markdown_content_format(self):
        """Test markdown content format output."""
        arguments = {
            "project_path": self.sample_python_file,
            "target_audience": "intermediate",
            "content_type": "tutorial",
            "output_format": "markdown"
        }
        
        result = await self.generator.execute(arguments)
        
        assert result["success"] is True
        
        content = result["generated_content"]["content"]
        assert isinstance(content, str)
        assert content.startswith("# Educational Content")
        assert "## Overview" in content
        assert "## Quality Score" in content

    @pytest.mark.asyncio
    async def test_metadata_generation(self):
        """Test metadata generation."""
        arguments = {
            "project_path": self.sample_python_file,
            "target_audience": "intermediate",
            "content_type": "tutorial"
        }
        
        result = await self.generator.execute(arguments)
        
        assert result["success"] is True
        
        metadata = result["metadata"]
        assert "generation_timestamp" in metadata
        assert "quality_score" in metadata
        assert "recommendations" in metadata
        assert "next_steps" in metadata
        
        assert isinstance(metadata["quality_score"], (int, float))
        assert isinstance(metadata["recommendations"], list)
        assert isinstance(metadata["next_steps"], list)

    @pytest.mark.asyncio
    async def test_file_not_found_error(self):
        """Test handling of non-existent files."""
        arguments = {
            "project_path": os.path.join(self.temp_dir, "nonexistent.py"),
            "target_audience": "intermediate",
            "content_type": "tutorial"
        }
        
        result = await self.generator.execute(arguments)
        
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_invalid_file_path(self):
        """Test handling of invalid file paths."""
        arguments = {
            "project_path": "/etc/passwd",  # Absolute path should be rejected
            "target_audience": "intermediate",
            "content_type": "tutorial"
        }
        
        result = await self.generator.execute(arguments)
        
        assert result["success"] is False
        assert "invalid" in result["error"].lower() or "unsafe" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_missing_required_arguments(self):
        """Test handling of missing required arguments."""
        arguments = {
            "target_audience": "intermediate",
            "content_type": "tutorial"
            # Missing project_path
        }

        # This should raise a ValueError, not return a result dict
        with pytest.raises(ValueError, match="project_path is required"):
            await self.generator.execute(arguments)

    def test_project_type_determination(self):
        """Test project type determination logic."""
        # Mock analysis result with many classes
        analysis_with_classes = {
            "structure": {
                "classes": 5,
                "methods": 15,
                "total_elements": 20
            }
        }
        
        project_type = self.generator._determine_project_type(analysis_with_classes)
        assert project_type == "Object-Oriented Application"
        
        # Mock analysis result with many methods but few classes
        analysis_with_methods = {
            "structure": {
                "classes": 1,
                "methods": 15,
                "total_elements": 16
            }
        }
        
        project_type = self.generator._determine_project_type(analysis_with_methods)
        assert project_type == "Functional Application"

    def test_key_concepts_identification(self):
        """Test key concepts identification."""
        # Mock analysis result
        mock_result = Mock()
        mock_result.elements = [
            Mock(__class__=Mock(__name__="Class")),
            Mock(__class__=Mock(__name__="Method")),
            Mock(__class__=Mock(__name__="Method"))
        ]
        
        concepts = self.generator._identify_key_concepts(mock_result, "python")
        
        assert "Object-Oriented Programming" in concepts
        assert "Functions and Methods" in concepts
        assert "Python Syntax" in concepts

    def test_architecture_patterns_identification(self):
        """Test architecture patterns identification."""
        # Mock analysis result with multiple classes
        mock_result = Mock()
        mock_result.elements = [
            Mock(__class__=Mock(__name__="Class")),
            Mock(__class__=Mock(__name__="Class")),
            Mock(__class__=Mock(__name__="Method"))
        ]
        
        patterns = self.generator._identify_architecture_patterns(mock_result)
        
        assert "Multi-class Design" in patterns
        assert "Modular Architecture" in patterns

    def test_tool_definition(self):
        """Test MCP tool definition."""
        tool_def = self.generator.get_tool_definition()
        
        # Should work with or without MCP library
        if hasattr(tool_def, 'name'):
            assert tool_def.name == "generate_educational_content"
            assert "educational content" in tool_def.description.lower()
        else:
            assert tool_def["name"] == "generate_educational_content"
            assert "educational content" in tool_def["description"].lower()

    @pytest.mark.asyncio
    async def test_concurrent_content_generation(self):
        """Test concurrent content generation."""
        import asyncio
        
        arguments = {
            "project_path": self.sample_python_file,
            "target_audience": "intermediate",
            "content_type": "tutorial",
            "content_depth": "basic"
        }
        
        # Run multiple generations concurrently
        tasks = [self.generator.execute(arguments) for _ in range(3)]
        results = await asyncio.gather(*tasks)
        
        for result in results:
            assert result["success"] is True
            assert result["target_audience"] == "intermediate"


if __name__ == "__main__":
    pytest.main([__file__])
