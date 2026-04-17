#!/usr/bin/env python3
"""
Understand Codebase Tool - 智能代码库理解入口

This is the "one entry point" for codebase understanding.
It orchestrates multiple analysis tools to provide a complete picture.

设计原则 (乔布斯认可的产品):
- 一个工具理解整个代码库
- 三种深度级别：quick（5秒）、standard（15秒）、deep（30秒）
- 默认 TOON 输出（token 优化）
"""

from pathlib import Path
from typing import Any, TypedDict

from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool

# Set up logging
logger = setup_logger(__name__)


class FileMetric(TypedDict):
    """File metric data."""
    file: str
    lines: int


class UnderstandCodebaseTool(BaseMCPTool):
    """
    智能代码库理解工具 - 乔布斯认可的产品入口

    One tool to understand everything. No friction.

    depth 参数控制分析深度：
    - quick: 代码概览（文件数、语言分布）
    - standard: 完整理解（概览 + 文件采样分析）
    - deep: 全部分析（更多采样文件 + 详细分析）
    """

    # 分析深度定义
    DEPTH_QUICK = "quick"
    DEPTH_STANDARD = "standard"
    DEPTH_DEEP = "deep"

    # 支持的深度级别
    DEPTHS = [DEPTH_QUICK, DEPTH_STANDARD, DEPTH_DEEP]

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize the understand codebase tool."""
        super().__init__(project_root)
        logger.info("UnderstandCodebaseTool initialized")

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """
        Validate tool arguments.

        Args:
            arguments: Arguments to validate

        Returns:
            True if arguments are valid

        Raises:
            ValueError: If arguments are invalid
        """
        project_root = arguments.get("project_root")
        if not project_root:
            raise ValueError("project_root is required")

        depth = arguments.get("depth", self.DEPTH_STANDARD)
        if depth not in self.DEPTHS:
            raise ValueError(f"Invalid depth '{depth}'. Must be one of: {self.DEPTHS}")

        file_patterns = arguments.get("file_patterns", [])
        if file_patterns and not isinstance(file_patterns, list):
            raise ValueError("file_patterns must be an array")

        max_files = arguments.get("max_files", 100)
        if not isinstance(max_files, int) or max_files <= 0:
            raise ValueError("max_files must be a positive integer")

        output_format = arguments.get("output_format", "toon")
        if output_format not in ["toon", "json"]:
            raise ValueError("output_format must be 'toon' or 'json'")

        return True

    def get_tool_definition(self) -> dict[str, Any]:
        """Get MCP tool definition."""
        return {
            "name": "understand_codebase",
            "description": (
                "理解代码库 - 一个工具获取完整图景。"
                "输入代码库路径，返回结构化理解：文件概览、语言分布、基本健康度。"
                "支持 17 种语言，自动检测。Token 优化（TOON 格式节省 50-70%）。"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_root": {
                        "type": "string",
                        "description": "代码库根目录路径",
                    },
                    "depth": {
                        "type": "string",
                        "enum": ["quick", "standard", "deep"],
                        "description": (
                            "分析深度：quick（5秒概览）、standard（15秒完整）、deep（30秒详细）"
                        ),
                        "default": "standard",
                    },
                    "file_patterns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "文件包含模式（如 ['**/*.py', '**/*.js']），默认自动检测",
                        "default": [],
                    },
                    "max_files": {
                        "type": "integer",
                        "description": "最大分析文件数（大代码库限制范围）",
                        "default": 100,
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["toon", "json"],
                        "description": "输出格式（默认 toon，token 优化）",
                        "default": "toon",
                    },
                },
                "required": ["project_root"],
                "additionalProperties": False,
            },
        }

    @handle_mcp_errors("understand_codebase")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        执行代码库理解分析

        Args:
            arguments: 包含 project_root 和可选参数

        Returns:
            结构化代码库理解结果
        """
        # 验证参数
        self.validate_arguments(arguments)

        # 解析参数
        project_root = arguments.get("project_root")
        assert project_root is not None  # validate_arguments ensures this
        depth = arguments.get("depth", self.DEPTH_STANDARD)
        file_patterns = arguments.get("file_patterns", [])
        max_files = arguments.get("max_files", 100)
        output_format = arguments.get("output_format", "toon")

        project_path = Path(project_root)
        if not project_path.exists():
            raise ValueError(f"Project root does not exist: {project_root}")

        logger.info(f"Understanding codebase: {project_root} (depth: {depth})")

        # 收集所有源文件
        source_files = await self._collect_source_files(
            project_path, file_patterns, max_files
        )

        if not source_files:
            raise ValueError(f"No source files found in {project_root}")

        logger.info(f"Found {len(source_files)} source files to analyze")

        # 根据 depth 执行分析
        result = await self._analyze_codebase(
            project_path, source_files, depth
        )

        # 应用 TOON 格式
        return apply_toon_format_to_response(result, output_format)

    async def _collect_source_files(
        self,
        project_path: Path,
        file_patterns: list[str],
        max_files: int,
    ) -> list[Path]:
        """
        收集源代码文件

        Args:
            project_path: 项目根目录
            file_patterns: 文件模式（如果为空则自动检测）
            max_files: 最大文件数

        Returns:
            源文件路径列表
        """
        # 支持的语言扩展名
        language_extensions = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".jsx": "javascript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".c": "c",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".cs": "csharp",
            ".php": "php",
            ".rb": "ruby",
            ".kt": "kotlin",
            ".swift": "swift",
            ".sql": "sql",
            ".sh": "bash",
        }

        # 如果没有提供模式，使用所有支持的语言
        if not file_patterns:
            file_patterns = [f"**{ext}" for ext in language_extensions.keys()]

        # 收集文件
        source_files = []
        for pattern in file_patterns:
            try:
                # Normalize pattern for rglob
                # rglob does recursive search, so "**/*.py" -> "*.py"
                glob_pattern = pattern.removeprefix("**/")
                matches = list(project_path.rglob(glob_pattern))
                source_files.extend([f for f in matches if f.is_file()])
            except Exception as e:
                logger.warning(f"Failed to glob pattern '{pattern}': {e}")

        # 去重并限制数量
        seen = set()
        unique_files = []
        for f in source_files:
            if str(f) not in seen:
                seen.add(str(f))
                unique_files.append(f)
                if len(unique_files) >= max_files:
                    break

        return unique_files

    async def _analyze_codebase(
        self,
        project_path: Path,
        source_files: list[Path],
        depth: str,
    ) -> dict[str, Any]:
        """
        分析代码库（核心逻辑）

        Args:
            project_path: 项目根目录
            source_files: 源文件列表
            depth: 分析深度

        Returns:
            分析结果
        """
        result: dict[str, Any] = {
            "project_root": str(project_path),
            "depth": depth,
            "files_analyzed": len(source_files),
        }

        if depth == self.DEPTH_QUICK:
            # Quick: 概览
            result.update(await self._quick_analysis(project_path, source_files))
        elif depth == self.DEPTH_STANDARD:
            # Standard: 概览 + 采样分析
            result.update(await self._standard_analysis(project_path, source_files))
        elif depth == self.DEPTH_DEEP:
            # Deep: 更多采样 + 详细分析
            result.update(await self._deep_analysis(project_path, source_files))

        return result

    async def _quick_analysis(
        self,
        project_path: Path,
        source_files: list[Path],
    ) -> dict[str, Any]:
        """
        快速分析（~5秒）

        - 代码概览（文件数、语言分布）
        - 基本健康度评分
        """
        # 语言分布
        language_counts: dict[str, int] = {}
        for file_path in source_files:
            ext = file_path.suffix.lower()
            # 简单语言检测
            if ext in [".py", ".pyi"]:
                language_counts["python"] = language_counts.get("python", 0) + 1
            elif ext in [".js", ".jsx", ".ts", ".tsx"]:
                if ext not in [".jsx", ".tsx"]:
                    language_counts["javascript"] = language_counts.get("javascript", 0) + 1
                if ext in [".ts", ".tsx"]:
                    language_counts["typescript"] = language_counts.get("typescript", 0) + 1
            elif ext == ".java":
                language_counts["java"] = language_counts.get("java", 0) + 1
            elif ext == ".go":
                language_counts["go"] = language_counts.get("go", 0) + 1
            elif ext in [".c", ".cpp", ".cc", ".h", ".hpp"]:
                lang = "cpp" if ext in [".cpp", ".cc", ".hpp"] else "c"
                language_counts[lang] = language_counts.get(lang, 0) + 1
            elif ext == ".rs":
                language_counts["rust"] = language_counts.get("rust", 0) + 1
            elif ext == ".php":
                language_counts["php"] = language_counts.get("php", 0) + 1
            elif ext == ".rb":
                language_counts["ruby"] = language_counts.get("ruby", 0) + 1
            elif ext in [".kt", ".kts"]:
                language_counts["kotlin"] = language_counts.get("kotlin", 0) + 1
            elif ext == ".swift":
                language_counts["swift"] = language_counts.get("swift", 0) + 1

        # 总行数（采样估算）
        total_lines = 0
        sample_size = min(20, len(source_files))
        for file_path in source_files[:sample_size]:
            try:
                total_lines += len(file_path.read_text(encoding="utf-8", errors="ignore").splitlines())
            except Exception:
                pass

        # 推算总行数
        if sample_size > 0:
            avg_lines = total_lines / sample_size
            estimated_total = int(avg_lines * len(source_files))
        else:
            estimated_total = 0

        # 基本健康度评分
        health_score = self._calculate_basic_health_score(
            len(source_files), estimated_total
        )

        return {
            "overview": {
                "total_files": len(source_files),
                "estimated_lines": estimated_total,
                "languages": language_counts,
                "primary_language": self._get_primary_language(language_counts),
            },
            "health": {
                "overall_grade": health_score,
                "assessment": self._get_health_assessment(health_score),
            },
        }

    async def _standard_analysis(
        self,
        project_path: Path,
        source_files: list[Path],
    ) -> dict[str, Any]:
        """
        标准分析（~15秒）

        - quick 分析结果
        - 采样文件的基本指标（平均行数、最大文件等）
        """
        # 先运行 quick 分析
        quick_result = await self._quick_analysis(project_path, source_files)

        # 计算采样文件的详细指标
        sample_size = min(30, len(source_files))
        file_metrics: list[FileMetric] = []

        for file_path in source_files[:sample_size]:
            try:
                lines = len(file_path.read_text(encoding="utf-8", errors="ignore").splitlines())
                file_metrics.append({
                    "file": str(file_path.relative_to(project_path)),
                    "lines": lines,
                })
            except Exception:
                pass

        # 计算统计
        if file_metrics:
            avg_lines = sum(int(m["lines"]) for m in file_metrics) / len(file_metrics)
            max_lines = max(int(m["lines"]) for m in file_metrics)
            largest_file = max(file_metrics, key=lambda x: int(x["lines"]))["file"]
        else:
            avg_lines = 0
            max_lines = 0
            largest_file = ""

        return {
            **quick_result,
            "metrics": {
                "average_file_lines": round(avg_lines, 1),
                "largest_file_lines": max_lines,
                "largest_file": largest_file,
                "files_sampled": sample_size,
            },
        }

    async def _deep_analysis(
        self,
        project_path: Path,
        source_files: list[Path],
    ) -> dict[str, Any]:
        """
        深度分析（~30秒）

        - standard 分析结果
        - 更多采样文件
        - 更详细的统计
        """
        # 先运行 standard 分析
        standard_result = await self._standard_analysis(project_path, source_files)

        # 增加更多采样文件的详细指标
        sample_size = min(50, len(source_files))
        file_metrics: list[FileMetric] = []

        for file_path in source_files[:sample_size]:
            try:
                lines = len(file_path.read_text(encoding="utf-8", errors="ignore").splitlines())
                file_metrics.append({
                    "file": str(file_path.relative_to(project_path)),
                    "lines": lines,
                })
            except Exception:
                pass

        # 计算统计
        if file_metrics:
            avg_lines = sum(int(m["lines"]) for m in file_metrics) / len(file_metrics)
            max_lines = max(int(m["lines"]) for m in file_metrics)
            largest_file = max(file_metrics, key=lambda x: int(x["lines"]))["file"]
            smallest_file = min(file_metrics, key=lambda x: int(x["lines"]))["file"]
        else:
            avg_lines = 0
            max_lines = 0
            largest_file = ""
            smallest_file = ""

        # 更新 metrics
        standard_result["metrics"].update({
            "average_file_lines": round(avg_lines, 1),
            "largest_file_lines": max_lines,
            "largest_file": largest_file,
            "smallest_file_lines": min((int(m["lines"]) for m in file_metrics), default=0),
            "smallest_file": smallest_file,
            "files_sampled": sample_size,
        })

        # 添加深度分析特有的指标
        total_size_bytes = sum(
            f.stat().st_size for f in source_files[:sample_size]
        )
        avg_size_bytes = total_size_bytes / sample_size if sample_size > 0 else 0

        standard_result["deep_metrics"] = {
            "total_size_bytes": total_size_bytes,
            "average_file_size_bytes": round(avg_size_bytes, 1),
        }

        return standard_result

    def _calculate_basic_health_score(
        self, file_count: int, line_count: int
    ) -> str:
        """计算基本健康度评分（简化版）"""
        # 简化逻辑：基于文件数和行数
        if file_count > 1000 or line_count > 100000:
            return "C"
        elif file_count > 500 or line_count > 50000:
            return "B"
        else:
            return "A"

    def _get_health_assessment(self, grade: str) -> str:
        """获取健康度评估描述"""
        assessments = {
            "A": "健康 - 代码库结构良好，易于维护",
            "B": "良好 - 有一些改进空间",
            "C": "需关注 - 建议优化结构和复杂度",
            "D": "风险 - 急需重构",
            "F": "严重问题 - 代码质量堪忧",
        }
        return assessments.get(grade, "未知")

    def _get_primary_language(self, language_counts: dict[str, int]) -> str:
        """获取主要语言"""
        if not language_counts:
            return "unknown"
        # 返回文件数最多的语言
        primary = max(language_counts, key=lambda k: language_counts[k])
        # 对于 JS/TS 组合，优先显示 TypeScript
        if primary == "javascript" and language_counts.get("typescript", 0) > 0:
            return "typescript"
        return primary

    def _detect_language(self, file_path: Path) -> str:
        """
        Detect programming language from file extension.

        Args:
            file_path: Path to the file

        Returns:
            Language name as string
        """
        ext = file_path.suffix.lower()
        lang_map: dict[str, str] = {
            ".py": "python",
            ".pyi": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".c": "c",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".hpp": "cpp",
            ".php": "php",
            ".rb": "ruby",
            ".kt": "kotlin",
            ".kts": "kotlin",
            ".swift": "swift",
        }
        return lang_map.get(ext, "unknown")
