"""测试数据工厂模块。

本模块提供用于创建测试数据的工厂类，用于简化测试用例的编写。
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class CodeElementFactory:
    """代码元素工厂类。

    用于创建测试用的代码元素对象。
    """

    @staticmethod
    def create_class_element(
        name: str = "TestClass",
        line_start: int = 1,
        line_end: int = 10,
        is_private: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """创建类元素。

        Args:
            name: 类名
            line_start: 起始行号
            line_end: 结束行号
            is_private: 是否为私有
            **kwargs: 其他属性

        Returns:
            代码元素字典
        """
        return {
            "name": name,
            "element_type": "class",
            "line_start": line_start,
            "line_end": line_end,
            "is_private": is_private,
            **kwargs,
        }

    @staticmethod
    def create_method_element(
        name: str = "test_method",
        line_start: int = 5,
        line_end: int = 8,
        is_private: bool = False,
        parameters: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """创建方法元素。

        Args:
            name: 方法名
            line_start: 起始行号
            line_end: 结束行号
            is_private: 是否为私有
            parameters: 参数列表
            **kwargs: 其他属性

        Returns:
            代码元素字典
        """
        return {
            "name": name,
            "element_type": "method",
            "line_start": line_start,
            "line_end": line_end,
            "is_private": is_private,
            "parameters": parameters or [],
            **kwargs,
        }

    @staticmethod
    def create_function_element(
        name: str = "test_function",
        line_start: int = 1,
        line_end: int = 5,
        is_private: bool = False,
        parameters: list[str] | None = None,
        return_type: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """创建函数元素。

        Args:
            name: 函数名
            line_start: 起始行号
            line_end: 结束行号
            is_private: 是否为私有
            parameters: 参数列表
            return_type: 返回类型
            **kwargs: 其他属性

        Returns:
            代码元素字典
        """
        return {
            "name": name,
            "element_type": "function",
            "line_start": line_start,
            "line_end": line_end,
            "is_private": is_private,
            "parameters": parameters or [],
            "return_type": return_type,
            **kwargs,
        }

    @staticmethod
    def create_property_element(
        name: str = "test_property",
        line_start: int = 3,
        line_end: int = 3,
        is_private: bool = False,
        property_type: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """创建属性元素。

        Args:
            name: 属性名
            line_start: 起始行号
            line_end: 结束行号
            is_private: 是否为私有
            property_type: 属性类型
            **kwargs: 其他属性

        Returns:
            代码元素字典
        """
        return {
            "name": name,
            "element_type": "property",
            "line_start": line_start,
            "line_end": line_end,
            "is_private": is_private,
            "property_type": property_type,
            **kwargs,
        }

    @staticmethod
    def create_variable_element(
        name: str = "test_variable",
        line_start: int = 2,
        line_end: int = 2,
        is_private: bool = False,
        variable_type: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """创建变量元素。

        Args:
            name: 变量名
            line_start: 起始行号
            line_end: 结束行号
            is_private: 是否为私有
            variable_type: 变量类型
            **kwargs: 其他属性

        Returns:
            代码元素字典
        """
        return {
            "name": name,
            "element_type": "variable",
            "line_start": line_start,
            "line_end": line_end,
            "is_private": is_private,
            "variable_type": variable_type,
            **kwargs,
        }

    @staticmethod
    def create_interface_element(
        name: str = "TestInterface",
        line_start: int = 1,
        line_end: int = 8,
        is_private: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """创建接口元素。

        Args:
            name: 接口名
            line_start: 起始行号
            line_end: 结束行号
            is_private: 是否为私有
            **kwargs: 其他属性

        Returns:
            代码元素字典
        """
        return {
            "name": name,
            "element_type": "interface",
            "line_start": line_start,
            "line_end": line_end,
            "is_private": is_private,
            **kwargs,
        }

    @staticmethod
    def create_enum_element(
        name: str = "TestEnum",
        line_start: int = 1,
        line_end: int = 6,
        is_private: bool = False,
        values: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """创建枚举元素。

        Args:
            name: 枚举名
            line_start: 起始行号
            line_end: 结束行号
            is_private: 是否为私有
            values: 枚举值列表
            **kwargs: 其他属性

        Returns:
            代码元素字典
        """
        return {
            "name": name,
            "element_type": "enum",
            "line_start": line_start,
            "line_end": line_end,
            "is_private": is_private,
            "values": values or [],
            **kwargs,
        }

    @staticmethod
    def create_namespace_element(
        name: str = "TestNamespace",
        line_start: int = 1,
        line_end: int = 20,
        is_private: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """创建命名空间元素。

        Args:
            name: 命名空间名
            line_start: 起始行号
            line_end: 结束行号
            is_private: 是否为私有
            **kwargs: 其他属性

        Returns:
            代码元素字典
        """
        return {
            "name": name,
            "element_type": "namespace",
            "line_start": line_start,
            "line_end": line_end,
            "is_private": is_private,
            **kwargs,
        }


@dataclass
class AnalysisResultFactory:
    """分析结果工厂类。

    用于创建测试用的分析结果对象。
    """

    @staticmethod
    def create_analysis_result(
        file_path: Path | None = None,
        language: str = "python",
        elements: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """创建分析结果。

        Args:
            file_path: 文件路径
            language: 编程语言
            elements: 代码元素列表
            metadata: 元数据
            **kwargs: 其他属性

        Returns:
            分析结果字典
        """
        return {
            "file_path": str(file_path or Path("test.py")),
            "language": language,
            "elements": elements or [],
            "metadata": metadata or {},
            **kwargs,
        }

    @staticmethod
    def create_simple_analysis_result(
        num_classes: int = 1,
        num_methods: int = 2,
        num_functions: int = 1,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """创建简单的分析结果。

        Args:
            num_classes: 类数量
            num_methods: 方法数量
            num_functions: 函数数量
            **kwargs: 其他属性

        Returns:
            分析结果字典
        """
        elements = []

        # 添加类
        for i in range(num_classes):
            elements.append(
                CodeElementFactory.create_class_element(
                    name=f"TestClass{i}", line_start=1 + i * 10, line_end=10 + i * 10
                )
            )

        # 添加方法
        for i in range(num_methods):
            elements.append(
                CodeElementFactory.create_method_element(
                    name=f"test_method{i}", line_start=2 + i * 3, line_end=4 + i * 3
                )
            )

        # 添加函数
        for i in range(num_functions):
            elements.append(
                CodeElementFactory.create_function_element(
                    name=f"test_function{i}", line_start=1 + i * 5, line_end=5 + i * 5
                )
            )

        return AnalysisResultFactory.create_analysis_result(elements=elements, **kwargs)

    @staticmethod
    def create_empty_analysis_result(
        file_path: Path | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        """创建空的分析结果。

        Args:
            file_path: 文件路径
            **kwargs: 其他属性

        Returns:
            分析结果字典
        """
        return AnalysisResultFactory.create_analysis_result(
            file_path=file_path, elements=[], **kwargs
        )

    @staticmethod
    def create_analysis_result_with_metadata(
        file_path: Path | None = None,
        analysis_time: float | None = None,
        element_count: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """创建带有元数据的分析结果。

        Args:
            file_path: 文件路径
            analysis_time: 分析时间（秒）
            element_count: 元素数量
            **kwargs: 其他属性

        Returns:
            分析结果字典
        """
        metadata = {
            "analysis_time": analysis_time or 0.5,
            "element_count": element_count or 10,
            "timestamp": datetime.utcnow().isoformat(),
        }

        return AnalysisResultFactory.create_analysis_result(
            file_path=file_path, metadata=metadata, **kwargs
        )


@dataclass
class QueryResultFactory:
    """查询结果工厂类。

    用于创建测试用的查询结果对象。
    """

    @staticmethod
    def create_query_result(
        query_name: str = "test_query",
        matches: list[dict[str, Any]] | None = None,
        success: bool = True,
        error_message: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """创建查询结果。

        Args:
            query_name: 查询名称
            matches: 匹配结果列表
            success: 是否成功
            error_message: 错误消息
            **kwargs: 其他属性

        Returns:
            查询结果字典
        """
        return {
            "query_name": query_name,
            "matches": matches or [],
            "success": success,
            "error_message": error_message,
            **kwargs,
        }

    @staticmethod
    def create_simple_query_result(
        num_matches: int = 3, **kwargs: Any
    ) -> dict[str, Any]:
        """创建简单的查询结果。

        Args:
            num_matches: 匹配数量
            **kwargs: 其他属性

        Returns:
            查询结果字典
        """
        matches = []
        for i in range(num_matches):
            matches.append({"name": f"match_{i}", "line": 1 + i * 2, "column": 0})

        return QueryResultFactory.create_query_result(matches=matches, **kwargs)

    @staticmethod
    def create_empty_query_result(
        query_name: str = "test_query", **kwargs: Any
    ) -> dict[str, Any]:
        """创建空的查询结果。

        Args:
            query_name: 查询名称
            **kwargs: 其他属性

        Returns:
            查询结果字典
        """
        return QueryResultFactory.create_query_result(
            query_name=query_name, matches=[], **kwargs
        )

    @staticmethod
    def create_error_query_result(
        query_name: str = "test_query",
        error_message: str = "Query failed",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """创建错误查询结果。

        Args:
            query_name: 查询名称
            error_message: 错误消息
            **kwargs: 其他属性

        Returns:
            查询结果字典
        """
        return QueryResultFactory.create_query_result(
            query_name=query_name, success=False, error_message=error_message, **kwargs
        )


@dataclass
class PerformanceStatsFactory:
    """性能统计工厂类。

    用于创建测试用的性能统计对象。
    """

    @staticmethod
    def create_performance_stats(
        operation_name: str = "test_operation",
        execution_time: float = 0.5,
        memory_usage: int = 1024,
        cache_hits: int = 5,
        cache_misses: int = 2,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """创建性能统计。

        Args:
            operation_name: 操作名称
            execution_time: 执行时间（秒）
            memory_usage: 内存使用（字节）
            cache_hits: 缓存命中次数
            cache_misses: 缓存未命中次数
            **kwargs: 其他属性

        Returns:
            性能统计字典
        """
        return {
            "operation_name": operation_name,
            "execution_time": execution_time,
            "memory_usage": memory_usage,
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            **kwargs,
        }

    @staticmethod
    def create_empty_performance_stats(
        operation_name: str = "test_operation", **kwargs: Any
    ) -> dict[str, Any]:
        """创建空的性能统计。

        Args:
            operation_name: 操作名称
            **kwargs: 其他属性

        Returns:
            性能统计字典
        """
        return PerformanceStatsFactory.create_performance_stats(
            operation_name=operation_name,
            execution_time=0.0,
            memory_usage=0,
            cache_hits=0,
            cache_misses=0,
            **kwargs,
        )


@dataclass
class FileContentFactory:
    """文件内容工厂类。

    用于创建测试用的文件内容。
    """

    @staticmethod
    def create_python_file_content(
        num_classes: int = 1, num_functions: int = 2, **kwargs: Any
    ) -> str:
        """创建Python文件内容。

        Args:
            num_classes: 类数量
            num_functions: 函数数量
            **kwargs: 其他属性

        Returns:
            Python文件内容字符串
        """
        content = '"""Test Python file."""\n\n'

        # 添加函数
        for i in range(num_functions):
            content += f"def test_function_{i}():\n"
            content += f'    """Test function {i}."""\n'
            content += "    pass\n\n"

        # 添加类
        for i in range(num_classes):
            content += f"class TestClass{i}:\n"
            content += f'    """Test class {i}."""\n\n'
            content += f"    def test_method_{i}(self):\n"
            content += f'        """Test method {i}."""\n'
            content += "        pass\n\n"

        return content

    @staticmethod
    def create_java_file_content(num_classes: int = 1, **kwargs: Any) -> str:
        """创建Java文件内容。

        Args:
            num_classes: 类数量
            **kwargs: 其他属性

        Returns:
            Java文件内容字符串
        """
        content = "public class TestFile {\n"

        for i in range(num_classes):
            content += f"    public static class InnerClass{i} {{\n"
            content += f"        public void method{i}() {{\n"
            content += f"            // Method {i}\n"
            content += "        }\n"
            content += "    }\n"

        content += "}\n"
        return content

    @staticmethod
    def create_javascript_file_content(num_functions: int = 2, **kwargs: Any) -> str:
        """创建JavaScript文件内容。

        Args:
            num_functions: 函数数量
            **kwargs: 其他属性

        Returns:
            JavaScript文件内容字符串
        """
        content = "// Test JavaScript file\n\n"

        for i in range(num_functions):
            content += f"function testFunction{i}() {{\n"
            content += f"    // Test function {i}\n"
            content += "    return true;\n"
            content += "}\n\n"

        return content


# 便捷函数
def create_test_elements(count: int = 5) -> list[dict[str, Any]]:
    """创建测试元素列表。

    Args:
        count: 元素数量

    Returns:
        元素列表
    """
    elements = []
    for i in range(count):
        elements.append(
            CodeElementFactory.create_class_element(
                name=f"TestClass{i}", line_start=1 + i * 10, line_end=10 + i * 10
            )
        )
    return elements


def create_test_analysis_result(
    file_path: Path | None = None, num_elements: int = 5
) -> dict[str, Any]:
    """创建测试分析结果。

    Args:
        file_path: 文件路径
        num_elements: 元素数量

    Returns:
        分析结果字典
    """
    return AnalysisResultFactory.create_analysis_result(
        file_path=file_path, elements=create_test_elements(num_elements)
    )
