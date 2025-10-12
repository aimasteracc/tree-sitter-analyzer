
# 品質保証ガイドライン

## 📋 概要

このドキュメントは、tree-sitter-analyzerプロジェクトの品質保証に関する包括的なガイドラインです。コードレビュー、テスト戦略、品質ゲート、パフォーマンステスト、セキュリティチェックの詳細な手順を提供します。

### 対象読者
- 開発者
- QAエンジニア
- プロジェクトメンテナー
- コードレビュアー

### 品質目標
- **コードカバレッジ**: 85%以上
- **バグ密度**: 1件/1000行以下
- **パフォーマンス**: 既存機能の105%以内
- **セキュリティ**: 脆弱性ゼロ

---

## 🔍 コードレビューガイドライン

### レビュープロセス

#### 1. プルリクエスト作成前チェックリスト

```markdown
## PR作成前チェックリスト

### コード品質
- [ ] コーディング規約（PEP 8）の遵守
- [ ] 型ヒントの適切な使用
- [ ] ドキュメント文字列の記述
- [ ] 適切な例外処理の実装

### テスト
- [ ] 単体テストの追加・更新
- [ ] テストカバレッジ85%以上の維持
- [ ] スナップショットテストの更新（必要に応じて）
- [ ] パフォーマンステストの実行

### ドキュメント
- [ ] README.mdの更新（必要に応じて）
- [ ] CHANGELOG.mdの更新
- [ ] APIドキュメントの更新
- [ ] 使用例の追加

### セキュリティ
- [ ] セキュリティスキャンの実行
- [ ] 機密情報の漏洩チェック
- [ ] 依存関係の脆弱性チェック
```

#### 2. レビュアー向けチェックポイント

```python
# コードレビューチェックポイント

class CodeReviewChecklist:
    """コードレビューチェックリスト"""
    
    ARCHITECTURE_CHECKS = [
        "プラグインアーキテクチャの遵守",
        "責務分離の適切性",
        "依存関係の方向性",
        "インターフェースの一貫性"
    ]
    
    CODE_QUALITY_CHECKS = [
        "命名規約の遵守",
        "関数・クラスサイズの適切性",
        "複雑度の管理",
        "重複コードの排除"
    ]
    
    PERFORMANCE_CHECKS = [
        "アルゴリズムの効率性",
        "メモリ使用量の最適化",
        "キャッシュの適切な利用",
        "I/O操作の最適化"
    ]
    
    SECURITY_CHECKS = [
        "入力値検証の実装",
        "パストラバーサル対策",
        "機密情報の適切な処理",
        "権限チェックの実装"
    ]
```

#### 3. レビューコメントテンプレート

```markdown
## 🔍 アーキテクチャレビュー

### ✅ 良い点
- プラグインインターフェースの適切な実装
- 責務分離が明確

### ⚠️ 改善点
- [ ] `query_service.py`の条件分岐を削除してプラグインに移譲
- [ ] エラーハンドリングの統一

### 💡 提案
- キャッシュ機能の追加を検討
- パフォーマンステストの追加

## 🧪 テストレビュー

### ✅ 良い点
- 包括的なテストケース
- エッジケースの考慮

### ⚠️ 改善点
- [ ] スナップショットテストの追加
- [ ] パフォーマンステストの強化

## 📝 ドキュメントレビュー

### ✅ 良い点
- 詳細な使用例
- 明確なAPI説明

### ⚠️ 改善点
- [ ] エラーケースの説明追加
- [ ] 設定オプションの詳細化
```

---

## 🧪 テスト戦略

### テストピラミッド

```mermaid
graph TD
    A[E2Eテスト<br/>10%] --> B[統合テスト<br/>20%]
    B --> C[単体テスト<br/>70%]
    
    style A fill:#ffcdd2
    style B fill:#fff3e0
    style C fill:#e8f5e8
```

### 1. 単体テスト（Unit Tests）

#### テスト対象
- プラグインクラス
- フォーマッタークラス
- ユーティリティ関数
- コアエンジンコンポーネント

#### テスト実装例

```python
# tests/unit/test_plugins/test_python_plugin.py
import pytest
from unittest.mock import Mock, patch
from tree_sitter_analyzer.languages.python import PythonPlugin
from tree_sitter_analyzer.models import AnalysisRequest
from tree_sitter_analyzer.exceptions import ParseError

class TestPythonPluginUnit:
    """Pythonプラグインの単体テスト"""
    
    @pytest.fixture
    def plugin(self):
        return PythonPlugin()
    
    def test_get_language_name(self, plugin):
        """言語名取得のテスト"""
        assert plugin.get_language_name() == "python"
    
    def test_get_file_extensions(self, plugin):
        """ファイル拡張子取得のテスト"""
        extensions = plugin.get_file_extensions()
        assert ".py" in extensions
        assert ".pyi" in extensions
        assert ".pyw" in extensions
    
    def test_is_applicable_positive(self, plugin):
        """適用可能ファイルの判定テスト（正常系）"""
        test_cases = [
            "test.py",
            "module.pyi", 
            "script.pyw",
            "/path/to/file.py"
        ]
        for file_path in test_cases:
            assert plugin.is_applicable(file_path) is True
    
    def test_is_applicable_negative(self, plugin):
        """適用可能ファイルの判定テスト（異常系）"""
        test_cases = [
            "test.js",
            "file.txt",
            "readme.md",
            "config.json"
        ]
        for file_path in test_cases:
            assert plugin.is_applicable(file_path) is False
    
    def test_query_definitions_structure(self, plugin):
        """クエリ定義の構造テスト"""
        queries = plugin.get_query_definitions()
        
        # 必須クエリの存在確認
        required_queries = ["functions", "classes", "variables", "imports"]
        for query_type in required_queries:
            assert query_type in queries
            assert isinstance(queries[query_type], str)
            assert len(queries[query_type].strip()) > 0
    
    @patch('tree_sitter_analyzer.languages.python.Path')
    def test_analyze_file_parse_error(self, mock_path, plugin):
        """解析エラーのテスト"""
        # ファイル読み込みエラーをシミュレート
        mock_path.return_value.read_text.side_effect = FileNotFoundError()
        
        request = AnalysisRequest(query_types=["functions"])
        
        with pytest.raises(ParseError):
            plugin.analyze_file("nonexistent.py", request)
    
    def test_performance_metrics_initialization(self, plugin):
        """パフォーマンスメトリクスの初期化テスト"""
        metrics = plugin.get_performance_metrics()
        
        assert "parse_count" in metrics
        assert "total_parse_time" in metrics
        assert "error_count" in metrics
        assert metrics["parse_count"] == 0
        assert metrics["total_parse_time"] == 0.0
        assert metrics["error_count"] == 0
```

### 2. 統合テスト（Integration Tests）

#### テスト対象
- プラグインマネージャーとプラグインの連携
- クエリエンジンとプラグインの統合
- フォーマッターとプラグインの統合
- MCPサーバーとの統合

#### テスト実装例

```python
# tests/integration/test_plugin_integration.py
import pytest
from pathlib import Path
from tree_sitter_analyzer.plugins.manager import PluginManager
from tree_sitter_analyzer.core.analysis_engine import AnalysisEngine
from tree_sitter_analyzer.models import AnalysisRequest

class TestPluginIntegration:
    """プラグイン統合テスト"""
    
    @pytest.fixture
    def plugin_manager(self):
        manager = PluginManager()
        manager.load_plugins()
        return manager
    
    @pytest.fixture
    def analysis_engine(self, plugin_manager):
        return AnalysisEngine(plugin_manager)
    
    @pytest.fixture
    def sample_files(self, tmp_path):
        """複数言語のサンプルファイルを作成"""
        files = {}
        
        # Python
        python_content = '''
def hello_world():
    print("Hello, World!")

class Calculator:
    def add(self, a, b):
        return a + b
        '''
        python_file = tmp_path / "sample.py"
        python_file.write_text(python_content)
        files["python"] = str(python_file)
        
        # JavaScript
        js_content = '''
function helloWorld() {
    console.log("Hello, World!");
}

class Calculator {
    add(a, b) {
        return a + b;
    }
}
        '''
        js_file = tmp_path / "sample.js"
        js_file.write_text(js_content)
        files["javascript"] = str(js_file)
        
        return files
    
    def test_multi_language_analysis(self, analysis_engine, sample_files):
        """複数言語の統合解析テスト"""
        request = AnalysisRequest(query_types=["functions", "classes"])
        
        for language, file_path in sample_files.items():
            result = analysis_engine.analyze_file(file_path, request)
            
            # 基本的な結果検証
            assert result is not None
            assert result.language == language
            assert len(result.functions) > 0
            assert len(result.classes) > 0
    
    def test_plugin_manager_integration(self, plugin_manager):
        """プラグインマネージャー統合テスト"""
        # 全プラグインの読み込み確認
        plugins = plugin_manager.get_all_plugins()
        assert len(plugins) > 0
        
        # 各プラグインの基本機能確認
        for language, plugin in plugins.items():
            assert plugin.get_language_name() == language
            assert len(plugin.get_file_extensions()) > 0
            assert len(plugin.get_query_definitions()) > 0
    
    def test_formatter_integration(self, analysis_engine, sample_files):
        """フォーマッター統合テスト"""
        request = AnalysisRequest(
            query_types=["functions"],
            output_format="table"
        )
        
        python_file = sample_files["python"]
        result = analysis_engine.analyze_file(python_file, request)
        
        # フォーマッター作成と実行
        plugin = analysis_engine.plugin_manager.get_plugin("python")
        formatter = plugin.create_formatter("table")
        formatted_output = formatter.format_functions(result.functions)
        
        assert isinstance(formatted_output, str)
        assert len(formatted_output) > 0
        assert "hello_world" in formatted_output
```

### 3. スナップショットテスト

#### 実装例

```python
# tests/snapshots/test_regression_snapshots.py
import pytest
from tree_sitter_analyzer.testing.snapshot import SnapshotTester

class TestRegressionSnapshots:
    """回帰テスト用スナップショット"""
    
    @pytest.fixture
    def snapshot_tester(self):
        return SnapshotTester("regression")
    
    def test_python_complex_analysis_snapshot(self, snapshot_tester):
        """Python複雑解析のスナップショット"""
        complex_python_code = '''
import asyncio
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class Person:
    name: str
    age: int
    
    def __post_init__(self):
        if self.age < 0:
            raise ValueError("Age cannot be negative")

class AsyncProcessor:
    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers
        self.semaphore = asyncio.Semaphore(max_workers)
    
    async def process_item(self, item: str) -> Dict[str, any]:
        async with self.semaphore:
            await asyncio.sleep(0.1)  # Simulate processing
            return {"item": item, "processed": True}
    
    async def process_batch(self, items: List[str]) -> List[Dict[str, any]]:
        tasks = [self.process_item(item) for item in items]
        return await asyncio.gather(*tasks)

def create_processor(workers: Optional[int] = None) -> AsyncProcessor:
    return AsyncProcessor(workers or 5)

if __name__ == "__main__":
    processor = create_processor()
    items = ["item1", "item2", "item3"]
    results = asyncio.run(processor.process_batch(items))
    print(f"Processed {len(results)} items")
        '''
        
        result = snapshot_tester.analyze_code(
            complex_python_code, 
            ["functions", "classes", "variables", "imports"]
        )
        snapshot_tester.assert_matches_snapshot("python_complex_analysis", result)
    
    def test_javascript_modern_features_snapshot(self, snapshot_tester):
        """JavaScript現代的機能のスナップショット"""
        modern_js_code = '''
import { EventEmitter } from 'events';

class AsyncDataProcessor extends EventEmitter {
    constructor(options = {}) {
        super();
        this.batchSize = options.batchSize || 100;
        this.delay = options.delay || 0;
    }
    
    async processData(data) {
        const batches = this.createBatches(data);
        const results = [];
        
        for (const batch of batches) {
            const batchResult = await this.processBatch(batch);
            results.push(...batchResult);
            this.emit('batchProcessed', { batch: batch.length, total: results.length });
            
            if (this.delay > 0) {
                await new Promise(resolve => setTimeout(resolve, this.delay));
            }
        }
        
        return results;
    }
    
    createBatches(data) {
        const batches = [];
        for (let i = 0; i < data.length; i += this.batchSize) {
            batches.push(data.slice(i, i + this.batchSize));
        }
        return batches;
    }
    
    async processBatch(batch) {
        return Promise.all(batch.map(item => this.processItem(item)));
    }
    
    async processItem(item) {
        // Simulate async processing
        return new Promise(resolve => {
            setTimeout(() => resolve({ ...item, processed: true }), 10);
        });
    }
}

export default AsyncDataProcessor;
        '''
        
        result = snapshot_tester.analyze_code(
            modern_js_code,
            ["functions", "classes", "variables", "imports"]
        )
        snapshot_tester.assert_matches_snapshot("javascript_modern_features", result)
```

---

## 🚀 パフォーマンステスト

### パフォーマンス指標

#### 1. 基準値

```python
# tests/performance/performance_benchmarks.py
class PerformanceBenchmarks:
    """パフォーマンス基準値"""
    
    # ファイルサイズ別の解析時間上限（秒）
    ANALYSIS_TIME_LIMITS = {
        "small_file": 0.1,      # < 1KB
        "medium_file": 1.0,     # 1KB - 100KB  
        "large_file": 5.0,      # 100KB - 1MB
        "huge_file": 30.0       # > 1MB
    }
    
    # メモリ使用量上限（MB）
    MEMORY_LIMITS = {
        "base_usage": 50,       # 基本使用量
        "per_file": 10,         # ファイルあたり
        "max_total": 500        # 最大総使用量
    }
    
    # スループット下限（ファイル/秒）
    THROUGHPUT_LIMITS = {
        "small_files": 100,
        "medium_files": 10,
        "large_files": 1
    }
```

#### 2. パフォーマンステスト実装

```python
import pytest
import time
import psutil
import os
from pathlib import Path
from tree_sitter_analyzer.core.analysis_engine import AnalysisEngine
from tree_sitter_analyzer.models import AnalysisRequest

class TestPerformance:
    """パフォーマンステスト"""
    
    @pytest.fixture
    def analysis_engine(self):
        from tree_sitter_analyzer.plugins.manager import PluginManager
        plugin_manager = PluginManager()
        plugin_manager.load_plugins()
        return AnalysisEngine(plugin_manager)
    
    @pytest.fixture
    def performance_files(self, tmp_path):
        """パフォーマンステスト用ファイル生成"""
        files = {}
        
        # 小ファイル（1KB未満）
        small_content = '''
def small_function():
    return "small"

class SmallClass:
    pass
        '''
        small_file = tmp_path / "small.py"
        small_file.write_text(small_content)
        files["small"] = str(small_file)
        
        # 中ファイル（10KB程度）
        medium_content = self._generate_python_code(100)  # 100関数
        medium_file = tmp_path / "medium.py"
        medium_file.write_text(medium_content)
        files["medium"] = str(medium_file)
        
        # 大ファイル（100KB程度）
        large_content = self._generate_python_code(1000)  # 1000関数
        large_file = tmp_path / "large.py"
        large_file.write_text(large_content)
        files["large"] = str(large_file)
        
        return files
    
    def _generate_python_code(self, function_count: int) -> str:
        """指定数の関数を含むPythonコードを生成"""
        lines = ["# Generated Python code for performance testing\n"]
        
        for i in range(function_count):
            lines.append(f'''
def function_{i}(param1, param2={i}):
    """Function {i} documentation"""
    result = param1 + param2
    if result > {i * 10}:
        return result * 2
    else:
        return result
            ''')
        
        return "\n".join(lines)
    
    @pytest.mark.performance
    def test_small_file_analysis_time(self, analysis_engine, performance_files):
        """小ファイル解析時間テスト"""
        request = AnalysisRequest(query_types=["functions", "classes"])
        
        start_time = time.time()
        result = analysis_engine.analyze_file(performance_files["small"], request)
        end_time = time.time()
        
        analysis_time = end_time - start_time
        assert analysis_time < PerformanceBenchmarks.ANALYSIS_TIME_LIMITS["small_file"]
        assert result is not None
    
    @pytest.mark.performance
    def test_large_file_analysis_time(self, analysis_engine, performance_files):
        """大ファイル解析時間テスト"""
        request = AnalysisRequest(query_types=["functions", "classes"])
        
        start_time = time.time()
        result = analysis_engine.analyze_file(performance_files["large"], request)
        end_time = time.time()
        
        analysis_time = end_time - start_time
        assert analysis_time < PerformanceBenchmarks.ANALYSIS_TIME_LIMITS["large_file"]
        assert len(result.functions) == 1000
    
    @pytest.mark.performance
    def test_memory_usage(self, analysis_engine, performance_files):
        """メモリ使用量テスト"""
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        request = AnalysisRequest(query_types=["functions", "classes"])
        
        # 複数ファイルを連続解析
        for _ in range(10):
            for file_path in performance_files.values():
                analysis_engine.analyze_file(file_path, request)
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        assert memory_increase < PerformanceBenchmarks.MEMORY_LIMITS["max_total"]
    
    @pytest.mark.performance
    def test_throughput(self, analysis_engine, performance_files):
        """スループットテスト"""
        request = AnalysisRequest(query_types=["functions"])
        small_file = performance_files["small"]
        
        # 100ファイルの解析時間を測定
        start_time = time.time()
        for _ in range(100):
            analysis_engine.analyze_file(small_file, request)
        end_time = time.time()
        
        total_time = end_time - start_time
        throughput = 100 / total_time  # ファイル/秒
        
        assert throughput >= PerformanceBenchmarks.THROUGHPUT_LIMITS["small_files"]
    
    @pytest.mark.performance
    def test_cache_effectiveness(self, analysis_engine, performance_files):
        """キャッシュ効果テスト"""
        request = AnalysisRequest(query_types=["functions"])
        file_path = performance_files["medium"]
        
        # 初回解析時間
        start_time = time.time()
        analysis_engine.analyze_file(file_path, request)
        first_analysis_time = time.time() - start_time
        
        # 2回目解析時間（キャッシュ効果期待）
        start_time = time.time()
        analysis_engine.analyze_file(file_path, request)
        second_analysis_time = time.time() - start_time
        
        # 2回目は1回目より高速であることを確認
        # （ただし、ファイル内容が同じ場合のキャッシュ効果）
        cache_improvement = first_analysis_time / second_analysis_time
        assert cache_improvement >= 1.0  # 少なくとも同等以上
```

---

## 🔒 セキュリティチェック

### セキュリティ要件

#### 1. 基本セキュリティ原則

```python
# tree_sitter_analyzer/security/guidelines.py
class SecurityGuidelines:
    """セキュリティガイドライン"""
    
    # 入力検証要件
    INPUT_VALIDATION = {
        "file_paths": "パストラバーサル攻撃の防止",
        "query_strings": "インジェクション攻撃の防止", 
        "user_input": "XSS攻撃の防止",
        "file_size": "DoS攻撃の防止"
    }
    
    # アクセス制御要件
    ACCESS_CONTROL = {
        "file_access": "許可されたディレクトリのみアクセス",
        "command_execution": "危険なコマンドの実行禁止",
        "network_access": "不要なネットワークアクセスの禁止"
    }
    
    # データ保護要件
    DATA_PROTECTION = {
        "sensitive_data": "機密情報の適切な処理",
        "logging": "ログへの機密情報出力禁止",
        "error_messages": "詳細エラー情報の漏洩防止"
    }
```

#### 2. セキュリティテスト実装

```python
# tests/security/test_security_validation.py
import pytest
import tempfile
from pathlib import Path
from tree_sitter_analyzer.core.analysis_engine import AnalysisEngine
from tree_sitter_analyzer.models import AnalysisRequest
from tree_sitter_analyzer.exceptions import SecurityError

class TestSecurityValidation:
    """セキュリティ検証テスト"""
    
    @pytest.fixture
    def analysis_engine(self):
        from tree_sitter_analyzer.plugins.manager import PluginManager
        plugin_manager = PluginManager()
        plugin_manager.load_plugins()
        return AnalysisEngine(plugin_manager)
    
    def test_path_traversal_prevention(self, analysis_engine):
        """パストラバーサル攻撃防止テスト"""
        malicious_paths = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "/etc/shadow",
            "C:\\Windows\\System32\\config\\SAM",
            "file://etc/passwd",
            "\\\\server\\share\\file.txt"
        ]
        
        request = AnalysisRequest(query_types=["functions"])
        
        for malicious_path in malicious_paths:
            with pytest.raises((SecurityError, FileNotFoundError, PermissionError)):
                analysis_engine.analyze_file(malicious_path, request)
    
    def test_file_size_limit(self, analysis_engine, tmp_path):
        """ファイルサイズ制限テスト"""
        # 非常に大きなファイルを作成（DoS攻撃シミュレート）
        large_file = tmp_path / "large_file.py"
        
        # 10MBのファイルを作成
        large_content = "# " + "x" * (10 * 1024 * 1024)
        large_file.write_text(large_content)
        
        request = AnalysisRequest(query_types=["functions"])
        
        # ファイルサイズ制限によりエラーが発生することを確認
        with pytest.raises(SecurityError):
            analysis_engine.analyze_file(str(large_file), request)
    
    def test_query_injection_prevention(self, analysis_engine, tmp_path):
        """クエリインジェクション防止テスト"""
        # 正常なPythonファイル
        python_file = tmp_path / "test.py"
        python_file.write_text("def test(): pass")
        
        # 悪意のあるクエリタイプ
        malicious_queries = [
            "functions; DROP TABLE users;",
            "functions' OR '1'='1",
            "functions\"; system('rm -rf /'); --",
            "../../../etc/passwd",
            "<script>alert('xss')</script>"
        ]
        
        for malicious_query in malicious_queries:
            request = AnalysisRequest(query_types=[malicious_query])
            
            # 不正なクエリタイプは無視または例外が発生
            result = analysis_engine.analyze_file(str(python_file), request)
            # 結果が空または例外が発生することを確認
            assert result.functions == [] or result is None
    
    def test_sensitive_data_handling(self, analysis_engine, tmp_path):
        """機密データ処理テスト"""
        # 機密情報を含むファイル
        sensitive_file = tmp_path / "sensitive.py"
        sensitive_content = '''
# This file contains sensitive information
API_KEY = "sk-1234567890abcdef"
PASSWORD = "super_secret_password"
DATABASE_URL = "postgresql://user:pass@localhost/db"

def process_payment(credit_card_number):
    """Process payment with credit card"""
    return f"Processing {credit_card_number}"
        '''
        sensitive_file.write_text(sensitive_content)
        
        request = AnalysisRequest(query_types=["functions", "variables"])
        result = analysis_engine.analyze_file(str(sensitive_file), request)
        
        # 結果に機密情報が含まれていないことを確認
        result_str = str(result)
        assert "sk-1234567890abcdef" not in result_str
        assert "super_secret_password" not in result_str
        assert "postgresql://user:pass@localhost/db" not in result_str
    
    def test_error_message_sanitization(self, analysis_engine):
        """エラーメッセージサニタイゼーションテスト"""
        # 存在しないファイルでエラーを発生させる
        nonexistent_file = "/path/to/nonexistent/file.py"
        request = AnalysisRequest(query_types=["functions"])
        
        try:
            analysis_engine.analyze_file(nonexistent_file, request)
        except Exception as e:
            error_message = str(e)
            
            # エラーメッセージに機密情報が含まれていないことを確認
            assert "/etc/passwd" not in error_message
            assert "C:\\Windows" not in error_message
            assert "password" not in error_message.lower()
```

#### 3. 静的セキュリティ分析
        
        try:
            analysis_engine.analyze_file(nonexistent_file, request)
        except Exception as e:
            error_message = str(e)
            
            # エラーメッセージに機密情報が含まれていないことを確認
            assert "/etc/passwd" not in error_message
            assert "C:\\Windows" not in error_message
            assert "password" not in error_message.lower()
```

#### 3. 静的セキュリティ分析

```bash
# セキュリティスキャンツールの実行
bandit -r tree_sitter_analyzer/ -f json -o security_report.json

# 依存関係の脆弱性チェック
safety check --json --output vulnerability_report.json

# 機密情報スキャン
truffleHog --regex --entropy=False tree_sitter_analyzer/
```

#### 4. セキュリティ設定

```python
# tree_sitter_analyzer/security/config.py
class SecurityConfig:
    """セキュリティ設定"""
    
    # ファイルアクセス制限
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS = ['.py', '.js', '.ts', '.java', '.rs', '.md', '.html']
    BLOCKED_PATHS = [
        '/etc/', '/proc/', '/sys/', '/dev/',
        'C:\\Windows\\', 'C:\\Program Files\\',
        '../', '..\\', '//', '\\\\'
    ]
    
    # クエリ制限
    MAX_QUERY_LENGTH = 1000
    ALLOWED_QUERY_TYPES = [
        'functions', 'classes', 'variables', 'imports',
        'structs', 'enums', 'traits', 'modules'
    ]
    
    # ログ設定
    SENSITIVE_PATTERNS = [
        r'password\s*=\s*["\'][^"\']+["\']',
        r'api_key\s*=\s*["\'][^"\']+["\']',
        r'secret\s*=\s*["\'][^"\']+["\']',
        r'token\s*=\s*["\'][^"\']+["\']'
    ]
```

---

## 📊 品質ゲート

### 品質ゲート定義

#### 1. コミット前品質ゲート

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 22.3.0
    hooks:
      - id: black
        language_version: python3

  - repo: https://github.com/pycqa/flake8
    rev: 4.0.1
    hooks:
      - id: flake8
        args: [--max-line-length=88, --extend-ignore=E203]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v0.950
    hooks:
      - id: mypy
        additional_dependencies: [types-all]

  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.4
    hooks:
      - id: bandit
        args: [-r, tree_sitter_analyzer/]

  - repo: local
    hooks:
      - id: pytest-unit
        name: Run unit tests
        entry: pytest tests/unit/ -v
        language: system
        pass_filenames: false
        always_run: true
```

#### 2. プルリクエスト品質ゲート

```python
# scripts/quality_gate.py
import subprocess
import sys
from pathlib import Path

class QualityGate:
    """品質ゲートチェッカー"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.failed_checks = []
    
    def run_all_checks(self) -> bool:
        """全品質チェックを実行"""
        checks = [
            ("Code Style", self.check_code_style),
            ("Type Checking", self.check_types),
            ("Unit Tests", self.check_unit_tests),
            ("Coverage", self.check_coverage),
            ("Security", self.check_security),
            ("Performance", self.check_performance)
        ]
        
        print("🚀 Running Quality Gate Checks...\n")
        
        for check_name, check_func in checks:
            print(f"🔍 {check_name}...")
            if not check_func():
                self.failed_checks.append(check_name)
                print(f"❌ {check_name} FAILED")
            else:
                print(f"✅ {check_name} PASSED")
            print()
        
        return len(self.failed_checks) == 0
    
    def check_code_style(self) -> bool:
        """コードスタイルチェック"""
        try:
            # Black check
            result = subprocess.run(
                ["black", "--check", "tree_sitter_analyzer/"],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                print(f"Black formatting issues: {result.stdout}")
                return False
            
            # Flake8 check
            result = subprocess.run(
                ["flake8", "tree_sitter_analyzer/"],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                print(f"Flake8 issues: {result.stdout}")
                return False
            
            return True
        except Exception as e:
            print(f"Code style check error: {e}")
            return False
    
    def check_types(self) -> bool:
        """型チェック"""
        try:
            result = subprocess.run(
                ["mypy", "tree_sitter_analyzer/"],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                print(f"MyPy type errors: {result.stdout}")
                return False
            return True
        except Exception as e:
            print(f"Type check error: {e}")
            return False
    
    def check_unit_tests(self) -> bool:
        """単体テストチェック"""
        try:
            result = subprocess.run(
                ["pytest", "tests/unit/", "-v", "--tb=short"],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                print(f"Unit test failures: {result.stdout}")
                return False
            return True
        except Exception as e:
            print(f"Unit test error: {e}")
            return False
    
    def check_coverage(self) -> bool:
        """カバレッジチェック"""
        try:
            result = subprocess.run([
                "pytest", "tests/", 
                "--cov=tree_sitter_analyzer",
                "--cov-report=term-missing",
                "--cov-fail-under=85"
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"Coverage below 85%: {result.stdout}")
                return False
            return True
        except Exception as e:
            print(f"Coverage check error: {e}")
            return False
    
    def check_security(self) -> bool:
        """セキュリティチェック"""
        try:
            # Bandit security check
            result = subprocess.run([
                "bandit", "-r", "tree_sitter_analyzer/",
                "-f", "json"
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"Security issues found: {result.stdout}")
                return False
            
            # Safety dependency check
            result = subprocess.run([
                "safety", "check", "--json"
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"Vulnerable dependencies: {result.stdout}")
                return False
            
            return True
        except Exception as e:
            print(f"Security check error: {e}")
            return False
    
    def check_performance(self) -> bool:
        """パフォーマンステストチェック"""
        try:
            result = subprocess.run([
                "pytest", "tests/performance/",
                "-m", "performance",
                "-v"
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"Performance tests failed: {result.stdout}")
                return False
            return True
        except Exception as e:
            print(f"Performance check error: {e}")
            return False

if __name__ == "__main__":
    gate = QualityGate()
    success = gate.run_all_checks()
    
    if success:
        print("🎉 All quality checks passed!")
        sys.exit(0)
    else:
        print(f"💥 Quality gate failed. Failed checks: {', '.join(gate.failed_checks)}")
        sys.exit(1)
```

#### 3. リリース前品質ゲート

```python
# scripts/release_quality_gate.py
class ReleaseQualityGate(QualityGate):
    """リリース前品質ゲート"""
    
    def run_release_checks(self) -> bool:
        """リリース前チェックを実行"""
        release_checks = [
            ("Full Test Suite", self.check_full_test_suite),
            ("Integration Tests", self.check_integration_tests),
            ("Snapshot Tests", self.check_snapshot_tests),
            ("Documentation", self.check_documentation),
            ("Version Consistency", self.check_version_consistency),
            ("Changelog", self.check_changelog),
            ("Performance Regression", self.check_performance_regression)
        ]
        
        print("🚀 Running Release Quality Gate Checks...\n")
        
        for check_name, check_func in release_checks:
            print(f"🔍 {check_name}...")
            if not check_func():
                self.failed_checks.append(check_name)
                print(f"❌ {check_name} FAILED")
            else:
                print(f"✅ {check_name} PASSED")
            print()
        
        return len(self.failed_checks) == 0
    
    def check_full_test_suite(self) -> bool:
        """全テストスイートの実行"""
        try:
            result = subprocess.run([
                "pytest", "tests/", "-v",
                "--cov=tree_sitter_analyzer",
                "--cov-report=html",
                "--cov-fail-under=85"
            ], capture_output=True, text=True)
            
            return result.returncode == 0
        except Exception:
            return False
    
    def check_integration_tests(self) -> bool:
        """統合テストチェック"""
        try:
            result = subprocess.run([
                "pytest", "tests/integration/", "-v"
            ], capture_output=True, text=True)
            
            return result.returncode == 0
        except Exception:
            return False
    
    def check_snapshot_tests(self) -> bool:
        """スナップショットテストチェック"""
        try:
            result = subprocess.run([
                "pytest", "tests/snapshots/", "-v"
            ], capture_output=True, text=True)
            
            return result.returncode == 0
        except Exception:
            return False
    
    def check_documentation(self) -> bool:
        """ドキュメントチェック"""
        required_docs = [
            "README.md",
            "CHANGELOG.md",
            "docs/IMPLEMENTATION_GUIDELINES.md",
            "docs/NEW_LANGUAGE_PLUGIN_GUIDE.md",
            "docs/QUALITY_ASSURANCE_GUIDE.md"
        ]
        
        for doc in required_docs:
            if not Path(doc).exists():
                print(f"Missing documentation: {doc}")
                return False
        
        return True
    
    def check_version_consistency(self) -> bool:
        """バージョン一貫性チェック"""
        # pyproject.toml, __init__.py, CHANGELOGのバージョンが一致するかチェック
        # 実装は省略
        return True
    
    def check_changelog(self) -> bool:
        """CHANGELOGチェック"""
        changelog_path = Path("CHANGELOG.md")
        if not changelog_path.exists():
            return False
        
        content = changelog_path.read_text()
        # 最新バージョンのエントリが存在するかチェック
        # 実装は省略
        return True
    
    def check_performance_regression(self) -> bool:
        """パフォーマンス回帰チェック"""
        try:
            result = subprocess.run([
                "pytest", "tests/performance/",
                "-m", "regression",
                "--benchmark-only"
            ], capture_output=True, text=True)
            
            return result.returncode == 0
        except Exception:
            return False
```

---

## 📈 継続的品質監視

### 品質メトリクス収集

#### 1. メトリクス定義

```python
# tree_sitter_analyzer/quality/metrics.py
from dataclasses import dataclass
from typing import Dict, List
import time

@dataclass
class QualityMetrics:
    """品質メトリクス"""
    
    # コード品質
    code_coverage: float
    cyclomatic_complexity: float
    maintainability_index: float
    technical_debt_ratio: float
    
    # パフォーマンス
    avg_analysis_time: float
    memory_usage: float
    throughput: float
    
    # 信頼性
    error_rate: float
    crash_rate: float
    recovery_time: float
    
    # セキュリティ
    vulnerability_count: int
    security_score: float
    
    # 使用性
    api_usability_score: float
    documentation_coverage: float

class QualityMonitor:
    """品質監視システム"""
    
    def __init__(self):
        self.metrics_history: List[QualityMetrics] = []
        self.alerts: List[str] = []
    
    def collect_metrics(self) -> QualityMetrics:
        """現在の品質メトリクスを収集"""
        return QualityMetrics(
            code_coverage=self._get_code_coverage(),
            cyclomatic_complexity=self._get_complexity(),
            maintainability_index=self._get_maintainability(),
            technical_debt_ratio=self._get_technical_debt(),
            avg_analysis_time=self._get_avg_analysis_time(),
            memory_usage=self._get_memory_usage(),
            throughput=self._get_throughput(),
            error_rate=self._get_error_rate(),
            crash_rate=self._get_crash_rate(),
            recovery_time=self._get_recovery_time(),
            vulnerability_count=self._get_vulnerability_count(),
            security_score=self._get_security_score(),
            api_usability_score=self._get_api_usability(),
            documentation_coverage=self._get_doc_coverage()
        )
    
    def check_quality_thresholds(self, metrics: QualityMetrics) -> List[str]:
        """品質閾値チェック"""
        alerts = []
        
        if metrics.code_coverage < 85.0:
            alerts.append(f"Code coverage below threshold: {metrics.code_coverage}%")
        
        if metrics.cyclomatic_complexity > 10.0:
            alerts.append(f"High complexity: {metrics.cyclomatic_complexity}")
        
        if metrics.avg_analysis_time > 5.0:
            alerts.append(f"Slow analysis time: {metrics.avg_analysis_time}s")
        
        if metrics.error_rate > 0.01:
            alerts.append(f"High error rate: {metrics.error_rate * 100}%")
        
        if metrics.vulnerability_count > 0:
            alerts.append(f"Security vulnerabilities found: {metrics.vulnerability_count}")
        
        return alerts
```

#### 2. 自動品質レポート

```python
# scripts/generate_quality_report.py
import json
from datetime import datetime
from pathlib import Path

class QualityReporter:
    """品質レポート生成器"""
    
    def generate_report(self, metrics: QualityMetrics) -> str:
        """品質レポートを生成"""
        report = f"""
# 品質レポート - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 📊 品質メトリクス概要

### コード品質
- **カバレッジ**: {metrics.code_coverage:.1f}% {'✅' if metrics.code_coverage >= 85 else '❌'}
- **複雑度**: {metrics.cyclomatic_complexity:.1f} {'✅' if metrics.cyclomatic_complexity <= 10 else '❌'}
- **保守性指数**: {metrics.maintainability_index:.1f}
- **技術的負債比率**: {metrics.technical_debt_ratio:.1f}%

### パフォーマンス
- **平均解析時間**: {metrics.avg_analysis_time:.3f}秒 {'✅' if metrics.avg_analysis_time <= 5.0 else '❌'}
- **メモリ使用量**: {metrics.memory_usage:.1f}MB
- **スループット**: {metrics.throughput:.1f}ファイル/秒

### 信頼性
- **エラー率**: {metrics.error_rate * 100:.2f}% {'✅' if metrics.error_rate <= 0.01 else '❌'}
- **クラッシュ率**: {metrics.crash_rate * 100:.2f}%
- **復旧時間**: {metrics.recovery_time:.1f}秒

### セキュリティ
- **脆弱性数**: {metrics.vulnerability_count} {'✅' if metrics.vulnerability_count == 0 else '❌'}
- **セキュリティスコア**: {metrics.security_score:.1f}/100

### 使用性
- **API使用性スコア**: {metrics.api_usability_score:.1f}/100
- **ドキュメントカバレッジ**: {metrics.documentation_coverage:.1f}%

## 🎯 品質目標達成状況

| メトリクス | 目標値 | 現在値 | 状態 |
|-----------|--------|--------|------|
| コードカバレッジ | ≥85% | {metrics.code_coverage:.1f}% | {'✅' if metrics.code_coverage >= 85 else '❌'} |
| 複雑度 | ≤10 | {metrics.cyclomatic_complexity:.1f} | {'✅' if metrics.cyclomatic_complexity <= 10 else '❌'} |
| 解析時間 | ≤5秒 | {metrics.avg_analysis_time:.3f}秒 | {'✅' if metrics.avg_analysis_time <= 5.0 else '❌'} |
| エラー率 | ≤1% | {metrics.error_rate * 100:.2f}% | {'✅' if metrics.error_rate <= 0.01 else '❌'} |
| 脆弱性 | 0件 | {metrics.vulnerability_count}件 | {'✅' if metrics.vulnerability_count == 0 else '❌'} |
        """
        
        return report
    
    def save_report(self, report: str, output_path: str = "quality_report.md"):
        """レポートをファイルに保存"""
        Path(output_path).write_text(report, encoding='utf-8')
    
    def generate_json_report(self, metrics: QualityMetrics) -> str:
        """JSON形式のレポートを生成"""
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "metrics": {
                "code_quality": {
                    "coverage": metrics.code_coverage,
                    "complexity": metrics.cyclomatic_complexity,
                    "maintainability": metrics.maintainability_index,
                    "technical_debt": metrics.technical_debt_ratio
                },
                "performance": {
                    "avg_analysis_time": metrics.avg_analysis_time,
                    "memory_usage": metrics.memory_usage,
                    "throughput": metrics.throughput
                },
                "reliability": {
                    "error_rate": metrics.error_rate,
                    "crash_rate": metrics.crash_rate,
                    "recovery_time": metrics.recovery_time
                },
                "security": {
                    "vulnerability_count": metrics.vulnerability_count,
                    "security_score": metrics.security_score
                },
                "usability": {
                    "api_usability": metrics.api_usability_score,
                    "documentation_coverage": metrics.documentation_coverage
                }
            },
            "quality_gates": {
                "coverage_passed": metrics.code_coverage >= 85,
                "complexity_passed": metrics.cyclomatic_complexity <= 10,
                "performance_passed": metrics.avg_analysis_time <= 5.0,
                "reliability_passed": metrics.error_rate <= 0.01,
                "security_passed": metrics.vulnerability_count == 0
            }
        }
        
        return json.dumps(report_data, indent=2)
```

---

## 🔄 品質改善プロセス

### 継続的改善サイクル

#### 1. 週次品質レビュー

```markdown
## 週次品質レビューアジェンダ

### 1. メトリクス確認（15分）
- [ ] 品質メトリクスの傾向分析
- [ ] 目標達成状況の確認
- [ ] 異常値の特定と原因分析

### 2. 問題の特定（15分）
- [ ] 品質低下の要因分析
- [ ] 技術的負債の蓄積状況
- [ ] パフォーマンス劣化の確認

### 3. 改善計画（20分）
- [ ] 優先度付けされた改善項目
- [ ] 具体的なアクションプラン
- [ ] 担当者と期限の設定

### 4. 次週の目標設定（10分）
- [ ] 品質目標の設定
- [ ] 重点改善項目の決定
- [ ] 成功指標の定義
```

#### 2. 品質改善アクション

```python
# scripts/quality_improvement.py
class QualityImprovementPlan:
    """品質改善計画"""
    
    def __init__(self):
        self.improvement_actions = []
    
    def analyze_quality_issues(self, metrics: QualityMetrics) -> List[str]:
        """品質問題の分析"""
        issues = []
        
        if metrics.code_coverage < 85:
            issues.append("低いコードカバレッジ")
        
        if metrics.cyclomatic_complexity > 10:
            issues.append("高い複雑度")
        
        if metrics.avg_analysis_time > 5.0:
            issues.append("パフォーマンス劣化")
        
        if metrics.error_rate > 0.01:
            issues.append("高いエラー率")
        
        return issues
    
    def generate_improvement_plan(self, issues: List[str]) -> Dict[str, List[str]]:
        """改善計画の生成"""
        improvement_plan = {}
        
        for issue in issues:
            if issue == "低いコードカバレッジ":
                improvement_plan[issue] = [
                    "未テストコードの特定",
                    "単体テストの追加",
                    "統合テストの強化",
                    "テストカバレッジの監視強化"
                ]
            elif issue == "高い複雑度":
                improvement_plan[issue] = [
                    "複雑な関数の分割",
                    "責務の分離",
                    "デザインパターンの適用",
                    "リファクタリングの実施"
                ]
            elif issue == "パフォーマンス劣化":
                improvement_plan[issue] = [
                    "ボトルネックの特定",
                    "アルゴリズムの最適化",
                    "キャッシュの活用",
                    "並列処理の導入"
                ]
            elif issue == "高いエラー率":
                improvement_plan[issue] = [
                    "エラーハンドリングの強化",
                    "入力値検証の追加",
                    "ログ出力の改善",
                    "例外処理の統一"
                ]
        
        return improvement_plan
```

---

## 📚 参考資料

### 品質保証ツール

#### 1. 静的解析ツール
- **Black**: コードフォーマッター
- **Flake8**: コードスタイルチェッカー
- **MyPy**: 型チェッカー
- **Bandit**: セキュリティスキャナー
- **Radon**: 複雑度測定

#### 2. テストツール
- **pytest**: テストフレームワーク
- **pytest-cov**: カバレッジ測定
- **pytest-benchmark**: パフォーマンステスト
- **pytest-mock**: モックライブラリ

#### 3. 品質監視ツール
- **SonarQube**: 品質管理プラットフォーム
- **CodeClimate**: 品質分析サービス
- **Codecov**: カバレッジ監視サービス

### ベストプラクティス

#### 1. テスト戦略
- テストピラミッドの遵守
- テストファーストの開発
- 継続的テストの実施

#### 2. コードレビュー
- 建設的なフィードバック
- 知識共有の促進
- 品質基準の統一

#### 3. 継続的改善
- 定期的な品質レビュー
- メトリクスベースの改善
- チーム全体での品質意識向上

---

*最終更新: 2025年10月12日*
*作成者: tree-sitter-analyzer開発チーム*