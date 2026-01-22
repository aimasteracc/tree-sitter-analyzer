# リファクタリングガイド: コード品質改善

## 概要

このドキュメントは、tree-sitter-analyzerプロジェクトで実施したコード品質改善のためのリファクタリング作業について説明します。リファクタリングは、SOLID原則とデザインパターンの適用に焦点を当て、複雑性を削減し、保守性を向上させることを目的としています。

## 目次

1. [リファクタリング概要](#リファクタリング概要)
2. [適用したデザインパターン](#適用したデザインパターン)
3. [Before/After比較](#beforeafter比較)
4. [ベストプラクティス](#ベストプラクティス)
5. [テスト戦略](#テスト戦略)

---

## リファクタリング概要

### リファクタリング対象モジュール

| モジュール | Before | After | 改善 |
|--------|--------|-------|-------------|
| SearchContentTool | 947行、610行メソッド | 416行、30行メソッド | 56%削減、95%メソッド削減 |
| fd_rg_utils | 825行、God module | モジュール構造（6ファイル） | 関心の分離 |
| UnifiedAnalysisEngine | Singletonのみ | Singleton + DI対応 | テスト容易性向上 |

### 主要メトリクス

| メトリクス | Before | After | 目標 | ステータス |
|--------|--------|-------|--------|--------|
| 最大メソッドサイズ | 610行 | 30行 | ≤50行 | ✅ 達成 |
| 最大複雑度 | 176 | <10 | ≤15 | ✅ 達成 |
| テストカバレッジ | 不明 | 80%+ | >80% | ✅ 達成 |
| 統合テスト | 0 | 91 | >50 | ✅ 達成 |

---

## 適用したデザインパターン

### 1. Strategy Pattern (SearchContentTool)

**問題**: 610行のexecute()メソッドに責務が混在

**解決策**: 検索戦略を個別のクラスに抽出

**実装**:

```python
# Before
class SearchContentTool:
    async def execute(self, arguments: dict) -> dict | int:
        # 610行の混在したロジック
        if total_only:
            # total onlyロジック
        elif count_only_matches:
            # count onlyロジック
        elif summary_only:
            # summaryロジック
        # ... さらに600行
```

```python
# After
class SearchContentTool:
    def __init__(self, ...):
        self._validator = SearchArgumentValidator(...)
        self._strategy = ContentSearchStrategy(...)
        self._formatter = SearchResultFormatter()
    
    async def execute(self, arguments: dict) -> dict | int:
        # 引数を検証
        context = self._validator.validate(arguments)
        
        # 戦略を実行
        result = await self._strategy.execute(context)
        
        # 結果をフォーマット
        return self._formatter.format(result, ...)
```

**メリット**:
- ✅ 単一責任原則
- ✅ 開放閉鎖原則（新しい戦略を簡単に追加可能）
- ✅ テスト容易性（各戦略を独立してテスト）
- ✅ 可読性（30行 vs 610行）

### 2. Builder Pattern (fd_rgモジュール)

**問題**: 16-18個のパラメータを持つ関数、パラメータの爆発

**解決策**: 設定用dataclassとbuilderクラスを使用

**実装**:

```python
# Before
def build_fd_command(
    pattern=None,
    roots=None,
    extensions=None,
    types=None,
    depth=None,
    exclude=None,
    hidden=False,
    no_ignore=False,
    follow_symlinks=False,
    absolute=True,
    full_path_match=False,
    glob=False,
    sort=None,
    limit=None,
    # ... さらに4個のパラメータ
):
    # 68行のコマンド構築
```

```python
# After
@dataclass(frozen=True)
class FdCommandConfig:
    roots: list[str]
    pattern: str | None = None
    extensions: list[str] | None = None
    # ... その他のフィールドとデフォルト値

class FdCommandBuilder:
    def __init__(self, config: FdCommandConfig):
        self.config = config
    
    def build(self) -> list[str]:
        # クリーンなコマンド構築ロジック
```

**メリット**:
- ✅ 不変な設定（frozen dataclass）
- ✅ 明確なパラメータ名と型
- ✅ __post_init__でのバリデーション
- ✅ テストが容易

### 3. Dependency Injection (UnifiedAnalysisEngine)

**問題**: Singletonパターンがテストを困難にする

**解決策**: SingletonとDependency Injectionの両方をサポート

**実装**:

```python
# Before (Singletonのみ)
class UnifiedAnalysisEngine:
    _instances: dict[str, "UnifiedAnalysisEngine"] = {}
    
    def __new__(cls, project_root: str):
        if project_root not in cls._instances:
            instance = super().__new__(cls)
            cls._instances[project_root] = instance
        return cls._instances[project_root]
```

```python
# After (Singleton + DI)
class UnifiedAnalysisEngine:
    def __new__(cls, project_root: str, file_loader=None, ...):
        # 依存性が提供された場合、singletonをスキップ
        if file_loader is not None or ...:
            instance = super().__new__(cls)
            instance._skip_singleton = True
            return instance
        
        # それ以外はsingletonを使用
        if project_root not in cls._instances:
            instance = super().__new__(cls)
            cls._instances[project_root] = instance
        return cls._instances[project_root]

# DI用のファクトリ関数
def create_analysis_engine(project_root: str, file_loader=None, ...):
    return UnifiedAnalysisEngine(
        project_root=project_root,
        file_loader=file_loader,
        ...
    )
```

**メリット**:
- ✅ 後方互換性（singletonは引き続き動作）
- ✅ テスト可能（モックを注入可能）
- ✅ 柔軟性（独立したインスタンスを作成可能）

---

## Before/After比較

### SearchContentTool.execute()

#### Before (610行、複雑度176)

```python
async def execute(self, arguments: dict[str, Any]) -> dict[str, Any] | int:
    # 引数検証（50行）
    if "query" not in arguments:
        return {"error": "Missing query"}
    # ... さらに48行
    
    # キャッシュ処理（30行）
    cache_key = self._create_cache_key(...)
    if cache_key in self._cache:
        return self._cache[cache_key]
    # ... さらに28行
    
    # コマンド構築（80行）
    if total_only:
        # total onlyコマンドを構築
    elif count_only_matches:
        # count onlyコマンドを構築
    # ... さらに76行
    
    # 結果処理（200行）
    if total_only:
        # total onlyを処理
    elif count_only_matches:
        # count onlyを処理
    # ... さらに196行
    
    # フォーマット変換（100行）
    if output_format == "toon":
        # toonに変換
    # ... さらに98行
    
    # ファイル出力（50行）
    if output_file:
        # ファイルに保存
    # ... さらに48行
    
    # エラーハンドリング（100行）
    try:
        # ... 上記すべて
    except Exception as e:
        # エラーを処理
    # ... さらに98行
```

#### After (30行、複雑度<10)

```python
async def execute(self, arguments: dict[str, Any]) -> dict[str, Any] | int:
    # ripgrepの可用性をチェック
    if not fd_rg_utils.check_external_command("rg"):
        return {
            "error": "ripgrep (rg) command not found",
            "suggestion": "Please install ripgrep",
        }
    
    try:
        # 引数を検証してコンテキストを作成
        context = self._validator.validate(arguments)
        
        # キャッシュキーを作成
        context.cache_key = self._create_cache_key(context)
        
        # 戦略を実行
        result = await self._strategy.execute(context)
        
        # 結果をフォーマット
        return self._formatter.format(
            result,
            output_format=context.output_format,
            suppress_output=context.suppress_output,
        )
    
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}
```

**影響**:
- 95%の行数削減（610 → 30）
- 94%の複雑度削減（176 → <10）
- 理解と保守が容易
- 各コンポーネントを独立してテスト可能

### fd_rg_utils.py

#### Before (825行、God module)

```python
# グローバルな可変状態
_COMMAND_EXISTS_CACHE: dict[str, bool] = {}

# 責務が混在した25個の関数
def build_fd_command(16個のパラメータ): ...  # 68行
def build_rg_command(18個のパラメータ): ...  # 109行
def execute_fd_command(...): ...
def execute_rg_command(...): ...
def parse_fd_output(...): ...
def parse_rg_output(...): ...
def summarize_search_results(...): ...  # 94行
def optimize_paths(...): ...
def group_by_file(...): ...
# ... さらに16個の関数
```

#### After (モジュール構造)

```
tree_sitter_analyzer/mcp/tools/fd_rg/
├── __init__.py
├── config.py              # FdCommandConfig, RgCommandConfig
├── command_builder.py     # FdCommandBuilder, RgCommandBuilder
├── result_parser.py       # FdResultParser, RgResultParser
├── result_transformer.py  # ResultTransformer
└── utils.py               # ユーティリティ関数
```

**メリット**:
- 明確な関心の分離
- 各ファイル<300行
- グローバルな可変状態なし
- コードの検索と修正が容易

---

## ベストプラクティス

### 1. 単一責任原則 (SRP)

**ルール**: 各クラスは変更する理由を1つだけ持つべき

**例**:
```python
# ❌ 悪い例: 複数の責務
class SearchTool:
    def validate_arguments(self): ...
    def execute_search(self): ...
    def format_results(self): ...
    def save_to_file(self): ...

# ✅ 良い例: 単一の責務
class ArgumentValidator:
    def validate(self): ...

class SearchStrategy:
    def execute(self): ...

class ResultFormatter:
    def format(self): ...

class FileOutputManager:
    def save(self): ...
```

### 2. 開放閉鎖原則 (OCP)

**ルール**: 拡張に対して開いており、修正に対して閉じている

**例**:
```python
# ❌ 悪い例: 新しいモードを追加するにはexecute()を修正する必要がある
async def execute(self, arguments):
    if mode == "total_only":
        # ...
    elif mode == "count_only":
        # ...
    elif mode == "new_mode":  # ここを修正する必要がある
        # ...

# ✅ 良い例: execute()を修正せずに新しい戦略を追加
class NewModeStrategy(SearchStrategy):
    async def execute(self, context):
        # 新しいモードの実装

# execute()の修正は不要
```

### 3. 依存性注入

**ルール**: 依存性を注入し、作成しない

**例**:
```python
# ❌ 悪い例: ハードコードされた依存性
class SearchTool:
    def __init__(self):
        self.cache = LRUCache()  # ハードコード
        self.validator = ArgumentValidator()  # ハードコード

# ✅ 良い例: 注入された依存性
class SearchTool:
    def __init__(self, cache=None, validator=None):
        self.cache = cache or LRUCache()
        self.validator = validator or ArgumentValidator()
```

### 4. 不変な設定

**ルール**: 設定にはfrozen dataclassを使用

**例**:
```python
# ❌ 悪い例: 可変な設定
class Config:
    def __init__(self):
        self.roots = []
        self.pattern = None

config = Config()
config.roots.append(".")  # 修正可能

# ✅ 良い例: 不変な設定
@dataclass(frozen=True)
class Config:
    roots: list[str]
    pattern: str | None = None

config = Config(roots=["."])
# config.roots = ["/tmp"]  # エラー: frozen
```

### 5. 小さなメソッド

**ルール**: メソッドは50行未満、理想的には20行未満

**例**:
```python
# ❌ 悪い例: 610行のメソッド
async def execute(self, arguments):
    # 610行の混在したロジック

# ✅ 良い例: 小さく焦点を絞ったメソッド
async def execute(self, arguments):
    context = self._validate(arguments)
    result = await self._execute_strategy(context)
    return self._format_result(result)

def _validate(self, arguments):
    # 10行

async def _execute_strategy(self, context):
    # 15行

def _format_result(self, result):
    # 12行
```

---

## テスト戦略

### 1. 特性化テスト

**目的**: リファクタリング前に現在の動作をキャプチャ

**例**:
```python
def test_search_basic_functionality():
    """特性化テスト: 基本的な検索が動作すること"""
    tool = SearchContentTool(...)
    result = await tool.execute({"query": "def", "roots": ["."]})
    
    assert isinstance(result, dict)
    assert "matches" in result
    # 正確な動作をキャプチャ
```

### 2. ユニットテスト

**目的**: 個別のコンポーネントを独立してテスト

**例**:
```python
def test_argument_validator_validates_query():
    """ユニットテスト: Validatorはqueryパラメータをチェックすること"""
    validator = ArgumentValidator(...)
    
    with pytest.raises(ValueError, match="query"):
        validator.validate({})  # queryが欠落
```

### 3. 統合テスト

**目的**: コンポーネントが連携して動作することをテスト

**例**:
```python
async def test_search_tool_integration():
    """統合テスト: 完全な検索ワークフロー"""
    tool = SearchContentTool(...)
    result = await tool.execute({
        "query": "class",
        "roots": [str(test_project)],
        "total_only": True,
    })
    
    assert isinstance(result, int)
    assert result > 0
```

### 4. エンドツーエンドテスト

**目的**: 完全なユーザーワークフローをテスト

**例**:
```python
async def test_discover_and_analyze_workflow():
    """E2Eテスト: ファイルを発見して解析"""
    # ステップ1: ファイルを発見
    list_tool = ListFilesTool(...)
    files = await list_tool.execute({"roots": ["."], "extensions": ["py"]})
    
    # ステップ2: 各ファイルを解析
    engine = UnifiedAnalysisEngine(...)
    for file in files["files"]:
        result = await engine.analyze(file_path=file["path"], language="python")
        assert result is not None
```

---

## マイグレーションガイド

詳細な移行手順については、[`migration-guide.md`](migration-guide.md)を参照してください。

---

## パフォーマンスに関する考慮事項

### ベンチマーク

リファクタリングの前後でベンチマークを実行:

```bash
# SearchContentTool
python scripts/benchmark_search_content_tool.py

# fd_rgモジュール
python scripts/benchmark_fd_rg.py

# UnifiedAnalysisEngine
python scripts/benchmark_analysis_engine.py
```

### パフォーマンス目標

- パフォーマンス劣化は10%以内
- 理想的には、より良いキャッシングによりパフォーマンスが向上すべき

### 結果

| モジュール | Before | After | 変化 |
|--------|--------|-------|--------|
| SearchContentTool | TBD | TBD | TBD |
| fd_rg | TBD | TBD | TBD |
| UnifiedAnalysisEngine | TBD | TBD | TBD |

---

## 結論

リファクタリング作業により、コード品質が大幅に改善されました:

- ✅ 複雑度の削減（176 → <10）
- ✅ 保守性の向上（610行 → 30行）
- ✅ テスト容易性の向上（91個の統合テストを追加）
- ✅ SOLID原則の適用
- ✅ 適切なデザインパターンの使用
- ✅ 後方互換性の維持

コードベースは、理解、修正、拡張が容易になりました。
