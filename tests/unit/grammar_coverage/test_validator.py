#!/usr/bin/env python3
"""
Unit Tests for Grammar Coverage Validator

测试 grammar coverage 验证逻辑，包括：
- CoverageReport 数据结构
- 节点类型统计
- 覆盖率计算
- 报告生成
- CI 阈值检查

测试策略：
- 使用 mock 避免依赖真实文件系统
- 测试边缘情况（空文件、100% 覆盖、0% 覆盖）
- 验证错误处理（文件不存在、不支持的语言）
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from tree_sitter_analyzer.grammar_coverage.validator import (
    CoverageReport,
    check_coverage_threshold,
    generate_coverage_report,
    validate_plugin_coverage_sync,
)


class TestCoverageReport:
    """测试 CoverageReport 数据结构"""

    def test_coverage_report_creation(self):
        """测试创建 CoverageReport 实例"""
        report = CoverageReport(
            language="python",
            total_node_types=50,
            covered_node_types=48,
            coverage_percentage=96.0,
            uncovered_types=["async_for_statement", "match_statement"],
            corpus_file="/path/to/corpus_python.py",
            expected_node_types={"function_definition": 10},
            actual_node_types={"function_definition": 10, "class_definition": 5},
        )

        assert report.language == "python"
        assert report.total_node_types == 50
        assert report.covered_node_types == 48
        assert report.coverage_percentage == 96.0
        assert len(report.uncovered_types) == 2
        assert "async_for_statement" in report.uncovered_types

    def test_coverage_report_zero_coverage(self):
        """测试 0% 覆盖率的报告"""
        report = CoverageReport(
            language="rust",
            total_node_types=30,
            covered_node_types=0,
            coverage_percentage=0.0,
            uncovered_types=[f"type_{i}" for i in range(30)],
            corpus_file="/path/to/corpus_rust.rs",
            expected_node_types={},
            actual_node_types={f"type_{i}": 1 for i in range(30)},
        )

        assert report.coverage_percentage == 0.0
        assert len(report.uncovered_types) == 30

    def test_coverage_report_full_coverage(self):
        """测试 100% 覆盖率的报告"""
        report = CoverageReport(
            language="javascript",
            total_node_types=45,
            covered_node_types=45,
            coverage_percentage=100.0,
            uncovered_types=[],
            corpus_file="/path/to/corpus_javascript.js",
            expected_node_types={"function_declaration": 5},
            actual_node_types={"function_declaration": 5, "class_declaration": 3},
        )

        assert report.coverage_percentage == 100.0
        assert len(report.uncovered_types) == 0


class TestGenerateCoverageReport:
    """测试 generate_coverage_report 函数"""

    def test_generate_report_with_uncovered_types(self):
        """测试生成包含未覆盖类型的报告"""
        report = CoverageReport(
            language="python",
            total_node_types=50,
            covered_node_types=48,
            coverage_percentage=96.0,
            uncovered_types=["async_for_statement", "match_statement"],
            corpus_file="/path/to/corpus_python.py",
            expected_node_types={},
            actual_node_types={},
        )

        output = generate_coverage_report(report)

        assert "Python: 96.0%" in output
        assert "(48/50 node types covered)" in output
        assert "Uncovered node types (2):" in output
        assert "- async_for_statement" in output
        assert "- match_statement" in output
        assert "Corpus file: /path/to/corpus_python.py" in output

    def test_generate_report_full_coverage(self):
        """测试生成 100% 覆盖的报告"""
        report = CoverageReport(
            language="javascript",
            total_node_types=45,
            covered_node_types=45,
            coverage_percentage=100.0,
            uncovered_types=[],
            corpus_file="/path/to/corpus_javascript.js",
            expected_node_types={},
            actual_node_types={},
        )

        output = generate_coverage_report(report)

        assert "Javascript: 100.0%" in output
        assert "(45/45 node types covered)" in output
        assert "All node types covered!" in output
        assert "Uncovered node types" not in output

    def test_generate_report_zero_coverage(self):
        """测试生成 0% 覆盖的报告"""
        report = CoverageReport(
            language="rust",
            total_node_types=30,
            covered_node_types=0,
            coverage_percentage=0.0,
            uncovered_types=[f"type_{i}" for i in range(3)],
            corpus_file="/path/to/corpus_rust.rs",
            expected_node_types={},
            actual_node_types={},
        )

        output = generate_coverage_report(report)

        assert "Rust: 0.0%" in output
        assert "(0/30 node types covered)" in output
        assert "Uncovered node types (3):" in output


class TestCheckCoverageThreshold:
    """测试 check_coverage_threshold 函数"""

    def test_coverage_meets_threshold(self):
        """测试覆盖率达到阈值"""
        assert check_coverage_threshold(100.0, 100.0) is True
        assert check_coverage_threshold(95.5, 90.0) is True
        assert check_coverage_threshold(80.0, 80.0) is True

    def test_coverage_below_threshold(self):
        """测试覆盖率低于阈值"""
        assert check_coverage_threshold(99.9, 100.0) is False
        assert check_coverage_threshold(75.0, 80.0) is False
        assert check_coverage_threshold(0.0, 100.0) is False

    def test_threshold_defaults_to_100(self):
        """测试默认阈值为 100%"""
        assert check_coverage_threshold(100.0) is True
        assert check_coverage_threshold(99.9) is False

    def test_edge_cases(self):
        """测试边缘情况"""
        assert check_coverage_threshold(0.0, 0.0) is True
        assert check_coverage_threshold(100.0, 0.0) is True
        assert check_coverage_threshold(50.0, 50.0) is True
        assert check_coverage_threshold(49.999, 50.0) is False


class TestCountNodeTypes:
    """测试 _count_node_types 函数（通过 validate_plugin_coverage 间接测试）"""

    def test_count_node_types_with_mock_tree(self):
        """测试节点类型统计（使用 mock tree）"""
        from tree_sitter_analyzer.grammar_coverage.validator import _count_node_types

        # 创建 mock node hierarchy
        root = MagicMock()
        root.is_named = True
        root.type = "module"

        child1 = MagicMock()
        child1.is_named = True
        child1.type = "function_definition"
        child1.children = []

        child2 = MagicMock()
        child2.is_named = True
        child2.type = "function_definition"
        child2.children = []

        child3 = MagicMock()
        child3.is_named = True
        child3.type = "class_definition"
        child3.children = []

        root.children = [child1, child2, child3]

        counts = _count_node_types(root)

        assert counts["module"] == 1
        assert counts["function_definition"] == 2
        assert counts["class_definition"] == 1

    def test_count_node_types_ignores_unnamed_nodes(self):
        """测试统计时忽略未命名节点"""
        from tree_sitter_analyzer.grammar_coverage.validator import _count_node_types

        root = MagicMock()
        root.is_named = True
        root.type = "module"

        # Unnamed node (如括号、逗号)
        unnamed = MagicMock()
        unnamed.is_named = False
        unnamed.type = "("
        unnamed.children = []

        named = MagicMock()
        named.is_named = True
        named.type = "function_definition"
        named.children = []

        root.children = [unnamed, named]

        counts = _count_node_types(root)

        assert "(" not in counts
        assert counts["function_definition"] == 1

    def test_count_node_types_nested_structure(self):
        """测试嵌套结构的节点统计"""
        from tree_sitter_analyzer.grammar_coverage.validator import _count_node_types

        root = MagicMock()
        root.is_named = True
        root.type = "module"

        func = MagicMock()
        func.is_named = True
        func.type = "function_definition"

        params = MagicMock()
        params.is_named = True
        params.type = "parameters"
        params.children = []

        func.children = [params]
        root.children = [func]

        counts = _count_node_types(root)

        assert counts["module"] == 1
        assert counts["function_definition"] == 1
        assert counts["parameters"] == 1


class TestGetTreeSitterModule:
    """测试 _get_tree_sitter_module 函数"""

    def test_get_supported_language_modules(self):
        """测试获取支持的语言模块"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_tree_sitter_module,
        )

        # 测试一些常见语言
        with patch("builtins.__import__") as mock_import:
            mock_import.return_value = MagicMock()

            _get_tree_sitter_module("python")
            mock_import.assert_called_with("tree_sitter_python")

            _get_tree_sitter_module("javascript")
            mock_import.assert_called_with("tree_sitter_javascript")

    def test_get_unsupported_language_raises_error(self):
        """测试不支持的语言抛出 ImportError"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_tree_sitter_module,
        )

        with pytest.raises(ImportError, match="No tree-sitter module found"):
            _get_tree_sitter_module("unsupported_language")


class TestGetLanguageExtension:
    """测试 _get_language_extension 函数"""

    def test_get_supported_extensions(self):
        """测试获取支持的文件扩展名"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_language_extension,
        )

        assert _get_language_extension("python") == "py"
        assert _get_language_extension("javascript") == "js"
        assert _get_language_extension("typescript") == "ts"
        assert _get_language_extension("java") == "java"
        assert _get_language_extension("c") == "c"
        assert _get_language_extension("cpp") == "cpp"

    def test_get_unsupported_extension_raises_error(self):
        """测试不支持的语言抛出 ValueError"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_language_extension,
        )

        with pytest.raises(ValueError, match="Unsupported language"):
            _get_language_extension("unsupported_language")


class TestLoadExpectedJson:
    """测试 _load_expected_json 函数"""

    def test_load_valid_json(self):
        """测试加载有效的 JSON 文件"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _load_expected_json,
        )

        mock_json_data = {
            "language": "python",
            "node_types": {"function_definition": 10, "class_definition": 5},
        }

        with patch("pathlib.Path.exists", return_value=True):
            with patch(
                "builtins.open", mock_open(read_data=json.dumps(mock_json_data))
            ):
                data = _load_expected_json(Path("/fake/path/expected.json"))

        assert data["language"] == "python"
        assert data["node_types"]["function_definition"] == 10

    def test_load_missing_file_raises_error(self):
        """测试文件不存在抛出 FileNotFoundError"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _load_expected_json,
        )

        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(FileNotFoundError, match="Expected file not found"):
                _load_expected_json(Path("/fake/path/expected.json"))

    def test_load_invalid_json_raises_error(self):
        """测试无效 JSON 抛出 JSONDecodeError"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _load_expected_json,
        )

        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data="invalid json {")):
                with pytest.raises(json.JSONDecodeError):
                    _load_expected_json(Path("/fake/path/expected.json"))


class TestParseCorpusFile:
    """测试 _parse_corpus_file 函数"""

    @patch("tree_sitter_analyzer.grammar_coverage.validator._get_tree_sitter_module")
    @patch("tree_sitter.Language")
    @patch("tree_sitter.Parser")
    def test_parse_corpus_file_success(
        self, mock_parser_class, mock_language_class, mock_get_module
    ):
        """测试成功解析 corpus 文件"""
        from tree_sitter_analyzer.grammar_coverage.validator import _parse_corpus_file

        # Mock tree-sitter components
        mock_module = MagicMock()
        mock_get_module.return_value = mock_module

        mock_lang = MagicMock()
        mock_language_class.return_value = mock_lang

        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser

        # Mock tree structure
        root = MagicMock()
        root.is_named = True
        root.type = "module"
        root.children = []

        mock_tree = MagicMock()
        mock_tree.root_node = root
        mock_parser.parse.return_value = mock_tree

        # Mock file system
        corpus_path = Path("/fake/corpus_python.py")
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value="def foo(): pass"):
                result = _parse_corpus_file(corpus_path, "python")

        assert "module" in result
        assert result["module"] == 1

    def test_parse_corpus_file_not_found(self):
        """测试文件不存在抛出 FileNotFoundError"""
        from tree_sitter_analyzer.grammar_coverage.validator import _parse_corpus_file

        corpus_path = Path("/fake/nonexistent.py")
        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(FileNotFoundError, match="Corpus file not found"):
                _parse_corpus_file(corpus_path, "python")


class TestValidatePluginCoverage:
    """测试 validate_plugin_coverage 函数（集成测试风格，使用真实文件）"""

    @pytest.mark.skipif(
        not Path(__file__).parent.parent.parent.parent.joinpath(
            "tests/golden/corpus_python.py"
        ).exists(),
        reason="Golden corpus files not available",
    )
    def test_validate_python_coverage_real_files(self):
        """测试使用真实 Python corpus 文件验证覆盖率"""
        # 此测试依赖真实的 corpus_python.py 和 corpus_python_expected.json
        # 当前插件覆盖率为 0%（_get_covered_node_types_from_plugin 返回空集）
        report = validate_plugin_coverage_sync("python")

        assert report.language == "python"
        assert report.total_node_types > 0
        assert report.covered_node_types == 0  # TODO: Phase 1.2 后应该 > 0
        assert report.coverage_percentage == 0.0
        assert len(report.uncovered_types) == report.total_node_types

    @patch("tree_sitter_analyzer.grammar_coverage.validator._parse_corpus_file")
    @patch("tree_sitter_analyzer.grammar_coverage.validator._load_expected_json")
    @patch(
        "tree_sitter_analyzer.grammar_coverage.validator._get_covered_node_types_from_plugin"
    )
    @patch("tree_sitter_analyzer.grammar_coverage.validator._get_language_extension")
    def test_validate_plugin_coverage_mocked(
        self,
        mock_get_ext,
        mock_get_covered,
        mock_load_expected,
        mock_parse_corpus,
    ):
        """测试 validate_plugin_coverage 逻辑（使用 mock）"""
        # Setup mocks
        mock_get_ext.return_value = "py"
        mock_parse_corpus.return_value = {
            "function_definition": 10,
            "class_definition": 5,
            "lambda": 3,
        }
        mock_load_expected.return_value = {
            "language": "python",
            "node_types": {"function_definition": 10, "class_definition": 5},
        }
        mock_get_covered.return_value = {"function_definition", "class_definition"}

        with patch("pathlib.Path.exists", return_value=True):
            report = validate_plugin_coverage_sync("python")

        assert report.language == "python"
        assert report.total_node_types == 3
        assert report.covered_node_types == 2
        assert report.coverage_percentage == pytest.approx(66.67, rel=0.1)
        assert "lambda" in report.uncovered_types


class TestEdgeCases:
    """测试边缘情况和错误处理"""

    def test_empty_corpus_file(self):
        """测试空的 corpus 文件"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _count_node_types,
        )

        # 空文件只有 root module 节点
        root = MagicMock()
        root.is_named = True
        root.type = "module"
        root.children = []

        counts = _count_node_types(root)

        assert len(counts) == 1
        assert counts["module"] == 1

    def test_coverage_with_zero_total_types(self):
        """测试总类型数为 0 的情况"""
        report = CoverageReport(
            language="empty",
            total_node_types=0,
            covered_node_types=0,
            coverage_percentage=0.0,
            uncovered_types=[],
            corpus_file="/path/to/empty.txt",
            expected_node_types={},
            actual_node_types={},
        )

        assert report.coverage_percentage == 0.0
        output = generate_coverage_report(report)
        assert "0/0 node types covered" in output
