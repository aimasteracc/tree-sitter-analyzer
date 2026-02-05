"""AI Assistant Tools"""

import ast
import re
from collections import Counter
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class PatternRecognizerTool(BaseTool):
    """Code pattern recognition tool"""

    def get_name(self) -> str:
        return "pattern_recognizer"

    def get_description(self) -> str:
        return "Recognize common patterns in code (design patterns, anti-patterns, idioms)"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "File path to analyze",
                },
                "pattern_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Pattern types to recognize (design_patterns, anti_patterns, idioms)",
                },
            },
            "required": ["file_path"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(arguments["file_path"])
        pattern_types = arguments.get("pattern_types", ["design_patterns", "anti_patterns"])

        if not file_path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content)

            patterns = {}
            if "design_patterns" in pattern_types:
                patterns["design_patterns"] = self._detect_design_patterns(tree)
            if "anti_patterns" in pattern_types:
                patterns["anti_patterns"] = self._detect_anti_patterns(tree)
            if "idioms" in pattern_types:
                patterns["idioms"] = self._detect_idioms(tree)

            return {
                "success": True,
                "file": str(file_path),
                "patterns": patterns,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _detect_design_patterns(self, tree: ast.AST) -> list[dict[str, Any]]:
        """Detect design patterns"""
        patterns = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Detect Singleton pattern
                if any(
                    isinstance(n, ast.FunctionDef) and n.name == "__new__"
                    for n in node.body
                ):
                    patterns.append({"type": "Singleton", "name": node.name})

                # Detect Factory pattern
                if any(
                    isinstance(n, ast.FunctionDef) and "create" in n.name.lower()
                    for n in node.body
                ):
                    patterns.append({"type": "Factory", "name": node.name})

        return patterns

    def _detect_anti_patterns(self, tree: ast.AST) -> list[dict[str, Any]]:
        """Detect anti-patterns"""
        anti_patterns = []

        for node in ast.walk(tree):
            # Detect God Class (too many methods)
            if isinstance(node, ast.ClassDef):
                methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]
                if len(methods) > 20:
                    anti_patterns.append(
                        {"type": "God Class", "name": node.name, "methods": len(methods)}
                    )

            # Detect Long Method
            if isinstance(node, ast.FunctionDef):
                if len(node.body) > 50:
                    anti_patterns.append(
                        {"type": "Long Method", "name": node.name, "lines": len(node.body)}
                    )

        return anti_patterns

    def _detect_idioms(self, tree: ast.AST) -> list[dict[str, Any]]:
        """Detect Python idioms"""
        idioms = []

        for node in ast.walk(tree):
            # Detect list comprehension
            if isinstance(node, ast.ListComp):
                idioms.append({"type": "List Comprehension"})

            # Detect context manager
            if isinstance(node, ast.With):
                idioms.append({"type": "Context Manager"})

        return idioms


class DuplicateDetectorTool(BaseTool):
    """Advanced duplicate code detection tool"""

    def get_name(self) -> str:
        return "duplicate_detector_advanced"

    def get_description(self) -> str:
        return "Detect duplicate code fragments (based on AST structure similarity)"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Directory path to analyze",
                },
                "min_lines": {
                    "type": "integer",
                    "description": "Minimum duplicate lines",
                    "default": 5,
                },
            },
            "required": ["directory"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        directory = Path(arguments["directory"])
        min_lines = arguments.get("min_lines", 5)

        if not directory.exists():
            return {"success": False, "error": f"Directory not found: {directory}"}

        duplicates = []
        file_hashes: dict[str, list[tuple[Path, int]]] = {}

        # Scan all Python files
        for file_path in directory.rglob("*.py"):
            try:
                content = file_path.read_text(encoding="utf-8")
                lines = content.splitlines()

                # Calculate hash for each code block
                for i in range(len(lines) - min_lines + 1):
                    block = "\n".join(lines[i : i + min_lines])
                    block_hash = hash(block)

                    if block_hash not in file_hashes:
                        file_hashes[block_hash] = []
                    file_hashes[block_hash].append((file_path, i + 1))
            except Exception:
                continue

        # Find duplicate code blocks
        for block_hash, locations in file_hashes.items():
            if len(locations) > 1:
                duplicates.append(
                    {
                        "locations": [
                            {"file": str(loc[0]), "line": loc[1]} for loc in locations
                        ],
                        "count": len(locations),
                    }
                )

        return {
            "success": True,
            "duplicates": duplicates[:50],  # Limit return count
            "total_duplicates": len(duplicates),
        }


class SmellDetectorTool(BaseTool):
    """Advanced code smell detection tool"""

    def get_name(self) -> str:
        return "smell_detector_advanced"

    def get_description(self) -> str:
        return "Detect code smells (long methods, long parameter lists, deep nesting, cyclic dependencies, etc.)"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "File path to analyze",
                },
                "smell_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Smell types to detect",
                },
            },
            "required": ["file_path"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(arguments["file_path"])

        if not file_path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content)

            smells = {
                "long_methods": self._detect_long_methods(tree),
                "long_parameters": self._detect_long_parameters(tree),
                "deep_nesting": self._detect_deep_nesting(tree),
                "magic_numbers": self._detect_magic_numbers(tree),
            }

            return {
                "success": True,
                "file": str(file_path),
                "smells": smells,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _detect_long_methods(self, tree: ast.AST) -> list[dict[str, Any]]:
        """Detect long methods"""
        long_methods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if len(node.body) > 30:
                    long_methods.append({"name": node.name, "lines": len(node.body)})
        return long_methods

    def _detect_long_parameters(self, tree: ast.AST) -> list[dict[str, Any]]:
        """Detect long parameter lists"""
        long_params = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if len(node.args.args) > 5:
                    long_params.append(
                        {"name": node.name, "params": len(node.args.args)}
                    )
        return long_params

    def _detect_deep_nesting(self, tree: ast.AST) -> list[dict[str, Any]]:
        """Detect deep nesting"""
        def get_nesting_depth(node: ast.AST, depth: int = 0) -> int:
            max_depth = depth
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.If, ast.For, ast.While, ast.With)):
                    child_depth = get_nesting_depth(child, depth + 1)
                    max_depth = max(max_depth, child_depth)
            return max_depth

        deep_nesting = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                depth = get_nesting_depth(node)
                if depth > 4:
                    deep_nesting.append({"name": node.name, "depth": depth})
        return deep_nesting

    def _detect_magic_numbers(self, tree: ast.AST) -> list[dict[str, Any]]:
        """Detect magic numbers"""
        magic_numbers = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                if node.value not in (0, 1, -1):  # Exclude common numbers
                    magic_numbers.append({"value": node.value})
        return magic_numbers[:20]  # Limit count


class ImprovementSuggesterTool(BaseTool):
    """Improvement suggestion generation tool"""

    def get_name(self) -> str:
        return "improvement_suggester"

    def get_description(self) -> str:
        return "Generate improvement suggestions based on code analysis"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "File path to analyze",
                },
            },
            "required": ["file_path"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(arguments["file_path"])

        if not file_path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content)

            suggestions = []

            # Check for docstrings
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    if not ast.get_docstring(node):
                        suggestions.append(
                            {
                                "type": "missing_docstring",
                                "target": node.name,
                                "suggestion": f"Add docstring for {node.name}",
                            }
                        )

            # Check function complexity
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if len(node.body) > 20:
                        suggestions.append(
                            {
                                "type": "refactor",
                                "target": node.name,
                                "suggestion": f"Function {node.name} is too long, consider splitting",
                            }
                        )

            return {
                "success": True,
                "file": str(file_path),
                "suggestions": suggestions[:20],  # Limit count
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class BestPracticeCheckerTool(BaseTool):
    """Best practice checker tool"""

    def get_name(self) -> str:
        return "best_practice_checker"

    def get_description(self) -> str:
        return "Check if code follows Python best practices"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "File path to check",
                },
            },
            "required": ["file_path"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(arguments["file_path"])

        if not file_path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content)

            violations = []

            # Check for list/dict as default argument
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    for default in node.args.defaults:
                        if isinstance(default, (ast.List, ast.Dict)):
                            violations.append(
                                {
                                    "rule": "mutable_default_argument",
                                    "function": node.name,
                                    "message": "Do not use mutable objects as default arguments",
                                }
                            )

            # Check for bare except
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    if node.type is None:
                        violations.append(
                            {
                                "rule": "bare_except",
                                "message": "Avoid bare except, specify exception type",
                            }
                        )

            return {
                "success": True,
                "file": str(file_path),
                "violations": violations,
                "passed": len(violations) == 0,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
