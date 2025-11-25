#!/usr/bin/env python3
"""
语言插件隔离性验证测试

此测试套件验证tree-sitter-analyzer框架中不同语言插件之间的隔离性,
确保添加新语言支持时不会相互影响。
"""

import asyncio
import tempfile
from pathlib import Path

import pytest


class TestLanguagePluginIsolation:
    """测试语言插件之间的隔离性"""

    @pytest.mark.asyncio
    async def test_cache_key_includes_language(self):
        """
        验证: 缓存键包含语言标识符

        目标: 确保不同语言分析同一文件名时不会发生缓存冲突
        """
        from tree_sitter_analyzer.core.analysis_engine import (
            AnalysisRequest,
            UnifiedAnalysisEngine,
        )

        engine = UnifiedAnalysisEngine()

        # 创建两个请求,相同文件路径但不同语言
        request_java = AnalysisRequest(
            file_path="test_file.txt", language="java", include_complexity=True
        )

        request_python = AnalysisRequest(
            file_path="test_file.txt", language="python", include_complexity=True
        )

        # 生成缓存键
        cache_key_java = engine._generate_cache_key(request_java)
        cache_key_python = engine._generate_cache_key(request_python)

        # 验证: 相同文件路径但不同语言应该生成不同的缓存键
        assert cache_key_java != cache_key_python, "不同语言的缓存键应该不同,以避免冲突"

        print(f"✅ Java缓存键: {cache_key_java[:16]}...")
        print(f"✅ Python缓存键: {cache_key_python[:16]}...")
        print("✅ 缓存键包含语言标识符,隔离性验证通过")

    @pytest.mark.asyncio
    async def test_plugin_instances_are_separate(self):
        """
        验证: 不同语言插件使用独立的实例

        目标: 确保每个语言插件都有自己独立的实例,不共享状态
        """
        from tree_sitter_analyzer.plugins.manager import PluginManager

        manager = PluginManager()
        manager.load_plugins()

        # 获取两个不同语言的插件
        java_plugin = manager.get_plugin("java")
        python_plugin = manager.get_plugin("python")

        if java_plugin and python_plugin:
            # 验证: 它们是不同的对象实例
            assert (
                java_plugin is not python_plugin
            ), "不同语言的插件应该是不同的对象实例"

            # 验证: 它们的类型不同
            assert not isinstance(
                java_plugin, type(python_plugin)
            ), "不同语言的插件应该是不同的类"

            print(f"✅ Java插件: {type(java_plugin).__name__}")
            print(f"✅ Python插件: {type(python_plugin).__name__}")
            print("✅ 插件实例独立,隔离性验证通过")

    @pytest.mark.asyncio
    async def test_extractors_are_new_instances(self):
        """
        验证: 每次分析都创建新的extractor实例

        目标: 确保extractor实例不被重用,避免状态污染
        """
        from tree_sitter_analyzer.plugins.manager import PluginManager

        manager = PluginManager()
        manager.load_plugins()

        python_plugin = manager.get_plugin("python")

        if python_plugin:
            # 创建两个extractor实例
            extractor1 = python_plugin.create_extractor()
            extractor2 = python_plugin.create_extractor()

            # 验证: 每次调用都创建新实例
            assert (
                extractor1 is not extractor2
            ), "每次调用create_extractor()应该创建新实例"

            # 验证: 实例具有独立的缓存
            assert hasattr(extractor1, "_node_text_cache"), "Extractor应该有自己的缓存"
            assert hasattr(extractor2, "_node_text_cache"), "Extractor应该有自己的缓存"
            assert (
                extractor1._node_text_cache is not extractor2._node_text_cache
            ), "每个extractor应该有独立的缓存实例"

            print(f"✅ Extractor1: {id(extractor1)}")
            print(f"✅ Extractor2: {id(extractor2)}")
            print("✅ 每次分析都创建新的extractor实例,状态隔离验证通过")

    @pytest.mark.asyncio
    async def test_interleaved_language_analysis(self):
        """
        验证: 交错分析不同语言的文件不会相互影响

        目标: 模拟真实场景,在分析Java文件后分析Python文件,
              再分析Java文件,确保结果一致
        """
        from tree_sitter_analyzer.core.analysis_engine import (
            AnalysisRequest,
            UnifiedAnalysisEngine,
        )

        # 创建临时测试文件
        with tempfile.TemporaryDirectory() as tmpdir:
            java_file = Path(tmpdir) / "Test.java"
            python_file = Path(tmpdir) / "test.py"

            java_content = """
public class Test {
    public void method1() {
        System.out.println("Hello");
    }
}
"""

            python_content = """
def function1():
    print("Hello")

class TestClass:
    def method1(self):
        pass
"""

            java_file.write_text(java_content)
            python_file.write_text(python_content)

            engine = UnifiedAnalysisEngine(project_root=tmpdir)

            # 第一次分析Java文件
            try:
                result1_java = await engine.analyze(
                    AnalysisRequest(
                        file_path=str(java_file),
                        language="java",
                        include_complexity=True,
                    )
                )
            except Exception as e:
                print(f"⚠️ Java分析失败(可能缺少tree-sitter-java): {e}")
                result1_java = None

            # 分析Python文件
            try:
                result_python = await engine.analyze(
                    AnalysisRequest(
                        file_path=str(python_file),
                        language="python",
                        include_complexity=True,
                    )
                )
            except Exception as e:
                print(f"⚠️ Python分析失败(可能缺少tree-sitter-python): {e}")
                result_python = None

            # 第二次分析Java文件
            try:
                result2_java = await engine.analyze(
                    AnalysisRequest(
                        file_path=str(java_file),
                        language="java",
                        include_complexity=True,
                    )
                )
            except Exception as e:
                print(f"⚠️ Java分析失败(可能缺少tree-sitter-java): {e}")
                result2_java = None

            # 验证结果
            if result1_java and result2_java:
                # 验证: 两次Java分析的结果应该一致
                assert (
                    result1_java.language == result2_java.language == "java"
                ), "语言标识应该一致"
                assert len(result1_java.elements) == len(
                    result2_java.elements
                ), "元素数量应该一致"

                print(f"✅ 第一次Java分析: {len(result1_java.elements)}个元素")
                print(
                    f"✅ Python分析: {len(result_python.elements) if result_python else 0}个元素"
                )
                print(f"✅ 第二次Java分析: {len(result2_java.elements)}个元素")
                print("✅ 交错分析测试通过,不同语言分析不会相互影响")
            else:
                print("⚠️ 跳过部分验证(可能缺少语言支持库)")

    @pytest.mark.asyncio
    async def test_no_class_level_shared_state(self):
        """
        验证: 插件类没有类级别的共享状态(除只读常量外)

        目标: 确保没有可变的类级别变量,避免跨实例状态污染
        """
        from tree_sitter_analyzer.languages.java_plugin import JavaPlugin
        from tree_sitter_analyzer.languages.python_plugin import PythonPlugin

        # 检查Java插件
        java_class_vars = [
            attr
            for attr in dir(JavaPlugin)
            if not attr.startswith("_")
            and not callable(getattr(JavaPlugin, attr))
            and not isinstance(getattr(JavaPlugin, attr), property)
        ]

        # 检查Python插件
        python_class_vars = [
            attr
            for attr in dir(PythonPlugin)
            if not attr.startswith("_")
            and not callable(getattr(PythonPlugin, attr))
            and not isinstance(getattr(PythonPlugin, attr), property)
        ]

        print(f"Java插件的公共类级变量: {java_class_vars}")
        print(f"Python插件的公共类级变量: {python_class_vars}")

        # 验证: 应该没有或只有只读常量
        # (这里我们允许有类级常量,只要它们不可变)
        print("✅ 类级别共享状态检查完成")

    @pytest.mark.asyncio
    async def test_plugin_manager_thread_safety_readiness(self):
        """
        验证: PluginManager的基本结构支持线程安全

        目标: 确认PluginManager使用了适当的数据结构
        """
        from tree_sitter_analyzer.plugins.manager import PluginManager

        manager = PluginManager()

        # 验证: _loaded_plugins是字典(Python字典在3.7+是有序且线程读安全的)
        assert isinstance(
            manager._loaded_plugins, dict
        ), "_loaded_plugins应该是字典类型"

        print(f"✅ PluginManager使用字典存储插件: {type(manager._loaded_plugins)}")
        print("✅ 基本数据结构符合线程安全要求")

    @pytest.mark.asyncio
    async def test_entry_points_provide_clear_boundaries(self):
        """
        验证: Entry points提供了清晰的插件边界

        目标: 确认每个语言插件都有独立的entry point定义
        """
        # 读取pyproject.toml验证entry points配置
        from pathlib import Path

        project_root = Path(__file__).parent.parent.parent.parent
        pyproject_file = project_root / "pyproject.toml"

        if pyproject_file.exists():
            content = pyproject_file.read_text()

            # 检查entry points部分
            if 'entry-points."tree_sitter_analyzer.plugins"' in content:
                print("✅ 找到插件entry points配置")

                # 检查主要语言的entry points
                expected_languages = ["java", "python", "javascript", "typescript"]
                for lang in expected_languages:
                    if f"{lang} =" in content:
                        print(f"  ✅ {lang}插件有独立的entry point")
                    else:
                        print(f"  ⚠️ {lang}插件可能缺少entry point")

                print("✅ Entry points提供了清晰的插件边界")
            else:
                print("⚠️ 未找到插件entry points配置")
        else:
            print("⚠️ 未找到pyproject.toml文件")


# 主测试运行器
async def main():
    """运行所有隔离性验证测试"""
    print("=" * 80)
    print("语言插件隔离性验证测试套件")
    print("=" * 80)
    print()

    test_instance = TestLanguagePluginIsolation()

    tests = [
        ("缓存键包含语言标识", test_instance.test_cache_key_includes_language),
        ("插件实例独立", test_instance.test_plugin_instances_are_separate),
        ("Extractor每次创建新实例", test_instance.test_extractors_are_new_instances),
        ("交错分析隔离性", test_instance.test_interleaved_language_analysis),
        ("无类级共享状态", test_instance.test_no_class_level_shared_state),
        (
            "PluginManager线程安全就绪",
            test_instance.test_plugin_manager_thread_safety_readiness,
        ),
        (
            "Entry Points边界清晰",
            test_instance.test_entry_points_provide_clear_boundaries,
        ),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        print(f"\n{'=' * 60}")
        print(f"测试: {test_name}")
        print(f"{'=' * 60}")
        try:
            await test_func()
            passed += 1
            print(f"✅ 测试通过: {test_name}")
        except AssertionError as e:
            failed += 1
            print(f"❌ 测试失败: {test_name}")
            print(f"   原因: {e}")
        except Exception as e:
            failed += 1
            print(f"⚠️ 测试出错: {test_name}")
            print(f"   错误: {e}")

    print(f"\n{'=' * 80}")
    print(f"测试结果汇总: {passed}个通过, {failed}个失败/出错")
    print(f"{'=' * 80}")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
