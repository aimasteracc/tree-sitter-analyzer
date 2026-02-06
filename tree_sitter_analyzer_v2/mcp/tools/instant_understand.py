"""
MCP Tool for Instant Project Understanding.

This module provides the instant_understand tool that performs comprehensive
project analysis and generates layered understanding reports (5/15/30 minute views).
"""

import logging
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.features.instant_understanding import (
    InstantUnderstandingEngine,
    instant_understand
)
from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool

logger = logging.getLogger(__name__)


class InstantUnderstandTool(BaseTool):
    """
    MCP tool for instant project understanding.
    
    Performs comprehensive analysis combining multiple analyzers to generate
    layered understanding reports without requiring AI/LLM.
    
    Features:
    - Layer 1 (5 min): Quick overview with statistics
    - Layer 2 (15 min): Architecture with Mermaid diagrams
    - Layer 3 (30 min): Deep insights with recommendations
    """
    
    def __init__(self):
        """Initialize the instant understand tool."""
        pass
    
    def get_name(self) -> str:
        """Get tool name."""
        return "instant_understand"
    
    def get_description(self) -> str:
        """Get tool description."""
        return (
            "Perform comprehensive project analysis and generate layered understanding reports. "
            "Combines multiple analyzers to provide 3 layers of understanding: "
            "Layer 1 (5 min) - Quick overview with statistics; "
            "Layer 2 (15 min) - Architecture with Mermaid diagrams; "
            "Layer 3 (30 min) - Deep insights with performance analysis, tech debt, and recommendations. "
            "Pure data-driven analysis - no AI/LLM required."
        )
    
    def get_schema(self) -> dict[str, Any]:
        """Get JSON schema for tool arguments."""
        return {
            "type": "object",
            "properties": {
                "project_path": {
                    "type": "string",
                    "description": "Path to the project directory to analyze"
                },
                "output_file": {
                    "type": "string",
                    "description": "Optional output file path (.md or .html). If not provided, returns report as text.",
                    "default": None
                },
                "force_rebuild": {
                    "type": "boolean",
                    "description": "Force rebuild all analysis caches (default: false)",
                    "default": False
                },
                "language": {
                    "type": "string",
                    "description": "Primary programming language (default: python)",
                    "enum": ["python", "java", "typescript", "javascript"],
                    "default": "python"
                },
                "output_format": {
                    "type": "string",
                    "description": "Output format type when saving to file",
                    "enum": ["markdown", "html"],
                    "default": "markdown"
                }
            },
            "required": ["project_path"]
        }
    
    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the instant understand tool.
        
        Args:
            arguments: Tool arguments containing:
                - project_path: Path to project directory
                - output_file: Optional output file path
                - force_rebuild: Force rebuild caches
                - language: Primary language (default: python)
                - output_format: markdown or html (default: markdown)
        
        Returns:
            Dict containing:
                - success: Whether analysis succeeded
                - project_name: Name of analyzed project
                - report_summary: Summary of analysis results
                - layer1: Quick overview (5 min)
                - layer2: Architecture understanding (15 min)
                - layer3: Deep insights (30 min)
                - markdown_report: Full markdown report
                - output_file: Path to saved file (if output_file was provided)
                - error: Error message if failed
        """
        project_path_str = arguments.get("project_path", "")
        output_file_str = arguments.get("output_file")
        force_rebuild = arguments.get("force_rebuild", False)
        language = arguments.get("language", "python")
        output_format = arguments.get("output_format", "markdown")
        
        # Validate project path
        project_path = Path(project_path_str)
        if not project_path.exists():
            return {
                "success": False,
                "error": f"Project path does not exist: {project_path_str}"
            }
        
        if not project_path.is_dir():
            return {
                "success": False,
                "error": f"Project path is not a directory: {project_path_str}"
            }
        
        try:
            logger.info(f"Starting instant understanding for {project_path}")
            
            # Create engine and analyze
            engine = InstantUnderstandingEngine(project_path, language=language)
            report = engine.analyze(force_rebuild=force_rebuild)
            
            # Generate markdown report
            markdown_report = engine.to_markdown(report)
            
            # Save to file if requested
            saved_file = None
            if output_file_str:
                output_path = Path(output_file_str)
                
                # Determine format from extension or argument
                if output_path.suffix == '.html' or output_format == 'html':
                    if output_path.suffix != '.html':
                        output_path = output_path.with_suffix('.html')
                    engine.save_report(report, output_path)
                    saved_file = str(output_path)
                else:
                    if output_path.suffix != '.md':
                        output_path = output_path.with_suffix('.md')
                    engine.save_report(report, output_path)
                    saved_file = str(output_path)
                
                logger.info(f"Report saved to {saved_file}")
            
            # Build layer summaries
            layer1_summary = {
                "project_name": report.layer1.project_name,
                "summary": report.layer1.summary,
                "statistics": report.layer1.statistics,
                "top_files_count": len(report.layer1.top_files),
                "entry_points_count": len(report.layer1.entry_points)
            }
            
            layer2_summary = {
                "modules_count": report.layer2.module_structure.get('total_modules', 0),
                "design_patterns": report.layer2.design_patterns,
                "call_graph_summary": report.layer2.call_graph,
                "diagrams_count": len(report.mermaid_diagrams)
            }
            
            layer3_summary = {
                "health_score": report.layer3.health_score,
                "performance_hotspots": report.layer3.performance_analysis.get('total_hotspots', 0),
                "tech_debt_items": report.layer3.tech_debt_report.get('total_count', 0),
                "tech_debt_hours": report.layer3.tech_debt_report.get('estimated_fix_hours', 0),
                "refactoring_suggestions": len(report.layer3.refactoring_suggestions),
                "learning_path_steps": len(report.layer3.learning_path)
            }
            
            # Build success response
            response = {
                "success": True,
                "project_name": report.layer1.project_name,
                "generated_at": report.generated_at,
                "report_summary": {
                    "files": report.layer1.statistics.get('files', 0),
                    "lines": report.layer1.statistics.get('lines', 0),
                    "functions": report.layer1.statistics.get('functions', 0),
                    "health_score": report.layer3.health_score,
                    "tech_debt_hours": layer3_summary['tech_debt_hours']
                },
                "layer1_quick_overview": layer1_summary,
                "layer2_architecture": layer2_summary,
                "layer3_deep_insights": layer3_summary,
                "markdown_report": markdown_report,
                "error": None
            }
            
            if saved_file:
                response["output_file"] = saved_file
            
            return response
            
        except Exception as e:
            logger.error(f"Instant understanding failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Analysis failed: {str(e)}"
            }


class CompareProjectsTool(BaseTool):
    """
    MCP tool for comparing two projects.
    
    Generates side-by-side comparison of project metrics, complexity,
    tech debt, and other key indicators.
    """
    
    def __init__(self):
        """Initialize the compare projects tool."""
        pass
    
    def get_name(self) -> str:
        """Get tool name."""
        return "compare_projects"
    
    def get_description(self) -> str:
        """Get tool description."""
        return (
            "Compare two projects side-by-side. Analyzes both projects and generates "
            "a comparison report showing differences in size, complexity, tech debt, "
            "design patterns, and health scores."
        )
    
    def get_schema(self) -> dict[str, Any]:
        """Get JSON schema for tool arguments."""
        return {
            "type": "object",
            "properties": {
                "project_a": {
                    "type": "string",
                    "description": "Path to first project"
                },
                "project_b": {
                    "type": "string",
                    "description": "Path to second project"
                },
                "output_file": {
                    "type": "string",
                    "description": "Optional output file path for comparison report",
                    "default": None
                }
            },
            "required": ["project_a", "project_b"]
        }
    
    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the compare projects tool.
        
        Args:
            arguments: Tool arguments
        
        Returns:
            Comparison report
        """
        project_a_str = arguments.get("project_a", "")
        project_b_str = arguments.get("project_b", "")
        output_file = arguments.get("output_file")
        
        # Validate paths
        project_a = Path(project_a_str)
        project_b = Path(project_b_str)
        
        if not project_a.exists() or not project_a.is_dir():
            return {"success": False, "error": f"Invalid project A path: {project_a_str}"}
        
        if not project_b.exists() or not project_b.is_dir():
            return {"success": False, "error": f"Invalid project B path: {project_b_str}"}
        
        try:
            logger.info(f"Comparing {project_a.name} vs {project_b.name}")
            
            # Analyze both projects
            engine_a = InstantUnderstandingEngine(project_a)
            report_a = engine_a.analyze()
            
            engine_b = InstantUnderstandingEngine(project_b)
            report_b = engine_b.analyze()
            
            # Build comparison
            comparison = {
                "success": True,
                "project_a": {
                    "name": report_a.layer1.project_name,
                    "files": report_a.layer1.statistics.get('files', 0),
                    "lines": report_a.layer1.statistics.get('lines', 0),
                    "functions": report_a.layer1.statistics.get('functions', 0),
                    "health_score": report_a.layer3.health_score,
                    "tech_debt_hours": report_a.layer3.tech_debt_report.get('estimated_fix_hours', 0),
                    "hotspots": report_a.layer3.performance_analysis.get('total_hotspots', 0)
                },
                "project_b": {
                    "name": report_b.layer1.project_name,
                    "files": report_b.layer1.statistics.get('files', 0),
                    "lines": report_b.layer1.statistics.get('lines', 0),
                    "functions": report_b.layer1.statistics.get('functions', 0),
                    "health_score": report_b.layer3.health_score,
                    "tech_debt_hours": report_b.layer3.tech_debt_report.get('estimated_fix_hours', 0),
                    "hotspots": report_b.layer3.performance_analysis.get('total_hotspots', 0)
                },
                "differences": {
                    "files_delta": report_b.layer1.statistics.get('files', 0) - report_a.layer1.statistics.get('files', 0),
                    "lines_delta": report_b.layer1.statistics.get('lines', 0) - report_a.layer1.statistics.get('lines', 0),
                    "health_score_delta": report_b.layer3.health_score - report_a.layer3.health_score,
                    "tech_debt_delta_hours": report_b.layer3.tech_debt_report.get('estimated_fix_hours', 0) - report_a.layer3.tech_debt_report.get('estimated_fix_hours', 0)
                },
                "error": None
            }
            
            # Generate comparison markdown
            comparison_md = self._generate_comparison_markdown(comparison)
            comparison["markdown_report"] = comparison_md
            
            # Save if requested
            if output_file:
                Path(output_file).write_text(comparison_md, encoding='utf-8')
                comparison["output_file"] = output_file
                logger.info(f"Comparison saved to {output_file}")
            
            return comparison
            
        except Exception as e:
            logger.error(f"Comparison failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Comparison failed: {str(e)}"
            }
    
    def _generate_comparison_markdown(self, comparison: dict) -> str:
        """Generate markdown comparison report."""
        lines = [
            "# Project Comparison Report\n",
            f"## {comparison['project_a']['name']} vs {comparison['project_b']['name']}\n",
            "### Size Comparison\n",
            f"| Metric | {comparison['project_a']['name']} | {comparison['project_b']['name']} | Delta |",
            "|--------|---------|---------|-------|",
            f"| Files | {comparison['project_a']['files']} | {comparison['project_b']['files']} | {comparison['differences']['files_delta']:+d} |",
            f"| Lines | {comparison['project_a']['lines']} | {comparison['project_b']['lines']} | {comparison['differences']['lines_delta']:+d} |",
            f"| Functions | {comparison['project_a']['functions']} | {comparison['project_b']['functions']} | N/A |",
            "",
            "### Quality Comparison\n",
            f"| Metric | {comparison['project_a']['name']} | {comparison['project_b']['name']} | Delta |",
            "|--------|---------|---------|-------|",
            f"| Health Score | {comparison['project_a']['health_score']:.1f} | {comparison['project_b']['health_score']:.1f} | {comparison['differences']['health_score_delta']:+.1f} |",
            f"| Tech Debt (hours) | {comparison['project_a']['tech_debt_hours']:.1f} | {comparison['project_b']['tech_debt_hours']:.1f} | {comparison['differences']['tech_debt_delta_hours']:+.1f} |",
            f"| Performance Hotspots | {comparison['project_a']['hotspots']} | {comparison['project_b']['hotspots']} | N/A |",
        ]
        
        return "\n".join(lines)
