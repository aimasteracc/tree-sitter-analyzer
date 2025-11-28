# 新言語サポート追加チェックリスト

## 📋 概要

新しいプログラミング言語のサポートを追加する際に、設計漏れを防ぐための包括的なチェックリストです。

## ✅ 完全実装チェックリスト

### Phase 1: 基盤セットアップ

#### 1.1 依存関係
- [ ] `pyproject.toml` に `tree-sitter-{language}` パッケージを追加
  - `dependencies` セクション（必須の場合）
  - `[project.optional-dependencies]` セクション（オプションの場合）
  - `{language}` グループ
  - `all-languages` グループ
- [ ] `uv lock` で依存関係を確認
- [ ] `uv add tree-sitter-{language}` でインストール確認

#### 1.2 言語ローダー設定
- [ ] `tree_sitter_analyzer/language_loader.py` の `LANGUAGE_MODULES` に追加
  ```python
  "{language}": "tree_sitter_{language}",
  ```
- [ ] エイリアス対応（例: C#の場合）
  ```python
  "csharp": "tree_sitter_c_sharp",
  "cs": "tree_sitter_c_sharp",  # Alias
  ```

#### 1.3 言語検出
- [ ] `tree_sitter_analyzer/language_detector.py` に拡張子マッピングを追加
  - `EXTENSION_TO_LANGUAGE` 辞書
  - `EXTENSION_CONFIDENCE` 辞書
- [ ] エイリアス対応（例: `.cs` → `csharp`）

### Phase 2: コアプラグイン実装

#### 2.1 プラグインファイル作成
- [ ] `tree_sitter_analyzer/languages/{language}_plugin.py` を作成
- [ ] `{Language}Plugin` クラス実装
  - [ ] `__init__()`: 初期化
  - [ ] `get_language_name()`: 言語名を返す
  - [ ] `get_file_extensions()`: 拡張子リストを返す
  - [ ] `create_extractor()`: Extractorインスタンスを返す
  - [ ] `get_tree_sitter_language()`: tree-sitter言語オブジェクトを返す
  - [ ] `analyze_file()`: ファイル解析メソッド

#### 2.2 Element Extractor実装
- [ ] `{Language}ElementExtractor` クラス実装
  - [ ] `__init__()`: キャッシュ初期化
  - [ ] `_reset_caches()`: キャッシュリセット
  - [ ] `_get_node_text_optimized()`: ノードテキスト抽出
  - [ ] `extract_classes()`: クラス抽出
  - [ ] `extract_functions()`: 関数/メソッド抽出
  - [ ] `extract_variables()`: 変数/フィールド抽出
  - [ ] `extract_imports()`: インポート抽出
  - [ ] `_traverse_iterative()`: 反復的なAST走査

#### 2.3 言語固有の抽出メソッド
- [ ] クラス型抽出（class, interface, etc.）
- [ ] メソッド型抽出（method, constructor, property, etc.）
- [ ] 修飾子抽出（public, private, static, etc.）
- [ ] 可視性判定
- [ ] 複雑度計算
- [ ] アノテーション/属性抽出

#### 2.4 エントリーポイント登録
- [ ] `pyproject.toml` の `[project.entry-points."tree_sitter_analyzer.plugins"]` に追加
  ```toml
  {language} = "tree_sitter_analyzer.languages.{language}_plugin:{Language}Plugin"
  ```

### Phase 3: クエリシステム実装

#### 3.1 クエリファイル作成
- [ ] `tree_sitter_analyzer/queries/{language}.py` を作成
- [ ] `{LANGUAGE}_QUERIES` 辞書を定義
  - [ ] 基本要素クエリ（class, method, function, etc.）
  - [ ] 修飾子クエリ（public, private, static, etc.）
  - [ ] 言語固有機能クエリ
  - [ ] 制御フロークエリ（if, for, while, etc.）
  - [ ] コメントクエリ

#### 3.2 プラグインにクエリメソッド追加
- [ ] `get_queries()`: クエリ辞書を返す
  ```python
  def get_queries(self) -> dict[str, str]:
      from ..queries.{language} import {LANGUAGE}_QUERIES
      return {LANGUAGE}_QUERIES
  ```
- [ ] `execute_query_strategy()`: クエリ実行戦略
  ```python
  def execute_query_strategy(self, query_key: str | None, language: str) -> str | None:
      if language != "{language}":
          return None
      queries = self.get_queries()
      return queries.get(query_key) if query_key else None
  ```
- [ ] `get_element_categories()`: 要素カテゴリ定義
  ```python
  def get_element_categories(self) -> dict[str, list[str]]:
      return {
          "classes": [...],
          "methods": [...],
          "fields": [...],
          ...
      }
  ```

### Phase 4: フォーマッター実装

#### 4.1 フォーマッターファイル作成
- [ ] `tree_sitter_analyzer/formatters/{language}_formatter.py` を作成
- [ ] `{Language}TableFormatter` クラス実装（`BaseTableFormatter` を継承）
  - [ ] `_format_full_table()`: 完全フォーマット
  - [ ] `_format_compact_table()`: コンパクトフォーマット
  - [ ] `_format_csv()`: CSVフォーマット
  - [ ] ヘルパーメソッド（`_add_methods_table()`, `_add_fields_table()`, etc.）

#### 4.2 フォーマッター設定
- [ ] `tree_sitter_analyzer/formatters/formatter_config.py` に追加
  ```python
  "{language}": {
      "table": "legacy",  # or "new"
      "compact": "legacy",
      "full": "legacy",
      "csv": "legacy",
      "json": "legacy",
  },
  ```
- [ ] エイリアス対応（例: `"cs"` for C#）

#### 4.3 フォーマッターファクトリー登録
- [ ] `tree_sitter_analyzer/formatters/language_formatter_factory.py` にインポート追加
  ```python
  from .{language}_formatter import {Language}TableFormatter
  ```
- [ ] `_formatters` 辞書に登録
  ```python
  "{language}": {Language}TableFormatter,
  ```

### Phase 5: サンプルとテスト

#### 5.1 サンプルファイル作成
- [ ] `examples/Sample.{ext}`: 基本機能デモ
- [ ] `examples/SampleAdvanced.{ext}`: 高度な機能デモ
- [ ] `examples/Sample{Framework}.{ext}`: フレームワーク固有機能（オプション）

#### 5.2 単体テスト作成
- [ ] `tests/test_languages/test_{language}_plugin.py` を作成
  - [ ] プラグインインスタンス化テスト
  - [ ] `get_language_name()` テスト
  - [ ] `get_file_extensions()` テスト
  - [ ] `get_tree_sitter_language()` テスト
  - [ ] クラス抽出テスト
  - [ ] メソッド抽出テスト
  - [ ] フィールド抽出テスト
  - [ ] インポート抽出テスト
  - [ ] エッジケーステスト

#### 5.3 統合テスト
- [ ] CLI分析テスト
- [ ] フォーマット出力テスト（Full, Compact, CSV）
- [ ] MCP統合テスト
- [ ] パフォーマンステスト

#### 5.4 Golden Masterテスト
- [ ] ゴールデンマスターファイル生成
  ```bash
  # Full形式
  uv run tree-sitter-analyzer examples/Sample.{ext} --table full > tests/golden_masters/full/{language}_sample_full.md
  
  # Compact形式
  uv run tree-sitter-analyzer examples/Sample.{ext} --table compact > tests/golden_masters/compact/{language}_sample_compact.md
  
  # CSV形式
  uv run tree-sitter-analyzer examples/Sample.{ext} --table csv > tests/golden_masters/csv/{language}_sample_csv.csv
  ```
- [ ] `tests/test_golden_master_regression.py` にテストケース追加
  ```python
  # {Language} tests
  ("examples/Sample.{ext}", "{language}_sample", "full"),
  ("examples/Sample.{ext}", "{language}_sample", "compact"),
  ("examples/Sample.{ext}", "{language}_sample", "csv"),
  ```
- [ ] ゴールデンマスターテスト実行
  ```bash
  uv run pytest tests/test_golden_master_regression.py -k "{language}" -v
  ```
- [ ] 出力の決定性確認（複数回実行して同じ結果になることを確認）
  ```bash
  # 5回実行して差分がないことを確認
  for i in {1..5}; do uv run tree-sitter-analyzer examples/Sample.{ext} --table full > /tmp/test_$i.txt; done
  diff /tmp/test_1.txt /tmp/test_2.txt
  ```

### Phase 6: ドキュメント更新

#### 6.1 README更新
- [ ] `README.md` の言語サポート表に追加
- [ ] 言語カウント更新（例: 8 → 9言語）
- [ ] 言語固有の機能説明追加
- [ ] サンプルコード追加（オプション）

#### 6.2 多言語README更新
- [ ] `README_ja.md` 更新
- [ ] `README_zh.md` 更新

#### 6.3 CHANGELOG更新
- [ ] `CHANGELOG.md` の `[Unreleased]` セクションに追加
  - 言語サポート追加
  - 主要機能リスト
  - クエリサポート
  - フォーマッターサポート

#### 6.4 ユーザーガイド更新
- [ ] `docs/ja/user-guides/00_クイックスタートガイド.md` 更新
- [ ] 言語固有のガイド作成（オプション）

### Phase 7: 品質保証

#### 7.1 コード品質チェック
- [ ] `uv run mypy tree_sitter_analyzer/languages/{language}_plugin.py`
- [ ] `uv run ruff check tree_sitter_analyzer/languages/{language}_plugin.py`
- [ ] `uv run ruff check tree_sitter_analyzer/queries/{language}.py`
- [ ] `uv run ruff check tree_sitter_analyzer/formatters/{language}_formatter.py`
- [ ] `uv run black tree_sitter_analyzer/languages/{language}_plugin.py`
- [ ] `uv run isort tree_sitter_analyzer/languages/{language}_plugin.py`

#### 7.2 テスト実行
- [ ] `uv run pytest tests/test_languages/test_{language}_plugin.py`
- [ ] `uv run pytest --cov` でカバレッジ確認（>80%）
- [ ] 既存テストのリグレッション確認

#### 7.3 手動テスト
- [ ] CLI: `uv run tree-sitter-analyzer examples/Sample.{ext} --table full`
- [ ] CLI: `uv run tree-sitter-analyzer examples/Sample.{ext} --table compact`
- [ ] CLI: `uv run tree-sitter-analyzer examples/Sample.{ext} --table csv`
- [ ] MCP: `mcp analyze_code_structure examples/Sample.{ext}`

### Phase 8: OpenSpec（オプション）

#### 8.1 OpenSpec提案作成
- [ ] `openspec/changes/add-{language}-language-support/proposal.md`
- [ ] `openspec/changes/add-{language}-language-support/design.md`
- [ ] `openspec/changes/add-{language}-language-support/tasks.md`
- [ ] `openspec/changes/add-{language}-language-support/specs/{language}-language-support/spec.md`

#### 8.2 タスク管理
- [ ] すべてのタスクチェックボックスを `[x]` に更新
- [ ] 成功基準の確認

## 🎯 3つの主要コンポーネント

新言語サポートは、以下の3つのコンポーネントすべてを実装する必要があります：

### 1. Language Plugin（必須）
```
tree_sitter_analyzer/languages/{language}_plugin.py
├── {Language}Plugin
│   ├── get_language_name()
│   ├── get_file_extensions()
│   ├── create_extractor()
│   ├── get_tree_sitter_language()
│   └── analyze_file()
└── {Language}ElementExtractor
    ├── extract_classes()
    ├── extract_functions()
    ├── extract_variables()
    └── extract_imports()
```

### 2. Query System（必須）
```
tree_sitter_analyzer/queries/{language}.py
├── {LANGUAGE}_QUERIES dictionary
└── Plugin methods:
    ├── get_queries()
    ├── execute_query_strategy()
    └── get_element_categories()
```

### 3. Table Formatter（必須）
```
tree_sitter_analyzer/formatters/{language}_formatter.py
├── {Language}TableFormatter
│   ├── _format_full_table()
│   ├── _format_compact_table()
│   └── _format_csv()
└── Configuration:
    ├── formatter_config.py
    └── language_formatter_factory.py
```

## 🔍 設計漏れ検出方法

### 自動チェック
```bash
# 1. プラグインが登録されているか
grep -r "class.*Plugin" tree_sitter_analyzer/languages/{language}_plugin.py

# 2. クエリファイルが存在するか
test -f tree_sitter_analyzer/queries/{language}.py && echo "✓ Query file exists"

# 3. フォーマッターが存在するか
test -f tree_sitter_analyzer/formatters/{language}_formatter.py && echo "✓ Formatter exists"

# 4. 設定ファイルに登録されているか
grep "{language}" tree_sitter_analyzer/formatters/formatter_config.py

# 5. ファクトリーに登録されているか
grep "{language}" tree_sitter_analyzer/formatters/language_formatter_factory.py
```

### 手動チェック
```bash
# 既存言語と比較
ls tree_sitter_analyzer/languages/*_plugin.py
ls tree_sitter_analyzer/queries/*.py
ls tree_sitter_analyzer/formatters/*_formatter.py

# 新言語が同じ構造を持っているか確認
```

## 📝 実装テンプレート

### Plugin Template
```python
#!/usr/bin/env python3
"""
{Language} Language Plugin

Provides {Language}-specific parsing and element extraction functionality.
"""

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter
    from ..core.analysis_engine import AnalysisRequest
    from ..models import AnalysisResult

try:
    import tree_sitter
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from ..models import Class, Function, Import, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error


class {Language}ElementExtractor(ElementExtractor):
    """
    {Language}-specific element extractor.
    """

    def __init__(self) -> None:
        super().__init__()
        self.source_code: str = ""
        self.content_lines: list[str] = []
        
        # Performance optimization caches
        self._node_text_cache: dict[int, str] = {}
        self._processed_nodes: set[int] = set()

    def extract_classes(self, tree: "tree_sitter.Tree", source_code: str) -> list[Class]:
        # Implementation
        pass

    def extract_functions(self, tree: "tree_sitter.Tree", source_code: str) -> list[Function]:
        # Implementation
        pass

    def extract_variables(self, tree: "tree_sitter.Tree", source_code: str) -> list[Variable]:
        # Implementation
        pass

    def extract_imports(self, tree: "tree_sitter.Tree", source_code: str) -> list[Import]:
        # Implementation
        pass


class {Language}Plugin(LanguagePlugin):
    """
    {Language} language plugin implementation.
    """

    def __init__(self) -> None:
        super().__init__()
        self.extractor = {Language}ElementExtractor()
        self.language = "{language}"
        self.supported_extensions = [".{ext}"]
        self._cached_language: Any | None = None

    def get_language_name(self) -> str:
        return "{language}"

    def get_file_extensions(self) -> list[str]:
        return [".{ext}"]

    def create_extractor(self) -> ElementExtractor:
        return {Language}ElementExtractor()

    def get_queries(self) -> dict[str, str]:
        from ..queries.{language} import {LANGUAGE}_QUERIES
        return {LANGUAGE}_QUERIES

    def execute_query_strategy(self, query_key: str | None, language: str) -> str | None:
        if language != "{language}":
            return None
        queries = self.get_queries()
        return queries.get(query_key) if query_key else None

    def get_element_categories(self) -> dict[str, list[str]]:
        return {
            "classes": ["class"],
            "methods": ["method"],
            "fields": ["field"],
        }

    def get_tree_sitter_language(self) -> Any | None:
        if self._cached_language is not None:
            return self._cached_language

        try:
            import tree_sitter_{language}
            lang = tree_sitter_{language}.language()
            
            if hasattr(lang, "__class__") and "Language" in str(type(lang)):
                self._cached_language = lang
            else:
                self._cached_language = tree_sitter.Language(lang)

            return self._cached_language
        except ImportError as e:
            log_error(f"tree-sitter-{language} not available: {e}")
            return None
        except Exception as e:
            log_error(f"Failed to load tree-sitter language for {Language}: {e}")
            return None

    async def analyze_file(self, file_path: str, request: "AnalysisRequest") -> "AnalysisResult":
        # Implementation
        pass
```

## 🚨 よくある設計漏れ

1. ❌ **クエリシステムの実装忘れ**
   - `get_queries()` メソッドがない
   - `queries/{language}.py` ファイルがない

2. ❌ **フォーマッターの実装忘れ**
   - `formatters/{language}_formatter.py` ファイルがない
   - `formatter_config.py` に登録していない
   - `language_formatter_factory.py` に登録していない

3. ❌ **エントリーポイント登録忘れ**
   - `pyproject.toml` の `[project.entry-points]` に登録していない

4. ❌ **言語検出設定忘れ**
   - `language_detector.py` に拡張子マッピングがない

5. ❌ **ドキュメント更新忘れ**
   - README の言語リストに追加していない
   - CHANGELOG に記載していない

6. ❌ **テスト作成忘れ**
   - 単体テストがない
   - 統合テストがない

## 📊 完成度チェックマトリクス

| コンポーネント | ファイル | 設定 | テスト | ドキュメント |
|---------------|---------|------|--------|-------------|
| Plugin | ✓ | ✓ | ✓ | ✓ |
| Query | ✓ | - | ✓ | ✓ |
| Formatter | ✓ | ✓ | ✓ | ✓ |
| Samples | ✓ | - | - | ✓ |

すべて ✓ になって初めて完成です。

## 🎓 学んだ教訓（C#実装から）

1. **3つのコンポーネントは必須**: Plugin, Query, Formatter
2. **既存言語を参照**: 同じOOP言語（Java）や最新言語（SQL）を参考にする
3. **段階的実装**: Plugin → Query → Formatter の順で実装
4. **早期テスト**: 各段階で動作確認
5. **設定ファイルの重要性**: 登録忘れが最も多い設計漏れ

## 🔄 実装順序推奨

1. **Phase 1-2**: Plugin実装（コア機能）
2. **Phase 3**: Query実装（検索機能）
3. **Phase 4**: Formatter実装（出力機能）
4. **Phase 5**: サンプルとテスト
5. **Phase 6-7**: ドキュメントと品質保証

各フェーズ完了後に動作確認を行うことで、早期に問題を発見できます。

## 📚 参考実装

- **OOP言語**: Java, C#, TypeScript
- **スクリプト言語**: Python, JavaScript
- **マークアップ言語**: HTML, Markdown
- **データ言語**: SQL, CSS

新言語を追加する際は、最も類似した既存言語の実装を参考にしてください。

