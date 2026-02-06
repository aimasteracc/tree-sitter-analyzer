"""
Mermaid Diagram Generator

Generates various types of Mermaid diagrams for code visualization:
1. Architecture Overview - Module dependencies
2. Call Graph - Function call relationships
3. Performance Heatmap - Hotspot visualization
4. Test Coverage Map - Coverage overlay
5. Dependency Health - Cycle detection
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class MermaidGenerator:
    """
    Generates Mermaid diagrams for code visualization.
    
    Supports 5 diagram types without requiring AI:
    - Architecture overview
    - Call graph
    - Performance heatmap
    - Test coverage map
    - Dependency health
    """
    
    @staticmethod
    def generate_architecture_diagram(
        modules: Dict[str, Any],
        entry_points: List[str],
        has_cli: bool = False,
        has_api: bool = False,
        has_mcp: bool = False
    ) -> str:
        """
        Generate architecture overview diagram.
        
        Args:
            modules: Module structure dictionary
            entry_points: List of entry point files
            has_cli: Has CLI module
            has_api: Has API module
            has_mcp: Has MCP server
            
        Returns:
            Mermaid diagram code
        """
        lines = ["graph TD"]
        nodes_added = set()
        
        # Add entry points
        if has_cli:
            lines.append("    CLI[CLI Entry] --> Core[Core Module]")
            nodes_added.add("CLI")
            nodes_added.add("Core")
        
        if has_api:
            lines.append("    API[API Layer] --> Core")
            nodes_added.add("API")
            nodes_added.add("Core")
        
        if has_mcp:
            lines.append("    MCP[MCP Server] --> Tools[Analysis Tools]")
            lines.append("    Tools --> Core")
            nodes_added.add("MCP")
            nodes_added.add("Tools")
            nodes_added.add("Core")
        
        # Add feature modules
        if "features" in str(modules):
            if "Core" not in nodes_added:
                lines.append("    Core[Core Module]")
                nodes_added.add("Core")
            lines.append("    Core --> Features[Feature Modules]")
            nodes_added.add("Features")
        
        # Add utilities
        if "utils" in str(modules):
            if "Core" not in nodes_added:
                lines.append("    Core[Core Module]")
                nodes_added.add("Core")
            lines.append("    Core --> Utils[Utilities]")
            nodes_added.add("Utils")
        
        # If nothing was added, create a basic structure
        if len(nodes_added) == 0:
            lines.append("    Root[Project Root]")
        
        return "\n".join(lines)
    
    @staticmethod
    def generate_call_graph_diagram(
        hotspots: List[Dict[str, Any]],
        max_nodes: int = 15
    ) -> str:
        """
        Generate call graph diagram showing function relationships.
        
        Args:
            hotspots: List of function hotspots with call information
            max_nodes: Maximum nodes to display
            
        Returns:
            Mermaid diagram code
        """
        lines = ["graph LR"]
        
        # Sort by impact and take top N
        sorted_hotspots = sorted(
            hotspots,
            key=lambda x: x.get('impact_score', 0),
            reverse=True
        )[:max_nodes]
        
        node_ids = {}
        node_counter = 0
        
        for hotspot in sorted_hotspots:
            func_name = hotspot.get('function', 'unknown')
            called_by = hotspot.get('called_by_count', 0)
            calls = hotspot.get('calls_count', 0)
            
            # Create sanitized node ID
            if func_name not in node_ids:
                node_ids[func_name] = f"F{node_counter}"
                node_counter += 1
            
            node_id = node_ids[func_name]
            
            # Add node with label
            impact = hotspot.get('impact_level', 'low')
            style_class = "critical" if impact == "high" else "normal"
            
            # Truncate long function names
            display_name = func_name[:40] + "..." if len(func_name) > 40 else func_name
            lines.append(f"    {node_id}[\"{display_name}\"]")
            
            # Add styling based on impact
            if impact == "high":
                lines.append(f"    style {node_id} fill:#ff6b6b")
            elif impact == "medium":
                lines.append(f"    style {node_id} fill:#ffd93d")
            
            # Show callers
            if called_by > 0:
                caller_id = f"Callers{node_counter}"
                lines.append(f"    {caller_id}[{called_by} callers] --> {node_id}")
                node_counter += 1
            
            # Show calls
            if calls > 0:
                called_id = f"Called{node_counter}"
                lines.append(f"    {node_id} --> {called_id}[calls {calls} functions]")
                node_counter += 1
        
        return "\n".join(lines)
    
    @staticmethod
    def generate_heatmap_diagram(
        performance_hotspots: List[Any],
        max_functions: int = 10
    ) -> str:
        """
        Generate performance heatmap diagram.
        
        Args:
            performance_hotspots: List of PerformanceHotspot objects
            max_functions: Maximum functions to display
            
        Returns:
            Mermaid diagram code
        """
        lines = ["graph TD"]
        lines.append("    subgraph PerformanceHotspots[\"Performance Hotspots\"]")
        
        # Sort by hotspot score
        sorted_hotspots = sorted(
            performance_hotspots,
            key=lambda x: x.hotspot_score,
            reverse=True
        )[:max_functions]
        
        for i, hotspot in enumerate(sorted_hotspots):
            # Sanitize function name for Mermaid
            func_name = hotspot.function.replace(".", "_").replace(":", "_").replace("(", "").replace(")", "")
            display_name = hotspot.function[:30]
            
            node_id = f"H{i}"
            complexity = hotspot.complexity
            score = hotspot.hotspot_score
            
            # Create node with info
            lines.append(f"        {node_id}[\"{display_name}\\nComplexity: {complexity}\\nScore: {score:.1f}\"]")
            
            # Color based on score
            if score > 80:
                lines.append(f"        style {node_id} fill:#ff4757,color:#fff")
            elif score > 50:
                lines.append(f"        style {node_id} fill:#ffa502,color:#fff")
            else:
                lines.append(f"        style {node_id} fill:#ffd93d")
        
        lines.append("    end")
        
        return "\n".join(lines)
    
    @staticmethod
    def generate_coverage_map(
        coverage_data: Dict[str, float],
        modules: List[str]
    ) -> str:
        """
        Generate test coverage map diagram.
        
        Args:
            coverage_data: Dict mapping file/module to coverage percentage
            modules: List of module names
            
        Returns:
            Mermaid diagram code
        """
        lines = ["graph TD"]
        lines.append("    subgraph CoverageMap[\"Test Coverage Map\"]")
        
        for i, module in enumerate(modules[:15]):
            coverage = coverage_data.get(module, 0.0)
            node_id = f"M{i}"
            
            # Display module and coverage
            display_name = module.replace("/", "_").replace("\\", "_")[:30]
            lines.append(f"        {node_id}[\"{display_name}\\n{coverage:.0f}%\"]")
            
            # Color based on coverage
            if coverage >= 80:
                lines.append(f"        style {node_id} fill:#2ed573,color:#fff")
            elif coverage >= 50:
                lines.append(f"        style {node_id} fill:#ffa502")
            else:
                lines.append(f"        style {node_id} fill:#ff4757,color:#fff")
        
        lines.append("    end")
        
        return "\n".join(lines)
    
    @staticmethod
    def generate_dependency_health_diagram(
        dependencies: Dict[str, List[str]],
        cycles: List[List[str]]
    ) -> str:
        """
        Generate dependency health diagram showing cycles and coupling.
        
        Args:
            dependencies: Dict mapping module to its dependencies
            cycles: List of detected dependency cycles
            
        Returns:
            Mermaid diagram code
        """
        lines = ["graph TD"]
        
        # Add main dependencies
        node_ids = {}
        node_counter = 0
        
        for module, deps in list(dependencies.items())[:20]:
            if module not in node_ids:
                node_ids[module] = f"M{node_counter}"
                node_counter += 1
            
            module_id = node_ids[module]
            module_display = module.replace("/", "_").replace("\\", "_")[:25]
            lines.append(f"    {module_id}[\"{module_display}\"]")
            
            for dep in deps[:3]:  # Limit to top 3 dependencies
                if dep not in node_ids:
                    node_ids[dep] = f"M{node_counter}"
                    node_counter += 1
                
                dep_id = node_ids[dep]
                dep_display = dep.replace("/", "_").replace("\\", "_")[:25]
                
                if dep_id not in [line.split("[")[0].strip() for line in lines if "[" in line]:
                    lines.append(f"    {dep_id}[\"{dep_display}\"]")
                
                lines.append(f"    {module_id} --> {dep_id}")
        
        # Highlight cycles
        if cycles:
            lines.append("\n    subgraph Cycles[\"Dependency Cycles Detected\"]")
            for cycle_idx, cycle in enumerate(cycles[:3]):
                for module in cycle:
                    if module in node_ids:
                        module_id = node_ids[module]
                        lines.append(f"        style {module_id} fill:#ff6b6b,color:#fff")
            lines.append("    end")
        
        return "\n".join(lines)
    
    @staticmethod
    def generate_evolution_timeline(
        snapshots: List[Dict[str, Any]]
    ) -> str:
        """
        Generate project evolution timeline.
        
        Args:
            snapshots: List of project snapshots over time
            
        Returns:
            Mermaid diagram code
        """
        lines = ["graph LR"]
        
        for i, snapshot in enumerate(snapshots):
            node_id = f"V{i}"
            date = snapshot.get('date', f'Snapshot {i}')
            files = snapshot.get('files', 0)
            functions = snapshot.get('functions', 0)
            
            lines.append(f"    {node_id}[\"{date}\\n{files} files\\n{functions} functions\"]")
            
            if i > 0:
                prev_id = f"V{i-1}"
                lines.append(f"    {prev_id} --> {node_id}")
        
        return "\n".join(lines)
    
    @staticmethod
    def generate_learning_path_diagram(
        learning_path: List[str]
    ) -> str:
        """
        Generate recommended learning path diagram.
        
        Args:
            learning_path: Ordered list of files/modules to read
            
        Returns:
            Mermaid diagram code
        """
        lines = ["graph TD"]
        lines.append("    Start[Start Here] --> Step1")
        
        for i, step in enumerate(learning_path[:10], 1):
            node_id = f"Step{i}"
            
            # Extract file name
            if " - " in step:
                parts = step.split(" - ", 1)
                file_name = parts[0].strip()
                description = parts[1].strip() if len(parts) > 1 else ""
            else:
                file_name = step
                description = ""
            
            # Truncate long names
            display_name = file_name[:30]
            if description:
                display_name += f"\\n({description[:20]})"
            
            lines.append(f"    {node_id}[\"{display_name}\"]")
            
            # Link to next step
            if i < len(learning_path):
                next_id = f"Step{i+1}"
                lines.append(f"    {node_id} --> {next_id}")
        
        return "\n".join(lines)
    
    @staticmethod
    def generate_tech_debt_breakdown(
        tech_debts: List[Any]
    ) -> str:
        """
        Generate tech debt breakdown diagram.
        
        Args:
            tech_debts: List of TechDebt objects
            
        Returns:
            Mermaid diagram code
        """
        lines = ["graph TD"]
        lines.append("    Root[Technical Debt]")
        
        # Group by severity
        by_severity = {'high': [], 'medium': [], 'low': []}
        for debt in tech_debts:
            by_severity.get(debt.severity, []).append(debt)
        
        # Add severity nodes
        if by_severity['high']:
            lines.append("    Root --> High[High Severity]")
            lines.append(f"    style High fill:#ff4757,color:#fff")
            lines.append(f"    High --> HighCount[\"{len(by_severity['high'])} items\"]")
        
        if by_severity['medium']:
            lines.append("    Root --> Medium[Medium Severity]")
            lines.append(f"    style Medium fill:#ffa502")
            lines.append(f"    Medium --> MediumCount[\"{len(by_severity['medium'])} items\"]")
        
        if by_severity['low']:
            lines.append("    Root --> Low[Low Severity]")
            lines.append(f"    style Low fill:#ffd93d")
            lines.append(f"    Low --> LowCount[\"{len(by_severity['low'])} items\"]")
        
        return "\n".join(lines)
    
    @staticmethod
    def generate_comparison_diagram(
        project_a: Dict[str, Any],
        project_b: Dict[str, Any]
    ) -> str:
        """
        Generate comparison diagram between two projects.
        
        Args:
            project_a: First project stats
            project_b: Second project stats
            
        Returns:
            Mermaid diagram code
        """
        lines = ["graph LR"]
        
        name_a = project_a.get('name', 'Project A')
        name_b = project_b.get('name', 'Project B')
        
        lines.append(f"    A[\"{name_a}\\n{project_a.get('files', 0)} files\\n{project_a.get('functions', 0)} functions\"]")
        lines.append(f"    B[\"{name_b}\\n{project_b.get('files', 0)} files\\n{project_b.get('functions', 0)} functions\"]")
        
        lines.append("    A -.Comparison.- B")
        
        # Add metrics comparison
        lines.append(f"    A --> MetricsA[\"Complexity: {project_a.get('complexity', 0)}\\nDebt: {project_a.get('debt', 0)}\"]")
        lines.append(f"    B --> MetricsB[\"Complexity: {project_b.get('complexity', 0)}\\nDebt: {project_b.get('debt', 0)}\"]")
        
        return "\n".join(lines)


# Convenience functions
def quick_architecture(project_path: Path) -> str:
    """
    Quick architecture diagram generation.
    
    Args:
        project_path: Path to project
        
    Returns:
        Mermaid diagram code
    """
    has_cli = (project_path / "cli").exists()
    has_api = (project_path / "api").exists()
    has_mcp = (project_path / "mcp").exists()
    
    return MermaidGenerator.generate_architecture_diagram(
        modules={},
        entry_points=[],
        has_cli=has_cli,
        has_api=has_api,
        has_mcp=has_mcp
    )


def quick_heatmap(performance_hotspots: List[Any]) -> str:
    """
    Quick performance heatmap generation.
    
    Args:
        performance_hotspots: List of PerformanceHotspot objects
        
    Returns:
        Mermaid diagram code
    """
    return MermaidGenerator.generate_heatmap_diagram(performance_hotspots)


def quick_call_graph(hotspots: List[Dict[str, Any]]) -> str:
    """
    Quick call graph generation.
    
    Args:
        hotspots: List of function hotspots
        
    Returns:
        Mermaid diagram code
    """
    return MermaidGenerator.generate_call_graph_diagram(hotspots)
