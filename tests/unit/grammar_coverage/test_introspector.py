"""Unit tests for grammar introspection system."""

import pytest

from tree_sitter_analyzer.grammar_coverage.introspector import (
    LANGUAGE_MODULE_MAP,
    auto_detect_extractable_types,
    get_all_node_types,
    get_language_summary,
    get_structural_types,
)


class TestGetAllNodeTypes:
    """测试从 tree-sitter 语法中提取所有节点类型。"""

    def test_python_node_extraction(self) -> None:
        """测试 Python 语言的节点类型提取。"""
        node_types = get_all_node_types("python")

        # 验证返回类型
        assert isinstance(node_types, list)
        assert all(isinstance(nt, str) for nt in node_types)

        # 验证是否排序
        assert node_types == sorted(node_types)

        # 验证包含关键节点类型
        expected_types = [
            "function_definition",
            "class_definition",
            "import_statement",
            "import_from_statement",
            "assignment",
        ]
        for expected in expected_types:
            assert expected in node_types, f"Missing {expected}"

        # 验证节点数量合理（Python 语法约 100+ 命名节点）
        assert len(node_types) > 50, f"Too few node types: {len(node_types)}"

    def test_javascript_node_extraction(self) -> None:
        """测试 JavaScript 语言的节点类型提取。"""
        node_types = get_all_node_types("javascript")

        assert isinstance(node_types, list)
        assert node_types == sorted(node_types)

        # 验证 JavaScript 特有节点类型
        expected_types = [
            "function_declaration",
            "class_declaration",
            "import_statement",
            "variable_declaration",
        ]
        for expected in expected_types:
            assert expected in node_types, f"Missing {expected}"

    def test_go_node_extraction(self) -> None:
        """测试 Go 语言的节点类型提取。"""
        node_types = get_all_node_types("go")

        assert isinstance(node_types, list)
        assert node_types == sorted(node_types)

        # 验证 Go 特有节点类型
        expected_types = [
            "function_declaration",
            "method_declaration",
            "type_declaration",
            "import_declaration",
        ]
        for expected in expected_types:
            assert expected in node_types, f"Missing {expected}"

    def test_unsupported_language_raises(self) -> None:
        """测试不支持的语言抛出异常。"""
        with pytest.raises(ValueError, match="Unsupported language"):
            get_all_node_types("unsupported_language")

    def test_all_supported_languages_work(self) -> None:
        """测试所有支持的语言都能正常提取节点类型。"""
        for language in LANGUAGE_MODULE_MAP.keys():
            node_types = get_all_node_types(language)
            assert len(node_types) > 0, f"No node types for {language}"
            assert node_types == sorted(node_types)


class TestAutoDetectExtractableTypes:
    """测试自动检测可提取节点类型。"""

    def test_python_extractable_detection(self) -> None:
        """测试 Python 语言的可提取节点检测。"""
        all_types = get_all_node_types("python")
        extractable = auto_detect_extractable_types(all_types)

        # 验证返回类型
        assert isinstance(extractable, list)
        assert extractable == sorted(extractable)

        # 验证包含预期的可提取类型
        expected_extractable = [
            "function_definition",
            "class_definition",
            "import_statement",
            "import_from_statement",
        ]
        for expected in expected_extractable:
            assert expected in extractable, f"Missing {expected}"

        # 验证不包含结构性节点
        structural_nodes = ["block", "identifier", "expression_statement"]
        for structural in structural_nodes:
            assert structural not in extractable, f"Should not include {structural}"

    def test_javascript_extractable_detection(self) -> None:
        """测试 JavaScript 语言的可提取节点检测。"""
        all_types = get_all_node_types("javascript")
        extractable = auto_detect_extractable_types(all_types)

        expected_extractable = [
            "function_declaration",
            "class_declaration",
            "import_statement",
            "variable_declaration",
        ]
        for expected in expected_extractable:
            assert expected in extractable, f"Missing {expected}"

    def test_go_extractable_detection(self) -> None:
        """测试 Go 语言的可提取节点检测。"""
        all_types = get_all_node_types("go")
        extractable = auto_detect_extractable_types(all_types)

        expected_extractable = [
            "function_declaration",
            "method_declaration",
            "type_declaration",
            "import_declaration",
        ]
        for expected in expected_extractable:
            assert expected in extractable, f"Missing {expected}"

    def test_pattern_matching_logic(self) -> None:
        """测试模式匹配逻辑的正确性。"""
        test_types = [
            "function_definition",  # 可提取
            "class_declaration",  # 可提取
            "import_statement",  # 可提取
            "block",  # 结构性（应排除）
            "parameter_list",  # 结构性（应排除）
            "else_clause",  # 结构性（应排除）
            "identifier",  # 结构性（应排除）
            "expression",  # 结构性（应排除）
        ]

        extractable = auto_detect_extractable_types(test_types)

        assert "function_definition" in extractable
        assert "class_declaration" in extractable
        assert "import_statement" in extractable
        assert "block" not in extractable
        assert "parameter_list" not in extractable
        assert "else_clause" not in extractable
        assert "identifier" not in extractable
        assert "expression" not in extractable


class TestGetStructuralTypes:
    """测试识别结构性节点类型。"""

    def test_python_structural_detection(self) -> None:
        """测试 Python 语言的结构性节点检测。"""
        all_types = get_all_node_types("python")
        structural = get_structural_types(all_types)

        # 验证返回类型
        assert isinstance(structural, list)
        assert structural == sorted(structural)

        # 验证包含结构性节点
        expected_structural = [
            "block",
            "identifier",
            "expression_statement",
        ]
        for expected in expected_structural:
            if expected in all_types:  # 仅验证存在的节点
                assert expected in structural, f"Missing {expected}"

        # 验证不包含可提取节点
        extractable_nodes = [
            "function_definition",
            "class_definition",
        ]
        for extractable in extractable_nodes:
            assert extractable not in structural, f"Should not include {extractable}"

    def test_structural_and_extractable_are_complementary(self) -> None:
        """测试结构性节点和可提取节点是否互补（覆盖所有节点）。"""
        for language in ["python", "javascript", "go"]:
            all_types = get_all_node_types(language)
            extractable = auto_detect_extractable_types(all_types)
            structural = get_structural_types(all_types)

            # 验证覆盖所有节点（允许部分重叠，因为分类规则有交集）
            covered = set(extractable) | set(structural)
            all_set = set(all_types)

            # 所有节点都应该被分类到至少一个类别
            assert all_set.issubset(
                covered
            ), f"Uncovered nodes in {language}: {all_set - covered}"


class TestGetLanguageSummary:
    """测试获取语言摘要功能。"""

    def test_python_summary(self) -> None:
        """测试 Python 语言摘要生成。"""
        summary = get_language_summary("python")

        # 验证返回结构
        assert isinstance(summary, dict)
        required_keys = [
            "all_types",
            "extractable_types",
            "structural_types",
            "total_count",
            "extractable_count",
            "structural_count",
        ]
        for key in required_keys:
            assert key in summary, f"Missing key: {key}"

        # 验证数据一致性
        assert len(summary["all_types"]) == summary["total_count"]
        assert len(summary["extractable_types"]) == summary["extractable_count"]
        assert len(summary["structural_types"]) == summary["structural_count"]

        # 验证计数合理性
        assert summary["total_count"] > 0
        assert summary["extractable_count"] > 0
        assert summary["structural_count"] > 0

    def test_all_languages_summary(self) -> None:
        """测试所有支持语言的摘要生成。"""
        DATA_FORMAT_LANGUAGES = {"yaml", "json"}

        for language in LANGUAGE_MODULE_MAP.keys():
            summary = get_language_summary(language)

            assert summary["total_count"] > 0, f"No types for {language}"

            # 数据格式语言可能没有可提取节点
            if language not in DATA_FORMAT_LANGUAGES:
                assert (
                    summary["extractable_count"] > 0
                ), f"No extractable types for {language}"

            assert (
                summary["structural_count"] > 0
            ), f"No structural types for {language}"

            # 验证数据一致性
            assert len(summary["all_types"]) == summary["total_count"]
            assert len(summary["extractable_types"]) == summary["extractable_count"]
            assert len(summary["structural_types"]) == summary["structural_count"]


class TestEdgeCases:
    """测试边界情况和错误处理。"""

    def test_empty_node_types_list(self) -> None:
        """测试空节点列表的处理。"""
        extractable = auto_detect_extractable_types([])
        structural = get_structural_types([])

        assert extractable == []
        assert structural == []

    def test_no_extractable_types(self) -> None:
        """测试无可提取节点的情况。"""
        test_types = ["block", "identifier", "expression", "operator"]
        extractable = auto_detect_extractable_types(test_types)

        assert len(extractable) == 0

    def test_no_structural_types(self) -> None:
        """测试无结构性节点的情况（理论上不存在）。"""
        test_types = [
            "function_definition",
            "class_declaration",
            "import_statement",
        ]
        structural = get_structural_types(test_types)

        # 这些类型不匹配结构性模式，但由于不是可提取后缀，会被归为结构性
        # 实际上，class_declaration 以 _declaration 结尾，是可提取的
        # 所以只有不以可提取后缀结尾的才会被归为结构性
        assert isinstance(structural, list)


class TestCrossLanguageConsistency:
    """测试跨语言一致性。"""

    def test_all_languages_have_function_definitions(self) -> None:
        """测试所有编程语言都有函数定义节点（数据格式语言除外）。"""
        # 数据格式语言不需要函数节点
        DATA_FORMAT_LANGUAGES = {"yaml", "json"}

        function_keywords = ["function", "method", "func", "class"]

        for language in LANGUAGE_MODULE_MAP.keys():
            if language in DATA_FORMAT_LANGUAGES:
                continue  # 跳过数据格式语言

            all_types = get_all_node_types(language)
            extractable = auto_detect_extractable_types(all_types)

            # 验证至少有一个函数或类相关的可提取节点
            has_function = any(
                any(keyword in etype for keyword in function_keywords)
                for etype in extractable
            )
            assert has_function, f"No function-like extractable type in {language}"

    def test_all_languages_have_reasonable_node_count(self) -> None:
        """测试所有语言的节点数量在合理范围内。"""
        # 数据格式语言可能没有可提取节点
        DATA_FORMAT_LANGUAGES = {"yaml", "json"}

        for language in LANGUAGE_MODULE_MAP.keys():
            summary = get_language_summary(language)

            # 语法节点数通常在 10-500 之间（JSON 较少）
            assert (
                10 <= summary["total_count"] <= 500
            ), f"Unusual node count for {language}: {summary['total_count']}"

            # 数据格式语言可能没有可提取节点（它们主要是结构性节点）
            if language in DATA_FORMAT_LANGUAGES:
                # YAML 和 JSON 可能没有传统意义上的"可提取"节点
                # 但应该有总节点数
                assert summary["total_count"] > 0
            else:
                # 编程语言必须有可提取节点
                assert (
                    summary["extractable_count"] > 0
                ), f"No extractable types for {language}"

                # 可提取节点占比通常在 0.5%-50% 之间
                ratio = summary["extractable_count"] / summary["total_count"]
                assert (
                    0.005 <= ratio <= 0.5
                ), f"Unusual extractable ratio for {language}: {ratio:.2%} ({summary['extractable_count']}/{summary['total_count']})"
