
# トラブルシューティングガイド

## 📋 概要

このガイドは、tree-sitter-analyzerプロジェクトの開発・運用・移行過程で発生する可能性のある問題とその解決方法を包括的に説明します。

## 🎯 対象読者

- 開発者
- システム管理者
- QAエンジニア
- プロジェクトマネージャー

---

## 🔧 一般的な問題と解決方法

### 1. インストールとセットアップの問題

#### 問題: tree-sitterライブラリのインストールエラー

**症状**:
```bash
ERROR: Failed building wheel for tree-sitter-python
```

**原因**:
- コンパイラの不足
- Python開発ヘッダーの不足
- 古いpipバージョン

**解決方法**:

```bash
# 1. システム依存関係のインストール
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install build-essential python3-dev

# CentOS/RHEL
sudo yum groupinstall "Development Tools"
sudo yum install python3-devel

# macOS
xcode-select --install

# 2. pipのアップグレード
pip install --upgrade pip setuptools wheel

# 3. tree-sitterライブラリの再インストール
pip install --no-cache-dir tree-sitter-python tree-sitter-javascript tree-sitter-java
```

#### 問題: MCPサーバーの起動エラー

**症状**:
```bash
ModuleNotFoundError: No module named 'tree_sitter_analyzer.mcp'
```

**原因**:
- パッケージの不完全なインストール
- PYTHONPATHの設定問題

**解決方法**:

```bash
# 1. 開発モードでのインストール
pip install -e .

# 2. PYTHONPATHの設定確認
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# 3. MCPサーバーの起動確認
python -m tree_sitter_analyzer.mcp.server
```

### 2. プラグインシステムの問題

#### 問題: プラグインが読み込まれない

**症状**:
```python
PluginNotFoundError: No plugin found for language 'rust'
```

**診断手順**:

```python
# デバッグスクリプト: debug_plugin_loading.py
from tree_sitter_analyzer.plugins.manager import PluginManager
import traceback

def diagnose_plugin_loading():
    """プラグイン読み込み問題の診断"""
    manager = PluginManager()
    
    print("=== プラグイン診断レポート ===")
    
    # 1. 利用可能なプラグインの確認
    print("\n1. 利用可能なプラグイン:")
    available_plugins = manager.get_available_plugins()
    for plugin_name in available_plugins:
        print(f"  ✅ {plugin_name}")
    
    # 2. 各プラグインの読み込みテスト
    print("\n2. プラグイン読み込みテスト:")
    test_languages = ["python", "javascript", "java", "typescript", "html"]
    
    for language in test_languages:
        try:
            plugin = manager.get_plugin(language)
            print(f"  ✅ {language}: {plugin.__class__.__name__}")
            
            # 基本機能テスト
            extensions = plugin.get_file_extensions()
            queries = plugin.get_query_definitions()
            print(f"    - 拡張子: {extensions}")
            print(f"    - クエリ数: {len(queries)}")
            
        except Exception as e:
            print(f"  ❌ {language}: {str(e)}")
            print(f"    詳細: {traceback.format_exc()}")
    
    # 3. 依存関係の確認
    print("\n3. 依存関係の確認:")
    dependencies = [
        "tree_sitter",
        "tree_sitter_python", 
        "tree_sitter_javascript",
        "tree_sitter_java"
    ]
    
    for dep in dependencies:
        try:
            __import__(dep)
            print(f"  ✅ {dep}")
        except ImportError as e:
            print(f"  ❌ {dep}: {str(e)}")
    
    # 4. 設定ファイルの確認
    print("\n4. 設定ファイルの確認:")
    config_files = [
        "pyproject.toml",
        "tree_sitter_analyzer/plugins/__init__.py"
    ]
    
    import os
    for config_file in config_files:
        if os.path.exists(config_file):
            print(f"  ✅ {config_file}")
        else:
            print(f"  ❌ {config_file}: ファイルが見つかりません")

if __name__ == "__main__":
    diagnose_plugin_loading()
```

**解決方法**:

1. **プラグインの手動登録**:
```python
# tree_sitter_analyzer/plugins/__init__.py
from .python_plugin import PythonPlugin
from .javascript_plugin import JavaScriptPlugin

# プラグインの明示的登録
AVAILABLE_PLUGINS = {
    "python": PythonPlugin,
    "javascript": JavaScriptPlugin,
    # 他のプラグイン...
}
```

2. **依存関係の再インストール**:
```bash
pip uninstall tree-sitter-python tree-sitter-javascript tree-sitter-java
pip install tree-sitter-python tree-sitter-javascript tree-sitter-java
```

#### 問題: カスタムプラグインの実装エラー

**症状**:
```python
TypeError: Can't instantiate abstract class CustomPlugin with abstract methods get_language_object
```

**原因**:
- 抽象メソッドの未実装
- インターフェース仕様の不理解

**解決方法**:

```python
# 正しいプラグイン実装例
from tree_sitter_analyzer.plugins.base import BaseLanguagePlugin
import tree_sitter_rust

class RustPlugin(BaseLanguagePlugin):
    """Rustプラグインの正しい実装例"""
    
    def __init__(self):
        super().__init__()
        self.language = tree_sitter_rust.language()
        self.parser = tree_sitter.Parser()
        self.parser.set_language(self.language)
    
    # 必須メソッドの実装
    def get_language_name(self) -> str:
        return "rust"
    
    def get_file_extensions(self) -> List[str]:
        return [".rs"]
    
    def is_applicable(self, file_path: str) -> bool:
        return file_path.endswith(".rs")
    
    def get_language_object(self) -> tree_sitter.Language:
        return self.language
    
    def get_query_definitions(self) -> Dict[str, str]:
        return {
            "functions": """
                (function_item
                    name: (identifier) @function.name
                    parameters: (parameters) @function.params
                    body: (block) @function.body
                ) @function.definition
            """,
            # 他のクエリ定義...
        }
    
    def create_formatter(self, format_type: str, **kwargs):
        from tree_sitter_analyzer.formatters.rust import RustFormatter
        return RustFormatter(format_type, **kwargs)
```

### 3. クエリ実行の問題

#### 問題: Tree-sitterクエリの構文エラー

**症状**:
```python
tree_sitter.QueryError: Invalid query syntax at line 2
```

**診断ツール**:

```python
# debug_query_syntax.py
import tree_sitter
from tree_sitter_analyzer.core.unified_query_engine import UnifiedQueryEngine

def debug_query_syntax(language: str, query_string: str):
    """クエリ構文の詳細デバッグ"""
    print(f"=== クエリ構文デバッグ: {language} ===")
    
    try:
        # 1. 言語パーサーの取得
        engine = UnifiedQueryEngine()
        lang_obj = engine.get_language_object(language)
        
        print(f"✅ 言語オブジェクト取得成功: {language}")
        
        # 2. クエリのコンパイル
        query = lang_obj.query(query_string)
        print(f"✅ クエリコンパイル成功")
        print(f"   キャプチャ数: {len(query.captures)}")
        print(f"   パターン数: {len(query.patterns)}")
        
        # 3. サンプルコードでのテスト
        sample_codes = {
            "python": "def hello(): pass",
            "javascript": "function hello() {}",
            "java": "public void hello() {}"
        }
        
        if language in sample_codes:
            parser = tree_sitter.Parser()
            parser.set_language(lang_obj)
            
            tree = parser.parse(sample_codes[language].encode())
            matches = query.matches(tree.root_node)
            
            print(f"✅ サンプルコードでのマッチ数: {len(matches)}")
            
            for i, match in enumerate(matches):
                print(f"   マッチ {i+1}:")
                for capture in match.captures:
                    node = capture.node
                    print(f"     - {capture.name}: {node.type} at {node.start_point}-{node.end_point}")
        
    except tree_sitter.QueryError as e:
        print(f"❌ クエリ構文エラー: {str(e)}")
        
        # エラー位置の特定
        lines = query_string.split('\n')
        print("\nクエリ内容:")
        for i, line in enumerate(lines, 1):
            marker = " >>> " if "line" in str(e) and str(i) in str(e) else "     "
            print(f"{marker}{i:2d}: {line}")
        
        # 一般的な構文エラーのヒント
        print("\n💡 一般的な構文エラー:")
        print("   - 括弧の不一致: ( ) [ ] の対応を確認")
        print("   - クエリパターンの形式: (node_type) @capture_name")
        print("   - フィールド指定: field_name: (node_type)")
        print("   - 選択肢: [option1 option2]")
        
    except Exception as e:
        print(f"❌ その他のエラー: {str(e)}")
        import traceback
        print(traceback.format_exc())

# 使用例
if __name__ == "__main__":
    # 問題のあるクエリをテスト
    problematic_query = """
        (function_definition
            name: (identifier) @function.name
            parameters: (parameters @function.params  # 括弧の不一致
            body: (block) @function.body
        ) @function.definition
    """
    
    debug_query_syntax("python", problematic_query)
```

**解決方法**:

1. **クエリ構文の修正**:
```python
# 正しいクエリ構文
correct_query = """
    (function_definition
        name: (identifier) @function.name
        parameters: (parameters) @function.params
        body: (block) @function.body
    ) @function.definition
"""
```

2. **段階的なクエリ開発**:
```python
# 1. 基本パターンから開始
basic_query = "(function_definition) @function"

# 2. フィールドを段階的に追加
with_name = """
    (function_definition
        name: (identifier) @function.name
    ) @function
"""

# 3. 完全なクエリに拡張
full_query = """
    (function_definition
        name: (identifier) @function.name
        parameters: (parameters) @function.params
        body: (block) @function.body
    ) @function.definition
"""
```

#### 問題: クエリ結果が期待と異なる

**症状**:
- 期待したノードがキャプチャされない
- 余分なノードがキャプチャされる
- キャプチャ名が正しく設定されない

**診断ツール**:

```python
# debug_query_results.py
def debug_query_results(language: str, code: str, query_string: str):
    """クエリ結果の詳細デバッグ"""
    import tree_sitter
    from tree_sitter_analyzer.core.unified_query_engine import UnifiedQueryEngine
    
    print(f"=== クエリ結果デバッグ ===")
    print(f"言語: {language}")
    print(f"コード:\n{code}")
    print(f"クエリ:\n{query_string}")
    print("=" * 50)
    
    try:
        engine = UnifiedQueryEngine()
        lang_obj = engine.get_language_object(language)
        
        # パース実行
        parser = tree_sitter.Parser()
        parser.set_language(lang_obj)
        tree = parser.parse(code.encode())
        
        # AST構造の表示
        print("\n📊 AST構造:")
        def print_ast(node, depth=0):
            indent = "  " * depth
            print(f"{indent}{node.type} [{node.start_point}-{node.end_point}]")
            if node.text and len(node.text) < 50:
                print(f"{indent}  text: {node.text}")
            
            for child in node.children:
                if depth < 3:  # 深さ制限
                    print_ast(child, depth + 1)
        
        print_ast(tree.root_node)
        
        # クエリ実行
        query = lang_obj.query(query_string)
        matches = query.matches(tree.root_node)
        
        print(f"\n🎯 クエリ結果: {len(matches)}件のマッチ")
        
        for i, match in enumerate(matches):
            print(f"\nマッチ {i+1}:")
            for capture in match.captures:
                node = capture.node
                text = node.text.decode() if node.text else ""
                print(f"  📌 {capture.name}:")
                print(f"     タイプ: {node.type}")
                print(f"     位置: {node.start_point}-{node.end_point}")
                print(f"     テキスト: {text[:100]}...")
        
        # キャプチャ名の分析
        print(f"\n🏷️  利用可能なキャプチャ名:")
        for capture_name in query.capture_names:
            print(f"  - {capture_name}")
        
    except Exception as e:
        print(f"❌ エラー: {str(e)}")
        import traceback
        print(traceback.format_exc())

# 使用例
if __name__ == "__main__":
    sample_code = """
def calculate_sum(numbers):
    total = 0
    for num in numbers:
        total += num
    return total

class Calculator:
    def add(self, a, b):
        return a + b
    """
    
    test_query = """
        (function_definition
            name: (identifier) @function.name
            parameters: (parameters) @function.params
        ) @function.definition
    """
    
    debug_query_results("python", sample_code, test_query)
```

### 4. パフォーマンスの問題

#### 問題: 大きなファイルの解析が遅い

**症状**:
- 数MB以上のファイルで解析時間が数分かかる
- メモリ使用量が急激に増加
- システムが応答しなくなる

**診断ツール**:

```python
# performance_profiler.py
import time
import psutil
import os
from pathlib import Path
import cProfile
import pstats
from tree_sitter_analyzer.core.enhanced_analysis_engine import EnhancedAnalysisEngine

class PerformanceProfiler:
    """パフォーマンス分析ツール"""
    
    def __init__(self):
        self.process = psutil.Process(os.getpid())
    
    def profile_file_analysis(self, file_path: str, output_file: str = "profile_results.txt"):
        """ファイル解析のプロファイリング"""
        print(f"=== パフォーマンス分析: {file_path} ===")
        
        # ファイル情報
        file_size = os.path.getsize(file_path) / 1024 / 1024  # MB
        print(f"ファイルサイズ: {file_size:.2f}MB")
        
        # メモリ使用量の初期値
        initial_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        print(f"初期メモリ使用量: {initial_memory:.2f}MB")
        
        # プロファイリング実行
        profiler = cProfile.Profile()
        
        start_time = time.time()
        profiler.enable()
        
        try:
            engine = EnhancedAnalysisEngine()
            result = engine.analyze_file(file_path)
            
            profiler.disable()
            end_time = time.time()
            
            # 結果の分析
            analysis_time = end_time - start_time
            final_memory = self.process.memory_info().rss / 1024 / 1024  # MB
            memory_usage = final_memory - initial_memory
            
            print(f"解析時間: {analysis_time:.2f}秒")
            print(f"メモリ使用量: {memory_usage:.2f}MB")
            print(f"処理速度: {file_size/analysis_time:.2f}MB/秒")
            
            # 結果統計
            if result:
                print(f"関数数: {len(result.functions)}")
                print(f"クラス数: {len(result.classes)}")
                print(f"変数数: {len(result.variables)}")
            
            # プロファイル結果の保存
            stats = pstats.Stats(profiler)
            stats.sort_stats('cumulative')
            
            with open(output_file, 'w') as f:
                stats.print_stats(20, file=f)  # 上位20関数
            
            print(f"詳細プロファイル結果: {output_file}")
            
            # ボトルネックの特定
            self._identify_bottlenecks(stats)
            
        except Exception as e:
            profiler.disable()
            print(f"❌ 解析エラー: {str(e)}")
            import traceback
            print(traceback.format_exc())
    
    def _identify_bottlenecks(self, stats):
        """ボトルネックの特定"""
        print("\n🔍 ボトルネック分析:")
        
        # 時間のかかる関数を特定
        stats.sort_stats('cumulative')
        top_functions = []
        
        for func_info in stats.stats.items():
            func_name = func_info[0]
            func_stats = func_info[1]
            cumulative_time = func_stats[3]
            
            if cumulative_time > 0.1:  # 0.1秒以上の関数
                top_functions.append((func_name, cumulative_time))
        
        top_functions.sort(key=lambda x: x[1], reverse=True)
        
        for i, (func_name, time_spent) in enumerate(top_functions[:5]):
            print(f"  {i+1}. {func_name}: {time_spent:.2f}秒")
    
    def benchmark_different_approaches(self, file_path: str):
        """異なるアプローチのベンチマーク"""
        print(f"\n=== アプローチ別ベンチマーク ===")
        
        approaches = [
            ("標準解析", self._standard_analysis),
            ("ストリーミング解析", self._streaming_analysis),
            ("部分解析", self._partial_analysis),
        ]
        
        for name, approach_func in approaches:
            try:
                start_time = time.time()
                initial_memory = self.process.memory_info().rss / 1024 / 1024
                
                result = approach_func(file_path)
                
                end_time = time.time()
                final_memory = self.process.memory_info().rss / 1024 / 1024
                
                print(f"\n{name}:")
                print(f"  時間: {end_time - start_time:.2f}秒")
                print(f"  メモリ: {final_memory - initial_memory:.2f}MB")
                print(f"  結果数: {len(result) if result else 0}")
                
            except Exception as e:
                print(f"\n{name}: ❌ エラー - {str(e)}")
    
    def _standard_analysis(self, file_path: str):
        """標準解析"""
        engine = EnhancedAnalysisEngine()
        return engine.analyze_file(file_path)
    
    def _streaming_analysis(self, file_path: str):
        """ストリーミング解析（大きなファイル用）"""
        # 実装例: ファイルを分割して処理
        chunk_size = 1024 * 1024  # 1MB chunks
        results = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                
                # チャンクごとに解析
                # 実際の実装では、構文的に意味のある単位で分割する必要がある
                pass
        
        return results
    
    def _partial_analysis(self, file_path: str):
        """部分解析（関数定義のみなど）"""
        from tree_sitter_analyzer.models import AnalysisRequest
        
        engine = EnhancedAnalysisEngine()
        request = AnalysisRequest(query_types=["functions"])  # 関数のみ
        return engine.analyze_file(file_path, request)

# 使用例
if __name__ == "__main__":
    profiler = PerformanceProfiler()
    
    # 大きなファイルのプロファイリング
    large_file = "path/to/large_file.py"
    if os.path.exists(large_file):
        profiler.profile_file_analysis(large_file)
        profiler.benchmark_different_approaches(large_file)
    else:
        print("大きなテストファイルが見つかりません")
```

**解決方法**:

1. **ファイルサイズ制限の実装**:
```python
# tree_sitter_analyzer/core/file_size_limiter.py
class FileSizeLimiter:
    """ファイルサイズ制限"""
    
    def __init__(self, max_size_mb: int = 10):
        self.max_size_bytes = max_size_mb * 1024 * 1024
    
    def check_file_size(self, file_path: str) -> bool:
        """ファイルサイズをチェック"""
        file_size = os.path.getsize(file_path)
        
        if file_size > self.max_size_bytes:
            raise FileTooLargeError(
                f"File {file_path} is too large: "
                f"{file_size / 1024 / 1024:.2f}MB > "
                f"{self.max_size_bytes / 1024 / 1024:.2f}MB"
            )
        
        return True
```

2. **メモリ効率的な解析**:
```python
# tree_sitter_analyzer/core/memory_efficient_analyzer.py
class MemoryEfficientAnalyzer:
    """メモリ効率的な解析器"""
    
    def __init__(self):
        self.chunk_size = 1024 * 1024  # 1MB
        self.max_memory_mb = 500  # 500MB制限
    
    def analyze_large_file(self, file_path: str):
        """大きなファイルの効率的解析"""
        # メモリ監視
        process = psutil.Process(os.getpid())
        
        def check_memory():
            memory_mb = process.memory_info().rss / 1024 / 1024
            if memory_mb > self.max_memory_mb:
                raise MemoryLimitExceededError(f"Memory usage: {memory_mb:.2f}MB")
        
        # ストリーミング処理
        results = []
        with open(file_path, 'r', encoding='utf-8') as f:
            buffer = ""
            
            while True:
                chunk = f.read(self.chunk_size)
                if not chunk:
                    break
                
                buffer += chunk
                check_memory()
                
                # 完全な構文単位で処理
                complete_units = self._extract_complete_units(buffer)
                for unit in complete_units:
                    result = self._analyze_unit(unit)
                    results.append(result)
                    check_memory()
                
                # 残りのバッファを保持
                buffer = self._get_remaining_buffer(buffer, complete_units)
        
        return results
    
    def _extract_complete_units(self, buffer: str) -> List[str]:
        """完全な構文単位を抽出"""
        # 実装例: 関数やクラス定義の完全な単位を抽出
        units = []
        # ... 実装詳細
        return units
    
    def _analyze_unit(self, unit: str):
        """個別単位の解析"""
        # ... 実装詳細
        pass
    
    def _get_remaining_buffer(self, buffer: str, processed_units: List[str]) -> str:
        """処理済み単位を除いた残りのバッファ"""
        # ... 実装詳細
        return buffer
```

### 5. 移行関連の問題

#### 問題: 後方互換性の破綻

**症状**:
```python
AttributeError: 'EnhancedAnalysisEngine' object has no attribute 'old_method'
```

**診断ツール**:

```python
# compatibility_checker.py
def check_api_compatibility():
    """API互換性の包括的チェック"""
    from tree_sitter_analyzer.compatibility.legacy_adapter import LegacyAnalysisEngine
    from tree_sitter_analyzer.core.enhanced_analysis_engine import EnhancedAnalysisEngine
    
    print("=== API互換性チェック ===")
    
    # テストケース定義
    test_cases = [
        {
            "method": "analyze_file",
            "args": ["examples/sample.py", ["functions", "classes"]],
            "kwargs": {"output_format": "table"}
        },
        {
            "method": "query_file", 
            "args": ["examples/sample.py", "python", "functions"],
            "kwargs": {}
        },
        {
            "method": "get_supported_languages",
            "args": [],
            "kwargs": {}
        }
    ]
    
    legacy_engine = LegacyAnalysisEngine()
    enhanced_engine = EnhancedAnalysisEngine()
    
    compatibility_issues = []
    
    for test_case in test_cases:
        method_name = test_case["method"]
        args = test_case["args"]
        kwargs = test_case["kwargs"]
        
        print(f"\n🧪 テスト: {method_name}")
        
        # レガシーエンジンでのテスト
        try:
            legacy_method = getattr(legacy_engine, method_name)
            legacy_result = legacy_method(*args, **kwargs)
            print(f"  ✅ レガシー: 成功")
        except Exception as e:
            print(f"  ❌ レガシー: {str(e)}")
            compatibility_issues.append({
                "method": method_name,
                "engine": "legacy",
                "error": str(e)
            })
            continue
        
        # 新エンジンでのテスト（互換性レイヤー経由）
        try:
            if hasattr(enhanced_engine, method_name):
                enhanced_method = getattr(enhanced_engine, method_name)
                enhanced_result = enhanced_method(*args, **kwargs)
                print(f"  ✅ 新エンジン: 成功")
                
                # 結果の比較
                if method_name == "get_supported_languages":
                    if set(legacy_result) != set(enhanced_result):
                        print(f"  ⚠️  結果の差異: {set(legacy_result) ^ set(enhanced_result)}")
                
            else:
                print(f"  ❌ 新エンジン: メソッドが存在しません")
                compatibility_issues.append({
                    "method": method_name,
                    "engine": "enhanced",
                    "error": "Method not found"
                })
        
        except Exception as e:
            print(f"  ❌ 新エンジン: {str(e)}")
            compatibility_issues.append({
                "method": method_name,
                "engine": "enhanced", 
                "error": str(e)
            })
    
    # 互換性レポート
    if compatibility_issues:
        print(f"\n⚠️  互換性問題: {len(compatibility_issues)}件")
        for issue in compatibility_issues:
            print(f"  - {issue['method']} ({issue['engine']}): {issue['error']}")

    else:
        print("✅ 互換性問題なし")
    
    return compatibility_issues

if __name__ == "__main__":
    check_api_compatibility()
```

**解決方法**:

1. **互換性レイヤーの強化**:
```python
# tree_sitter_analyzer/compatibility/enhanced_legacy_adapter.py
class EnhancedLegacyAdapter:
    """強化された後方互換性アダプター"""
    
    def __init__(self):
        self.enhanced_engine = EnhancedAnalysisEngine()
        self.method_mappings = {
            "old_analyze": "analyze_file",
            "query_code": "analyze_file", 
            "format_results": "format_results"
        }
    
    def __getattr__(self, name):
        """動的メソッド解決"""
        # 1. 直接マッピング
        if name in self.method_mappings:
            return getattr(self.enhanced_engine, self.method_mappings[name])
        
        # 2. 新エンジンに存在するか確認
        if hasattr(self.enhanced_engine, name):
            return getattr(self.enhanced_engine, name)
        
        # 3. 非推奨メソッドの警告
        warnings.warn(
            f"Method '{name}' is deprecated and not available in the new engine. "
            f"Please refer to the migration guide for alternatives.",
            DeprecationWarning,
            stacklevel=2
        )
        
        # 4. フォールバック実装
        return self._create_fallback_method(name)
    
    def _create_fallback_method(self, method_name: str):
        """フォールバックメソッドの作成"""
        def fallback_method(*args, **kwargs):
            raise NotImplementedError(
                f"Method '{method_name}' is not implemented in the new engine. "
                f"Please use the enhanced API instead."
            )
        return fallback_method
```

#### 問題: 条件分岐削除後の機能不全

**症状**:
- 特定の言語で解析が失敗する
- 予期しない結果が返される
- 新しい言語が認識されない

**診断ツール**:

```python
# migration_validator.py
def validate_migration_completeness():
    """移行完了度の検証"""
    from scripts.conditional_branch_migration import ConditionalBranchAnalyzer
    
    print("=== 移行完了度検証 ===")
    
    analyzer = ConditionalBranchAnalyzer()
    remaining_branches = analyzer.analyze_project("tree_sitter_analyzer/")
    
    print(f"残存条件分岐: {sum(len(branches) for branches in remaining_branches.values())}件")
    
    if remaining_branches:
        print("\n🔍 残存条件分岐の詳細:")
        for file_path, branches in remaining_branches.items():
            print(f"\n📁 {file_path}:")
            for branch in branches:
                print(f"  Line {branch['line']}: {branch['content']}")
                print(f"    言語: {branch['language']}")
                print(f"    パターン: {branch['pattern']}")
    
    # プラグインベース実装の確認
    print("\n🔌 プラグインベース実装の確認:")
    from tree_sitter_analyzer.plugins.manager import PluginManager
    
    manager = PluginManager()
    plugins = manager.get_all_plugins()
    
    for language, plugin in plugins.items():
        print(f"  ✅ {language}: {plugin.__class__.__name__}")
        
        # プラグインの完全性チェック
        required_methods = [
            "get_language_name",
            "get_file_extensions", 
            "get_query_definitions",
            "create_formatter"
        ]
        
        missing_methods = []
        for method in required_methods:
            if not hasattr(plugin, method):
                missing_methods.append(method)
        
        if missing_methods:
            print(f"    ⚠️  不足メソッド: {missing_methods}")
    
    # 機能テスト
    print("\n🧪 機能テスト:")
    test_files = {
        "python": "examples/sample.py",
        "javascript": "examples/sample.js", 
        "java": "examples/Sample.java"
    }
    
    from tree_sitter_analyzer.core.enhanced_analysis_engine import EnhancedAnalysisEngine
    engine = EnhancedAnalysisEngine()
    
    for language, file_path in test_files.items():
        if os.path.exists(file_path):
            try:
                result = engine.analyze_file(file_path)
                print(f"  ✅ {language}: 解析成功 ({len(result.functions)}関数, {len(result.classes)}クラス)")
            except Exception as e:
                print(f"  ❌ {language}: 解析失敗 - {str(e)}")
        else:
            print(f"  ⏭️  {language}: テストファイルなし")

if __name__ == "__main__":
    validate_migration_completeness()
```

### 6. テストとCI/CDの問題

#### 問題: テストの失敗

**症状**:
```bash
FAILED tests/test_plugins.py::test_python_plugin - AssertionError: Expected 5 functions, got 3
```

**診断手順**:

```python
# test_debugger.py
import pytest
from pathlib import Path

def debug_test_failure(test_file: str, test_function: str):
    """テスト失敗の詳細デバッグ"""
    print(f"=== テスト失敗デバッグ: {test_file}::{test_function} ===")
    
    # 1. テスト環境の確認
    print("\n1. テスト環境:")
    import sys
    print(f"  Python: {sys.version}")
    print(f"  作業ディレクトリ: {os.getcwd()}")
    
    # 2. 依存関係の確認
    print("\n2. 依存関係:")
    required_packages = [
        "tree_sitter", "tree_sitter_python", "pytest"
    ]
    
    for package in required_packages:
        try:
            module = __import__(package)
            version = getattr(module, '__version__', 'unknown')
            print(f"  ✅ {package}: {version}")
        except ImportError:
            print(f"  ❌ {package}: 未インストール")
    
    # 3. テストデータの確認
    print("\n3. テストデータ:")
    test_data_dir = Path("test_samples")
    if test_data_dir.exists():
        for file_path in test_data_dir.glob("*.py"):
            print(f"  📄 {file_path}: {file_path.stat().st_size}bytes")
    else:
        print("  ❌ テストデータディレクトリが見つかりません")
    
    # 4. 実際のテスト実行
    print("\n4. テスト実行:")
    try:
        # テストを個別実行
        result = pytest.main(["-v", "-s", f"{test_file}::{test_function}"])
        print(f"  テスト結果: {result}")
    except Exception as e:
        print(f"  ❌ テスト実行エラー: {str(e)}")
    
    # 5. ログの確認
    print("\n5. ログ確認:")
    log_files = ["pytest.log", "test.log"]
    for log_file in log_files:
        if os.path.exists(log_file):
            print(f"  📋 {log_file}:")
            with open(log_file, 'r') as f:
                lines = f.readlines()[-10:]  # 最後の10行
                for line in lines:
                    print(f"    {line.strip()}")

# 使用例
if __name__ == "__main__":
    debug_test_failure("tests/test_plugins.py", "test_python_plugin")
```

**解決方法**:

1. **テストデータの標準化**:
```python
# tests/conftest.py
import pytest
from pathlib import Path

@pytest.fixture
def standard_test_files():
    """標準テストファイルの提供"""
    test_data = {
        "python": """
def hello_world():
    '''Hello world function'''
    print("Hello, World!")

class Calculator:
    def add(self, a, b):
        return a + b
    
    def subtract(self, a, b):
        return a - b

def main():
    calc = Calculator()
    result = calc.add(1, 2)
    print(result)

if __name__ == "__main__":
    main()
        """,
        "javascript": """
function helloWorld() {
    console.log("Hello, World!");
}

class Calculator {
    add(a, b) {
        return a + b;
    }
    
    subtract(a, b) {
        return a - b;
    }
}

function main() {
    const calc = new Calculator();
    const result = calc.add(1, 2);
    console.log(result);
}

main();
        """
    }
    
    # 一時ファイルの作成
    temp_files = {}
    for language, content in test_data.items():
        temp_file = Path(f"temp_test_{language}.{language}")
        temp_file.write_text(content)
        temp_files[language] = str(temp_file)
    
    yield temp_files
    
    # クリーンアップ
    for file_path in temp_files.values():
        Path(file_path).unlink(missing_ok=True)
```

2. **テストの堅牢性向上**:
```python
# tests/test_robust_plugins.py
def test_python_plugin_robust(standard_test_files):
    """堅牢なPythonプラグインテスト"""
    from tree_sitter_analyzer.plugins.manager import PluginManager
    
    manager = PluginManager()
    plugin = manager.get_plugin("python")
    
    file_path = standard_test_files["python"]
    
    # 解析実行
    result = plugin.analyze_file(file_path)
    
    # 柔軟な検証
    assert len(result.functions) >= 2, f"Expected at least 2 functions, got {len(result.functions)}"
    assert len(result.classes) >= 1, f"Expected at least 1 class, got {len(result.classes)}"
    
    # 具体的な関数名の確認
    function_names = [func.name for func in result.functions]
    expected_functions = ["hello_world", "main"]
    
    for expected_func in expected_functions:
        assert expected_func in function_names, f"Function '{expected_func}' not found in {function_names}"
    
    # クラス名の確認
    class_names = [cls.name for cls in result.classes]
    assert "Calculator" in class_names, f"Class 'Calculator' not found in {class_names}"
```

#### 問題: CI/CDパイプラインの失敗

**症状**:
- GitHub Actionsでテストが失敗
- 依存関係のインストールエラー
- 環境固有の問題

**解決方法**:

```yaml
# .github/workflows/robust_ci.yml
name: Robust CI/CD Pipeline

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python-version: [3.8, 3.9, "3.10", "3.11"]
        
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install system dependencies
      run: |
        if [ "$RUNNER_OS" == "Linux" ]; then
          sudo apt-get update
          sudo apt-get install -y build-essential
        elif [ "$RUNNER_OS" == "macOS" ]; then
          xcode-select --install || true
        fi
      shell: bash
    
    - name: Cache pip dependencies
      uses: actions/cache@v3
      with:
        path: ~/.cache/pip
        key: ${{ runner.os }}-pip-${{ hashFiles('**/pyproject.toml') }}
        restore-keys: |
          ${{ runner.os }}-pip-
    
    - name: Install dependencies with retry
      run: |
        python -m pip install --upgrade pip setuptools wheel
        for i in {1..3}; do
          pip install -e .[dev] && break || sleep 10
        done
    
    - name: Verify installation
      run: |
        python -c "import tree_sitter_analyzer; print('Installation successful')"
        python -c "import tree_sitter_python; print('tree-sitter-python OK')"
    
    - name: Run tests with coverage
      run: |
        pytest tests/ -v --cov=tree_sitter_analyzer --cov-report=xml
    
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
        fail_ci_if_error: false
```

### 7. デプロイメントの問題

#### 問題: パッケージングエラー

**症状**:
```bash
ERROR: Could not build wheels for tree-sitter-analyzer
```

**診断ツール**:

```python
# packaging_validator.py
def validate_packaging():
    """パッケージング検証"""
    import subprocess
    import sys
    from pathlib import Path
    
    print("=== パッケージング検証 ===")
    
    # 1. pyproject.tomlの確認
    pyproject_path = Path("pyproject.toml")
    if pyproject_path.exists():
        print("✅ pyproject.toml存在")
        
        import tomli
        with open(pyproject_path, 'rb') as f:
            config = tomli.load(f)
        
        # 必須フィールドの確認
        required_fields = [
            "project.name",
            "project.version", 
            "project.description",
            "project.dependencies"
        ]
        
        for field in required_fields:
            keys = field.split('.')
            value = config
            try:
                for key in keys:
                    value = value[key]
                print(f"  ✅ {field}: {value}")
            except KeyError:
                print(f"  ❌ {field}: 未設定")
    else:
        print("❌ pyproject.toml不存在")
    
    # 2. MANIFESTファイルの確認
    manifest_files = ["MANIFEST.in", "pyproject.toml"]
    for manifest_file in manifest_files:
        if Path(manifest_file).exists():
            print(f"✅ {manifest_file}存在")
        else:
            print(f"⚠️  {manifest_file}不存在")
    
    # 3. 必要ファイルの確認
    required_files = [
        "README.md",
        "LICENSE", 
        "tree_sitter_analyzer/__init__.py"
    ]
    
    for file_path in required_files:
        if Path(file_path).exists():
            print(f"✅ {file_path}")
        else:
            print(f"❌ {file_path}不存在")
    
    # 4. ビルドテスト
    print("\n🔨 ビルドテスト:")
    try:
        result = subprocess.run([
            sys.executable, "-m", "build", "--wheel", "--no-isolation"
        ], capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            print("✅ ビルド成功")
        else:
            print(f"❌ ビルド失敗: {result.stderr}")
    except subprocess.TimeoutExpired:
        print("❌ ビルドタイムアウト")
    except Exception as e:
        print(f"❌ ビルドエラー: {str(e)}")
    
    # 5. インストールテスト
    print("\n📦 インストールテスト:")
    wheel_files = list(Path("dist").glob("*.whl"))
    if wheel_files:
        latest_wheel = max(wheel_files, key=lambda x: x.stat().st_mtime)
        try:
            result = subprocess.run([
                sys.executable, "-m", "pip", "install", str(latest_wheel), "--force-reinstall"
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✅ インストール成功")
                
                # インポートテスト
                try:
                    import tree_sitter_analyzer
                    print("✅ インポート成功")
                except ImportError as e:
                    print(f"❌ インポート失敗: {str(e)}")
            else:
                print(f"❌ インストール失敗: {result.stderr}")
        except Exception as e:
            print(f"❌ インストールエラー: {str(e)}")
    else:
        print("❌ wheelファイルが見つかりません")

if __name__ == "__main__":
    validate_packaging()
```

**解決方法**:

1. **堅牢なパッケージング設定**:
```toml
# pyproject.toml
[build-system]
requires = [
    "setuptools>=61.0",
    "wheel",
    "setuptools-scm[toml]>=6.2"
]
build-backend = "setuptools.build_meta"

[project]
name = "tree-sitter-analyzer"
dynamic = ["version"]
description = "Enhanced tree-sitter analyzer with plugin architecture"
readme = "README.md"
license = {file = "LICENSE"}
authors = [
    {name = "Your Name", email = "your.email@example.com"}
]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.8",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
]
requires-python = ">=3.8"
dependencies = [
    "tree-sitter>=0.20.0",
    "tree-sitter-python>=0.20.0",
    "tree-sitter-javascript>=0.20.0", 
    "tree-sitter-java>=0.20.0",
    "click>=8.0.0",
    "rich>=12.0.0",
    "pydantic>=1.10.0"
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "black>=22.0.0",
    "isort>=5.10.0",
    "mypy>=0.991",
    "pre-commit>=2.20.0"
]
mcp = [
    "mcp>=0.1.0"
]

[project.urls]
Homepage = "https://github.com/yourusername/tree-sitter-analyzer"
Repository = "https://github.com/yourusername/tree-sitter-analyzer"
Documentation = "https://tree-sitter-analyzer.readthedocs.io"
"Bug Tracker" = "https://github.com/yourusername/tree-sitter-analyzer/issues"

[project.scripts]
tree-sitter-analyzer = "tree_sitter_analyzer.cli:main"

[tool.setuptools.packages.find]
where = ["."]
include = ["tree_sitter_analyzer*"]
exclude = ["tests*"]

[tool.setuptools.package-data]
tree_sitter_analyzer = ["queries/*.scm", "templates/*.txt"]

[tool.setuptools_scm]
write_to = "tree_sitter_analyzer/_version.py"
```

2. **MANIFEST.inファイル**:
```
# MANIFEST.in
include README.md
include LICENSE
include CHANGELOG.md
recursive-include tree_sitter_analyzer *.py
recursive-include tree_sitter_analyzer *.scm
recursive-include tree_sitter_analyzer *.txt
recursive-include docs *.md
recursive-exclude tests *
recursive-exclude .github *
global-exclude *.pyc
global-exclude __pycache__
```

---

## 🚨 緊急時対応

### システム障害時の対応手順

#### 1. 即座の対応

```bash
# 緊急時対応スクリプト
#!/bin/bash
# emergency_response.sh

echo "=== 緊急時対応開始 ==="

# 1. システム状態の確認
echo "1. システム状態確認"
python -c "import tree_sitter_analyzer; print('✅ パッケージ読み込み可能')" || echo "❌ パッケージ読み込み失敗"

# 2. 基本機能テスト
echo "2. 基本機能テスト"
python -c "
from tree_sitter_analyzer.core.enhanced_analysis_engine import EnhancedAnalysisEngine
engine = EnhancedAnalysisEngine()
print('✅ エンジン初期化成功')
" || echo "❌ エンジン初期化失敗"

# 3. ロールバック準備
echo "3. ロールバック準備"
if [ -d "backup/" ]; then
    echo "✅ バックアップディレクトリ存在"
    ls -la backup/ | tail -5
else
    echo "❌ バックアップディレクトリなし"
fi

# 4. ログ収集
echo "4. ログ収集"
mkdir -p emergency_logs/
cp *.log emergency_logs/ 2>/dev/null || echo "ログファイルなし"
python -c "
import traceback
import sys
try:
    from tree_sitter_analyzer.core.enhanced_analysis_engine import EnhancedAnalysisEngine
    engine = EnhancedAnalysisEngine()
    result = engine.analyze_file('examples/sample.py')
    print('✅ 基本解析成功')
except Exception as e:
    with open('emergency_logs/error_trace.txt', 'w') as f:
        f.write(traceback.format_exc())
    print(f'❌ 基本解析失敗: {str(e)}')
"

echo "=== 緊急時対応完了 ==="
```

#### 2. ロールバック手順

```python
# emergency_rollback.py
import shutil
import subprocess
import sys
from pathlib import Path
import json
from datetime import datetime

class EmergencyRollback:
    """緊急時ロールバック"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.backup_dir = self.project_root / "backup"
        self.rollback_log = []
    
    def execute_rollback(self, backup_timestamp: str = None):
        """ロールバック実行"""
        print("🔄 緊急ロールバック開始")
        
        try:
            # 1. バックアップの選択
            backup_path = self._select_backup(backup_timestamp)
            if not backup_path:
                raise Exception("利用可能なバックアップが見つかりません")
            
            print(f"📁 使用するバックアップ: {backup_path}")
            
            # 2. 現在の状態をバックアップ
            current_backup = self._backup_current_state()
            print(f"💾 現在の状態をバックアップ: {current_backup}")
            
            # 3. ファイルの復元
            self._restore_files(backup_path)
            print("📂 ファイル復元完了")
            
            # 4. 依存関係の復元
            self._restore_dependencies(backup_path)
            print("📦 依存関係復元完了")
            
            # 5. 動作確認
            if self._verify_rollback():
                print("✅ ロールバック成功")
                self._log_rollback_success(backup_path)
                return True
            else:
                print("❌ ロールバック後の動作確認失敗")
                return False
                
        except Exception as e:
            print(f"💥 ロールバック失敗: {str(e)}")
            self._log_rollback_failure(str(e))
            return False
    
    def _select_backup(self, timestamp: str = None) -> Path:
        """バックアップの選択"""
        if not self.backup_dir.exists():
            return None
        
        backups = list(self.backup_dir.glob("migration_*"))
        if not backups:
            return None
        
        if timestamp:
            target_backup = self.backup_dir / f"migration_{timestamp}"
            if target_backup.exists():
                return target_backup
        
        # 最新のバックアップを選択
        return max(backups, key=lambda x: x.stat().st_mtime)
    
    def _backup_current_state(self) -> Path:
        """現在の状態をバックアップ"""
        timestamp = int(datetime.now().timestamp())
        backup_path = self.backup_dir / f"emergency_backup_{timestamp}"
        backup_path.mkdir(parents=True, exist_ok=True)
        
        # 重要ディレクトリのバックアップ
        important_dirs = ["tree_sitter_analyzer", "docs", "tests"]
        for dir_name in important_dirs:
            source_dir = self.project_root / dir_name
            if source_dir.exists():
                shutil.copytree(source_dir, backup_path / dir_name)
        
        return backup_path
    
    def _restore_files(self, backup_path: Path):
        """ファイルの復元"""
        # 現在のファイルを削除
        dirs_to_restore = ["tree_sitter_analyzer", "docs"]
        for dir_name in dirs_to_restore:
            current_dir = self.project_root / dir_name
            if current_dir.exists():
                shutil.rmtree(current_dir)
        
        # バックアップから復元
        for dir_name in dirs_to_restore:
            backup_source = backup_path / dir_name
            if backup_source.exists():
                shutil.copytree(backup_source, self.project_root / dir_name)
    
    def _restore_dependencies(self, backup_path: Path):
        """依存関係の復元"""
        # pyproject.tomlの復元
        backup_pyproject = backup_path / "pyproject.toml"
        if backup_pyproject.exists():
            shutil.copy2(backup_pyproject, self.project_root / "pyproject.toml")
            
            # 依存関係の再インストール
            subprocess.run([
                sys.executable, "-m", "pip", "install", "-e", "."
            ], check=True)
    
    def _verify_rollback(self) -> bool:
        """ロールバック後の動作確認"""
        try:
            # 基本インポートテスト
            import tree_sitter_analyzer
            
            # 基本機能テスト
            from tree_sitter_analyzer.core.enhanced_analysis_engine import EnhancedAnalysisEngine
            engine = EnhancedAnalysisEngine()
            
            # サンプルファイルでのテスト
            sample_file = self.project_root / "examples" / "sample.py"
            if sample_file.exists():
                result = engine.analyze_file(str(sample_file))
                return result is not None
            
            return True
            
        except Exception as e:
            print(f"動作確認エラー: {str(e)}")
            return False
    
    def _log_rollback_success(self, backup_path: Path):
        """ロールバック成功ログ"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": "rollback_success",
            "backup_used": str(backup_path),
            "status": "success"
        }
        self._write_log(log_entry)
    
    def _log_rollback_failure(self, error: str):
        """ロールバック失敗ログ"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": "rollback_failure", 
            "error": error,
            "status": "failure"
        }
        self._write_log(log_entry)
    
    def _write_log(self, log_entry: dict):
        """ログの書き込み"""
        log_file = self.project_root / "emergency_rollback.log"
        with open(log_file, 'a') as f:
            f.write(json.dumps(log_entry) + "\n")

if __name__ == "__main__":
    rollback = EmergencyRollback()
    
    # コマンドライン引数からタイムスタンプを取得
    timestamp = sys.argv[1] if len(sys.argv) > 1 else None
    
    success = rollback.execute_rollback(timestamp)
    sys.exit(0 if success else 1)
```

---

## 📞 サポートとエスカレーション

### サポート体制

#### 1. 問題の分類と対応レベル

| レベル | 問題の種類 | 対応時間 | 対応者 |
|--------|------------|----------|--------|
| P0 | システム全体停止 | 即座 | 全チーム |
| P1 | 主要機能停止 | 2時間以内 | シニア開発者 |
| P2 | 部分的機能不全 |
 1日以内 | 開発者 |
| P3 | 軽微な問題・改善要求 | 1週間以内 | 開発者 |

#### 2. エスカレーション手順

```python
# support_escalation.py
from enum import Enum
from datetime import datetime, timedelta
import json

class PriorityLevel(Enum):
    P0 = "critical"
    P1 = "high" 
    P2 = "medium"
    P3 = "low"

class SupportTicket:
    """サポートチケット管理"""
    
    def __init__(self, title: str, description: str, priority: PriorityLevel):
        self.id = self._generate_ticket_id()
        self.title = title
        self.description = description
        self.priority = priority
        self.created_at = datetime.now()
        self.status = "open"
        self.assigned_to = None
        self.escalation_history = []
    
    def _generate_ticket_id(self) -> str:
        """チケットID生成"""
        timestamp = int(datetime.now().timestamp())
        return f"TSA-{timestamp}"
    
    def escalate(self, reason: str, escalated_to: str):
        """エスカレーション実行"""
        escalation = {
            "timestamp": datetime.now().isoformat(),
            "reason": reason,
            "escalated_to": escalated_to,
            "escalated_by": self.assigned_to
        }
        self.escalation_history.append(escalation)
        self.assigned_to = escalated_to
        
        print(f"🚨 チケット {self.id} をエスカレーション")
        print(f"   理由: {reason}")
        print(f"   エスカレーション先: {escalated_to}")
    
    def check_sla_breach(self) -> bool:
        """SLA違反チェック"""
        sla_hours = {
            PriorityLevel.P0: 0,  # 即座
            PriorityLevel.P1: 2,
            PriorityLevel.P2: 24,
            PriorityLevel.P3: 168  # 1週間
        }
        
        max_hours = sla_hours[self.priority]
        elapsed = datetime.now() - self.created_at
        
        return elapsed > timedelta(hours=max_hours)
    
    def auto_escalate_if_needed(self):
        """自動エスカレーション"""
        if self.check_sla_breach() and self.status == "open":
            escalation_chain = {
                "developer": "senior_developer",
                "senior_developer": "team_lead",
                "team_lead": "engineering_manager"
            }
            
            current_assignee = self.assigned_to or "developer"
            next_assignee = escalation_chain.get(current_assignee)
            
            if next_assignee:
                self.escalate(
                    f"SLA違反による自動エスカレーション ({self.priority.value})",
                    next_assignee
                )

# 使用例
if __name__ == "__main__":
    # 緊急チケットの作成
    critical_ticket = SupportTicket(
        "システム全体が応答しない",
        "tree-sitter-analyzerが全く動作せず、すべての解析が失敗する",
        PriorityLevel.P0
    )
    
    # エスカレーション
    critical_ticket.escalate(
        "即座の対応が必要",
        "senior_developer"
    )
```

#### 3. 問題報告テンプレート

```markdown
# 問題報告テンプレート

## 基本情報
- **チケットID**: [自動生成]
- **報告者**: [名前]
- **報告日時**: [YYYY-MM-DD HH:MM:SS]
- **優先度**: [P0/P1/P2/P3]

## 問題の詳細
### 問題の概要
[問題の簡潔な説明]

### 発生環境
- **OS**: [Windows/Linux/macOS + バージョン]
- **Python**: [バージョン]
- **tree-sitter-analyzer**: [バージョン]
- **関連パッケージ**: [tree-sitter, tree-sitter-python等のバージョン]

### 再現手順
1. [手順1]
2. [手順2]
3. [手順3]

### 期待される動作
[正常に動作した場合の期待される結果]

### 実際の動作
[実際に発生した問題の詳細]

### エラーメッセージ
```
[エラーメッセージやスタックトレースをここに貼り付け]
```

### 関連ファイル
- **設定ファイル**: [pyproject.toml等]
- **ログファイル**: [関連するログファイル]
- **サンプルコード**: [問題を再現するコード]

## 影響範囲
- **影響を受ける機能**: [具体的な機能]
- **影響を受けるユーザー**: [開発者/エンドユーザー/システム管理者]
- **ビジネスへの影響**: [高/中/低]

## 試行した解決策
[既に試した解決方法があれば記載]

## 追加情報
[その他の関連情報]
```

### 4. よくある質問 (FAQ)

#### Q1: インストール時に「tree-sitter-python」のビルドが失敗する

**A**: 以下の手順で解決できます：

```bash
# 1. 開発ツールのインストール
# Ubuntu/Debian
sudo apt-get install build-essential python3-dev

# CentOS/RHEL  
sudo yum groupinstall "Development Tools"
sudo yum install python3-devel

# macOS
xcode-select --install

# 2. pipとsetuptoolsのアップグレード
pip install --upgrade pip setuptools wheel

# 3. キャッシュをクリアして再インストール
pip cache purge
pip install --no-cache-dir tree-sitter-python
```

#### Q2: 解析結果が期待と異なる

**A**: 以下の診断手順を実行してください：

```python
# 診断スクリプト
from tree_sitter_analyzer.core.enhanced_analysis_engine import EnhancedAnalysisEngine

def diagnose_analysis_issue(file_path: str):
    engine = EnhancedAnalysisEngine()
    
    # 1. ファイルの基本情報
    print(f"ファイル: {file_path}")
    print(f"サイズ: {os.path.getsize(file_path)} bytes")
    
    # 2. 言語検出
    detected_language = engine.detect_language(file_path)
    print(f"検出言語: {detected_language}")
    
    # 3. 利用可能なクエリ
    queries = engine.get_supported_queries(detected_language)
    print(f"利用可能クエリ: {queries}")
    
    # 4. 解析実行
    result = engine.analyze_file(file_path)
    print(f"関数数: {len(result.functions)}")
    print(f"クラス数: {len(result.classes)}")
    
    return result

# 使用例
result = diagnose_analysis_issue("your_file.py")
```

#### Q3: MCPサーバーが起動しない

**A**: 以下の確認を行ってください：

```bash
# 1. インストール確認
python -c "import tree_sitter_analyzer.mcp; print('MCP module OK')"

# 2. 依存関係確認
pip list | grep mcp

# 3. 手動起動テスト
python -m tree_sitter_analyzer.mcp.server

# 4. ポート確認
netstat -an | grep 8000  # デフォルトポート
```

#### Q4: パフォーマンスが遅い

**A**: パフォーマンス最適化の手順：

```python
# パフォーマンス最適化設定
from tree_sitter_analyzer.core.enhanced_analysis_engine import EnhancedAnalysisEngine
from tree_sitter_analyzer.models import AnalysisRequest

# 1. 必要最小限のクエリのみ実行
request = AnalysisRequest(
    query_types=["functions"],  # 必要なクエリのみ
    include_metadata=False,     # メタデータを除外
    max_depth=3                 # 解析深度を制限
)

# 2. キャッシュの活用
engine = EnhancedAnalysisEngine(enable_cache=True)

# 3. 大きなファイルの分割処理
def analyze_large_file_efficiently(file_path: str):
    file_size = os.path.getsize(file_path)
    
    if file_size > 1024 * 1024:  # 1MB以上
        # 分割処理
        return engine.analyze_file_streaming(file_path, request)
    else:
        # 通常処理
        return engine.analyze_file(file_path, request)
```

---

## 📚 参考資料

### 関連ドキュメント

1. **[実装ガイドライン](IMPLEMENTATION_GUIDELINES.md)** - 開発の基本方針
2. **[新言語プラグインガイド](NEW_LANGUAGE_PLUGIN_GUIDE.md)** - プラグイン開発手順
3. **[品質保証ガイド](QUALITY_ASSURANCE_GUIDE.md)** - テストと品質管理
4. **[移行実装ガイド](MIGRATION_IMPLEMENTATION_GUIDE.md)** - アーキテクチャ移行手順

### 外部リソース

1. **Tree-sitter公式ドキュメント**: https://tree-sitter.github.io/tree-sitter/
2. **Python tree-sitter**: https://github.com/tree-sitter/py-tree-sitter
3. **言語別パーサー**: https://github.com/tree-sitter
4. **MCPプロトコル**: https://modelcontextprotocol.io/

### コミュニティサポート

1. **GitHub Issues**: プロジェクトのIssueページで問題報告
2. **Discussions**: 一般的な質問や議論
3. **Stack Overflow**: `tree-sitter-analyzer`タグで質問
4. **Discord/Slack**: リアルタイムサポート（コミュニティチャンネル）

---

## 🔄 継続的改善

### フィードバック収集

```python
# feedback_collector.py
class FeedbackCollector:
    """フィードバック収集システム"""
    
    def __init__(self):
        self.feedback_file = "user_feedback.json"
        self.feedback_data = self._load_feedback()
    
    def collect_error_feedback(self, error_type: str, error_message: str, 
                              user_action: str, resolution: str = None):
        """エラー関連フィードバックの収集"""
        feedback = {
            "timestamp": datetime.now().isoformat(),
            "type": "error",
            "error_type": error_type,
            "error_message": error_message,
            "user_action": user_action,
            "resolution": resolution,
            "status": "resolved" if resolution else "open"
        }
        
        self.feedback_data.append(feedback)
        self._save_feedback()
    
    def collect_performance_feedback(self, operation: str, duration: float,
                                   file_size: int, satisfaction: int):
        """パフォーマンス関連フィードバックの収集"""
        feedback = {
            "timestamp": datetime.now().isoformat(),
            "type": "performance",
            "operation": operation,
            "duration": duration,
            "file_size": file_size,
            "satisfaction": satisfaction,  # 1-5スケール
        }
        
        self.feedback_data.append(feedback)
        self._save_feedback()
    
    def generate_improvement_suggestions(self) -> List[str]:
        """改善提案の生成"""
        suggestions = []
        
        # エラー頻度分析
        error_counts = {}
        for feedback in self.feedback_data:
            if feedback["type"] == "error":
                error_type = feedback["error_type"]
                error_counts[error_type] = error_counts.get(error_type, 0) + 1
        
        # 頻出エラーの特定
        frequent_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        for error_type, count in frequent_errors:
            suggestions.append(f"頻出エラー '{error_type}' の対策強化 (発生回数: {count})")
        
        # パフォーマンス問題の特定
        performance_issues = [
            f for f in self.feedback_data 
            if f["type"] == "performance" and f["satisfaction"] < 3
        ]
        
        if performance_issues:
            avg_duration = sum(f["duration"] for f in performance_issues) / len(performance_issues)
            suggestions.append(f"パフォーマンス改善が必要 (平均処理時間: {avg_duration:.2f}秒)")
        
        return suggestions
    
    def _load_feedback(self) -> List[dict]:
        """フィードバックデータの読み込み"""
        try:
            with open(self.feedback_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return []
    
    def _save_feedback(self):
        """フィードバックデータの保存"""
        with open(self.feedback_file, 'w') as f:
            json.dump(self.feedback_data, f, indent=2)

# 使用例
collector = FeedbackCollector()

# エラーフィードバック
collector.collect_error_feedback(
    "PluginNotFoundError",
    "No plugin found for language 'rust'", 
    "Rustファイルの解析を試行",
    "Rustプラグインを追加"
)

# パフォーマンスフィードバック
collector.collect_performance_feedback(
    "file_analysis",
    15.5,  # 15.5秒
    2048000,  # 2MB
    2  # 満足度2/5
)

# 改善提案の生成
suggestions = collector.generate_improvement_suggestions()
for suggestion in suggestions:
    print(f"💡 {suggestion}")
```

### ドキュメント更新プロセス

```python
# documentation_updater.py
class DocumentationUpdater:
    """ドキュメント自動更新"""
    
    def __init__(self):
        self.docs_dir = Path("docs")
        self.update_log = []
    
    def update_troubleshooting_guide(self, new_issue: dict):
        """トラブルシューティングガイドの更新"""
        guide_file = self.docs_dir / "TROUBLESHOOTING_GUIDE.md"
        
        # 新しい問題の追加
        new_section = f"""
#### 問題: {new_issue['title']}

**症状**:
{new_issue['symptoms']}

**原因**:
{new_issue['causes']}

**解決方法**:
{new_issue['solutions']}
"""
        
        # ファイルに追加
        with open(guide_file, 'a', encoding='utf-8') as f:
            f.write(new_section)
        
        self.update_log.append({
            "file": str(guide_file),
            "action": "add_issue",
            "title": new_issue['title'],
            "timestamp": datetime.now().isoformat()
        })
    
    def update_faq(self, question: str, answer: str):
        """FAQ更新"""
        guide_file = self.docs_dir / "TROUBLESHOOTING_GUIDE.md"
        
        faq_entry = f"""
#### Q: {question}

**A**: {answer}
"""
        
        # FAQ セクションに追加
        content = guide_file.read_text(encoding='utf-8')
        faq_section_start = content.find("### よくある質問 (FAQ)")
        
        if faq_section_start != -1:
            # FAQ セクションの最後に追加
            insertion_point = content.find("\n---", faq_section_start)
            if insertion_point != -1:
                new_content = content[:insertion_point] + faq_entry + content[insertion_point:]
                guide_file.write_text(new_content, encoding='utf-8')
        
        self.update_log.append({
            "file": str(guide_file),
            "action": "add_faq",
            "question": question,
            "timestamp": datetime.now().isoformat()
        })
    
    def generate_update_report(self) -> str:
        """更新レポートの生成"""
        if not self.update_log:
            return "ドキュメントの更新はありません。"
        
        report = ["# ドキュメント更新レポート", ""]
        
        for update in self.update_log:
            report.append(f"- **{update['timestamp']}**: {update['action']} in {update['file']}")
            if 'title' in update:
                report.append(f"  - 問題: {update['title']}")
            elif 'question' in update:
                report.append(f"  - 質問: {update['question']}")
        
        return "\n".join(report)

# 使用例
updater = DocumentationUpdater()

# 新しい問題の追加
new_issue = {
    "title": "Rustプラグインの読み込みエラー",
    "symptoms": "RustファイルでPluginNotFoundErrorが発生",
    "causes": "Rustプラグインが未実装",
    "solutions": "Rustプラグインの実装またはサポート言語の確認"
}

updater.update_troubleshooting_guide(new_issue)

# FAQ の追加
updater.update_faq(
    "新しい言語のサポートを追加するにはどうすればよいですか？",
    "NEW_LANGUAGE_PLUGIN_GUIDE.mdを参照して、プラグインを実装してください。"
)

# 更新レポート
print(updater.generate_update_report())
```

---

## 🎯 まとめ

このトラブルシューティングガイドは、tree-sitter-analyzerプロジェクトで発生する可能性のある問題に対する包括的な解決策を提供します。

### 主要なポイント

1. **予防的アプローチ**: 問題の発生を未然に防ぐための診断ツールと監視システム
2. **段階的解決**: 簡単な解決策から複雑な対応まで、段階的なアプローチ
3. **自動化**: 診断、ロールバック、エスカレーションの自動化
4. **継続的改善**: フィードバック収集とドキュメント更新の仕組み

### 緊急時の対応

1. **即座の対応**: 緊急時対応スクリプトの実行
2. **ロールバック**: 自動ロールバックシステムの活用
3. **エスカレーション**: 適切なサポート体制への連絡
4. **復旧確認**: システムの動作確認と検証

### 継続的な改善

1. **問題の分析**: 発生した問題の根本原因分析
2. **予防策の実装**: 同様の問題の再発防止
3. **ドキュメントの更新**: 新しい問題と解決策の追加
4. **チームの学習**: 問題解決のノウハウ共有

このガイドを活用することで、プロジェクトの安定性と信頼性を大幅に向上させることができます。