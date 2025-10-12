# 🤖 Tree-sitter Analyzer LLM開発用コンテキストガイド

> **AI開発者向けの構造化されたプロジェクト情報とコンテキスト**

## 📋 目次

- [1. 🎯 このガイドについて](#1--このガイドについて)
- [2. 🏗️ プロジェクト概要](#2-️-プロジェクト概要)
- [3. 📊 重要な統計情報](#3--重要な統計情報)
- [4. 🔧 開発時の重要なコンテキスト](#4--開発時の重要なコンテキスト)
- [5. 📝 実装パターンとサンプルコード](#5--実装パターンとサンプルコード)
- [6. ⚠️ 注意点とベストプラクティス](#6-️-注意点とベストプラクティス)
- [7. 🚀 よくある開発タスク](#7--よくある開発タスク)
- [8. 🔍 デバッグとトラブルシューティング](#8--デバッグとトラブルシューティング)

---

## 1. 🎯 このガイドについて

### 対象読者
- **LLM/AI開発者**: コード生成、改善、レビューを行うAI
- **AI支援開発者**: AIツールを活用してプロジェクトを改善する開発者
- **自動化ツール**: CI/CD、コード分析、品質保証ツール

### 使用方法
このガイドは、以下の場面で参照してください：
- 新機能の実装時
- バグ修正時
- コードレビュー時
- アーキテクチャ改善時
- 品質向上施策の検討時

---

## 2. 🏗️ プロジェクト概要

### 2.1 プロジェクトの本質

Tree-sitter Analyzerは、**統一されたインターフェースで多言語のコード解析を行うエンタープライズグレードのツール**です。

#### 核心的価値提案
```
🎯 統一性: 全言語で同一のAPIとクエリ構文
⚡ 高性能: Tree-sitterによる高速解析
🔌 拡張性: プラグインベースのアーキテクチャ
🤖 AI統合: MCP対応によるAIツールとの連携
```

#### 主要ユースケース
1. **コード構造分析**: クラス、関数、変数の抽出と分析
2. **品質評価**: 複雑度、規模、設計パターンの評価
3. **AI開発支援**: LLMへのコンテキスト提供
4. **大規模検索**: fd/ripgrepによる高速ファイル・コンテンツ検索

### 2.2 技術スタック

#### 核心技術
```python
# 解析エンジン
tree-sitter >= 0.20.0        # 統一AST解析
tree-sitter-languages        # 多言語サポート

# 高性能検索
fd-find                       # 高速ファイル検索
ripgrep                       # 高速コンテンツ検索

# AI統合
mcp                          # Model Context Protocol
```

#### 開発・品質保証
```python
# 開発ツール
black                        # コードフォーマット
isort                        # インポート整理
ruff                         # 高速リンター
mypy                         # 型チェック

# テスト
pytest >= 7.0.0             # テストフレームワーク
pytest-snapshot             # スナップショットテスト
coverage                     # カバレッジ測定
```

---

## 3. 📊 重要な統計情報

### 3.1 プロジェクト規模

```
📁 総ファイル数: 300+ ファイル
📄 総コード行数: 50,000+ 行
🧪 テスト数: 2,934 テスト
📊 カバレッジ: 80.09%
🌐 サポート言語: 6言語 (Java, Python, JavaScript, TypeScript, Markdown, HTML)
```

### 3.2 コンポーネント別統計

| コンポーネント | ファイル数 | 総サイズ | 複雑度 | 状態 |
|---------------|-----------|----------|--------|------|
| **言語プラグイン** | 6 | 336,661 bytes | 高 | 🟡 要最適化 |
| **MCPツール** | 12 | 231,164 bytes | 中 | 🟢 良好 |
| **コアエンジン** | 7 | 94,502 bytes | 中 | 🟡 要リファクタリング |
| **フォーマッター** | 9 | 133,965 bytes | 低 | 🟢 良好 |
| **テストスイート** | 159 | - | 低 | 🟢 良好 |

### 3.3 品質指標

```
✅ 品質スコア: A級 (80.09%カバレッジ)
⚠️ 技術的負債: 中程度 (54個の条件分岐要改善)
🚀 パフォーマンス: 高 (fd/ripgrep統合)
🔒 セキュリティ: 良好 (境界チェック実装済み)
```

---

## 4. 🔧 開発時の重要なコンテキスト

### 4.1 アーキテクチャの核心原則

#### **プラグイン指向設計**
```python
# ❌ 避けるべきパターン: コアエンジンに言語固有ロジック
def analyze_code(code: str, language: str):
    if language == "java":
        # Java固有処理
    elif language == "python":
        # Python固有処理
    # ... 54個の条件分岐が存在（要改善）

# ✅ 推奨パターン: プラグインベース
def analyze_code(code: str, language: str):
    plugin = plugin_manager.get_plugin(language)
    return plugin.analyze(code)
```

#### **統一要素モデル**
```python
# 全言語共通のデータ構造
@dataclass
class Element:
    name: str                    # 要素名
    element_type: str           # 要素タイプ (class, function, variable)
    start_line: int             # 開始行
    end_line: int               # 終了行
    start_column: int           # 開始列
    end_column: int             # 終了列
    content: str                # 要素の内容
    metadata: Dict[str, Any]    # 言語固有メタデータ
    children: List['Element']   # 子要素
```

### 4.2 重要な設計パターン

#### **ファクトリーパターン**
```python
# プラグインの動的生成
class PluginFactory:
    @classmethod
    def create_plugin(cls, language: str) -> LanguagePlugin:
        plugin_class = AVAILABLE_PLUGINS.get(language)
        if not plugin_class:
            raise UnsupportedLanguageError(language)
        return plugin_class()
```

#### **ストラテジーパターン**
```python
# 出力形式の切り替え
class OutputManager:
    def __init__(self, strategy: OutputStrategy):
        self._strategy = strategy
    
    def format_output(self, data: AnalysisResult) -> str:
        return self._strategy.format(data)
```

### 4.3 パフォーマンス最適化ポイント

#### **キャッシュ戦略**
```python
# ファイルハッシュベースキャッシュ
def analyze_with_cache(file_path: str) -> AnalysisResult:
    file_hash = calculate_file_hash(file_path)
    cached_result = cache.get(file_hash)
    if cached_result:
        return cached_result
    
    result = analyze_file(file_path)
    cache.put(file_hash, result)
    return result
```

#### **並列処理**
```python
# マルチプロセッシングによる高速化
def analyze_multiple_files(file_paths: List[str]) -> List[AnalysisResult]:
    with ProcessPoolExecutor(max_workers=cpu_count()) as executor:
        futures = [executor.submit(analyze_file, path) for path in file_paths]
        return [future.result() for future in as_completed(futures)]
```

---

## 5. 📝 実装パターンとサンプルコード

### 5.1 新言語プラグイン実装

#### **基本構造**
```python
# tree_sitter_analyzer/languages/new_language_plugin.py
from tree_sitter_analyzer.plugins.base import LanguagePlugin
from tree_sitter_analyzer.models import Element

class NewLanguagePlugin(LanguagePlugin):
    def get_language_name(self) -> str:
        return "new_language"
    
    def get_supported_extensions(self) -> List[str]:
        return [".newlang", ".nl"]
    
    def parse_elements(self, code: str, file_path: str) -> List[Element]:
        # Tree-sitterパーサーを使用した解析
        parser = self._get_parser()
        tree = parser.parse(bytes(code, "utf8"))
        
        elements = []
        for query_name, query_string in self.get_queries().items():
            query = self._language.query(query_string)
            captures = query.captures(tree.root_node)
            
            for node, capture_name in captures:
                element = self._create_element(node, capture_name, code)
                elements.append(element)
        
        return elements
    
    def get_queries(self) -> Dict[str, str]:
        return {
            "functions": """
                (function_declaration
                    name: (identifier) @function.name
                ) @function.definition
            """,
            "classes": """
                (class_declaration
                    name: (identifier) @class.name
                ) @class.definition
            """
        }
```

#### **クエリ定義パターン**
```python
# tree_sitter_analyzer/queries/new_language.py
QUERIES = {
    # 関数定義の抽出
    "functions": """
        (function_declaration
            name: (identifier) @function.name
            parameters: (parameter_list) @function.parameters
            body: (block) @function.body
        ) @function.definition
    """,
    
    # クラス定義の抽出
    "classes": """
        (class_declaration
            name: (identifier) @class.name
            superclass: (superclass)? @class.superclass
            body: (class_body) @class.body
        ) @class.definition
    """,
    
    # 変数定義の抽出
    "variables": """
        (variable_declaration
            declarator: (variable_declarator
                name: (identifier) @variable.name
                value: (_)? @variable.value
            )
        ) @variable.definition
    """
}
```

### 5.2 MCPツール実装

#### **基本MCPツール構造**
```python
# tree_sitter_analyzer/mcp/tools/custom_tool.py
from tree_sitter_analyzer.mcp.tools.base_tool import BaseTool

class CustomAnalysisTool(BaseTool):
    name = "custom_analysis"
    description = "カスタム解析を実行"
    
    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "解析対象ファイルのパス"
                },
                "analysis_type": {
                    "type": "string",
                    "enum": ["complexity", "structure", "patterns"],
                    "description": "解析タイプ"
                }
            },
            "required": ["file_path"]
        }
    
    async def execute(self, arguments: dict) -> dict:
        file_path = arguments["file_path"]
        analysis_type = arguments.get("analysis_type", "structure")
        
        # セキュリティチェック
        safe_path = self.path_resolver.resolve_path(file_path)
        
        # 解析実行
        result = await self._perform_analysis(safe_path, analysis_type)
        
        return {
            "file_path": file_path,
            "analysis_type": analysis_type,
            "result": result
        }
```

### 5.3 テスト実装パターン

#### **包括的テストクラス**
```python
# tests/test_new_language_plugin.py
import pytest
from tree_sitter_analyzer.languages.new_language_plugin import NewLanguagePlugin

class TestNewLanguagePlugin:
    @pytest.fixture
    def plugin(self):
        return NewLanguagePlugin()
    
    @pytest.fixture
    def sample_code(self):
        return """
        class Example {
            function hello(name) {
                return "Hello, " + name;
            }
        }
        """
    
    class TestBasicFunctionality:
        def test_language_name(self, plugin):
            assert plugin.get_language_name() == "new_language"
        
        def test_supported_extensions(self, plugin):
            extensions = plugin.get_supported_extensions()
            assert ".newlang" in extensions
            assert ".nl" in extensions
    
    class TestParsing:
        def test_parse_classes(self, plugin, sample_code):
            elements = plugin.parse_elements(sample_code, "test.newlang")
            classes = [e for e in elements if e.element_type == "class"]
            
            assert len(classes) == 1
            assert classes[0].name == "Example"
        
        def test_parse_functions(self, plugin, sample_code):
            elements = plugin.parse_elements(sample_code, "test.newlang")
            functions = [e for e in elements if e.element_type == "function"]
            
            assert len(functions) == 1
            assert functions[0].name == "hello"
    
    class TestEdgeCases:
        def test_empty_file(self, plugin):
            elements = plugin.parse_elements("", "empty.newlang")
            assert elements == []
        
        def test_malformed_code(self, plugin):
            malformed = "class { function }"
            # エラーが発生しても例外を投げない
            elements = plugin.parse_elements(malformed, "bad.newlang")
            assert isinstance(elements, list)
```

---

## 6. ⚠️ 注意点とベストプラクティス

### 6.1 アーキテクチャ上の制約

#### **現在の技術的負債**
```python
# ⚠️ 現在のコアエンジンに存在する問題
class UnifiedAnalysisEngine:
    def analyze(self, file_path: str) -> AnalysisResult:
        # 54個の言語固有条件分岐が存在（要改善）
        if language == "java":
            # Java固有処理
        elif language == "python":
            # Python固有処理
        # ... 他52個の条件分岐
```

#### **推奨される改善方向**
```python
# ✅ 目標アーキテクチャ
class UnifiedAnalysisEngine:
    def analyze(self, file_path: str) -> AnalysisResult:
        plugin = self.plugin_manager.get_plugin_for_file(file_path)
        return plugin.analyze(file_path)  # 条件分岐なし
```

### 6.2 パフォーマンス考慮事項

#### **大規模ファイル処理**
```python
# ✅ メモリ効率的な実装
def process_large_file(file_path: str) -> Iterator[Element]:
    """大規模ファイルをチャンクごとに処理"""
    with open(file_path, 'r', encoding='utf-8') as f:
        for chunk in read_in_chunks(f, chunk_size=1024*1024):
            elements = parse_chunk(chunk)
            yield from elements

# ❌ 避けるべき: 全体をメモリに読み込み
def process_large_file_bad(file_path: str) -> List[Element]:
    with open(file_path, 'r') as f:
        content = f.read()  # 大規模ファイルでメモリ不足の可能性
    return parse_all(content)
```

#### **キャッシュ活用**
```python
# ✅ 効率的なキャッシュ利用
@lru_cache(maxsize=128)
def get_language_parser(language: str):
    """言語パーサーのキャッシュ"""
    return load_parser(language)

# ファイルハッシュベースキャッシュ
def analyze_with_cache(file_path: str) -> AnalysisResult:
    file_hash = calculate_file_hash(file_path)
    if cached_result := cache.get(file_hash):
        return cached_result
    
    result = analyze_file(file_path)
    cache.put(file_hash, result)
    return result
```

### 6.3 セキュリティ考慮事項

#### **パス検証**
```python
# ✅ 安全なパス処理
def validate_file_path(file_path: str) -> str:
    """ファイルパスの安全性を検証"""
    # パスの正規化
    normalized_path = os.path.normpath(os.path.abspath(file_path))
    
    # ディレクトリトラバーサル攻撃の防止
    if ".." in normalized_path:
        raise SecurityError("ディレクトリトラバーサルは許可されていません")
    
    return normalized_path
```

#### **入力検証**
```python
# ✅ 正規表現の安全性チェック
def validate_regex(pattern: str) -> bool:
    """正規表現パターンの安全性を検証"""
    dangerous_patterns = [
        r'\(\?\#',      # コメント構文
        r'\(\?\=',      # 先読み
        r'\(\?\!',      # 否定先読み
    ]
    
    for dangerous in dangerous_patterns:
        if dangerous in pattern:
            return False
    
    return True
```

---

## 7. 🚀 よくある開発タスク

### 7.1 新言語サポート追加

#### **Step-by-Step実装ガイド**

**Step 1: プラグインクラス作成**
```bash
# ファイル作成
touch tree_sitter_analyzer/languages/rust_plugin.py
touch tree_sitter_analyzer/queries/rust.py
touch tree_sitter_analyzer/formatters/rust_formatter.py
touch tests/test_rust_plugin.py
```

**Step 2: 依存関係追加**
```toml
# pyproject.toml に追加
[tool.poetry.dependencies]
tree-sitter-rust = "^0.20.0"
```

**Step 3: プラグイン実装**
```python
# 最小限の実装から開始
class RustPlugin(LanguagePlugin):
    def get_language_name(self) -> str:
        return "rust"
    
    def get_supported_extensions(self) -> List[str]:
        return [".rs"]
    
    def parse_elements(self, code: str, file_path: str) -> List[Element]:
        # 基本的な関数抽出から開始
        return self._extract_functions(code)
```

**Step 4: テスト作成**
```python
# 段階的なテスト実装
def test_basic_function_parsing():
    plugin = RustPlugin()
    code = "fn hello() { println!('Hello'); }"
    elements = plugin.parse_elements(code, "test.rs")
    assert len(elements) == 1
    assert elements[0].name == "hello"
```

### 7.2 パフォーマンス改善

#### **プロファイリング実装**
```python
# パフォーマンス測定
import cProfile
import pstats

def profile_analysis(file_path: str):
    """解析処理のプロファイリング"""
    profiler = cProfile.Profile()
    profiler.enable()
    
    result = analyze_file(file_path)
    
    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(10)  # 上位10個の関数を表示
    
    return result
```

#### **メモリ使用量監視**
```python
import psutil
import os

def monitor_memory_usage():
    """メモリ使用量の監視"""
    process = psutil.Process(os.getpid())
    
    def get_memory_mb():
        return process.memory_info().rss / 1024 / 1024
    
    initial_memory = get_memory_mb()
    
    # 処理実行
    yield initial_memory
    
    final_memory = get_memory_mb()
    yield final_memory
    yield final_memory - initial_memory  # 増加量
```

### 7.3 品質向上

#### **スナップショットテスト追加**
```python
# 新しいスナップショットテストの追加
def test_rust_analysis_snapshot(snapshot):
    """Rust解析結果のスナップショットテスト"""
    code = load_test_file("sample.rs")
    result = analyze_code(code, "rust")
    
    # 結果をスナップショットと比較
    snapshot.assert_match(result.to_dict(), "rust_analysis_result.json")
```

#### **カバレッジ向上**
```bash
# カバレッジ測定と改善
pytest --cov=tree_sitter_analyzer --cov-report=html
# htmlcov/index.html でカバレッジ詳細を確認
```

---

## 8. 🔍 デバッグとトラブルシューティング

### 8.1 よくある問題と解決方法

#### **Tree-sitterパーサーの問題**
```python
# 問題: パーサーが見つからない
ImportError: No module named 'tree_sitter_rust'

# 解決方法
pip install tree-sitter-rust

# または、動的インポートでエラーハンドリング
try:
    import tree_sitter_rust as ts_rust
    language = ts_rust.language()
except ImportError:
    raise ImportError(
        "tree-sitter-rust パッケージが必要です。\n"
        "pip install tree-sitter-rust"
    )
```

#### **メモリ不足問題**
```python
# 問題: 大規模ファイルでメモリ不足
MemoryError: Unable to allocate array

# 解決方法: チャンク処理
def process_large_file_safely(file_path: str) -> List[Element]:
    """大規模ファイルの安全な処理"""
    file_size = os.path.getsize(file_path)
    
    if file_size > 10 * 1024 * 1024:  # 10MB以上
        return process_in_chunks(file_path)
    else:
        return process_normally(file_path)
```

#### **パフォーマンス問題**
```python
# 問題: 解析が遅い
# 解決方法: プロファイリングと最適化

# 1. ボトルネックの特定
@profile_time
def analyze_file(file_path: str) -> AnalysisResult:
    # 処理時間を測定
    pass

# 2. キャッシュの活用
@lru_cache(maxsize=128)
def get_cached_parser(language: str):
    return load_parser(language)

# 3. 並列処理の導入
def analyze_multiple_files_parallel(file_paths: List[str]):
    with ProcessPoolExecutor() as executor:
        return list(executor.map(analyze_file, file_paths))
```

### 8.2 デバッグユーティリティ

#### **詳細ログ出力**
```python
# デバッグ用の詳細ログ
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def debug_analysis(file_path: str):
    """デバッグ用の詳細解析"""
    logger.debug(f"解析開始: {file_path}")
    
    # 言語検出
    language = detect_language(file_path)
    logger.debug(f"検出言語: {language}")
    
    # プラグイン取得
    plugin = get_plugin(language)
    logger.debug(f"使用プラグイン: {plugin.__class__.__name__}")
    
    # 解析実行
    result = plugin.analyze(file_path)
    logger.debug(f"解析結果: {len(result.elements)}個の要素")
    
    return result
```

#### **Tree-sitterクエリのデバッグ**
```python
def debug_tree_sitter_query(code: str, query_string: str, language: str):
    """Tree-sitterクエリのデバッグ"""
    parser = get_parser(language)
    tree = parser.parse(bytes(code, "utf8"))
    
    # AST構造の表示
    print("AST構造:")
    print_ast(tree.root_node)
    
    # クエリ実行
    query = language.query(query_string)
    captures = query.captures(tree.root_node)
    
    print(f"\nクエリ結果: {len(captures)}個のマッチ")
    for node, capture_name in captures:
        print(f"  {capture_name}: {node.text.decode('utf8')}")
```

### 8.3 テストデバッグ

#### **失敗テストの詳細分析**
```python
# テスト失敗時の詳細情報出力
def test_with_debug_info():
    try:
        result = analyze_file("test.py")
        assert len(result.elements) == 5
    except AssertionError as e:
        # 詳細情報を出力
        print(f"期待値: 5, 実際: {len(result.elements)}")
        print("実際の要素:")
        for i, element in enumerate(result.elements):
            print(f"  {i}: {element.name} ({element.element_type})")
        raise
```

---

## 🎯 まとめ

### ✅ 重要なポイント

1. **アーキテクチャ理解**: プラグインベース設計の活用
2. **パフォーマンス**: キャッシュと並列処理の重要性
3. **品質保証**: 包括的テストとスナップショットテスト
4. **セキュリティ**: 入力検証とパス検証の徹底
5. **拡張性**: 新機能は既存コードを変更せずに追加

### 🚀 開発効率化のコツ

1. **段階的実装**: 最小限の機能から開始し、徐々に拡張
2. **テスト駆動**: 実装前にテストを作成
3. **プロファイリング**: パフォーマンス問題は測定から
4. **ドキュメント**: 実装と同時にドキュメントを更新
5. **レビュー**: 既存パターンとの整合性を確認

### 📚 参考資料

- **[DEVELOPER_GUIDE.md](./DEVELOPER_GUIDE.md)**: 開発者向け総合ガイド
- **[PROJECT_STRUCTURE.md](./PROJECT_STRUCTURE.md)**: プロジェクト構造詳細
- **[IMPLEMENTATION_RULES.md](./IMPLEMENTATION_RULES.md)**: 実装ルールとパターン
- **[ARCHITECTURE_DECISIONS.md](./ARCHITECTURE_DECISIONS.md)**: アーキテクチャ決定記録
- **[training/](../training/)**: 詳細なトレーニング資料

---

**🤖 このガイドは、AI開発者がTree-sitter Analyzerプロジェクトを効率的に理解し、高品質なコードを生成するための包括的なコンテキストを提供します。**