#!/usr/bin/env python3
"""
Regression test for Issue #112: Python decorated methods detection

https://github.com/aimasteracc/tree-sitter-analyzer/issues/112

Bug: get_code_outline silently drops all @classmethod and @staticmethod methods.
Root cause: _traverse_and_extract_iterative didn't include decorated_definition
in container_node_types, so decorated methods were never visited.

Fix: Add "decorated_definition" to container_node_types in
tree_sitter_analyzer/languages/python_plugin.py
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from tree_sitter_analyzer.languages.python_plugin import PythonPlugin


@pytest.mark.regression
class TestPythonDecoratedMethodsRegression:
    """回归测试：确保装饰的方法（@classmethod, @staticmethod）被正确提取"""

    @pytest.fixture
    def plugin(self):
        """创建 Python 插件实例"""
        return PythonPlugin()

    def _create_mock_request(self, file_path: str):
        """创建 mock AnalysisRequest"""
        mock_request = Mock()
        mock_request.file_path = file_path
        mock_request.language = "python"
        mock_request.include_complexity = False
        mock_request.include_details = False
        return mock_request

    async def _analyze_file(self, plugin, file_path: str):
        """分析文件并返回结果"""
        mock_request = self._create_mock_request(file_path)
        return await plugin.analyze_file(file_path, mock_request)

    @pytest.fixture
    def test_code(self):
        """测试代码：包含各种装饰器的类"""
        return '''
class ClassWithNormalMethods:
    def method_a(self, x: int) -> str:
        return str(x)
    async def method_b(self, y: str) -> bool:
        return bool(y)

class ClassWithClassMethods:
    @classmethod
    def class_method_a(cls, x: int) -> str:
        return str(x)
    @classmethod
    async def class_method_b(cls, y: str) -> bool:
        return bool(y)

class ClassWithStaticMethods:
    @staticmethod
    def static_method_a(x: int) -> str:
        return str(x)

class ClassWithMixed:
    def normal(self): pass
    @classmethod
    def cls_method(cls): pass
    @staticmethod
    def static_method(): pass

class ClassWithProperty:
    @property
    def my_property(self) -> str:
        return "value"

    @my_property.setter
    def my_property(self, value: str) -> None:
        pass
'''

    def test_normal_methods_count(self, plugin, test_code):
        """测试普通方法被正确提取"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(test_code)
            temp_path = f.name

        try:
            result = asyncio.run(self._analyze_file(plugin, temp_path))

            # 找到 ClassWithNormalMethods
            normal_class = next(
                (e for e in result.elements if e.name == "ClassWithNormalMethods"),
                None,
            )
            assert normal_class is not None, "ClassWithNormalMethods not found"

            # 应该有 2 个方法
            methods = [
                e
                for e in result.elements
                if hasattr(e, "name")
                and e.name in ["method_a", "method_b"]
            ]
            assert len(methods) == 2, f"Expected 2 methods, got {len(methods)}"
        finally:
            Path(temp_path).unlink()

    def test_classmethod_detection(self, plugin, test_code):
        """测试 @classmethod 装饰的方法被正确提取"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(test_code)
            temp_path = f.name

        try:
            result = asyncio.run(self._analyze_file(plugin, temp_path))

            # 找到 ClassWithClassMethods
            class_methods_class = next(
                (e for e in result.elements if e.name == "ClassWithClassMethods"),
                None,
            )
            assert class_methods_class is not None, "ClassWithClassMethods not found"

            # 应该有 2 个类方法
            class_methods = [
                e
                for e in result.elements
                if hasattr(e, "name")
                and e.name in ["class_method_a", "class_method_b"]
            ]
            assert (
                len(class_methods) == 2
            ), f"Expected 2 class methods, got {len(class_methods)}"

            # 验证装饰器信息
            for method in class_methods:
                if hasattr(method, "decorators"):
                    assert (
                        "classmethod" in method.decorators
                    ), f"{method.name} missing @classmethod decorator"
        finally:
            Path(temp_path).unlink()

    def test_staticmethod_detection(self, plugin, test_code):
        """测试 @staticmethod 装饰的方法被正确提取"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(test_code)
            temp_path = f.name

        try:
            result = asyncio.run(self._analyze_file(plugin, temp_path))

            # 找到 ClassWithStaticMethods
            static_class = next(
                (e for e in result.elements if e.name == "ClassWithStaticMethods"),
                None,
            )
            assert static_class is not None, "ClassWithStaticMethods not found"

            # 应该有 1 个静态方法
            static_methods = [
                e
                for e in result.elements
                if hasattr(e, "name") and e.name == "static_method_a"
            ]
            assert (
                len(static_methods) == 1
            ), f"Expected 1 static method, got {len(static_methods)}"

            # 验证装饰器信息
            method = static_methods[0]
            if hasattr(method, "decorators"):
                assert (
                    "staticmethod" in method.decorators
                ), "static_method_a missing @staticmethod decorator"
        finally:
            Path(temp_path).unlink()

    def test_mixed_methods_count(self, plugin, test_code):
        """测试混合方法类（普通 + classmethod + staticmethod）"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(test_code)
            temp_path = f.name

        try:
            result = asyncio.run(self._analyze_file(plugin, temp_path))

            # 找到 ClassWithMixed
            mixed_class = next(
                (e for e in result.elements if e.name == "ClassWithMixed"), None
            )
            assert mixed_class is not None, "ClassWithMixed not found"

            # 应该有 3 个方法：normal, cls_method, static_method
            mixed_methods = [
                e
                for e in result.elements
                if hasattr(e, "name")
                and e.name in ["normal", "cls_method", "static_method"]
            ]
            assert (
                len(mixed_methods) == 3
            ), f"Expected 3 methods, got {len(mixed_methods)}: {[m.name for m in mixed_methods]}"
        finally:
            Path(temp_path).unlink()

    def test_property_detection(self, plugin, test_code):
        """测试 @property 装饰的方法被正确提取"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(test_code)
            temp_path = f.name

        try:
            result = asyncio.run(self._analyze_file(plugin, temp_path))

            # 找到 ClassWithProperty
            property_class = next(
                (e for e in result.elements if e.name == "ClassWithProperty"), None
            )
            assert property_class is not None, "ClassWithProperty not found"

            # 应该有 2 个方法：getter 和 setter
            property_methods = [
                e
                for e in result.elements
                if hasattr(e, "name") and e.name == "my_property"
            ]
            assert (
                len(property_methods) == 2
            ), f"Expected 2 property methods (getter + setter), got {len(property_methods)}"
        finally:
            Path(temp_path).unlink()

    def test_no_methods_dropped(self, plugin, test_code):
        """综合测试：确保所有方法都被提取，没有遗漏"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(test_code)
            temp_path = f.name

        try:
            result = asyncio.run(self._analyze_file(plugin, temp_path))

            # 统计所有函数/方法
            all_functions = [
                e for e in result.elements if hasattr(e, "name") and hasattr(e, "parameters")
            ]

            # 期望的方法列表
            expected_methods = {
                "method_a",
                "method_b",
                "class_method_a",
                "class_method_b",
                "static_method_a",
                "normal",
                "cls_method",
                "static_method",
                "my_property",  # getter + setter = 2 occurrences
            }

            found_methods = {e.name for e in all_functions}

            # 验证没有遗漏
            missing = expected_methods - found_methods
            assert not missing, f"Missing methods: {missing}"

            # 验证总数（my_property 有 getter + setter，所以是 10 个）
            assert (
                len(all_functions) >= 10
            ), f"Expected at least 10 methods, got {len(all_functions)}"
        finally:
            Path(temp_path).unlink()
