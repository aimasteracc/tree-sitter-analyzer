"""
サンプルテストケース実装例

このファイルは、tree-sitter-analyzerプロジェクトのテストケースを作成する際の
参考として使用できる完全なサンプル実装です。
"""

import pytest
import tempfile
import os
from pathlib import Path
from typing import Dict, List, Any
import json

from tree_sitter_analyzer.core.enhanced_analysis_engine import EnhancedAnalysisEngine
from tree_sitter_analyzer.plugins.manager import PluginManager
from tree_sitter_analyzer.models import AnalysisRequest, AnalysisResult
from tree_sitter_analyzer.formatters.base import BaseFormatter


class TestDataManager:
    """テストデータ管理クラス"""
    
    def __init__(self):
        self.test_files = {}
        self.temp_files = []
    
    def create_test_files(self) -> Dict[str, str]:
        """各言語のテストファイルを作成"""
        
        # Python テストファイル
        python_content = '''
"""
サンプルPythonファイル
テスト用のコードサンプル
"""

import os
import sys
from typing import List, Dict, Optional

class Calculator:
    """計算機クラス"""
    
    def __init__(self, initial_value: int = 0):
        """
        計算機を初期化
        
        Args:
            initial_value: 初期値
        """
        self.value = initial_value
        self._history = []
    
    def add(self, x: int) -> int:
        """加算を実行"""
        self.value += x
        self._history.append(f"add({x})")
        return self.value
    
    def subtract(self, x: int) -> int:
        """減算を実行"""
        self.value -= x
        self._history.append(f"subtract({x})")
        return self.value
    
    @property
    def history(self) -> List[str]:
        """計算履歴を取得"""
        return self._history.copy()
    
    @staticmethod
    def multiply(a: int, b: int) -> int:
        """静的メソッド: 乗算"""
        return a * b

def calculate_factorial(n: int) -> int:
    """階乗を計算する関数"""
    if n <= 1:
        return 1
    return n * calculate_factorial(n - 1)

async def async_operation(data: List[int]) -> Dict[str, Any]:
    """非同期操作のサンプル"""
    import asyncio
    await asyncio.sleep(0.1)
    return {
        "sum": sum(data),
        "count": len(data),
        "average": sum(data) / len(data) if data else 0
    }

# グローバル変数
GLOBAL_CONSTANT = 42
global_variable = "test"

if __name__ == "__main__":
    calc = Calculator(10)
    result = calc.add(5)
    print(f"Result: {result}")
        '''
        
        # JavaScript テストファイル
        javascript_content = '''
/**
 * サンプルJavaScriptファイル
 * テスト用のコードサンプル
 */

const fs = require('fs');
const path = require('path');

/**
 * 計算機クラス
 */
class Calculator {
    /**
     * コンストラクタ
     * @param {number} initialValue - 初期値
     */
    constructor(initialValue = 0) {
        this.value = initialValue;
        this._history = [];
    }
    
    /**
     * 加算を実行
     * @param {number} x - 加算する値
     * @returns {number} 計算結果
     */
    add(x) {
        this.value += x;
        this._history.push(`add(${x})`);
        return this.value;
    }
    
    /**
     * 減算を実行
     * @param {number} x - 減算する値
     * @returns {number} 計算結果
     */
    subtract(x) {
        this.value -= x;
        this._history.push(`subtract(${x})`);
        return this.value;
    }
    
    /**
     * 履歴を取得
     * @returns {Array<string>} 計算履歴
     */
    get history() {
        return [...this._history];
    }
    
    /**
     * 静的メソッド: 乗算
     * @param {number} a - 値1
     * @param {number} b - 値2
     * @returns {number} 乗算結果
     */
    static multiply(a, b) {
        return a * b;
    }
}

/**
 * 階乗を計算する関数
 * @param {number} n - 計算対象の数値
 * @returns {number} 階乗の結果
 */
function calculateFactorial(n) {
    if (n <= 1) {
        return 1;
    }
    return n * calculateFactorial(n - 1);
}

/**
 * 非同期操作のサンプル
 * @param {Array<number>} data - データ配列
 * @returns {Promise<Object>} 処理結果
 */
async function asyncOperation(data) {
    await new Promise(resolve => setTimeout(resolve, 100));
    return {
        sum: data.reduce((a, b) => a + b, 0),
        count: data.length,
        average: data.length > 0 ? data.reduce((a, b) => a + b, 0) / data.length : 0
    };
}

// グローバル変数
const GLOBAL_CONSTANT = 42;
let globalVariable = "test";

// アロー関数
const arrowFunction = (x, y) => x + y;

// 即座実行関数
(function() {
    console.log("IIFE executed");
})();

// メイン処理
if (require.main === module) {
    const calc = new Calculator(10);
    const result = calc.add(5);
    console.log(`Result: ${result}`);
}
        '''
        
        # Java テストファイル
        java_content = '''
/**
 * サンプルJavaファイル
 * テスト用のコードサンプル
 */

package com.example.calculator;

import java.util.List;
import java.util.ArrayList;
import java.util.concurrent.CompletableFuture;

/**
 * 計算機クラス
 */
public class Calculator {
    private int value;
    private List<String> history;
    
    public static final int GLOBAL_CONSTANT = 42;
    
    /**
     * コンストラクタ
     * @param initialValue 初期値
     */
    public Calculator(int initialValue) {
        this.value = initialValue;
        this.history = new ArrayList<>();
    }
    
    /**
     * デフォルトコンストラクタ
     */
    public Calculator() {
        this(0);
    }
    
    /**
     * 加算を実行
     * @param x 加算する値
     * @return 計算結果
     */
    public int add(int x) {
        this.value += x;
        this.history.add("add(" + x + ")");
        return this.value;
    }
    
    /**
     * 減算を実行
     * @param x 減算する値
     * @return 計算結果
     */
    public int subtract(int x) {
        this.value -= x;
        this.history.add("subtract(" + x + ")");
        return this.value;
    }
    
    /**
     * 履歴を取得
     * @return 計算履歴
     */
    public List<String> getHistory() {
        return new ArrayList<>(this.history);
    }
    
    /**
     * 静的メソッド: 乗算
     * @param a 値1
     * @param b 値2
     * @return 乗算結果
     */
    public static int multiply(int a, int b) {
        return a * b;
    }
    
    /**
     * プライベートメソッド
     */
    private void resetHistory() {
        this.history.clear();
    }
    
    /**
     * 値を取得
     * @return 現在の値
     */
    public int getValue() {
        return this.value;
    }
    
    /**
     * 値を設定
     * @param value 設定する値
     */
    public void setValue(int value) {
        this.value = value;
    }
}

/**
 * ユーティリティクラス
 */
class MathUtils {
    /**
     * 階乗を計算する関数
     * @param n 計算対象の数値
     * @return 階乗の結果
     */
    public static long calculateFactorial(int n) {
        if (n <= 1) {
            return 1;
        }
        return n * calculateFactorial(n - 1);
    }
    
    /**
     * 非同期操作のサンプル
     * @param data データ配列
     * @return 処理結果のFuture
     */
    public static CompletableFuture<String> asyncOperation(List<Integer> data) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                Thread.sleep(100);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            
            int sum = data.stream().mapToInt(Integer::intValue).sum();
            double average = data.isEmpty() ? 0 : (double) sum / data.size();
            
            return String.format("Sum: %d, Count: %d, Average: %.2f", 
                               sum, data.size(), average);
        });
    }
}

/**
 * メインクラス
 */
public class Main {
    public static void main(String[] args) {
        Calculator calc = new Calculator(10);
        int result = calc.add(5);
        System.out.println("Result: " + result);
    }
}
        '''
        
        # 一時ファイルの作成
        test_files = {
            "python": (python_content, ".py"),
            "javascript": (javascript_content, ".js"),
            "java": (java_content, ".java")
        }
        
        for language, (content, extension) in test_files.items():
            temp_file = tempfile.NamedTemporaryFile(
                mode='w', 
                suffix=extension, 
                delete=False,
                encoding='utf-8'
            )
            temp_file.write(content)
            temp_file.close()
            
            self.test_files[language] = temp_file.name
            self.temp_files.append(temp_file.name)
        
        return self.test_files
    
    def cleanup(self):
        """一時ファイルのクリーンアップ"""
        for temp_file in self.temp_files:
            try:
                os.unlink(temp_file)
            except OSError:
                pass
        self.temp_files.clear()
        self.test_files.clear()


class TestEnhancedAnalysisEngine:
    """EnhancedAnalysisEngineのテストクラス"""
    
    @pytest.fixture(scope="class")
    def test_data_manager(self):
        """テストデータマネージャーのフィクスチャ"""
        manager = TestDataManager()
        manager.create_test_files()
        yield manager
        manager.cleanup()
    
    @pytest.fixture
    def analysis_engine(self):
        """解析エンジンのフィクスチャ"""
        return EnhancedAnalysisEngine()
    
    def test_engine_initialization(self, analysis_engine):
        """エンジンの初期化テスト"""
        assert analysis_engine is not None
        assert hasattr(analysis_engine, 'plugin_manager')
        assert hasattr(analysis_engine, 'query_engine')
        assert hasattr(analysis_engine, 'formatter_factory')
    
    def test_supported_languages(self, analysis_engine):
        """サポート言語のテスト"""
        languages = analysis_engine.get_supported_languages()
        
        assert isinstance(languages, list)
        assert len(languages) > 0
        
        # 基本言語のサポート確認
        expected_languages = ["python", "javascript", "java"]
        for lang in expected_languages:
            assert lang in languages, f"Language {lang} should be supported"
    
    @pytest.mark.parametrize("language", ["python", "javascript", "java"])
    def test_file_analysis(self, analysis_engine, test_data_manager, language):
        """ファイル解析のテスト"""
        file_path = test_data_manager.test_files[language]
        
        # 基本解析
        request = AnalysisRequest(query_types=["functions", "classes"])
        result = analysis_engine.analyze_file(file_path, request)
        
        # 結果の検証
        assert isinstance(result, AnalysisResult)
        assert result.file_path == file_path
        assert result.language == language
        
        # 関数の検出確認
        assert len(result.functions) > 0, f"No functions found in {language} file"
        
        # クラスの検出確認（言語によって異なる）
        if language in ["python", "javascript", "java"]:
            assert len(result.classes) > 0, f"No classes found in {language} file"
    
    def test_python_specific_analysis(self, analysis_engine, test_data_manager):
        """Python固有の解析テスト"""
        file_path = test_data_manager.test_files["python"]
        
        request = AnalysisRequest(
            query_types=["functions", "classes", "variables", "imports"]
        )
        result = analysis_engine.analyze_file(file_path, request)
        
        # 関数の詳細確認
        function_names = [f.name for f in result.functions]
        expected_functions = ["__init__", "add", "subtract", "calculate_factorial", "async_operation"]
        
        for expected_func in expected_functions:
            assert expected_func in function_names, f"Function {expected_func} not found"
        
        # クラスの確認
        class_names = [c.name for c in result.classes]
        assert "Calculator" in class_names
        
        # 非同期関数の確認
        async_functions = [f for f in result.functions if f.is_async]
        assert len(async_functions) > 0, "No async functions found"
        
        # メソッドの確認
        methods = [f for f in result.functions if f.is_method]
        assert len(methods) > 0, "No methods found"
        
        # インポートの確認
        assert len(result.imports) > 0, "No imports found"
    
    def test_javascript_specific_analysis(self, analysis_engine, test_data_manager):
        """JavaScript固有の解析テスト"""
        file_path = test_data_manager.test_files["javascript"]
        
        request = AnalysisRequest(query_types=["functions", "classes"])
        result = analysis_engine.analyze_file(file_path, request)
        
        # 関数の確認
        function_names = [f.name for f in result.functions]
        expected_functions = ["constructor", "add", "subtract", "calculateFactorial", "asyncOperation"]
        
        for expected_func in expected_functions:
            assert expected_func in function_names, f"Function {expected_func} not found"
        
        # クラスの確認
        class_names = [c.name for c in result.classes]
        assert "Calculator" in class_names
        
        # 非同期関数の確認
        async_functions = [f for f in result.functions if f.is_async]
        assert len(async_functions) > 0, "No async functions found"
    
    def test_java_specific_analysis(self, analysis_engine, test_data_manager):
        """Java固有の解析テスト"""
        file_path = test_data_manager.test_files["java"]
        
        request = AnalysisRequest(query_types=["functions", "classes"])
        result = analysis_engine.analyze_file(file_path, request)
        
        # メソッドの確認
        method_names = [f.name for f in result.functions]
        expected_methods = ["add", "subtract", "getHistory", "multiply", "calculateFactorial"]
        
        for expected_method in expected_methods:
            assert expected_method in method_names, f"Method {expected_method} not found"
        
        # クラスの確認
        class_names = [c.name for c in result.classes]
        expected_classes = ["Calculator", "MathUtils", "Main"]
        
        for expected_class in expected_classes:
            assert expected_class in class_names, f"Class {expected_class} not found"
        
        # 可視性の確認
        public_methods = [f for f in result.functions if f.visibility == "public"]
        private_methods = [f for f in result.functions if f.visibility == "private"]
        
        assert len(public_methods) > 0, "No public methods found"
        assert len(private_methods) > 0, "No private methods found"
    
    def test_error_handling(self, analysis_engine):
        """エラーハンドリングのテスト"""
        # 存在しないファイル
        with pytest.raises(Exception):
            analysis_engine.analyze_file("nonexistent_file.py")
        
        # 無効なファイル
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("invalid python syntax $$$ !!!")
            invalid_file = f.name
        
        try:
            with pytest.raises(Exception):
                analysis_engine.analyze_file(invalid_file)
        finally:
            os.unlink(invalid_file)
    
    def test_performance_metrics(self, analysis_engine, test_data_manager):
        """パフォーマンスメトリクスのテスト"""
        file_path = test_data_manager.test_files["python"]
        
        request = AnalysisRequest(query_types=["functions"])
        result = analysis_engine.analyze_file(file_path, request)
        
        # メタデータの確認
        assert "parse_time" in result.metadata
        assert "total_time" in result.metadata
        assert isinstance(result.metadata["parse_time"], (int, float))
        assert isinstance(result.metadata["total_time"], (int, float))
        
        # エンジン統計の確認
        stats = analysis_engine.get_engine_stats()
        assert "files_analyzed" in stats
        assert stats["files_analyzed"] > 0


class TestPluginSystem:
    """プラグインシステムのテストクラス"""
    
    @pytest.fixture
    def plugin_manager(self):
        """プラグインマネージャーのフィクスチャ"""
        return PluginManager()
    
    def test_plugin_loading(self, plugin_manager):
        """プラグイン読み込みのテスト"""
        # 利用可能なプラグインの確認
        available_plugins = plugin_manager.get_available_plugins()
        assert len(available_plugins) > 0
        
        # 各プラグインの読み込み確認
        for plugin_name in available_plugins:
            plugin = plugin_manager.get_plugin(plugin_name)
            assert plugin is not None
            assert hasattr(plugin, 'get_language_name')
            assert hasattr(plugin, 'get_file_extensions')
            assert hasattr(plugin, 'get_query_definitions')
    
    def test_plugin_interface_compliance(self, plugin_manager):
        """プラグインインターフェース準拠のテスト"""
        for plugin_name in plugin_manager.get_available_plugins():
            plugin = plugin_manager.get_plugin(plugin_name)
            
            # 必須メソッドの存在確認
            assert callable(getattr(plugin, 'get_language_name'))
            assert callable(getattr(plugin, 'get_file_extensions'))
            assert callable(getattr(plugin, 'is_applicable'))
            assert callable(getattr(plugin, 'get_query_definitions'))
            assert callable(getattr(plugin, 'create_formatter'))
            
            # 戻り値の型確認
            assert isinstance(plugin.get_language_name(), str)
            assert isinstance(plugin.get_file_extensions(), list)
            assert isinstance(plugin.get_query_definitions(), dict)
    
    def test_plugin_query_definitions(self, plugin_manager):
        """プラグインクエリ定義のテスト"""
        for plugin_name in plugin_manager.get_available_plugins():
            plugin = plugin_manager.get_plugin(plugin_name)
            queries = plugin.get_query_definitions()
            
            # 基本クエリの存在確認
            basic_queries = ["functions", "classes"]
            for query_type in basic_queries:
                if query_type in queries:
                    assert isinstance(queries[query_type], str)
                    assert len(queries[query_type].strip()) > 0


class TestFormatterSystem:
    """フォーマッターシステムのテストクラス"""
    
    @pytest.fixture
    def sample_result(self):
        """サンプル解析結果のフィクスチャ"""
        from tree_sitter_analyzer.models import ModelFunction, ModelClass
        
        sample_function = ModelFunction(
            name="test_function",
            start_line=10,
            end_line=15,
            start_column=0,
            end_column=20,
            docstring="テスト関数",
            parameters=["param1: int", "param2: str"],
            return_type="bool",
            is_async=False,
            is_method=False,
            visibility="public",
            metadata={}
        )
        
        sample_class = ModelClass(
            name="TestClass",
            start_line=20,
            end_line=40,
            start_column=0,
            end_column=10,
            docstring="テストクラス",
            methods=[sample_function],
            fields=["field1: int"],
            base_classes=["BaseClass"],
            is_abstract=False,
            visibility="public",
            metadata={}
        )
        
        return AnalysisResult(
            file_path="test.py",
            language="python",
            functions=[sample_function],
            classes=[sample_class],
            variables=[],
            imports=[],
            metadata={"test": True}
        )
    
    @pytest.mark.parametrize("format_type", ["table", "json", "csv", "markdown"])
    def test_formatter_output(self, sample_result, format_type):
        """フォーマッター出力のテスト"""
        from examples.implementation.sample_formatter import EnhancedFormatter
        
        formatter = EnhancedFormatter(format_type)
        output = formatter.format_analysis_result(sample_result)
        
        assert isinstance(output, str)
        assert len(output) > 0
        
        # フォーマット固有の確認
        if format_type == "json":
            # JSONとして解析可能か確認
            data = json.loads(output)
            assert "file_path" in data
            assert "language" in data
        
        elif format_type == "table":
            # テーブル形式の基本構造確認
            assert "test.py" in output
            assert "python" in output
            assert "test_function" in output
            assert "TestClass" in output
        
        elif format_type == "markdown":
            # Markdown形式の基本構造確認
            assert "# 解析結果" in output
            assert "## " in output  # セクションヘッダー
            assert "test_function" in output
        
        elif format_type == "csv":
            # CSV形式の基本構造確認
            lines = output.strip().split('\n')
            assert len(lines) > 1  # ヘッダー + データ
    
    def test_formatter_options(self, sample_result):
        """フォーマッターオプションのテスト"""
        from examples.implementation.sample_formatter import EnhancedFormatter
        
        # オプション付きフォーマッター
        formatter = EnhancedFormatter(
            "json",
            include_metadata=False,
            include_docstrings=False,
            include_line_numbers=False
        )
        
        output = formatter.format_analysis_result(sample_result)
        data = json.loads(output)
        
        # メタデータが除外されていることを確認
        assert "metadata" not in data
        
        # 関数にドキュメントが含まれていないことを確認
        if "functions" in data and data["functions"]:
            function_data = data["functions"][0]
            assert "docstring" not in function_data


class TestIntegration:
    """統合テストクラス"""
    
    @pytest.fixture(scope="class")
    def test_data_manager(self):
        """テストデータマネージャーのフィクスチャ"""
        manager = TestDataManager()
        manager.create_test_files()
        yield manager
        manager.cleanup()
    
    def test_end_to_end_workflow(self, test_data_manager):
        """エンドツーエンドワークフローのテスト"""
        engine = EnhancedAnalysisEngine()
        
        for language, file_path in test_data_manager.test_files.items():
            # 解析実行
            request = AnalysisRequest(
                query_types=["functions", "classes"],
                output_format="json"
            )
            result = engine.analyze_file(file_path, request)
            
            # 結果の検証
            assert result.language == language
            assert len(result.functions) > 0
            
            # フォーマット出力
            formatted_output = engine.format_results(result, "table")
            assert isinstance(formatted_output, str)
            assert len(formatted_output) > 0
            
            # JSON出力
            json_output = engine.format_results(result, "json")
            json_data = json.loads(json_output)
            assert json_data["language"] == language
    
    def test_performance_benchmark(self, test_data_manager):
        """パフォーマンスベンチマークテスト"""
        import time
        
        engine = EnhancedAnalysisEngine()
        
        for language, file_path in test_data_manager.test_files.items():
            # 複数回実行してパフォーマンスを測定
            times = []
            
            for _ in range(5):
                start_time = time.time()
                
                request = AnalysisRequest(query_types=["functions"])
                result = engine.analyze_file(file_path, request)
                
                end_time = time.time()
                times.append(end_time - start_time)
            
            # パフォーマンス要件の確認
            avg_time = sum(times) / len(times)
            max_time = max(times)
            
            # 基本的なパフォーマンス要件
            assert avg_time < 5.0, f"Average analysis time too slow for {language}: {avg_time}s"
            assert max_time < 10.0, f"Max analysis time too slow for {language}: {max_time}s"
    
    def test_memory_usage(self, test_data_manager):
        """メモリ使用量のテスト"""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        engine = EnhancedAnalysisEngine()
        
        # 複数ファイルを連続解析
        for _ in range(10):
            for file_path in test_data_manager.test_files.values():
                request = AnalysisRequest(query_types=["functions", "classes"])
                result = engine.analyze_file(file_path, request)
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        # メモリ使用量の要件
        assert memory_increase < 100, f"Memory usage increased too much: {memory_increase}MB"


# カスタムマーカー
pytest_plugins = []

def pytest_configure(config):
    """pytest設定"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )


# 実行例
if __name__ == "__main__":
    # 基本的なテスト実行
    print("🧪 サンプルテストケースの実行例")
    print("=" * 50)
    
    # テストデータの作成
    test_manager = TestDataManager()
    test_files = test_manager.create_test_files()
    
    try:
        # 簡単な動作確認
        engine = EnhancedAnalysisEngine()
        
        for language, file_path in test_files.items():
            print(f"\n📁 {language.upper()}ファイルのテスト: {file_path}")
            
            try:
                request = AnalysisRequest(query_types=["functions", "classes"])
                result = engine.analyze_file(file_path, request)
                
                print(f"  ✅ 解析成功")
                print(f"  📊 関数数: {len(result.functions)}")
                print(f"  📦 クラス数: {len(result.classes)}")
                print(f"  ⏱️  解析時間: {result.metadata.get('total_time', 'N/A')}秒")
                
            except Exception as e:
                print(f"  ❌ 解析失敗: {str(e)}")
    
    finally:
        test_manager.cleanup()
    
    print(f"\n{'='*50}")
    print("テスト実行完了")
    print("\n💡 完全なテストを実行するには:")
    print("   pytest examples/implementation/sample_test_cases.py -v")