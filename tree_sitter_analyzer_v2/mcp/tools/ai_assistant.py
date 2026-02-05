"""AI 辅助工具"""

import ast
import re
from collections import Counter
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class PatternRecognizerTool(BaseTool):
    """代码模式识别工具"""

    def get_name(self) -> str:
        return "pattern_recognizer"

    def get_description(self) -> str:
        return "识别代码中的常见模式（设计模式、反模式等）"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要分析的文件路径",
                },
                "pattern_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要识别的模式类型（design_patterns, anti_patterns, idioms）",
                },
            },
            "required": ["file_path"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(arguments["file_path"])
        pattern_types = arguments.get("pattern_types", ["design_patterns", "anti_patterns"])

        if not file_path.exists():
            return {"success": False, "error": f"文件不存在: {file_path}"}

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
        """检测设计模式"""
        patterns = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # 检测单例模式
                if any(
                    isinstance(n, ast.FunctionDef) and n.name == "__new__"
                    for n in node.body
                ):
                    patterns.append({"type": "Singleton", "name": node.name})

                # 检测工厂模式
                if any(
                    isinstance(n, ast.FunctionDef) and "create" in n.name.lower()
                    for n in node.body
                ):
                    patterns.append({"type": "Factory", "name": node.name})

        return patterns

    def _detect_anti_patterns(self, tree: ast.AST) -> list[dict[str, Any]]:
        """检测反模式"""
        anti_patterns = []

        for node in ast.walk(tree):
            # 检测上帝类（方法过多）
            if isinstance(node, ast.ClassDef):
                methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]
                if len(methods) > 20:
                    anti_patterns.append(
                        {"type": "God Class", "name": node.name, "methods": len(methods)}
                    )

            # 检测长方法
            if isinstance(node, ast.FunctionDef):
                if len(node.body) > 50:
                    anti_patterns.append(
                        {"type": "Long Method", "name": node.name, "lines": len(node.body)}
                    )

        return anti_patterns

    def _detect_idioms(self, tree: ast.AST) -> list[dict[str, Any]]:
        """检测 Python 惯用法"""
        idioms = []

        for node in ast.walk(tree):
            # 检测列表推导式
            if isinstance(node, ast.ListComp):
                idioms.append({"type": "List Comprehension"})

            # 检测上下文管理器
            if isinstance(node, ast.With):
                idioms.append({"type": "Context Manager"})

        return idioms


class DuplicateDetectorTool(BaseTool):
    """高级重复代码检测工具"""

    def get_name(self) -> str:
        return "duplicate_detector_advanced"

    def get_description(self) -> str:
        return "检测代码中的重复片段（基于 AST 结构相似性）"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "要分析的目录路径",
                },
                "min_lines": {
                    "type": "integer",
                    "description": "最小重复行数",
                    "default": 5,
                },
            },
            "required": ["directory"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        directory = Path(arguments["directory"])
        min_lines = arguments.get("min_lines", 5)

        if not directory.exists():
            return {"success": False, "error": f"目录不存在: {directory}"}

        duplicates = []
        file_hashes: dict[str, list[tuple[Path, int]]] = {}

        # 扫描所有 Python 文件
        for file_path in directory.rglob("*.py"):
            try:
                content = file_path.read_text(encoding="utf-8")
                lines = content.splitlines()

                # 计算每个代码块的哈希
                for i in range(len(lines) - min_lines + 1):
                    block = "\n".join(lines[i : i + min_lines])
                    block_hash = hash(block)

                    if block_hash not in file_hashes:
                        file_hashes[block_hash] = []
                    file_hashes[block_hash].append((file_path, i + 1))
            except Exception:
                continue

        # 找出重复的代码块
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
            "duplicates": duplicates[:50],  # 限制返回数量
            "total_duplicates": len(duplicates),
        }


class SmellDetectorTool(BaseTool):
    """高级代码异味检测工具"""

    def get_name(self) -> str:
        return "smell_detector_advanced"

    def get_description(self) -> str:
        return "检测代码异味（长方法、长参数列表、深度嵌套、循环依赖等）"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要分析的文件路径",
                },
                "smell_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要检测的异味类型",
                },
            },
            "required": ["file_path"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(arguments["file_path"])

        if not file_path.exists():
            return {"success": False, "error": f"文件不存在: {file_path}"}

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
        """检测长方法"""
        long_methods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if len(node.body) > 30:
                    long_methods.append({"name": node.name, "lines": len(node.body)})
        return long_methods

    def _detect_long_parameters(self, tree: ast.AST) -> list[dict[str, Any]]:
        """检测长参数列表"""
        long_params = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if len(node.args.args) > 5:
                    long_params.append(
                        {"name": node.name, "params": len(node.args.args)}
                    )
        return long_params

    def _detect_deep_nesting(self, tree: ast.AST) -> list[dict[str, Any]]:
        """检测深度嵌套"""
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
        """检测魔法数字"""
        magic_numbers = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                if node.value not in (0, 1, -1):  # 排除常见的数字
                    magic_numbers.append({"value": node.value})
        return magic_numbers[:20]  # 限制数量


class ImprovementSuggesterTool(BaseTool):
    """改进建议生成工具"""

    def get_name(self) -> str:
        return "improvement_suggester"

    def get_description(self) -> str:
        return "基于代码分析生成改进建议"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要分析的文件路径",
                },
            },
            "required": ["file_path"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(arguments["file_path"])

        if not file_path.exists():
            return {"success": False, "error": f"文件不存在: {file_path}"}

        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content)

            suggestions = []

            # 检查是否有文档字符串
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    if not ast.get_docstring(node):
                        suggestions.append(
                            {
                                "type": "missing_docstring",
                                "target": node.name,
                                "suggestion": f"为 {node.name} 添加文档字符串",
                            }
                        )

            # 检查函数复杂度
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if len(node.body) > 20:
                        suggestions.append(
                            {
                                "type": "refactor",
                                "target": node.name,
                                "suggestion": f"函数 {node.name} 过长，考虑拆分",
                            }
                        )

            return {
                "success": True,
                "file": str(file_path),
                "suggestions": suggestions[:20],  # 限制数量
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class BestPracticeCheckerTool(BaseTool):
    """最佳实践检查工具"""

    def get_name(self) -> str:
        return "best_practice_checker"

    def get_description(self) -> str:
        return "检查代码是否符合 Python 最佳实践"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要检查的文件路径",
                },
            },
            "required": ["file_path"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(arguments["file_path"])

        if not file_path.exists():
            return {"success": False, "error": f"文件不存在: {file_path}"}

        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content)

            violations = []

            # 检查是否使用 list/dict 作为默认参数
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    for default in node.args.defaults:
                        if isinstance(default, (ast.List, ast.Dict)):
                            violations.append(
                                {
                                    "rule": "mutable_default_argument",
                                    "function": node.name,
                                    "message": "不要使用可变对象作为默认参数",
                                }
                            )

            # 检查是否使用 bare except
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    if node.type is None:
                        violations.append(
                            {
                                "rule": "bare_except",
                                "message": "避免使用裸 except，应指定具体异常类型",
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
