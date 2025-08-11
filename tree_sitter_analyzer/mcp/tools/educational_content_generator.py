#!/usr/bin/env python3
"""
Educational Content Generator MCP Tool

This is the main MCP tool that orchestrates the entire educational content generation
process using multi-agent collaboration and intelligent analysis.
"""

import json
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import asdict

from ...core.analysis_engine import AnalysisRequest, get_analysis_engine
from ...language_detector import detect_language_from_file
from ...security import SecurityValidator
from ...utils import setup_logger
from .base_tool import MCPTool
from .learning_complexity_tool import LearningComplexityTool
from ..agents.multi_agent_coordinator import (
    MultiAgentCoordinator,
    ProjectContext,
    LearningContext,
    LearningLevel,
    ContentType
)

# Set up logging
logger = setup_logger(__name__)


class EducationalContentGenerator(MCPTool):
    """
    Main MCP tool for generating educational content for open source projects.
    
    This tool combines:
    - Code analysis using tree-sitter
    - Learning complexity assessment
    - Multi-agent AI collaboration
    - Dynamic prompt generation
    - Comprehensive educational content creation
    """

    def __init__(self, project_root: str = None) -> None:
        """Initialize the educational content generator."""
        super().__init__(project_root)
        self.analysis_engine = get_analysis_engine(project_root)
        self.security_validator = SecurityValidator(project_root)
        self.complexity_tool = LearningComplexityTool(project_root)
        self.coordinator = MultiAgentCoordinator()
        logger.info("EducationalContentGenerator initialized")

    def get_tool_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for the educational content generator."""
        return {
            "type": "object",
            "properties": {
                "project_path": {
                    "type": "string",
                    "description": "Path to the project or main file to analyze"
                },
                "target_audience": {
                    "type": "string",
                    "enum": ["beginner", "intermediate", "advanced", "expert"],
                    "description": "Target learning audience level",
                    "default": "intermediate"
                },
                "content_type": {
                    "type": "string",
                    "enum": ["overview", "tutorial", "example", "exercise", "project", "reference"],
                    "description": "Type of educational content to generate",
                    "default": "tutorial"
                },
                "learning_objectives": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific learning objectives for the content",
                    "default": []
                },
                "content_depth": {
                    "type": "string",
                    "enum": ["basic", "detailed", "comprehensive"],
                    "description": "Depth of content analysis and generation",
                    "default": "detailed"
                },
                "include_exercises": {
                    "type": "boolean",
                    "description": "Include practical exercises and activities",
                    "default": True
                },
                "include_assessments": {
                    "type": "boolean",
                    "description": "Include assessment criteria and rubrics",
                    "default": True
                },
                "output_format": {
                    "type": "string",
                    "enum": ["markdown", "html", "json", "structured"],
                    "description": "Output format for the generated content",
                    "default": "structured"
                }
            },
            "required": ["project_path"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the educational content generation process.
        
        Args:
            arguments: Tool arguments containing project path and generation options
            
        Returns:
            Dictionary containing generated educational content and metadata
        """
        # Validate required arguments
        if "project_path" not in arguments:
            raise ValueError("project_path is required")

        project_path = arguments["project_path"]
        target_audience = arguments.get("target_audience", "intermediate")
        content_type = arguments.get("content_type", "tutorial")
        learning_objectives = arguments.get("learning_objectives", [])
        content_depth = arguments.get("content_depth", "detailed")
        include_exercises = arguments.get("include_exercises", True)
        include_assessments = arguments.get("include_assessments", True)
        output_format = arguments.get("output_format", "structured")

        try:
            # Security validation
            is_valid, error_msg = self.security_validator.validate_file_path(project_path)
            if not is_valid:
                raise ValueError(f"Invalid or unsafe project path: {project_path} - {error_msg}")

            # Check if path exists
            if not Path(project_path).exists():
                raise FileNotFoundError(f"Project path not found: {project_path}")

            logger.info(f"Starting educational content generation for {project_path}")

            # Step 1: Analyze project structure and complexity
            project_analysis = await self._analyze_project(project_path, content_depth)

            # Step 2: Assess learning complexity
            complexity_analysis = await self._assess_learning_complexity(
                project_path, target_audience, content_depth
            )
            
            # Step 3: Create project and learning contexts
            project_context = self._create_project_context(project_analysis, complexity_analysis)
            learning_context = self._create_learning_context(
                target_audience, content_type, learning_objectives
            )
            
            # Step 4: Generate content using multi-agent collaboration
            content_requirements = {
                "include_exercises": include_exercises,
                "include_assessments": include_assessments,
                "output_format": output_format,
                "content_depth": content_depth
            }
            
            collaboration_result = await self.coordinator.generate_educational_content(
                project_context, learning_context, content_requirements
            )
            
            # Step 5: Format and structure the final output
            final_content = self._format_final_content(
                collaboration_result, output_format, arguments
            )
            
            logger.info("Educational content generation completed successfully")
            
            return {
                "success": True,
                "project_path": project_path,
                "target_audience": target_audience,
                "content_type": content_type,
                "project_analysis": project_analysis,
                "complexity_analysis": complexity_analysis,
                "collaboration_result": asdict(collaboration_result) if hasattr(collaboration_result, '__dict__') else str(collaboration_result),
                "generated_content": final_content,
                "metadata": {
                    "generation_timestamp": self._get_timestamp(),
                    "quality_score": collaboration_result.quality_score,
                    "recommendations": collaboration_result.recommendations,
                    "next_steps": collaboration_result.next_steps
                }
            }

        except Exception as e:
            logger.error(f"Error in educational content generation: {e}")
            return {
                "success": False,
                "error": str(e),
                "project_path": project_path,
                "target_audience": target_audience,
                "content_type": content_type
            }

    async def _analyze_project(self, project_path: str, depth: str) -> Dict[str, Any]:
        """Analyze the project structure and characteristics."""
        
        # Detect language
        language = detect_language_from_file(project_path)
        if not language:
            raise ValueError(f"Unsupported or undetectable language for: {project_path}")

        # Perform comprehensive analysis
        request = AnalysisRequest(
            file_path=project_path,
            language=language,
            include_complexity=True,
            include_details=(depth in ["detailed", "comprehensive"]),
        )
        
        analysis_result = await self.analysis_engine.analyze(request)
        if analysis_result is None:
            raise RuntimeError(f"Failed to analyze project: {project_path}")

        # Extract project characteristics
        project_analysis = {
            "language": language,
            "file_path": project_path,
            "structure": self._extract_structure_info(analysis_result),
            "complexity_metrics": self._extract_complexity_metrics(analysis_result),
            "key_concepts": self._identify_key_concepts(analysis_result, language),
            "architecture_patterns": self._identify_architecture_patterns(analysis_result),
            "dependencies": self._analyze_dependencies(project_path)
        }
        
        return project_analysis

    async def _assess_learning_complexity(
        self, project_path: str, target_audience: str, depth: str
    ) -> Dict[str, Any]:
        """Assess the learning complexity of the project."""
        
        complexity_args = {
            "file_path": project_path,
            "analysis_depth": depth,
            "target_audience": target_audience,
            "include_recommendations": True
        }
        
        complexity_result = await self.complexity_tool.execute(complexity_args)
        return complexity_result

    def _create_project_context(
        self, project_analysis: Dict[str, Any], complexity_analysis: Dict[str, Any]
    ) -> ProjectContext:
        """Create a ProjectContext object from analysis results."""
        
        return ProjectContext(
            language=project_analysis["language"],
            project_type=self._determine_project_type(project_analysis),
            complexity_score=complexity_analysis["learning_difficulty"]["adjusted_score"],
            domain=self._determine_domain(project_analysis),
            architecture_patterns=project_analysis["architecture_patterns"],
            key_concepts=project_analysis["key_concepts"],
            prerequisites=complexity_analysis["recommendations"]["prerequisite_topics"]
        )

    def _create_learning_context(
        self, target_audience: str, content_type: str, learning_objectives: List[str]
    ) -> LearningContext:
        """Create a LearningContext object from parameters."""
        
        # Set default learning objectives if none provided
        if not learning_objectives:
            learning_objectives = [
                "Understand the project structure and architecture",
                "Learn key programming concepts and patterns",
                "Gain practical implementation skills",
                "Apply knowledge through hands-on exercises"
            ]
        
        return LearningContext(
            target_level=LearningLevel(target_audience),
            content_type=ContentType(content_type),
            learning_objectives=learning_objectives
        )

    def _extract_structure_info(self, analysis_result: Any) -> Dict[str, Any]:
        """Extract structural information from analysis result."""
        classes = [e for e in analysis_result.elements if e.__class__.__name__ == "Class"]
        methods = [e for e in analysis_result.elements if e.__class__.__name__ == "Method"]
        
        return {
            "classes": len(classes),
            "methods": len(methods),
            "total_elements": len(analysis_result.elements),
            "has_inheritance": any(hasattr(c, 'parent') and c.parent for c in classes),
            "has_interfaces": False  # Placeholder - would need language-specific detection
        }

    def _extract_complexity_metrics(self, analysis_result: Any) -> Dict[str, Any]:
        """Extract complexity metrics from analysis result."""
        return {
            "cyclomatic_complexity": getattr(analysis_result, 'complexity', 0),
            "nesting_depth": 3,  # Placeholder
            "coupling": 2,  # Placeholder
            "cohesion": 0.8  # Placeholder
        }

    def _identify_key_concepts(self, analysis_result: Any, language: str) -> List[str]:
        """Identify key programming concepts present in the code."""
        concepts = []
        
        classes = [e for e in analysis_result.elements if e.__class__.__name__ == "Class"]
        methods = [e for e in analysis_result.elements if e.__class__.__name__ == "Method"]
        
        if classes:
            concepts.append("Object-Oriented Programming")
        if methods:
            concepts.append("Functions and Methods")
        
        # Language-specific concepts
        if language == "python":
            concepts.extend(["Python Syntax", "Dynamic Typing"])
        elif language == "java":
            concepts.extend(["Static Typing", "Compilation"])
        elif language == "javascript":
            concepts.extend(["Dynamic Typing", "Prototypes"])
        
        return concepts

    def _identify_architecture_patterns(self, analysis_result: Any) -> List[str]:
        """Identify architecture patterns in the code."""
        patterns = []
        
        classes = [e for e in analysis_result.elements if e.__class__.__name__ == "Class"]
        
        if len(classes) > 1:
            patterns.append("Multi-class Design")
        
        # This would be more sophisticated in a real implementation
        patterns.append("Modular Architecture")
        
        return patterns

    def _analyze_dependencies(self, project_path: str) -> Dict[str, Any]:
        """Analyze project dependencies."""
        try:
            with open(project_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            import_count = len([line for line in content.split('\n') 
                              if line.strip().startswith(('import', 'from', '#include', 'using'))])
            
            return {
                "import_count": import_count,
                "external_dependencies": import_count > 5,
                "complexity_level": "high" if import_count > 10 else "medium" if import_count > 3 else "low"
            }
        except Exception:
            return {"import_count": 0, "external_dependencies": False, "complexity_level": "low"}

    def _determine_project_type(self, project_analysis: Dict[str, Any]) -> str:
        """Determine the type of project based on analysis."""
        structure = project_analysis["structure"]
        
        if structure["classes"] > 3:
            return "Object-Oriented Application"
        elif structure["methods"] > 10:
            return "Functional Application"
        else:
            return "Simple Script"

    def _determine_domain(self, project_analysis: Dict[str, Any]) -> str:
        """Determine the domain/field of the project."""
        # This would be more sophisticated in a real implementation
        # Could analyze imports, class names, method names, etc.
        return "general"

    def _format_final_content(
        self, collaboration_result: Any, output_format: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Format the final content based on the requested output format."""
        
        if output_format == "markdown":
            return {
                "format": "markdown",
                "content": self._generate_markdown_content(collaboration_result)
            }
        elif output_format == "html":
            return {
                "format": "html", 
                "content": self._generate_html_content(collaboration_result)
            }
        elif output_format == "json":
            return {
                "format": "json",
                "content": self._generate_json_content(collaboration_result)
            }
        else:  # structured
            return {
                "format": "structured",
                "content": self._generate_structured_content(collaboration_result, arguments)
            }

    def _generate_markdown_content(self, collaboration_result: Any) -> str:
        """Generate markdown formatted content."""
        return f"""# Educational Content

## Overview
{collaboration_result.synthesized_content}

## Quality Score
{collaboration_result.quality_score:.2f}/1.0

## Recommendations
{chr(10).join(f'- {rec}' for rec in collaboration_result.recommendations)}

## Next Steps
{chr(10).join(f'1. {step}' for step in collaboration_result.next_steps)}
"""

    def _generate_html_content(self, collaboration_result: Any) -> str:
        """Generate HTML formatted content."""
        return f"""
<html>
<head><title>Educational Content</title></head>
<body>
<h1>Educational Content</h1>
<div>{collaboration_result.synthesized_content}</div>
<h2>Quality Score: {collaboration_result.quality_score:.2f}</h2>
</body>
</html>
"""

    def _generate_json_content(self, collaboration_result: Any) -> Dict[str, Any]:
        """Generate JSON formatted content."""
        return {
            "content": collaboration_result.synthesized_content,
            "quality_score": collaboration_result.quality_score,
            "recommendations": collaboration_result.recommendations,
            "next_steps": collaboration_result.next_steps
        }

    def _generate_structured_content(
        self, collaboration_result: Any, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate structured content with all components."""
        
        structured_content = {
            "course_outline": self._generate_course_outline(collaboration_result),
            "learning_materials": self._generate_learning_materials(collaboration_result),
            "quality_metrics": {
                "overall_score": collaboration_result.quality_score,
                "agent_confidence": self._extract_agent_confidence(collaboration_result),
                "content_completeness": self._assess_content_completeness(collaboration_result)
            },
            "implementation_guide": {
                "recommendations": collaboration_result.recommendations,
                "next_steps": collaboration_result.next_steps,
                "success_criteria": self._generate_success_criteria(collaboration_result)
            }
        }
        
        if arguments.get("include_exercises", True):
            structured_content["exercises"] = self._generate_exercises(collaboration_result)
        
        if arguments.get("include_assessments", True):
            structured_content["assessments"] = self._generate_assessments(collaboration_result)
        
        return structured_content

    def _generate_course_outline(self, collaboration_result: Any) -> Dict[str, Any]:
        """Generate a structured course outline."""
        return {
            "title": f"Learning {collaboration_result.project_context.language.title()}",
            "description": "Comprehensive educational content for understanding this project",
            "learning_objectives": collaboration_result.learning_context.learning_objectives,
            "modules": [
                {"title": "Project Overview", "duration": "30 minutes"},
                {"title": "Core Concepts", "duration": "60 minutes"},
                {"title": "Implementation Details", "duration": "90 minutes"},
                {"title": "Practical Exercises", "duration": "120 minutes"}
            ]
        }

    def _generate_learning_materials(self, collaboration_result: Any) -> Dict[str, Any]:
        """Generate structured learning materials."""
        return {
            "content": collaboration_result.synthesized_content,
            "examples": ["Example 1: Basic usage", "Example 2: Advanced patterns"],
            "resources": ["Official documentation", "Community tutorials", "Best practices guide"]
        }

    def _extract_agent_confidence(self, collaboration_result: Any) -> Dict[str, float]:
        """Extract confidence scores from each agent."""
        confidence_scores = {}
        for role, response in collaboration_result.agent_responses.items():
            confidence_scores[role] = response.confidence
        return confidence_scores

    def _assess_content_completeness(self, collaboration_result: Any) -> float:
        """Assess the completeness of generated content."""
        # Simple heuristic based on content length and agent participation
        content_length = len(collaboration_result.synthesized_content)
        agent_participation = len(collaboration_result.agent_responses)
        
        completeness = min((content_length / 1000) * (agent_participation / 4), 1.0)
        return completeness

    def _generate_success_criteria(self, collaboration_result: Any) -> List[str]:
        """Generate success criteria for the educational content."""
        return [
            "Learners can explain key concepts clearly",
            "Learners can implement basic functionality",
            "Learners can identify and fix common issues",
            "Learners can extend the project with new features"
        ]

    def _generate_exercises(self, collaboration_result: Any) -> List[Dict[str, Any]]:
        """Generate practical exercises."""
        return [
            {
                "title": "Code Reading Exercise",
                "description": "Analyze the main components and explain their purpose",
                "difficulty": "beginner",
                "estimated_time": "20 minutes"
            },
            {
                "title": "Implementation Exercise", 
                "description": "Implement a similar feature using the same patterns",
                "difficulty": "intermediate",
                "estimated_time": "45 minutes"
            }
        ]

    def _generate_assessments(self, collaboration_result: Any) -> List[Dict[str, Any]]:
        """Generate assessment criteria and rubrics."""
        return [
            {
                "type": "knowledge_check",
                "questions": [
                    "What are the main components of this system?",
                    "How do the different parts interact?",
                    "What design patterns are used and why?"
                ]
            },
            {
                "type": "practical_assessment",
                "tasks": [
                    "Modify the code to add a new feature",
                    "Debug a provided broken implementation",
                    "Optimize the code for better performance"
                ]
            }
        ]

    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.now().isoformat()

    def get_tool_definition(self) -> Any:
        """Get the MCP tool definition for educational content generation."""
        try:
            from mcp.types import Tool
            
            return Tool(
                name="generate_educational_content",
                description="Generate comprehensive educational content for open source projects using multi-agent AI collaboration",
                inputSchema=self.get_tool_schema(),
            )
        except ImportError:
            return {
                "name": "generate_educational_content",
                "description": "Generate comprehensive educational content for open source projects using multi-agent AI collaboration",
                "inputSchema": self.get_tool_schema(),
            }


# Tool instance for easy access
educational_content_generator = EducationalContentGenerator()
