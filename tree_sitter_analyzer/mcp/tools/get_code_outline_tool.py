#!/usr/bin/env python3
"""
get_code_outline MCP Tool

返回文件或模块的层次化结构大纲（package → class → method），
不包含代码正文内容，供 AI 在取回完整内容之前先导航结构。

这是 outline-first 检索模式的核心工具：
AI 先看大纲，再决定要取哪个具体方法/类，从而大幅降低 token 消耗。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_PACKAGE,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)
from ...core.analysis_engine import AnalysisRequest, get_analysis_engine
from ...language_detector import detect_language_from_file
from ...utils import setup_logger
from ..utils import get_performance_monitor
from ..utils.format_helper import format_as_json, format_as_toon
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class GetCodeOutlineTool(BaseMCPTool):
    """
    MCP Tool: get_code_outline

    返回代码文件的层次化结构大纲，不含方法体内容。
    输出格式：package → class（含行号范围） → method（含签名和行号），
    token 消耗远低于 analyze_code_structure 的表格格式。

    典型用法：
        AI 调用 get_code_outline 得到结构树，
        再调用 extract_code_section 只取需要的方法体。
    """

    def __init__(self, project_root: str | None = None) -> None:
        """初始化 get_code_outline 工具。"""
        super().__init__(project_root)
        self.analysis_engine = get_analysis_engine(project_root)
        self.logger = logger

    def set_project_path(self, project_path: str) -> None:
        """更新项目路径。"""
        super().set_project_path(project_path)
        self.analysis_engine = get_analysis_engine(project_path)
        logger.info(f"GetCodeOutlineTool project path updated to: {project_path}")

    def get_tool_schema(self) -> dict[str, Any]:
        """返回 MCP tool JSON Schema。"""
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": (
                        "Path to the source file to outline. "
                        "Must be within project boundaries."
                    ),
                },
                "language": {
                    "type": "string",
                    "description": (
                        "Programming language (optional, auto-detected from file extension). "
                        "Example: 'java', 'python', 'go'"
                    ),
                },
                "include_fields": {
                    "type": "boolean",
                    "description": (
                        "Include class fields/attributes in the outline. "
                        "Default false to keep outline compact."
                    ),
                    "default": False,
                },
                "include_imports": {
                    "type": "boolean",
                    "description": (
                        "Include import statements summary in the outline. "
                        "Default false."
                    ),
                    "default": False,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": (
                        "Output format: 'toon' for compact TOON format (50-70% token savings), "
                        "or 'json' for standard JSON. Default 'toon'."
                    ),
                    "default": "toon",
                },
            },
            "required": ["file_path"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """
        校验工具参数。

        Args:
            arguments: 工具调用参数

        Returns:
            True 表示参数合法

        Raises:
            ValueError: 参数不合法时抛出
        """
        if "file_path" not in arguments:
            raise ValueError("Required field 'file_path' is missing")

        file_path = arguments["file_path"]
        if not isinstance(file_path, str) or not file_path.strip():
            raise ValueError("file_path must be a non-empty string")

        if "language" in arguments and arguments["language"] is not None:
            if not isinstance(arguments["language"], str):
                raise ValueError("language must be a string")

        for bool_field in ("include_fields", "include_imports"):
            if bool_field in arguments and not isinstance(arguments[bool_field], bool):
                raise ValueError(f"{bool_field} must be a boolean")

        # 验证 output_format
        if "output_format" in arguments:
            output_format = arguments["output_format"]
            if output_format not in ("json", "toon"):
                return False  # 无效格式返回 False

        return True

    def _build_outline(
        self,
        analysis_result: Any,
        include_fields: bool,
        include_imports: bool,
    ) -> dict[str, Any]:
        """
        从分析结果构建层次化大纲。

        大纲结构：
            package (str | None)
            imports_count (int)
            classes: list of
                name, type, line_start, line_end
                extends, implements
                methods: list of
                    name, return_type, parameters, visibility
                    line_start, line_end, is_constructor, is_static
                fields (if include_fields): list of
                    name, type, visibility, line_start, line_end
            top_level_functions: list of
                name, return_type, parameters, line_start, line_end
            statistics: class_count, method_count, field_count, import_count
        """
        elements = analysis_result.elements or []

        packages = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_PACKAGE)]
        imports = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_IMPORT)]
        classes = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_CLASS)]
        all_methods = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)]
        all_fields = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_VARIABLE)]

        # 构建 class 行号区间集合，用于区分类方法与顶层函数
        class_ranges: list[tuple[int, int]] = [
            (getattr(cls, "start_line", 0), getattr(cls, "end_line", 0))
            for cls in classes
        ]

        def _in_class(method: Any) -> bool:
            """判断方法是否在某个类内部（按行号）。"""
            m_start = getattr(method, "start_line", 0)
            for cls_start, cls_end in class_ranges:
                if cls_start <= m_start <= cls_end:
                    return True
            return False

        def _method_entry(m: Any) -> dict[str, Any]:
            """将方法元素转换为大纲条目。"""
            params = getattr(m, "parameters", [])
            if params and isinstance(params[0], str):
                param_list = params
            else:
                param_list = [
                    f"{getattr(p, 'type', 'Object')} {getattr(p, 'name', 'param')}"
                    for p in params
                ]
            return {
                "name": getattr(m, "name", "unknown"),
                "return_type": getattr(m, "return_type", "void"),
                "parameters": param_list,
                "visibility": getattr(m, "visibility", "public"),
                "is_constructor": getattr(m, "is_constructor", False),
                "is_static": getattr(m, "is_static", False),
                "line_start": getattr(m, "start_line", 0),
                "line_end": getattr(m, "end_line", 0),
            }

        def _field_entry(f: Any) -> dict[str, Any]:
            """将字段元素转换为大纲条目。"""
            return {
                "name": getattr(f, "name", "unknown"),
                "type": getattr(f, "field_type", "Object"),
                "visibility": getattr(f, "visibility", "private"),
                "is_static": getattr(f, "is_static", False),
                "line_start": getattr(f, "start_line", 0),
                "line_end": getattr(f, "end_line", 0),
            }

        # 构建类大纲
        class_outlines = []
        for cls in classes:
            cls_start = getattr(cls, "start_line", 0)
            cls_end = getattr(cls, "end_line", 0)

            # 属于这个类的方法
            cls_methods = [
                _method_entry(m)
                for m in all_methods
                if cls_start <= getattr(m, "start_line", 0) <= cls_end
            ]
            cls_methods.sort(key=lambda x: x["line_start"])

            class_entry: dict[str, Any] = {
                "name": getattr(cls, "name", "unknown"),
                "type": getattr(cls, "class_type", "class"),
                "line_start": cls_start,
                "line_end": cls_end,
                "extends": getattr(cls, "extends_class", None),
                "implements": getattr(cls, "implements_interfaces", []),
                "methods": cls_methods,
            }

            if include_fields:
                cls_fields = [
                    _field_entry(f)
                    for f in all_fields
                    if cls_start <= getattr(f, "start_line", 0) <= cls_end
                ]
                cls_fields.sort(key=lambda x: x["line_start"])
                class_entry["fields"] = cls_fields

            class_outlines.append(class_entry)

        class_outlines.sort(key=lambda x: x["line_start"])

        # 顶层函数（不属于任何类）
        top_level_fns = [
            _method_entry(m) for m in all_methods if not _in_class(m)
        ]
        top_level_fns.sort(key=lambda x: x["line_start"])

        outline: dict[str, Any] = {
            "file_path": analysis_result.file_path,
            "language": analysis_result.language,
            "total_lines": analysis_result.line_count,
            "package": packages[0].name if packages else None,
            "classes": class_outlines,
            "top_level_functions": top_level_fns,
            "statistics": {
                "class_count": len(classes),
                "method_count": len(all_methods),
                "field_count": len(all_fields),
                "import_count": len(imports),
            },
        }

        if include_imports:
            outline["imports"] = [
                getattr(imp, "import_statement", getattr(imp, "name", ""))
                for imp in imports
            ]

        return outline

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """执行 get_code_outline 工具。"""
        try:
            self.validate_arguments(arguments)

            file_path = arguments["file_path"]
            language = arguments.get("language")
            include_fields = arguments.get("include_fields", False)
            include_imports = arguments.get("include_imports", False)
            output_format = arguments.get("output_format", "toon")

            resolved_path = self.resolve_and_validate_file_path(file_path)

            if not Path(resolved_path).exists():
                raise ValueError(f"File not found: {file_path}")

            if not language:
                language = detect_language_from_file(
                    resolved_path, project_root=self.project_root
                )

            monitor = get_performance_monitor()
            with monitor.measure_operation("get_code_outline"):
                request = AnalysisRequest(
                    file_path=resolved_path,
                    language=language,
                    include_complexity=False,
                    include_details=True,
                )
                analysis_result = await self.analysis_engine.analyze(request)

            if analysis_result is None:
                raise RuntimeError(f"Failed to analyze file: {file_path}")

            outline = self._build_outline(
                analysis_result,
                include_fields=include_fields,
                include_imports=include_imports,
            )

            result = {"success": True, "outline": outline}

            # 根据 output_format 格式化输出
            if output_format == "toon":
                formatted_text = format_as_toon(result)
            else:  # json
                formatted_text = format_as_json(result)

            return [{"type": "text", "text": formatted_text}]

        except Exception as e:
            self.logger.error(f"Error in get_code_outline: {e}")
            raise

    def get_tool_definition(self) -> dict[str, Any]:
        """返回 MCP tool 定义。"""
        return {
            "name": "get_code_outline",
            "description": (
                "Return a hierarchical structural outline of a source file "
                "(package → class → method tree with line numbers) "
                "WITHOUT reading the method bodies. "
                "Supports TOON format (default) for 50-70% token savings. "
                "Use this BEFORE extract_code_section to navigate large files efficiently. "
                "Enables outline-first retrieval: understand structure first, "
                "then fetch only the specific code you need."
            ),
            "inputSchema": self.get_tool_schema(),
        }


# 模块级实例，供直接访问使用
get_code_outline_tool = GetCodeOutlineTool()
