#!/usr/bin/env python3
"""
Basic tests for Python plugin

Pythonプラグインの基本テスト
"""

from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.languages.python_plugin import (
    PythonElementExtractor,
    PythonPlugin,
)


class TestPythonPlugin:
    """PythonPluginの基本テストクラス"""

    @pytest.fixture
    def plugin(self):
        """Pluginインスタンスを提供"""
        return PythonPlugin()

    def test_plugin_properties(self, plugin):
        """プラグインプロパティテスト"""
        assert plugin.get_language_name() == "python"
        assert ".py" in plugin.get_file_extensions()
        assert ".pyw" in plugin.get_file_extensions()

    def test_create_extractor(self, plugin):
        """エクストラクタ作成テスト"""
        extractor = plugin.create_extractor()
        assert isinstance(extractor, PythonElementExtractor)

    def test_is_applicable_method(self, plugin):
        """is_applicableメソッドテスト"""
        # Python関連ファイル
        assert plugin.is_applicable("test.py")
        assert plugin.is_applicable("script.pyw")

        # 非Python関連ファイル
        assert not plugin.is_applicable("test.java")
        assert not plugin.is_applicable("script.js")


class TestPythonElementExtractor:
    """PythonElementExtractorの基本テストクラス"""

    @pytest.fixture
    def extractor(self):
        """Extractorインスタンスを提供"""
        return PythonElementExtractor()

    def test_extractor_creation(self, extractor):
        """エクストラクタ作成テスト"""
        assert extractor is not None
        assert hasattr(extractor, "extract_functions")
        assert hasattr(extractor, "extract_classes")
        assert hasattr(extractor, "extract_variables")
        assert hasattr(extractor, "extract_imports")

    def test_extract_methods_return_lists(self, extractor):
        """抽出メソッドがリストを返すことを確認"""
        mock_tree = MagicMock()
        mock_language = MagicMock()

        # モックが適切に設定されているかテスト
        functions = extractor.extract_functions(mock_tree, mock_language)
        classes = extractor.extract_classes(mock_tree, mock_language)
        variables = extractor.extract_variables(mock_tree, mock_language)
        imports = extractor.extract_imports(mock_tree, mock_language)

        assert isinstance(functions, list)
        assert isinstance(classes, list)
        assert isinstance(variables, list)
        assert isinstance(imports, list)

    def test_extract_without_language(self, extractor):
        """言語なしでの抽出テスト"""
        mock_tree = MagicMock()

        # 言語がNoneの場合
        result = extractor.extract_functions(mock_tree, None)
        assert isinstance(result, list)
        assert len(result) == 0
