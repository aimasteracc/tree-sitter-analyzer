# 🛠️ Tree-sitter Analyzer 実装ルール

> **コーディング規約、設計パターン、実装ガイドライン**

## 📋 目次

- [1. 🎯 基本原則](#1--基本原則)
- [2. 📝 コーディング規約](#2--コーディング規約)
- [3. 🏗️ 設計パターン](#3-️-設計パターン)
- [4. 🔌 プラグイン開発ルール](#4--プラグイン開発ルール)
- [5. 🧪 テスト実装ルール](#5--テスト実装ルール)
- [6. 📊 パフォーマンス最適化](#6--パフォーマンス最適化)
- [7. 🔒 セキュリティガイドライン](#7--セキュリティガイドライン)
- [8. 📚 ドキュメント作成ルール](#8--ドキュメント作成ルール)

---

## 1. 🎯 基本原則

### 1.1 SOLID原則の適用

#### **単一責任原則 (SRP)**
```python
# ❌ 悪い例: 複数の責任を持つクラス
class LanguageProcessor:
    def parse_code(self, code: str) -> AST: ...
    def format_output(self, data: dict) -> str: ...
    def save_to_file(self, content: str, path: str) -> None: ...

# ✅ 良い例: 責任を分離
class CodeParser:
    def parse(self, code: str) -> AST: ...

class OutputFormatter:
    def format(self, data: dict) -> str: ...

class FileWriter:
    def write(self, content: str, path: str) -> None: ...
```

#### **開放閉鎖原則 (OCP)**
```python
# ✅ 拡張に開放、修正に閉鎖
class LanguagePlugin(ABC):
    @abstractmethod
    def get_supported_extensions(self) -> List[str]: ...
    
    @abstractmethod
    def parse_elements(self, code: str) -> List[Element]: ...

# 新しい言語サポートは既存コードを変更せずに追加
class RustPlugin(LanguagePlugin):
    def get_supported_extensions(self) -> List[str]:
        return ['.rs']
    
    def parse_elements(self, code: str) -> List[Element]:
        # Rust固有の実装
        pass
```

#### **依存性逆転原則 (DIP)**
```python
# ✅ 抽象に依存、具象に依存しない
class AnalysisEngine:
    def __init__(self, plugin_manager: PluginManagerInterface):
        self._plugin_manager = plugin_manager  # インターフェースに依存
    
    def analyze(self, file_path: str) -> AnalysisResult:
        plugin = self._plugin_manager.get_plugin_for_file(file_path)
        return plugin.analyze(file_path)
```

### 1.2 設計哲学

#### **プラグイン指向アーキテクチャ**
- 新機能は既存コードを変更せずにプラグインとして追加
- コアエンジンは言語固有のロジックを含まない
- プラグインは独立してテスト可能

#### **パフォーマンス重視**
- 大規模ファイルの効率的な処理
- メモリ使用量の最適化
- キャッシュ機能の活用

#### **エラーハンドリング**
- 明確なエラーメッセージ
- 段階的なフォールバック
- ユーザーフレンドリーな例外処理

---

## 2. 📝 コーディング規約

### 2.1 Python コーディングスタイル

#### **フォーマッター設定**
```toml
# pyproject.toml
[tool.black]
line-length = 88
target-version = ['py310']
skip-string-normalization = false

[tool.isort]
profile = "black"
multi_line_output = 3
line_length = 88
known_first_party = ["tree_sitter_analyzer"]

[tool.ruff]
target-version = "py310"
line-length = 88
select = ["E", "F", "W", "C90", "I", "N", "UP", "YTT", "S", "BLE", "FBT", "B", "A", "COM", "C4", "DTZ", "T10", "EM", "EXE", "ISC", "ICN", "G", "INP", "PIE", "T20", "PYI", "PT", "Q", "RSE", "RET", "SLF", "SIM", "TID", "TCH", "ARG", "PTH", "ERA", "PD", "PGH", "PL", "TRY", "NPY", "RUF"]
```

#### **命名規則**
```python
# ✅ 推奨命名パターン
class LanguagePlugin:           # クラス: PascalCase
    def parse_elements(self):   # メソッド: snake_case
        pass

SUPPORTED_LANGUAGES = []       # 定数: UPPER_SNAKE_CASE
plugin_manager = None          # 変数: snake_case
_private_method = None         # プライベート: _prefix

# ✅ 意味のある名前
def extract_method_signatures(code: str) -> List[MethodSignature]:
    """メソッドシグネチャを抽出する"""
    pass

# ❌ 避けるべき名前
def process(data):  # 曖昧
def func1():        # 意味不明
def temp():         # 一時的すぎる
```

#### **型アノテーション**
```python
# ✅ 必須: すべての公開関数に型アノテーション
from typing import List, Dict, Optional, Union, Protocol

def analyze_file(
    file_path: str,
    language: Optional[str] = None,
    options: Dict[str, Any] = None
) -> AnalysisResult:
    """ファイルを解析する
    
    Args:
        file_path: 解析対象ファイルのパス
        language: 言語指定（自動検出の場合はNone）
        options: 解析オプション
        
    Returns:
        解析結果
        
    Raises:
        FileNotFoundError: ファイルが見つからない場合
        UnsupportedLanguageError: サポートされていない言語の場合
    """
    pass

# ✅ Protocol を使用したインターフェース定義
class FormatterProtocol(Protocol):
    def format(self, elements: List[Element]) -> str: ...
```

### 2.2 エラーハンドリング

#### **カスタム例外の使用**
```python
# ✅ 明確な例外階層
class TreeSitterAnalyzerError(Exception):
    """ベース例外クラス"""
    pass

class UnsupportedLanguageError(TreeSitterAnalyzerError):
    """サポートされていない言語エラー"""
    def __init__(self, language: str, supported: List[str]):
        self.language = language
        self.supported = supported
        super().__init__(
            f"言語 '{language}' はサポートされていません。"
            f"サポート言語: {', '.join(supported)}"
        )

class ParseError(TreeSitterAnalyzerError):
    """パースエラー"""
    def __init__(self, file_path: str, line: int, message: str):
        self.file_path = file_path
        self.line = line
        super().__init__(f"{file_path}:{line} - {message}")
```

#### **エラーハンドリングパターン**
```python
# ✅ 段階的フォールバック
def detect_language(file_path: str) -> str:
    try:
        # 1. 拡張子による検出
        return detect_by_extension(file_path)
    except UnsupportedLanguageError:
        try:
            # 2. ファイル内容による検出
            return detect_by_content(file_path)
        except UnsupportedLanguageError:
            # 3. デフォルト言語
            logger.warning(f"言語を検出できませんでした: {file_path}")
            return "text"

# ✅ コンテキストマネージャーの活用
@contextmanager
def performance_monitor(operation_name: str):
    start_time = time.time()
    try:
        yield
    finally:
        duration = time.time() - start_time
        logger.info(f"{operation_name} 完了: {duration:.2f}秒")
```

### 2.3 ログ出力

#### **ログレベルの使い分け**
```python
import logging

logger = logging.getLogger(__name__)

# ✅ 適切なログレベル
def analyze_file(file_path: str) -> AnalysisResult:
    logger.debug(f"ファイル解析開始: {file_path}")  # デバッグ情報
    
    try:
        language = detect_language(file_path)
        logger.info(f"言語検出: {language}")  # 重要な情報
        
        result = parse_file(file_path, language)
        logger.info(f"解析完了: {len(result.elements)}個の要素")
        
        return result
        
    except Exception as e:
        logger.error(f"解析エラー: {file_path} - {e}")  # エラー
        raise
```

---

## 3. 🏗️ 設計パターン

### 3.1 プラグインパターン

#### **プラグインベースクラス**
```python
# ✅ 統一されたプラグインインターフェース
class LanguagePlugin(ABC):
    """言語プラグインのベースクラス"""
    
    @abstractmethod
    def get_language_name(self) -> str:
        """言語名を返す"""
        pass
    
    @abstractmethod
    def get_supported_extensions(self) -> List[str]:
        """サポートする拡張子のリストを返す"""
        pass
    
    @abstractmethod
    def parse_elements(self, code: str, file_path: str) -> List[Element]:
        """コードを解析して要素のリストを返す"""
        pass
    
    @abstractmethod
    def get_queries(self) -> Dict[str, str]:
        """Tree-sitterクエリの辞書を返す"""
        pass
    
    def get_formatter(self) -> Optional[FormatterProtocol]:
        """専用フォーマッターを返す（オプション）"""
        return None
    
    def validate_code(self, code: str) -> bool:
        """コードの妥当性を検証する（オプション）"""
        return True
```

#### **プラグイン実装例**
```python
# ✅ 新言語プラグインの実装
class RustPlugin(LanguagePlugin):
    def get_language_name(self) -> str:
        return "rust"
    
    def get_supported_extensions(self) -> List[str]:
        return [".rs"]
    
    def parse_elements(self, code: str, file_path: str) -> List[Element]:
        # Tree-sitterパーサーを使用
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
                (function_item
                    name: (identifier) @function.name
                ) @function.definition
            """,
            "structs": """
                (struct_item
                    name: (type_identifier) @struct.name
                ) @struct.definition
            """
        }
```

### 3.2 ファクトリーパターン

#### **フォーマッターファクトリー**
```python
# ✅ ファクトリーパターンによる柔軟な生成
class FormatterFactory:
    _formatters: Dict[str, Type[BaseFormatter]] = {}
    
    @classmethod
    def register(cls, language: str, formatter_class: Type[BaseFormatter]):
        """フォーマッターを登録"""
        cls._formatters[language] = formatter_class
    
    @classmethod
    def create(cls, language: str, format_type: str = "full") -> BaseFormatter:
        """フォーマッターを生成"""
        if language not in cls._formatters:
            return DefaultFormatter(format_type)
        
        formatter_class = cls._formatters[language]
        return formatter_class(format_type)

# 使用例
@FormatterFactory.register("rust")
class RustFormatter(BaseFormatter):
    def format_function(self, element: Element) -> str:
        # Rust固有のフォーマット
        pass
```

### 3.3 ストラテジーパターン

#### **出力戦略の切り替え**
```python
# ✅ 出力形式の戦略パターン
class OutputStrategy(ABC):
    @abstractmethod
    def format(self, data: AnalysisResult) -> str:
        pass

class TableOutputStrategy(OutputStrategy):
    def format(self, data: AnalysisResult) -> str:
        # テーブル形式の出力
        pass

class JSONOutputStrategy(OutputStrategy):
    def format(self, data: AnalysisResult) -> str:
        return json.dumps(data.to_dict(), ensure_ascii=False, indent=2)

class CSVOutputStrategy(OutputStrategy):
    def format(self, data: AnalysisResult) -> str:
        # CSV形式の出力
        pass

# 使用例
class OutputManager:
    def __init__(self, strategy: OutputStrategy):
        self._strategy = strategy
    
    def output(self, data: AnalysisResult) -> str:
        return self._strategy.format(data)
```

---

## 4. 🔌 プラグイン開発ルール

### 4.1 新言語プラグイン追加手順

#### **Step 1: プラグインクラス作成**
```python
# tree_sitter_analyzer/languages/new_language_plugin.py
from tree_sitter_analyzer.plugins.base import LanguagePlugin
from tree_sitter_analyzer.models import Element

class NewLanguagePlugin(LanguagePlugin):
    def __init__(self):
        super().__init__()
        self._language = self._load_language()
    
    def _load_language(self):
        """Tree-sitter言語パーサーをロード"""
        try:
            import tree_sitter_new_language as ts_lang
            return ts_lang.language()
        except ImportError:
            raise ImportError(
                "tree-sitter-new-language パッケージが必要です。"
                "pip install tree-sitter-new-language"
            )
```

#### **Step 2: クエリ定義**
```python
# tree_sitter_analyzer/queries/new_language.py
QUERIES = {
    "functions": """
        (function_declaration
            name: (identifier) @function.name
            parameters: (parameter_list) @function.parameters
        ) @function.definition
    """,
    
    "classes": """
        (class_declaration
            name: (identifier) @class.name
            body: (class_body) @class.body
        ) @class.definition
    """,
    
    "variables": """
        (variable_declaration
            declarator: (variable_declarator
                name: (identifier) @variable.name
            )
        ) @variable.definition
    """
}
```

#### **Step 3: フォーマッター作成**
```python
# tree_sitter_analyzer/formatters/new_language_formatter.py
from tree_sitter_analyzer.formatters.base_formatter import BaseFormatter

class NewLanguageFormatter(BaseFormatter):
    def format_function(self, element: Element) -> str:
        """関数要素のフォーマット"""
        signature = self._build_function_signature(element)
        return f"📋 {signature}"
    
    def format_class(self, element: Element) -> str:
        """クラス要素のフォーマット"""
        return f"🏗️ class {element.name}"
```

#### **Step 4: テスト作成**
```python
# tests/test_new_language_plugin.py
import pytest
from tree_sitter_analyzer.languages.new_language_plugin import NewLanguagePlugin

class TestNewLanguagePlugin:
    @pytest.fixture
    def plugin(self):
        return NewLanguagePlugin()
    
    def test_supported_extensions(self, plugin):
        extensions = plugin.get_supported_extensions()
        assert ".newlang" in extensions
    
    def test_parse_function(self, plugin):
        code = """
        function hello(name) {
            return "Hello, " + name;
        }
        """
        elements = plugin.parse_elements(code, "test.newlang")
        functions = [e for e in elements if e.element_type == "function"]
        assert len(functions) == 1
        assert functions[0].name == "hello"
```

#### **Step 5: 統合とテスト**
```python
# tree_sitter_analyzer/plugins/__init__.py に追加
from .new_language_plugin import NewLanguagePlugin

# プラグインマネージャーに登録
AVAILABLE_PLUGINS = {
    # ... 既存のプラグイン
    "new_language": NewLanguagePlugin,
}
```

### 4.2 プラグイン品質基準

#### **必須要件**
- [ ] `LanguagePlugin` インターフェースの完全実装
- [ ] 包括的なテストカバレッジ（90%以上）
- [ ] 型アノテーションの完備
- [ ] エラーハンドリングの実装
- [ ] ドキュメント文字列の記述

#### **推奨要件**
- [ ] 専用フォーマッターの提供
- [ ] パフォーマンステストの実装
- [ ] 大規模ファイルでの動作確認
- [ ] エッジケースのテスト

---

## 5. 🧪 テスト実装ルール

### 5.1 テスト構造

#### **テストファイル命名規則**
```
tests/
├── test_[module_name].py              # 単体テスト
├── test_[module_name]_integration.py  # 統合テスト
├── test_[module_name]_performance.py  # パフォーマンステスト
└── test_languages/
    └── test_[language]_plugin_comprehensive.py
```

#### **テストクラス構造**
```python
# ✅ 推奨テスト構造
class TestLanguagePlugin:
    """言語プラグインのテストクラス"""
    
    @pytest.fixture
    def plugin(self):
        """プラグインインスタンスを提供"""
        return LanguagePlugin()
    
    @pytest.fixture
    def sample_code(self):
        """テスト用サンプルコード"""
        return """
        function example() {
            return "test";
        }
        """
    
    class TestBasicFunctionality:
        """基本機能のテスト"""
        
        def test_supported_extensions(self, plugin):
            """サポート拡張子のテスト"""
            pass
        
        def test_language_name(self, plugin):
            """言語名のテスト"""
            pass
    
    class TestParsing:
        """パース機能のテスト"""
        
        def test_parse_functions(self, plugin, sample_code):
            """関数パースのテスト"""
            pass
        
        def test_parse_classes(self, plugin):
            """クラスパースのテスト"""
            pass
    
    class TestEdgeCases:
        """エッジケースのテスト"""
        
        def test_empty_file(self, plugin):
            """空ファイルのテスト"""
            pass
        
        def test_malformed_code(self, plugin):
            """不正なコードのテスト"""
            pass
```

### 5.2 テストデータ管理

#### **スナップショットテスト**
```python
# ✅ スナップショットテストの活用
def test_java_analysis_snapshot(snapshot):
    """Java解析結果のスナップショットテスト"""
    code = load_test_file("BigService.java")
    result = analyze_code(code, "java")
    
    # 結果をスナップショットと比較
    snapshot.assert_match(result.to_dict(), "java_analysis_result.json")

# テストデータの配置
test_snapshots/
├── baselines/           # 期待される結果
│   ├── java/
│   ├── python/
│   └── javascript/
├── current/            # 現在の結果
└── config/
    └── test_cases.json # テストケース設定
```

#### **パラメータ化テスト**
```python
# ✅ 複数言語での同一テスト
@pytest.mark.parametrize("language,extension,sample_code", [
    ("java", ".java", "public class Test {}"),
    ("python", ".py", "class Test: pass"),
    ("javascript", ".js", "class Test {}"),
])
def test_class_detection(language, extension, sample_code):
    """クラス検出の言語横断テスト"""
    plugin = get_plugin(language)
    elements = plugin.parse_elements(sample_code, f"test{extension}")
    classes = [e for e in elements if e.element_type == "class"]
    assert len(classes) == 1
    assert classes[0].name == "Test"
```

### 5.3 パフォーマンステスト

#### **大規模ファイルテスト**
```python
# ✅ パフォーマンス要件の検証
@pytest.mark.performance
def test_large_file_performance():
    """大規模ファイルの処理性能テスト"""
    # 10,000行のJavaファイルを生成
    large_code = generate_large_java_file(lines=10000)
    
    start_time = time.time()
    result = analyze_code(large_code, "java")
    duration = time.time() - start_time
    
    # 性能要件: 10,000行を30秒以内で処理
    assert duration < 30.0
    assert len(result.elements) > 0

@pytest.mark.memory
def test_memory_usage():
    """メモリ使用量テスト"""
    import psutil
    import os
    
    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss
    
    # 大量のファイルを処理
    for i in range(100):
        code = f"class Test{i}: pass"
        analyze_code(code, "python")
    
    final_memory = process.memory_info().rss
    memory_increase = final_memory - initial_memory
    
    # メモリ増加量が100MB以下であることを確認
    assert memory_increase < 100 * 1024 * 1024
```

---

## 6. 📊 パフォーマンス最適化

### 6.1 メモリ最適化

#### **ジェネレーターの活用**
```python
# ✅ メモリ効率的な実装
def parse_large_file(file_path: str) -> Iterator[Element]:
    """大規模ファイルを段階的に解析"""
    with open(file_path, 'r', encoding='utf-8') as f:
        for chunk in read_in_chunks(f, chunk_size=1024*1024):  # 1MBずつ
            elements = parse_chunk(chunk)
            yield from elements

def read_in_chunks(file_obj, chunk_size: int):
    """ファイルをチャンクごとに読み取り"""
    while True:
        chunk = file_obj.read(chunk_size)
        if not chunk:
            break
        yield chunk
```

#### **キャッシュ戦略**
```python
# ✅ 効率的なキャッシュ実装
from functools import lru_cache
from typing import Dict, Any

class AnalysisCache:
    def __init__(self, max_size: int = 1000):
        self._cache: Dict[str, Any] = {}
        self._max_size = max_size
        self._access_order = []
    
    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            # LRU更新
            self._access_order.remove(key)
            self._access_order.append(key)
            return self._cache[key]
        return None
    
    def put(self, key: str, value: Any) -> None:
        if len(self._cache) >= self._max_size:
            # 最も古いエントリを削除
            oldest_key = self._access_order.pop(0)
            del self._cache[oldest_key]
        
        self._cache[key] = value
        self._access_order.append(key)

# ファイルハッシュベースのキャッシュ
@lru_cache(maxsize=128)
def get_file_hash(file_path: str) -> str:
    """ファイルのハッシュ値を計算（キャッシュ付き）"""
    import hashlib
    with open(file_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()
```

### 6.2 並列処理

#### **マルチプロセッシング**
```python
# ✅ CPU集約的タスクの並列化
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count

def analyze_multiple_files(file_paths: List[str]) -> List[AnalysisResult]:
    """複数ファイルの並列解析"""
    max_workers = min(cpu_count(), len(file_paths))
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # タスクを投入
        future_to_path = {
            executor.submit(analyze_file, path): path 
            for path in file_paths
        }
        
        results = []
        for future in as_completed(future_to_path):
            path = future_to_path[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.error(f"ファイル解析エラー {path}: {e}")
        
        return results
```

#### **非同期I/O**
```python
# ✅ I/O集約的タスクの非同期化
import asyncio
import aiofiles

async def read_file_async(file_path: str) -> str:
    """非同期ファイル読み取り"""
    async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
        return await f.read()

async def analyze_files_async(file_paths: List[str]) -> List[AnalysisResult]:
    """複数ファイルの非同期解析"""
    tasks = [analyze_file_async(path) for path in file_paths]
    return await asyncio.gather(*tasks)

async def analyze_file_async(file_path: str) -> AnalysisResult:
    """単一ファイルの非同期解析"""
    content = await read_file_async(file_path)
    # CPU集約的な処理は別スレッドで実行
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, analyze_code, content)
```

---

## 7. 🔒 セキュリティガイドライン

### 7.1 入力検証

#### **パス検証**
```python
# ✅ 安全なパス処理
import os
from pathlib import Path

def validate_file_path(file_path: str, allowed_dirs: List[str]) -> str:
    """ファイルパスの安全性を検証"""
    # パスの正規化
    normalized_path = os.path.normpath(os.path.abspath(file_path))
    
    # ディレクトリトラバーサル攻撃の防止
    if ".." in normalized_path:
        raise SecurityError("ディレクトリトラバーサルは許可されていません")
    
    # 許可されたディレクトリ内かチェック
    path_obj = Path(normalized_path)
    for allowed_dir in allowed_dirs:
        if path_obj.is_relative_to(Path(allowed_dir)):
            return normalized_path
    
    raise SecurityError(f"許可されていないディレクトリです: {file_path}")

# 使用例
def analyze_file_safely(file_path: str) -> AnalysisResult:
    allowed_dirs = ["/home/user/projects", "/tmp/analysis"]
    safe_path = validate_file_path(file_path, allowed_dirs)
    return analyze_file(safe_path)
```

#### **正規表現検証**
```python
# ✅ 安全な正規表現処理
import re
from typing import Pattern

class RegexValidator:
    # 危険なパターンのブラックリスト
    DANGEROUS_PATTERNS = [
        r'\(\?\#',      # コメント構文
        r'\(\