#!/usr/bin/env python3
"""
Test suite for Learning Complexity Tool

This module contains comprehensive tests for the learning complexity analysis tool,
including unit tests, integration tests, and edge case handling.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

from tree_sitter_analyzer.mcp.tools.learning_complexity_tool import LearningComplexityTool
from tree_sitter_analyzer.core.analysis_engine import AnalysisResult
from tree_sitter_analyzer.models import CodeElement


class TestLearningComplexityTool:
    """Test suite for LearningComplexityTool."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.tool = LearningComplexityTool(self.temp_dir)
        
        # Create test files
        self.simple_python_file = os.path.join(self.temp_dir, "simple.py")
        with open(self.simple_python_file, 'w') as f:
            f.write('''
class Calculator:
    def add(self, a, b):
        return a + b
    
    def multiply(self, a, b):
        return a * b
''')
        
        self.complex_python_file = os.path.join(self.temp_dir, "complex.py")
        with open(self.complex_python_file, 'w') as f:
            f.write('''
import asyncio
import logging
from typing import Dict, List, Optional, Union
from dataclasses import dataclass

@dataclass
class ComplexClass:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    async def complex_method(self, data: List[Dict]) -> Optional[Union[str, int]]:
        try:
            for item in data:
                if item.get('type') == 'special':
                    result = await self._process_special(item)
                    if result:
                        return result
                elif item.get('type') == 'normal':
                    for i in range(10):
                        if self._validate_item(item, i):
                            return self._transform_item(item)
            return None
        except Exception as e:
            self.logger.error(f"Error processing: {e}")
            raise
    
    def _process_special(self, item):
        # Complex nested logic
        pass
    
    def _validate_item(self, item, index):
        # Validation logic
        pass
    
    def _transform_item(self, item):
        # Transformation logic
        pass
''')

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_tool_schema(self):
        """Test tool schema definition."""
        schema = self.tool.get_tool_schema()
        
        assert schema["type"] == "object"
        assert "file_path" in schema["properties"]
        assert "analysis_depth" in schema["properties"]
        assert "target_audience" in schema["properties"]
        assert "include_recommendations" in schema["properties"]
        assert schema["required"] == ["file_path"]

    @pytest.mark.asyncio
    async def test_simple_file_analysis(self):
        """Test analysis of a simple Python file."""
        arguments = {
            "file_path": self.simple_python_file,
            "analysis_depth": "basic",
            "target_audience": "beginner",
            "include_recommendations": True
        }
        
        result = await self.tool.execute(arguments)
        
        assert result["success"] is True
        assert result["file_path"] == self.simple_python_file
        assert result["language"] == "python"
        assert result["target_audience"] == "beginner"
        assert "complexity_metrics" in result
        assert "learning_difficulty" in result
        assert "recommendations" in result

    @pytest.mark.asyncio
    async def test_complex_file_analysis(self):
        """Test analysis of a complex Python file."""
        arguments = {
            "file_path": self.complex_python_file,
            "analysis_depth": "comprehensive",
            "target_audience": "advanced",
            "include_recommendations": True
        }
        
        result = await self.tool.execute(arguments)
        
        assert result["success"] is True
        assert result["learning_difficulty"]["difficulty_level"] in ["Moderate", "Challenging", "Very Challenging"]
        assert result["complexity_metrics"]["cognitive_load"]["complexity_score"] > 0
        assert len(result["recommendations"]["prerequisite_topics"]) > 0

    @pytest.mark.asyncio
    async def test_different_analysis_depths(self):
        """Test different analysis depth levels."""
        base_args = {
            "file_path": self.simple_python_file,
            "target_audience": "intermediate",
            "include_recommendations": True
        }
        
        for depth in ["basic", "detailed", "comprehensive"]:
            args = {**base_args, "analysis_depth": depth}
            result = await self.tool.execute(args)
            
            assert result["success"] is True
            assert result["analysis_depth"] == depth
            
            # Comprehensive analysis should have more metrics
            if depth == "comprehensive":
                assert "advanced_patterns" in result["complexity_metrics"]
                assert "architectural_complexity" in result["complexity_metrics"]

    @pytest.mark.asyncio
    async def test_different_target_audiences(self):
        """Test different target audience levels."""
        base_args = {
            "file_path": self.simple_python_file,
            "analysis_depth": "detailed",
            "include_recommendations": True
        }
        
        for audience in ["beginner", "intermediate", "advanced", "expert"]:
            args = {**base_args, "target_audience": audience}
            result = await self.tool.execute(args)
            
            assert result["success"] is True
            assert result["target_audience"] == audience
            
            # Beginner audience should have higher adjusted complexity scores
            if audience == "beginner":
                assert result["learning_difficulty"]["adjusted_score"] >= result["learning_difficulty"]["raw_score"]

    @pytest.mark.asyncio
    async def test_complexity_metrics_calculation(self):
        """Test complexity metrics calculation."""
        arguments = {
            "file_path": self.complex_python_file,
            "analysis_depth": "detailed",
            "target_audience": "intermediate"
        }
        
        result = await self.tool.execute(arguments)
        metrics = result["complexity_metrics"]
        
        # Verify all expected metrics are present
        assert "file_size" in metrics
        assert "structural_complexity" in metrics
        assert "cognitive_load" in metrics
        assert "dependency_complexity" in metrics
        assert "pattern_complexity" in metrics
        
        # Verify metric structure
        assert "complexity_score" in metrics["structural_complexity"]
        assert "complexity_score" in metrics["cognitive_load"]
        assert "dependency_score" in metrics["dependency_complexity"]

    @pytest.mark.asyncio
    async def test_learning_difficulty_assessment(self):
        """Test learning difficulty assessment."""
        arguments = {
            "file_path": self.complex_python_file,
            "analysis_depth": "detailed",
            "target_audience": "beginner"
        }
        
        result = await self.tool.execute(arguments)
        difficulty = result["learning_difficulty"]
        
        assert "raw_score" in difficulty
        assert "adjusted_score" in difficulty
        assert "difficulty_level" in difficulty
        assert "target_audience" in difficulty
        assert "confidence" in difficulty
        
        assert difficulty["difficulty_level"] in ["Easy", "Moderate", "Challenging", "Very Challenging"]
        assert 0 <= difficulty["confidence"] <= 1

    @pytest.mark.asyncio
    async def test_recommendations_generation(self):
        """Test recommendations generation."""
        arguments = {
            "file_path": self.complex_python_file,
            "analysis_depth": "detailed",
            "target_audience": "intermediate",
            "include_recommendations": True
        }
        
        result = await self.tool.execute(arguments)
        recommendations = result["recommendations"]
        
        assert "suggested_approach" in recommendations
        assert "prerequisite_topics" in recommendations
        assert "learning_sequence" in recommendations
        assert "time_estimate" in recommendations
        assert "teaching_strategies" in recommendations
        
        assert isinstance(recommendations["prerequisite_topics"], list)
        assert isinstance(recommendations["learning_sequence"], list)
        assert isinstance(recommendations["teaching_strategies"], list)

    @pytest.mark.asyncio
    async def test_file_not_found_error(self):
        """Test handling of non-existent files."""
        arguments = {
            "file_path": os.path.join(self.temp_dir, "nonexistent.py"),
            "analysis_depth": "basic",
            "target_audience": "beginner"
        }
        
        result = await self.tool.execute(arguments)
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_invalid_file_path(self):
        """Test handling of invalid file paths."""
        arguments = {
            "file_path": "/etc/passwd",  # Absolute path should be rejected
            "analysis_depth": "basic",
            "target_audience": "beginner"
        }
        
        result = await self.tool.execute(arguments)
        assert result["success"] is False
        assert "invalid" in result["error"].lower() or "unsafe" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_unsupported_language(self):
        """Test handling of unsupported file types."""
        unsupported_file = os.path.join(self.temp_dir, "test.unknown")
        with open(unsupported_file, 'w') as f:
            f.write("some content")
        
        arguments = {
            "file_path": unsupported_file,
            "analysis_depth": "basic",
            "target_audience": "beginner"
        }
        
        result = await self.tool.execute(arguments)
        assert result["success"] is False
        assert "unsupported" in result["error"].lower() or "undetectable" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_missing_required_arguments(self):
        """Test handling of missing required arguments."""
        arguments = {
            "analysis_depth": "basic",
            "target_audience": "beginner"
            # Missing file_path
        }
        
        result = await self.tool.execute(arguments)
        assert result["success"] is False
        assert "file_path is required" in result["error"]

    @pytest.mark.asyncio
    async def test_tool_definition(self):
        """Test MCP tool definition."""
        tool_def = self.tool.get_tool_definition()
        
        # Should work with or without MCP library
        if hasattr(tool_def, 'name'):
            assert tool_def.name == "analyze_learning_complexity"
            assert "learning complexity" in tool_def.description.lower()
        else:
            assert tool_def["name"] == "analyze_learning_complexity"
            assert "learning complexity" in tool_def["description"].lower()

    def test_complexity_metrics_edge_cases(self):
        """Test complexity metrics calculation edge cases."""
        # Test with empty analysis result
        empty_result = Mock()
        empty_result.elements = []
        
        metrics = self.tool._calculate_complexity_metrics(empty_result, self.simple_python_file, "basic")
        
        assert metrics["structural_complexity"]["class_count"] == 0
        assert metrics["structural_complexity"]["method_count"] == 0

    def test_learning_difficulty_edge_cases(self):
        """Test learning difficulty assessment edge cases."""
        # Test with minimal metrics
        minimal_metrics = {
            "structural_complexity": {"complexity_score": 0},
            "cognitive_load": {"complexity_score": 0},
            "dependency_complexity": {"dependency_score": 0},
            "pattern_complexity": {"complexity_score": 0}
        }
        
        difficulty = self.tool._assess_learning_difficulty(minimal_metrics, "beginner")
        
        assert difficulty["difficulty_level"] == "Easy"
        assert difficulty["adjusted_score"] >= 0

    def test_analysis_summary_generation(self):
        """Test analysis summary generation."""
        sample_metrics = {
            "structural_complexity": {"complexity_score": 5.0},
            "cognitive_load": {"complexity_score": 3.0},
            "pattern_complexity": {"complexity_score": 2.0}
        }
        
        sample_difficulty = {
            "difficulty_level": "Moderate",
            "adjusted_score": 4.5
        }
        
        summary = self.tool._generate_analysis_summary(sample_metrics, sample_difficulty)
        
        assert "Moderate" in summary
        assert "4.5" in summary
        assert "5.0" in summary

    @pytest.mark.asyncio
    async def test_concurrent_analysis(self):
        """Test concurrent analysis of multiple files."""
        import asyncio
        
        tasks = []
        for i in range(3):
            arguments = {
                "file_path": self.simple_python_file,
                "analysis_depth": "basic",
                "target_audience": "intermediate"
            }
            tasks.append(self.tool.execute(arguments))
        
        results = await asyncio.gather(*tasks)
        
        for result in results:
            assert result["success"] is True
            assert result["language"] == "python"

    @pytest.mark.asyncio
    async def test_large_file_handling(self):
        """Test handling of large files."""
        large_file = os.path.join(self.temp_dir, "large.py")
        with open(large_file, 'w') as f:
            # Create a large file with many classes and methods
            for i in range(50):
                f.write(f'''
class Class{i}:
    def method1_{i}(self):
        if True:
            for j in range(10):
                try:
                    result = self._helper_{i}(j)
                    if result:
                        return result
                except Exception:
                    continue
        return None
    
    def method2_{i}(self):
        pass
    
    def _helper_{i}(self, value):
        return value * 2
''')
        
        arguments = {
            "file_path": large_file,
            "analysis_depth": "detailed",
            "target_audience": "advanced"
        }
        
        result = await self.tool.execute(arguments)
        
        assert result["success"] is True
        assert result["complexity_metrics"]["structural_complexity"]["class_count"] == 50
        assert result["learning_difficulty"]["difficulty_level"] in ["Challenging", "Very Challenging"]


if __name__ == "__main__":
    pytest.main([__file__])
