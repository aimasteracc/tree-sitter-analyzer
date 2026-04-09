#!/usr/bin/env python3
"""
Trace Impact Tool

Lightweight impact analysis tool that finds all call sites of a symbol (method/class/function)
using ripgrep. Unlike full call graph solutions, this provides fast "usage tracing" without
requiring a graph database.

This tool is inspired by GitNexus's impact analysis but optimized for tree-sitter-analyzer's
architecture, reusing existing ripgrep infrastructure.
"""

from __future__ import annotations

from typing import Any

from ...language_detector import LanguageDetector, detect_language_from_file
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool
from .fd_rg_utils import (
    build_rg_command,
    parse_rg_json_lines_to_matches,
    run_command_capture,
)

# Set up logging
logger = setup_logger(__name__)


def _get_impact_level(count: int) -> dict[str, str]:
    """
    Return a severity dict for a given caller count.

    Args:
        count: Number of callers found for a symbol

    Returns:
        Dictionary with level, badge, and guidance keys
    """
    if count == 0:
        return {
            "level": "none",
            "badge": "✅ NO CALLERS",
            "guidance": "Safe to modify or delete.",
        }
    elif count <= 5:
        return {
            "level": "low",
            "badge": "⚠️ LOW IMPACT",
            "guidance": f"{count} caller(s) found. Review before modifying.",
        }
    elif count <= 20:
        return {
            "level": "medium",
            "badge": "🔶 MEDIUM IMPACT",
            "guidance": (
                f"{count} callers found. "
                "Check all call sites before changing the signature."
            ),
        }
    else:
        return {
            "level": "high",
            "badge": f"🚨 HIGH IMPACT — {count} CALLERS",
            "guidance": (
                f"{count} callers across the codebase. "
                "Do NOT modify signature without updating all callers. "
                "Consider deprecation strategy."
            ),
        }


class TraceImpactTool(BaseMCPTool):
    """
    MCP tool for tracing the impact of code changes by finding all usage sites of a symbol.

    This tool uses ripgrep to efficiently search for occurrences of a method, class, or
    function name across the project, optionally filtering by language to reduce noise.
    """

    def __init__(self, project_root: str | None = None) -> None:
        """
        Initialize the trace impact tool.

        Args:
            project_root: Optional project root directory
        """
        super().__init__(project_root)
        self.language_detector = LanguageDetector()

    def get_tool_definition(self) -> dict[str, Any]:
        """
        Get the MCP tool definition for trace_impact.

        Returns:
            Tool definition with name, description, and input schema
        """
        return {
            "name": "trace_impact",
            "description": (
                "Find every caller and usage site of a symbol across the entire project. "
                "\n\n"
                "REQUIRED before modifying any public function, class, or variable. "
                "Without this, you are editing blindly — you do not know what breaks. "
                "This tool answers: 'if I change X, what else changes?' "
                "\n\n"
                "WHEN TO USE:\n"
                "- ALWAYS call this before renaming, removing, or changing the signature of any "
                "public method, class, or exported variable\n"
                "- Before refactoring code used across multiple files\n"
                "- To understand the blast radius of a deprecation\n"
                "- To verify that a symbol is truly unused before deletion\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- Private/internal methods (single-underscore prefix) within the same file — "
                "the impact is local and visible in context\n"
                "- Pure comment or docstring edits — no callers are affected\n"
                "- Adding a brand-new symbol that has no existing usages\n"
                "\n"
                "IMPORTANT: Provide file_path when available — this filters results to the same "
                "language, eliminating cross-language false positives. "
                "Set word_match=true (the default) to avoid substring noise."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": (
                            "Symbol name to trace (method, class, function, or variable name). "
                            "Example: 'processPayment', 'UserService', 'calculateTotal'"
                        ),
                    },
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Optional: Source file where the symbol is defined. "
                            "If provided, filters results to the same language. "
                            "Example: 'src/services/PaymentService.java'"
                        ),
                    },
                    "project_root": {
                        "type": "string",
                        "description": (
                            "Optional: Project root directory to search. "
                            "Defaults to the tool's configured project root. "
                            "Can provide multiple roots as comma-separated paths."
                        ),
                    },
                    "case_sensitive": {
                        "type": "boolean",
                        "description": (
                            "Whether to perform case-sensitive search. "
                            "Default: false (smart case - case-sensitive if symbol has uppercase)"
                        ),
                    },
                    "word_match": {
                        "type": "boolean",
                        "description": (
                            "Whether to match whole words only (not substrings). "
                            "Default: true (recommended to avoid false positives)"
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return. Default: 1000",
                    },
                    "exclude_patterns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional: Glob patterns to exclude from search. "
                            "Example: ['**/test/**', '**/node_modules/**', '**/*.min.js']"
                        ),
                    },
                },
                "required": ["symbol"],
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """
        Validate input arguments.

        Args:
            arguments: Tool arguments to validate

        Returns:
            True if arguments are valid

        Raises:
            ValueError: If arguments are invalid
        """
        # 验证 symbol
        symbol = arguments.get("symbol")
        if not symbol or not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol parameter is required and must be a non-empty string")

        # 验证 file_path（如果提供）
        file_path = arguments.get("file_path")
        if file_path is not None and not isinstance(file_path, str):
            raise ValueError("file_path must be a string")

        # 验证 project_root（如果提供）
        project_root = arguments.get("project_root")
        if project_root is not None and not isinstance(project_root, str):
            raise ValueError("project_root must be a string")

        # 验证布尔参数
        for param in ["case_sensitive", "word_match"]:
            value = arguments.get(param)
            if value is not None and not isinstance(value, bool):
                raise ValueError(f"{param} must be a boolean")

        # 验证整数参数
        max_results = arguments.get("max_results")
        if max_results is not None:
            if not isinstance(max_results, int) or max_results <= 0:
                raise ValueError("max_results must be a positive integer")

        # 验证 exclude_patterns
        exclude_patterns = arguments.get("exclude_patterns")
        if exclude_patterns is not None:
            if not isinstance(exclude_patterns, list):
                raise ValueError("exclude_patterns must be an array")
            for pattern in exclude_patterns:
                if not isinstance(pattern, str):
                    raise ValueError("exclude_patterns must contain only strings")

        return True

    @handle_mcp_errors("trace_impact")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the trace impact tool.

        Args:
            arguments: Tool arguments containing symbol and optional filters

        Returns:
            Dictionary with usage sites, call count, and metadata
        """
        # 验证参数
        self.validate_arguments(arguments)

        # 提取参数
        symbol = arguments["symbol"].strip()
        file_path = arguments.get("file_path")
        project_root_arg = arguments.get("project_root")
        case_sensitive = arguments.get("case_sensitive", False)
        word_match = arguments.get("word_match", True)
        max_results = arguments.get("max_results", 1000)
        exclude_patterns = arguments.get("exclude_patterns", [])

        # 确定项目根目录
        if project_root_arg:
            # 支持逗号分隔的多个根目录
            roots = [root.strip() for root in project_root_arg.split(",")]
        elif self.project_root:
            roots = [self.project_root]
        else:
            # 默认使用当前目录
            from pathlib import Path
            roots = [str(Path.cwd())]

        # 检测语言（如果提供了 file_path）
        language = None
        language_extensions: list[str] = []
        if file_path:
            language = detect_language_from_file(file_path, project_root=self.project_root)
            if language and language != "unknown":
                # 获取该语言的所有扩展名
                language_extensions = self._get_extensions_for_language(language)
                logger.debug(
                    f"Detected language '{language}' from file '{file_path}', "
                    f"will filter by extensions: {language_extensions}"
                )

        # 构建 ripgrep 命令
        # 使用固定字符串搜索（-F）+ 单词边界（-w）以获得更准确的结果
        case_mode = "sensitive" if case_sensitive else "smart"

        # 构建排除模式
        exclude_globs = list(exclude_patterns)
        # 添加常见的排除模式
        exclude_globs.extend([
            "**/node_modules/**",
            "**/.git/**",
            "**/vendor/**",
            "**/__pycache__/**",
            "**/*.min.js",
            "**/*.min.css",
        ])

        # 如果检测到语言，添加语言过滤
        include_globs: list[str] = []
        if language_extensions:
            # 为每个扩展名创建包含模式
            for ext in language_extensions:
                include_globs.append(f"**/*{ext}")

        # 构建 ripgrep 命令
        cmd = build_rg_command(
            query=symbol,
            case=case_mode,
            fixed_strings=True,  # 使用固定字符串搜索，不使用正则
            word=word_match,  # 单词匹配
            multiline=False,
            include_globs=include_globs if include_globs else None,
            exclude_globs=exclude_globs,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize="10M",
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=5000,
            roots=roots,
            files_from=None,
            count_only_matches=False,
        )

        # 执行搜索
        logger.debug(f"Executing ripgrep command: {' '.join(cmd)}")
        rc, stdout, stderr = await run_command_capture(cmd, timeout_ms=5000)

        # 处理错误
        if rc == 127:
            # ripgrep 未安装
            return {
                "success": False,
                "error": "ripgrep (rg) is not installed. Please install ripgrep to use trace_impact.",
                "usages": [],
                "call_count": 0,
            }
        elif rc == 124:
            # 超时
            return {
                "success": False,
                "error": "Search timed out. Try narrowing the search scope or excluding more directories.",
                "usages": [],
                "call_count": 0,
            }
        elif rc not in (0, 1):
            # 其他错误
            error_msg = stderr.decode("utf-8", errors="replace") if stderr else "Unknown error"
            return {
                "success": False,
                "error": f"Search failed: {error_msg}",
                "usages": [],
                "call_count": 0,
            }

        # 解析结果
        if rc == 1:
            # 没有匹配
            impact = _get_impact_level(0)
            return {
                "success": True,
                "symbol": symbol,
                "language": language,
                "usages": [],
                "call_count": 0,
                "impact_level": impact["level"],
                "impact_badge": impact["badge"],
                "impact_guidance": impact["guidance"],
                "message": f"No usages of '{symbol}' found in the project.",
            }

        # 解析 JSON 输出
        matches = parse_rg_json_lines_to_matches(stdout)

        # Capture true total BEFORE truncating for display.
        # impact_level and call_count must reflect the actual number of callers,
        # not the display-capped count. If max_results=5 and there are 695 matches,
        # call_count must be 695 and impact_level must be "high", not "low".
        true_total = len(matches)

        # 限制结果数量（只影响显示，不影响 call_count）
        if true_total > max_results:
            matches = matches[:max_results]
            truncated = True
        else:
            truncated = False

        # 转换为用户友好的格式
        usages = []
        for match in matches:
            usage = {
                "file": match["file"],
                "line": match["line"],
                "context": match["text"],  # 匹配行的文本
            }
            usages.append(usage)

        # 计算影响等级（使用真实总数，而非截断后的显示数）
        total_count = true_total
        impact = _get_impact_level(total_count)

        # 构建响应
        result: dict[str, Any] = {
            "success": True,
            "symbol": symbol,
            "call_count": total_count,
            "impact_level": impact["level"],
            "impact_badge": impact["badge"],
            "impact_guidance": impact["guidance"],
            "usages": usages,
        }

        # 高影响时加入醒目 warning
        if impact["level"] == "high":
            result["warning"] = (
                f"🚨 HIGH IMPACT: This symbol has {total_count} callers. "
                f"Modifying its signature requires updating all call sites. "
                f"Use batch_search to locate all callers before proceeding."
            )

        # 添加可选字段
        if language:
            result["language"] = language
            result["filtered_by_language"] = True

        if file_path:
            result["source_file"] = file_path

        if truncated:
            result["truncated"] = True
            result["message"] = (
                f"Results truncated to {max_results} usages. "
                f"Consider narrowing the search scope or increasing max_results."
            )

        return result

    def _get_extensions_for_language(self, language: str) -> list[str]:
        """
        Get file extensions for a given language.

        Args:
            language: Language name (e.g., 'java', 'python', 'javascript')

        Returns:
            List of file extensions (with dots, e.g., ['.java', '.jsp'])
        """
        extensions = []
        for ext, lang in self.language_detector.EXTENSION_MAPPING.items():
            if lang == language:
                extensions.append(ext)
        return extensions
