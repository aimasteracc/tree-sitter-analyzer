"""
C++ 插件集成测试：命名空间提取准确性验证。

测试覆盖 AC-CPP-001 ~ AC-CPP-005（规格见 openspec/changes/fix-plugin-namespace-state/specs/cpp-namespace-extraction/spec.md）
使用真实 tree-sitter 解析器，不使用 Mock。
"""

import pytest
import tree_sitter
import tree_sitter_cpp

from tree_sitter_analyzer.languages.cpp_plugin import CppElementExtractor, CppPlugin


# --------------------------------------------------------------------------
# 测试用 C++ 源码片段
# --------------------------------------------------------------------------

CPP_CLASS_IN_NAMESPACE = """\
namespace MyApp {
    class UserService {
    public:
        void doWork();
    };
}
"""

CPP_CLASS_NO_NAMESPACE = """\
class StandaloneClass {
public:
    void run();
};
"""

CPP_STRUCT_IN_NAMESPACE = """\
namespace Utils {
    struct Config {
        int timeout;
    };
}
"""

CPP_SEQUENTIAL_FILES = [
    (
        "FileA.cpp",
        """\
namespace Alpha {
    class ServiceA {};
}
""",
        "Alpha",
    ),
    (
        "FileB.cpp",
        """\
namespace Beta {
    class ServiceB {};
}
""",
        "Beta",
    ),
]


def _parse(code: str) -> "tree_sitter.Tree":
    """使用 tree-sitter-cpp 解析给定代码，返回语法树。"""
    language = tree_sitter.Language(tree_sitter_cpp.language())
    parser = tree_sitter.Parser(language)
    return parser.parse(code.encode("utf-8"))


class TestCppClassNamespaceExtraction:
    """AC-CPP-001~003: 验证 extract_classes() 产生正确的限定名。"""

    def test_class_in_namespace_full_qualified_name(self) -> None:
        """AC-CPP-001: 命名空间内的类 full_qualified_name 应包含命名空间前缀。"""
        extractor = CppElementExtractor()
        tree = _parse(CPP_CLASS_IN_NAMESPACE)
        classes = extractor.extract_classes(tree, CPP_CLASS_IN_NAMESPACE)

        assert len(classes) >= 1
        user_service = next(c for c in classes if c.name == "UserService")
        assert user_service.full_qualified_name == "MyApp::UserService", (
            f"期望 'MyApp::UserService'，实际为 '{user_service.full_qualified_name}'"
        )

    def test_class_in_namespace_package_name(self) -> None:
        """AC-CPP-002: 命名空间内的类 package_name 应为命名空间名称。"""
        extractor = CppElementExtractor()
        tree = _parse(CPP_CLASS_IN_NAMESPACE)
        classes = extractor.extract_classes(tree, CPP_CLASS_IN_NAMESPACE)

        user_service = next(c for c in classes if c.name == "UserService")
        assert user_service.package_name == "MyApp", (
            f"期望 'MyApp'，实际为 '{user_service.package_name}'"
        )

    def test_class_not_in_namespace_plain_name(self) -> None:
        """AC-CPP-003: 不在命名空间内的类 full_qualified_name 不应有额外前缀。"""
        extractor = CppElementExtractor()
        tree = _parse(CPP_CLASS_NO_NAMESPACE)
        classes = extractor.extract_classes(tree, CPP_CLASS_NO_NAMESPACE)

        assert len(classes) >= 1
        standalone = next(c for c in classes if c.name == "StandaloneClass")
        assert standalone.full_qualified_name == "StandaloneClass", (
            f"期望 'StandaloneClass'，实际为 '{standalone.full_qualified_name}'"
        )
        assert "::" not in standalone.full_qualified_name

    def test_struct_in_namespace_qualified_name(self) -> None:
        """struct 在命名空间内时也应有正确的限定名。"""
        extractor = CppElementExtractor()
        tree = _parse(CPP_STRUCT_IN_NAMESPACE)
        classes = extractor.extract_classes(tree, CPP_STRUCT_IN_NAMESPACE)

        assert len(classes) >= 1
        config = next(c for c in classes if c.name == "Config")
        assert "Utils" in config.full_qualified_name


class TestCppSequentialFilesNamespace:
    """AC-CPP-005: 连续分析两个不同命名空间的文件时，各自使用正确的命名空间。"""

    def test_sequential_files_use_correct_namespaces(self) -> None:
        """连续调用 extract_classes() 时，每次结果应反映该文件的命名空间。"""
        extractor = CppElementExtractor()

        for _filename, code, expected_ns in CPP_SEQUENTIAL_FILES:
            tree = _parse(code)
            classes = extractor.extract_classes(tree, code)

            assert len(classes) >= 1
            cls = classes[0]
            assert cls.package_name == expected_ns, (
                f"期望命名空间 '{expected_ns}'，实际为 '{cls.package_name}'"
            )


class TestCppExtractElementsNamespace:
    """通过 CppPlugin.extract_elements() 验证端到端流程。"""

    def test_extract_elements_classes_have_namespace(self) -> None:
        """extract_elements() 返回的类列表中，命名空间内的类应有正确的限定名。"""
        plugin = CppPlugin()
        tree = _parse(CPP_CLASS_IN_NAMESPACE)
        result = plugin.extract_elements(tree, CPP_CLASS_IN_NAMESPACE)

        classes = result.get("classes", [])
        user_service = next((c for c in classes if c.name == "UserService"), None)
        assert user_service is not None
        assert user_service.full_qualified_name == "MyApp::UserService"
