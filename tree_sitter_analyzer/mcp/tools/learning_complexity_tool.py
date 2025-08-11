#!/usr/bin/env python3
"""
Learning Complexity Analysis MCP Tool

This tool analyzes the learning complexity of code projects by evaluating
multiple factors including code structure, dependencies, design patterns,
and cognitive load. Designed for educational content generation.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...core.analysis_engine import AnalysisRequest, get_analysis_engine
from ...language_detector import detect_language_from_file
from ...security import SecurityValidator
from ...utils import setup_logger
from .base_tool import MCPTool

# Set up logging
logger = setup_logger(__name__)


class LearningComplexityTool(MCPTool):
    """
    MCP Tool for analyzing learning complexity of code projects.
    
    This tool evaluates multiple dimensions of complexity to determine
    the appropriate learning approach and difficulty level for educational
    content generation.
    """

    def __init__(self, project_root: str = None) -> None:
        """Initialize the learning complexity analysis tool."""
        super().__init__(project_root)
        self.analysis_engine = get_analysis_engine(project_root)
        self.security_validator = SecurityValidator(project_root)
        logger.info("LearningComplexityTool initialized")

    def get_tool_schema(self) -> Dict[str, Any]:
        """
        Get the JSON schema for the learning complexity analysis tool.
        
        Returns:
            Dictionary containing the tool's input schema
        """
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the code file to analyze for learning complexity"
                },
                "analysis_depth": {
                    "type": "string",
                    "enum": ["basic", "detailed", "comprehensive"],
                    "description": "Depth of complexity analysis (default: detailed)",
                    "default": "detailed"
                },
                "target_audience": {
                    "type": "string",
                    "enum": ["beginner", "intermediate", "advanced", "expert"],
                    "description": "Target learning audience level (default: intermediate)",
                    "default": "intermediate"
                },
                "include_recommendations": {
                    "type": "boolean",
                    "description": "Include learning path recommendations (default: true)",
                    "default": True
                }
            },
            "required": ["file_path"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the learning complexity analysis.
        
        Args:
            arguments: Tool arguments containing file_path and analysis options
            
        Returns:
            Dictionary containing complexity analysis results and recommendations
        """
        # Validate required arguments
        if "file_path" not in arguments:
            raise ValueError("file_path is required")

        file_path = arguments["file_path"]
        analysis_depth = arguments.get("analysis_depth", "detailed")
        target_audience = arguments.get("target_audience", "intermediate")
        include_recommendations = arguments.get("include_recommendations", True)

        try:
            # Security validation
            is_valid, error_msg = self.security_validator.validate_file_path(file_path)
            if not is_valid:
                raise ValueError(f"Invalid or unsafe file path: {file_path} - {error_msg}")

            # Check if file exists
            if not Path(file_path).exists():
                raise FileNotFoundError(f"File not found: {file_path}")

            # Detect language
            language = detect_language_from_file(file_path)
            if not language:
                raise ValueError(f"Unsupported or undetectable language for file: {file_path}")

            logger.info(f"Analyzing learning complexity for {file_path} (language: {language})")

            # Perform code analysis
            request = AnalysisRequest(
                file_path=file_path,
                language=language,
                include_complexity=True,
                include_details=True,
            )
            analysis_result = await self.analysis_engine.analyze(request)

            if analysis_result is None:
                raise RuntimeError(f"Failed to analyze file: {file_path}")

            # Calculate complexity metrics
            complexity_metrics = self._calculate_complexity_metrics(
                analysis_result, file_path, analysis_depth
            )

            # Determine learning difficulty
            learning_difficulty = self._assess_learning_difficulty(
                complexity_metrics, target_audience
            )

            # Generate recommendations if requested
            recommendations = {}
            if include_recommendations:
                recommendations = self._generate_learning_recommendations(
                    complexity_metrics, learning_difficulty, target_audience
                )

            return {
                "file_path": file_path,
                "language": language,
                "analysis_depth": analysis_depth,
                "target_audience": target_audience,
                "complexity_metrics": complexity_metrics,
                "learning_difficulty": learning_difficulty,
                "recommendations": recommendations,
                "analysis_summary": self._generate_analysis_summary(
                    complexity_metrics, learning_difficulty
                )
            }

        except Exception as e:
            logger.error(f"Error in learning complexity analysis: {e}")
            raise

    def _calculate_complexity_metrics(
        self, analysis_result: Any, file_path: str, depth: str
    ) -> Dict[str, Any]:
        """Calculate various complexity metrics for learning assessment."""
        
        # Read file content for additional analysis
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        total_lines = len(lines)
        code_lines = len([line for line in lines if line.strip() and not line.strip().startswith('#')])
        
        # Basic metrics
        metrics = {
            "file_size": {
                "total_lines": total_lines,
                "code_lines": code_lines,
                "complexity_score": min(code_lines / 50, 10)  # Scale 0-10
            },
            "structural_complexity": self._analyze_structural_complexity(analysis_result),
            "cognitive_load": self._assess_cognitive_load(content, analysis_result),
            "dependency_complexity": self._analyze_dependencies(content),
            "pattern_complexity": self._identify_design_patterns(content, analysis_result)
        }
        
        if depth in ["detailed", "comprehensive"]:
            metrics.update({
                "abstraction_levels": self._count_abstraction_levels(analysis_result),
                "concept_density": self._calculate_concept_density(content, analysis_result),
                "learning_prerequisites": self._identify_prerequisites(content, analysis_result)
            })
        
        if depth == "comprehensive":
            metrics.update({
                "advanced_patterns": self._identify_advanced_patterns(content, analysis_result),
                "architectural_complexity": self._assess_architectural_complexity(analysis_result),
                "domain_specific_knowledge": self._assess_domain_knowledge(content)
            })
        
        return metrics

    def _analyze_structural_complexity(self, analysis_result: Any) -> Dict[str, Any]:
        """Analyze structural complexity of the code."""
        classes = [e for e in analysis_result.elements if e.__class__.__name__ == "Class"]
        methods = [e for e in analysis_result.elements if e.__class__.__name__ == "Method"]
        
        return {
            "class_count": len(classes),
            "method_count": len(methods),
            "average_methods_per_class": len(methods) / max(len(classes), 1),
            "nesting_depth": self._calculate_max_nesting_depth(analysis_result),
            "complexity_score": min((len(classes) + len(methods)) / 10, 10)
        }

    def _assess_cognitive_load(self, content: str, analysis_result: Any) -> Dict[str, Any]:
        """Assess the cognitive load required to understand the code."""
        # Count various complexity indicators
        conditional_statements = len(re.findall(r'\b(if|else|elif|switch|case)\b', content))
        loops = len(re.findall(r'\b(for|while|do)\b', content))
        try_catch = len(re.findall(r'\b(try|catch|except|finally)\b', content))
        
        return {
            "conditional_complexity": conditional_statements,
            "loop_complexity": loops,
            "exception_handling": try_catch,
            "total_cognitive_load": conditional_statements + loops + try_catch * 2,
            "complexity_score": min((conditional_statements + loops + try_catch) / 5, 10)
        }

    def _analyze_dependencies(self, content: str) -> Dict[str, Any]:
        """Analyze dependency complexity."""
        imports = len(re.findall(r'^(import|from|#include|using)', content, re.MULTILINE))
        external_calls = len(re.findall(r'\w+\.\w+\(', content))
        
        return {
            "import_count": imports,
            "external_calls": external_calls,
            "dependency_score": min((imports + external_calls / 10) / 3, 10)
        }

    def _identify_design_patterns(self, content: str, analysis_result: Any) -> Dict[str, Any]:
        """Identify design patterns that affect learning complexity."""
        patterns = {
            "singleton": bool(re.search(r'class.*Singleton|getInstance\(\)', content)),
            "factory": bool(re.search(r'Factory|create\w*\(', content)),
            "observer": bool(re.search(r'Observer|notify|subscribe', content)),
            "decorator": bool(re.search(r'@\w+|decorator', content)),
            "inheritance": len(re.findall(r'extends|inherits|:', content)) > 0
        }
        
        pattern_count = sum(patterns.values())
        return {
            "identified_patterns": patterns,
            "pattern_count": pattern_count,
            "complexity_score": min(pattern_count * 2, 10)
        }

    def _calculate_max_nesting_depth(self, analysis_result: Any) -> int:
        """Calculate maximum nesting depth in the code."""
        # This is a simplified implementation
        # In a real implementation, you'd traverse the AST
        return 3  # Placeholder

    def _count_abstraction_levels(self, analysis_result: Any) -> Dict[str, Any]:
        """Count different levels of abstraction."""
        return {
            "interfaces": 0,  # Placeholder
            "abstract_classes": 0,  # Placeholder
            "concrete_classes": len([e for e in analysis_result.elements if e.__class__.__name__ == "Class"]),
            "abstraction_score": 5  # Placeholder
        }

    def _calculate_concept_density(self, content: str, analysis_result: Any) -> Dict[str, Any]:
        """Calculate the density of programming concepts."""
        concepts = {
            "oop_concepts": len(re.findall(r'\bclass\b|\binheritance\b|\bpolymorphism\b', content)),
            "functional_concepts": len(re.findall(r'\blambda\b|\bmap\b|\bfilter\b|\breduce\b', content)),
            "async_concepts": len(re.findall(r'\basync\b|\bawait\b|\bPromise\b', content)),
            "generic_concepts": len(re.findall(r'<\w+>|\bgeneric\b|\btemplate\b', content))
        }
        
        total_concepts = sum(concepts.values())
        code_lines = len([line for line in content.split('\n') if line.strip()])
        
        return {
            "concepts": concepts,
            "total_concepts": total_concepts,
            "concept_density": total_concepts / max(code_lines, 1) * 100,
            "complexity_score": min(total_concepts / 5, 10)
        }

    def _identify_prerequisites(self, content: str, analysis_result: Any) -> List[str]:
        """Identify learning prerequisites for understanding the code."""
        prerequisites = []
        
        if re.search(r'\bclass\b', content):
            prerequisites.append("Object-Oriented Programming")
        if re.search(r'\basync\b|\bawait\b', content):
            prerequisites.append("Asynchronous Programming")
        if re.search(r'\bgeneric\b|<\w+>', content):
            prerequisites.append("Generic Programming")
        if re.search(r'\btry\b|\bcatch\b|\bexcept\b', content):
            prerequisites.append("Exception Handling")
        
        return prerequisites

    def _identify_advanced_patterns(self, content: str, analysis_result: Any) -> Dict[str, Any]:
        """Identify advanced programming patterns."""
        return {
            "metaprogramming": bool(re.search(r'__getattr__|__setattr__|metaclass', content)),
            "reflection": bool(re.search(r'getattr|hasattr|isinstance', content)),
            "concurrency": bool(re.search(r'thread|process|concurrent|parallel', content)),
            "complexity_score": 5  # Placeholder
        }

    def _assess_architectural_complexity(self, analysis_result: Any) -> Dict[str, Any]:
        """Assess architectural complexity."""
        return {
            "layered_architecture": False,  # Placeholder
            "microservices": False,  # Placeholder
            "design_patterns_count": 0,  # Placeholder
            "complexity_score": 5  # Placeholder
        }

    def _assess_domain_knowledge(self, content: str) -> Dict[str, Any]:
        """Assess domain-specific knowledge requirements."""
        domains = {
            "web_development": bool(re.search(r'http|html|css|javascript|react|vue', content, re.IGNORECASE)),
            "data_science": bool(re.search(r'pandas|numpy|sklearn|tensorflow', content, re.IGNORECASE)),
            "database": bool(re.search(r'sql|database|query|orm', content, re.IGNORECASE)),
            "networking": bool(re.search(r'socket|tcp|udp|protocol', content, re.IGNORECASE))
        }
        
        return {
            "domains": domains,
            "domain_count": sum(domains.values()),
            "complexity_score": sum(domains.values()) * 2
        }

    def _assess_learning_difficulty(
        self, metrics: Dict[str, Any], target_audience: str
    ) -> Dict[str, Any]:
        """Assess overall learning difficulty based on metrics."""
        
        # Calculate weighted complexity score
        weights = {
            "structural": 0.25,
            "cognitive": 0.30,
            "dependency": 0.15,
            "pattern": 0.20,
            "concept_density": 0.10
        }
        
        total_score = (
            metrics["structural_complexity"]["complexity_score"] * weights["structural"] +
            metrics["cognitive_load"]["complexity_score"] * weights["cognitive"] +
            metrics["dependency_complexity"]["dependency_score"] * weights["dependency"] +
            metrics["pattern_complexity"]["complexity_score"] * weights["pattern"] +
            metrics.get("concept_density", {}).get("complexity_score", 0) * weights["concept_density"]
        )
        
        # Adjust for target audience
        audience_multipliers = {
            "beginner": 1.5,
            "intermediate": 1.0,
            "advanced": 0.8,
            "expert": 0.6
        }
        
        adjusted_score = total_score * audience_multipliers.get(target_audience, 1.0)
        
        # Determine difficulty level
        if adjusted_score <= 3:
            difficulty = "Easy"
        elif adjusted_score <= 6:
            difficulty = "Moderate"
        elif adjusted_score <= 8:
            difficulty = "Challenging"
        else:
            difficulty = "Very Challenging"
        
        return {
            "raw_score": total_score,
            "adjusted_score": adjusted_score,
            "difficulty_level": difficulty,
            "target_audience": target_audience,
            "confidence": min(0.8 + (10 - adjusted_score) * 0.02, 1.0)
        }

    def _generate_learning_recommendations(
        self, metrics: Dict[str, Any], difficulty: Dict[str, Any], target_audience: str
    ) -> Dict[str, Any]:
        """Generate learning path recommendations."""
        
        recommendations = {
            "suggested_approach": self._suggest_learning_approach(difficulty, metrics),
            "prerequisite_topics": metrics.get("learning_prerequisites", []),
            "learning_sequence": self._suggest_learning_sequence(metrics),
            "time_estimate": self._estimate_learning_time(difficulty, metrics),
            "teaching_strategies": self._suggest_teaching_strategies(difficulty, metrics, target_audience)
        }
        
        return recommendations

    def _suggest_learning_approach(self, difficulty: Dict[str, Any], metrics: Dict[str, Any]) -> str:
        """Suggest the best learning approach."""
        if difficulty["difficulty_level"] == "Easy":
            return "Direct code reading with minimal explanation"
        elif difficulty["difficulty_level"] == "Moderate":
            return "Step-by-step walkthrough with examples"
        elif difficulty["difficulty_level"] == "Challenging":
            return "Incremental learning with practice exercises"
        else:
            return "Comprehensive tutorial with multiple examples and projects"

    def _suggest_learning_sequence(self, metrics: Dict[str, Any]) -> List[str]:
        """Suggest optimal learning sequence."""
        sequence = ["Basic structure overview"]
        
        if metrics["structural_complexity"]["class_count"] > 0:
            sequence.append("Class and object concepts")
        
        if metrics["cognitive_load"]["conditional_complexity"] > 5:
            sequence.append("Control flow and logic")
        
        if metrics["dependency_complexity"]["import_count"] > 3:
            sequence.append("Dependencies and modules")
        
        if metrics["pattern_complexity"]["pattern_count"] > 0:
            sequence.append("Design patterns")
        
        sequence.append("Complete implementation walkthrough")
        sequence.append("Practical exercises")
        
        return sequence

    def _estimate_learning_time(self, difficulty: Dict[str, Any], metrics: Dict[str, Any]) -> Dict[str, str]:
        """Estimate learning time for different audiences."""
        base_hours = difficulty["adjusted_score"] * 2
        
        return {
            "beginner": f"{int(base_hours * 1.5)}-{int(base_hours * 2)} hours",
            "intermediate": f"{int(base_hours)}-{int(base_hours * 1.3)} hours",
            "advanced": f"{int(base_hours * 0.7)}-{int(base_hours)} hours",
            "expert": f"{int(base_hours * 0.5)}-{int(base_hours * 0.7)} hours"
        }

    def _suggest_teaching_strategies(
        self, difficulty: Dict[str, Any], metrics: Dict[str, Any], target_audience: str
    ) -> List[str]:
        """Suggest effective teaching strategies."""
        strategies = []
        
        if difficulty["difficulty_level"] in ["Challenging", "Very Challenging"]:
            strategies.append("Break down into smaller, digestible chunks")
            strategies.append("Provide multiple examples and analogies")
        
        if metrics["cognitive_load"]["total_cognitive_load"] > 10:
            strategies.append("Use visual diagrams and flowcharts")
            strategies.append("Provide step-by-step debugging exercises")
        
        if metrics["pattern_complexity"]["pattern_count"] > 2:
            strategies.append("Explain design patterns with real-world analogies")
            strategies.append("Show evolution from simple to complex patterns")
        
        if target_audience == "beginner":
            strategies.append("Start with conceptual overview before diving into code")
            strategies.append("Provide extensive comments and explanations")
        
        return strategies

    def _generate_analysis_summary(
        self, metrics: Dict[str, Any], difficulty: Dict[str, Any]
    ) -> str:
        """Generate a human-readable analysis summary."""
        
        summary_parts = [
            f"Learning Difficulty: {difficulty['difficulty_level']} ({difficulty['adjusted_score']:.1f}/10)",
            f"Structural Complexity: {metrics['structural_complexity']['complexity_score']:.1f}/10",
            f"Cognitive Load: {metrics['cognitive_load']['complexity_score']:.1f}/10",
            f"Pattern Complexity: {metrics['pattern_complexity']['complexity_score']:.1f}/10"
        ]
        
        if metrics.get("concept_density"):
            summary_parts.append(f"Concept Density: {metrics['concept_density']['complexity_score']:.1f}/10")
        
        return " | ".join(summary_parts)

    def get_tool_definition(self) -> Any:
        """Get the MCP tool definition for learning complexity analysis."""
        try:
            from mcp.types import Tool
            
            return Tool(
                name="analyze_learning_complexity",
                description="Analyze learning complexity of code files for educational content generation",
                inputSchema=self.get_tool_schema(),
            )
        except ImportError:
            return {
                "name": "analyze_learning_complexity",
                "description": "Analyze learning complexity of code files for educational content generation",
                "inputSchema": self.get_tool_schema(),
            }


# Tool instance for easy access
learning_complexity_tool = LearningComplexityTool()
