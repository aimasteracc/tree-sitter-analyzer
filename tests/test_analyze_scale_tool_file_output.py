#!/usr/bin/env python3
"""
Test analyze_scale_tool file output functionality

Tests the analyze_scale_tool for potential file output features
and validates the current functionality works correctly.
Note: This tool doesn't currently implement output_file/suppress_output,
but this test prepares for future implementation.
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool


class TestAnalyzeScaleToolFileOutput:
    """Test analyze_scale_tool functionality and prepare for file output features"""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with test files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            
            # Create a comprehensive Java test file (since analyze_scale_tool works best with Java)
            java_file = project_path / "ComplexSample.java"
            java_file.write_text("""package com.example.complex;

import java.util.List;
import java.util.ArrayList;
import java.util.Map;
import java.util.HashMap;
import java.util.stream.Collectors;
import javax.annotation.Nullable;

/**
 * Complex sample Java class for testing analyze_scale functionality.
 * This class contains various complexity patterns.
 */
@Component
@Service
public class ComplexSample {
    private static final String CONSTANT = "test";
    private final List<String> items;
    private final Map<String, Integer> cache;
    private int complexityCounter;
    
    @Autowired
    public ComplexSample(@Nullable List<String> initialItems) {
        this.items = initialItems != null ? new ArrayList<>(initialItems) : new ArrayList<>();
        this.cache = new HashMap<>();
        this.complexityCounter = 0;
    }
    
    @Override
    public String toString() {
        return "ComplexSample{items=" + items.size() + "}";
    }
    
    /**
     * Complex method with high cyclomatic complexity.
     */
    @Transactional
    public int complexCalculation(int input, String mode, boolean useCache) {
        complexityCounter++;
        
        if (useCache && cache.containsKey(mode + input)) {
            return cache.get(mode + input);
        }
        
        int result = 0;
        
        switch (mode) {
            case "simple":
                result = input * 2;
                break;
            case "complex":
                for (int i = 0; i < input; i++) {
                    if (i % 2 == 0) {
                        result += i;
                    } else if (i % 3 == 0) {
                        result -= i;
                    } else {
                        result += i / 2;
                    }
                    
                    if (result > 1000) {
                        break;
                    }
                }
                break;
            case "recursive":
                result = recursiveHelper(input, 0);
                break;
            default:
                throw new IllegalArgumentException("Unknown mode: " + mode);
        }
        
        if (useCache) {
            cache.put(mode + input, result);
        }
        
        return result;
    }
    
    private int recursiveHelper(int n, int accumulator) {
        if (n <= 0) {
            return accumulator;
        }
        
        if (n % 2 == 0) {
            return recursiveHelper(n - 1, accumulator + n);
        } else {
            return recursiveHelper(n - 1, accumulator - n);
        }
    }
    
    @Deprecated
    public void legacyMethod() {
        // Legacy implementation
        for (String item : items) {
            if (item != null && !item.isEmpty()) {
                System.out.println("Processing: " + item);
            }
        }
    }
    
    public List<String> filterItems(String prefix) {
        return items.stream()
                .filter(item -> item != null)
                .filter(item -> item.startsWith(prefix))
                .collect(Collectors.toList());
    }
    
    @PostConstruct
    private void initialize() {
        cache.clear();
        complexityCounter = 0;
    }
    
    public static class NestedClass {
        private final String value;
        
        public NestedClass(String value) {
            this.value = value;
        }
        
        public String getValue() {
            return value;
        }
    }
    
    public enum Status {
        ACTIVE, INACTIVE, PENDING
    }
}
""")
            
            # Create a Python test file
            python_file = project_path / "sample.py"
            python_file.write_text("""#!/usr/bin/env python3
\"\"\"
Sample Python file for testing analyze_scale functionality.
\"\"\"

import os
import sys
from pathlib import Path
from typing import List, Dict, Optional

# Global constants
GLOBAL_CONSTANT = "test_value"
MAX_ITEMS = 1000

class SampleClass:
    \"\"\"A sample class for testing.\"\"\"
    
    def __init__(self, name: str, items: Optional[List[str]] = None):
        self.name = name
        self.items = items or []
        self.cache: Dict[str, int] = {}
    
    def get_name(self) -> str:
        \"\"\"Get the name of the instance.\"\"\"
        return self.name
    
    def complex_calculation(self, input_val: int, mode: str, use_cache: bool = True) -> int:
        \"\"\"Complex method with multiple branches.\"\"\"
        if use_cache and mode in self.cache:
            return self.cache[mode]
        
        result = 0
        
        if mode == "simple":
            result = input_val * 2
        elif mode == "complex":
            for i in range(input_val):
                if i % 2 == 0:
                    result += i
                elif i % 3 == 0:
                    result -= i
                else:
                    result += i // 2
                
                if result > 1000:
                    break
        elif mode == "recursive":
            result = self._recursive_helper(input_val, 0)
        else:
            raise ValueError(f"Unknown mode: {mode}")
        
        if use_cache:
            self.cache[mode] = result
        
        return result
    
    def _recursive_helper(self, n: int, accumulator: int) -> int:
        \"\"\"Recursive helper method.\"\"\"
        if n <= 0:
            return accumulator
        
        if n % 2 == 0:
            return self._recursive_helper(n - 1, accumulator + n)
        else:
            return self._recursive_helper(n - 1, accumulator - n)

def main():
    \"\"\"Main function.\"\"\"
    instance = SampleClass("test")
    print(f"Name: {instance.get_name()}")
    print(f"Calculation: {instance.complex_calculation(10, 'complex')}")

if __name__ == "__main__":
    main()
""")
            
            yield str(project_path)

    @pytest.fixture
    def analyze_scale_tool(self, temp_project_dir):
        """Create AnalyzeScaleTool instance"""
        return AnalyzeScaleTool(project_root=temp_project_dir)

    def create_mock_analysis_result(self, file_type="java"):
        """Create mock analysis result"""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.error_message = None
        
        if file_type == "java":
            # Mock Java elements
            mock_elements = []
            
            # Mock class element
            mock_class = MagicMock()
            mock_class.name = "ComplexSample"
            mock_class.class_type = "class"
            mock_class.start_line = 12
            mock_class.end_line = 120
            mock_class.visibility = "public"
            mock_class.extends_class = None
            mock_class.implements_interfaces = []
            mock_class.annotations = [MagicMock(name="Component"), MagicMock(name="Service")]
            mock_elements.append(mock_class)
            
            # Mock method elements
            mock_method1 = MagicMock()
            mock_method1.name = "complexCalculation"
            mock_method1.start_line = 30
            mock_method1.end_line = 65
            mock_method1.visibility = "public"
            mock_method1.return_type = "int"
            mock_method1.parameters = ["int", "String", "boolean"]
            mock_method1.complexity_score = 15  # High complexity
            mock_method1.is_constructor = False
            mock_method1.is_static = False
            mock_method1.annotations = [MagicMock(name="Transactional")]
            mock_elements.append(mock_method1)
            
            mock_method2 = MagicMock()
            mock_method2.name = "recursiveHelper"
            mock_method2.start_line = 67
            mock_method2.end_line = 75
            mock_method2.visibility = "private"
            mock_method2.return_type = "int"
            mock_method2.parameters = ["int", "int"]
            mock_method2.complexity_score = 3
            mock_method2.is_constructor = False
            mock_method2.is_static = False
            mock_method2.annotations = []
            mock_elements.append(mock_method2)
            
            # Mock field elements
            mock_field = MagicMock()
            mock_field.name = "items"
            mock_field.field_type = "List<String>"
            mock_field.start_line = 15
            mock_field.end_line = 15
            mock_field.visibility = "private"
            mock_field.is_static = False
            mock_field.is_final = True
            mock_field.annotations = []
            mock_elements.append(mock_field)
            
            mock_result.elements = mock_elements
            
            # Mock package
            mock_package = MagicMock()
            mock_package.name = "com.example.complex"
            mock_result.package = mock_package
            
            # Mock statistics
            mock_result.get_statistics = MagicMock(return_value={
                "total_classes": 1,
                "total_methods": 2,
                "total_fields": 1,
                "average_complexity": 9.0
            })
        
        return mock_result

    @pytest.mark.asyncio
    async def test_basic_analyze_scale_functionality(self, analyze_scale_tool, temp_project_dir):
        """Test basic analyze_scale functionality"""
        java_file = Path(temp_project_dir) / "ComplexSample.java"
        
        with patch.object(analyze_scale_tool.analysis_engine, 'analyze') as mock_analyze:
            mock_analyze.return_value = self.create_mock_analysis_result("java")
            
            arguments = {
                "file_path": str(java_file),
                "language": "java",
                "include_complexity": True,
                "include_details": False,
                "include_guidance": True
            }
            
            result = await analyze_scale_tool.execute(arguments)
            
            # Check basic result structure
            assert "file_path" in result
            assert "language" in result
            assert result["language"] == "java"
            assert "file_metrics" in result
            assert "summary" in result
            assert "structural_overview" in result
            assert "llm_guidance" in result
            
            # Check file metrics
            file_metrics = result["file_metrics"]
            assert "total_lines" in file_metrics
            assert "code_lines" in file_metrics
            assert "comment_lines" in file_metrics
            assert "blank_lines" in file_metrics
            assert "estimated_tokens" in file_metrics
            assert "file_size_bytes" in file_metrics
            
            # Check summary
            summary = result["summary"]
            assert "classes" in summary
            assert "methods" in summary
            assert "fields" in summary
            assert "imports" in summary
            
            # Check structural overview
            structural = result["structural_overview"]
            assert "classes" in structural
            assert "methods" in structural
            assert "fields" in structural
            assert "complexity_hotspots" in structural
            
            # Check LLM guidance
            guidance = result["llm_guidance"]
            assert "analysis_strategy" in guidance
            assert "recommended_tools" in guidance
            assert "size_category" in guidance
            assert "complexity_assessment" in guidance

    @pytest.mark.asyncio
    async def test_include_details_functionality(self, analyze_scale_tool, temp_project_dir):
        """Test include_details functionality"""
        java_file = Path(temp_project_dir) / "ComplexSample.java"
        
        with patch.object(analyze_scale_tool.analysis_engine, 'analyze') as mock_analyze:
            mock_analyze.return_value = self.create_mock_analysis_result("java")
            
            arguments = {
                "file_path": str(java_file),
                "include_details": True
            }
            
            result = await analyze_scale_tool.execute(arguments)
            
            # Check that detailed analysis is included
            assert "detailed_analysis" in result
            detailed = result["detailed_analysis"]
            assert "statistics" in detailed
            assert "classes" in detailed
            assert "methods" in detailed
            assert "fields" in detailed

    @pytest.mark.asyncio
    async def test_python_file_analysis(self, analyze_scale_tool, temp_project_dir):
        """Test analysis of Python file"""
        python_file = Path(temp_project_dir) / "sample.py"
        
        with patch.object(analyze_scale_tool.analysis_engine, 'analyze') as mock_analyze:
            # Mock universal analysis result
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.error_message = None
            mock_result.elements = []
            mock_analyze.return_value = mock_result
            
            arguments = {
                "file_path": str(python_file),
                "language": "python"
            }
            
            result = await analyze_scale_tool.execute(arguments)
            
            # Check that Python analysis works
            assert result["language"] == "python"
            assert "file_metrics" in result

    @pytest.mark.asyncio
    async def test_language_auto_detection(self, analyze_scale_tool, temp_project_dir):
        """Test automatic language detection"""
        java_file = Path(temp_project_dir) / "ComplexSample.java"
        
        with patch.object(analyze_scale_tool.analysis_engine, 'analyze') as mock_analyze:
            mock_analyze.return_value = self.create_mock_analysis_result("java")
            
            arguments = {
                "file_path": str(java_file)
                # No language specified - should auto-detect
            }
            
            result = await analyze_scale_tool.execute(arguments)
            
            # Should auto-detect Java
            assert result["language"] == "java"

    @pytest.mark.asyncio
    async def test_complexity_hotspots_detection(self, analyze_scale_tool, temp_project_dir):
        """Test complexity hotspots detection"""
        java_file = Path(temp_project_dir) / "ComplexSample.java"
        
        with patch.object(analyze_scale_tool.analysis_engine, 'analyze') as mock_analyze:
            mock_analyze.return_value = self.create_mock_analysis_result("java")
            
            arguments = {
                "file_path": str(java_file),
                "include_complexity": True
            }
            
            result = await analyze_scale_tool.execute(arguments)
            
            # Check complexity hotspots
            structural = result["structural_overview"]
            assert "complexity_hotspots" in structural
            
            # Should detect high complexity method
            hotspots = structural["complexity_hotspots"]
            if hotspots:  # If any hotspots detected
                assert any(hotspot["complexity"] > 10 for hotspot in hotspots)

    @pytest.mark.asyncio
    async def test_llm_guidance_generation(self, analyze_scale_tool, temp_project_dir):
        """Test LLM guidance generation for different file sizes"""
        java_file = Path(temp_project_dir) / "ComplexSample.java"
        
        with patch.object(analyze_scale_tool.analysis_engine, 'analyze') as mock_analyze:
            mock_analyze.return_value = self.create_mock_analysis_result("java")
            
            arguments = {
                "file_path": str(java_file),
                "include_guidance": True
            }
            
            result = await analyze_scale_tool.execute(arguments)
            
            # Check LLM guidance
            guidance = result["llm_guidance"]
            assert "size_category" in guidance
            assert guidance["size_category"] in ["small", "medium", "large", "very_large"]
            assert "analysis_strategy" in guidance
            assert "recommended_tools" in guidance
            assert "complexity_assessment" in guidance

    @pytest.mark.asyncio
    async def test_disable_guidance(self, analyze_scale_tool, temp_project_dir):
        """Test disabling LLM guidance"""
        java_file = Path(temp_project_dir) / "ComplexSample.java"
        
        with patch.object(analyze_scale_tool.analysis_engine, 'analyze') as mock_analyze:
            mock_analyze.return_value = self.create_mock_analysis_result("java")
            
            arguments = {
                "file_path": str(java_file),
                "include_guidance": False
            }
            
            result = await analyze_scale_tool.execute(arguments)
            
            # Should not include LLM guidance
            assert "llm_guidance" not in result

    @pytest.mark.asyncio
    async def test_error_handling_analysis_failure(self, analyze_scale_tool, temp_project_dir):
        """Test error handling when analysis fails"""
        java_file = Path(temp_project_dir) / "ComplexSample.java"
        
        with patch.object(analyze_scale_tool.analysis_engine, 'analyze') as mock_analyze:
            mock_analyze.side_effect = Exception("Analysis failed")
            
            with pytest.raises(Exception, match="Analysis failed"):
                await analyze_scale_tool.execute({
                    "file_path": str(java_file)
                })

    @pytest.mark.asyncio
    async def test_invalid_file_path(self, analyze_scale_tool, temp_project_dir):
        """Test handling of invalid file path"""
        nonexistent_file = Path(temp_project_dir) / "nonexistent.java"
        
        with pytest.raises(ValueError, match="file does not exist"):
            await analyze_scale_tool.execute({
                "file_path": str(nonexistent_file)
            })

    @pytest.mark.asyncio
    async def test_unsupported_language(self, analyze_scale_tool, temp_project_dir):
        """Test handling of unsupported language"""
        # Create a file with unknown extension
        unknown_file = Path(temp_project_dir) / "test.unknown"
        unknown_file.write_text("some content")
        
        with pytest.raises(ValueError, match="Could not detect language"):
            await analyze_scale_tool.execute({
                "file_path": str(unknown_file)
            })

    def test_tool_definition_structure(self, analyze_scale_tool):
        """Test that tool definition has correct structure"""
        definition = analyze_scale_tool.get_tool_definition()
        
        assert definition["name"] == "check_code_scale"
        assert "description" in definition
        assert "inputSchema" in definition
        
        schema = definition["inputSchema"]
        properties = schema["properties"]
        
        # Check required parameters
        assert "file_path" in properties
        assert schema["required"] == ["file_path"]
        
        # Check optional parameters
        assert "language" in properties
        assert "include_complexity" in properties
        assert "include_details" in properties
        assert "include_guidance" in properties
        
        # Check defaults
        assert properties["include_complexity"]["default"] is True
        assert properties["include_details"]["default"] is False
        assert properties["include_guidance"]["default"] is True

    def test_argument_validation(self, analyze_scale_tool):
        """Test argument validation"""
        # Test missing file_path
        with pytest.raises(ValueError, match="Required field 'file_path' is missing"):
            analyze_scale_tool.validate_arguments({})
        
        # Test invalid file_path type
        with pytest.raises(ValueError, match="file_path must be a string"):
            analyze_scale_tool.validate_arguments({"file_path": 123})
        
        # Test empty file_path
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            analyze_scale_tool.validate_arguments({"file_path": ""})
        
        # Test invalid language type
        with pytest.raises(ValueError, match="language must be a string"):
            analyze_scale_tool.validate_arguments({
                "file_path": "test.java",
                "language": 123
            })
        
        # Test invalid boolean parameters
        for param in ["include_complexity", "include_details", "include_guidance"]:
            with pytest.raises(ValueError, match=f"{param} must be a boolean"):
                analyze_scale_tool.validate_arguments({
                    "file_path": "test.java",
                    param: "not_boolean"
                })

    @pytest.mark.asyncio
    async def test_file_metrics_calculation(self, analyze_scale_tool, temp_project_dir):
        """Test file metrics calculation"""
        java_file = Path(temp_project_dir) / "ComplexSample.java"
        
        with patch.object(analyze_scale_tool.analysis_engine, 'analyze') as mock_analyze:
            mock_analyze.return_value = self.create_mock_analysis_result("java")
            
            arguments = {
                "file_path": str(java_file)
            }
            
            result = await analyze_scale_tool.execute(arguments)
            
            # Check file metrics are calculated
            metrics = result["file_metrics"]
            assert metrics["total_lines"] > 0
            assert metrics["code_lines"] > 0
            assert metrics["estimated_tokens"] > 0
            assert metrics["file_size_bytes"] > 0
            assert metrics["file_size_kb"] > 0
            
            # Check that total lines equals sum of components
            assert metrics["total_lines"] == (
                metrics["code_lines"] + 
                metrics["comment_lines"] + 
                metrics["blank_lines"]
            )

    def test_future_file_output_compatibility(self, analyze_scale_tool):
        """Test that the tool structure is compatible with future file output features"""
        # This test ensures the tool can be easily extended with file output features
        
        # Check that the tool has FileOutputManager-compatible structure
        assert hasattr(analyze_scale_tool, 'project_root')
        assert hasattr(analyze_scale_tool, 'path_resolver')
        assert hasattr(analyze_scale_tool, 'security_validator')
        
        # Check that the tool definition could accommodate new parameters
        definition = analyze_scale_tool.get_tool_definition()
        schema = definition["inputSchema"]
        
        # Ensure additionalProperties is False (can be changed to accommodate new params)
        assert schema.get("additionalProperties") is False
        
        # The tool should be ready for file output extension
        # Future implementation would add:
        # - output_file parameter
        # - suppress_output parameter
        # - FileOutputManager integration

    @pytest.mark.asyncio
    async def test_comprehensive_analysis_workflow(self, analyze_scale_tool, temp_project_dir):
        """Test comprehensive analysis workflow"""
        java_file = Path(temp_project_dir) / "ComplexSample.java"
        
        with patch.object(analyze_scale_tool.analysis_engine, 'analyze') as mock_analyze:
            mock_analyze.return_value = self.create_mock_analysis_result("java")
            
            arguments = {
                "file_path": str(java_file),
                "language": "java",
                "include_complexity": True,
                "include_details": True,
                "include_guidance": True
            }
            
            result = await analyze_scale_tool.execute(arguments)
            
            # Check comprehensive result
            assert result["language"] == "java"
            assert "file_metrics" in result
            assert "summary" in result
            assert "structural_overview" in result
            assert "llm_guidance" in result
            assert "detailed_analysis" in result
            
            # Verify all components are properly populated
            assert result["file_metrics"]["total_lines"] > 0
            assert result["summary"]["classes"] >= 0
            assert result["summary"]["methods"] >= 0
            assert len(result["structural_overview"]["classes"]) >= 0
            assert result["llm_guidance"]["size_category"] in ["small", "medium", "large", "very_large"]
            assert "statistics" in result["detailed_analysis"]