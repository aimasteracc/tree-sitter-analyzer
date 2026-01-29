# マイグレーションガイド: V1からV2へ

## 概要

このガイドは、リファクタリング前のバージョン（V1）からリファクタリング後のバージョン（V2）へのtree-sitter-analyzerの移行を支援します。リファクタリングは100%の後方互換性を維持しているため、既存のコードは変更なしで引き続き動作します。

## 目次

1. [破壊的変更](#破壊的変更)
2. [非推奨機能](#非推奨機能)
3. [新機能](#新機能)
4. [移行手順](#移行手順)
5. [移行のテスト](#移行のテスト)

---

## 破壊的変更

### ✅ なし

**良いニュース**: 破壊的変更はありません。すべての既存コードは引き続き動作します。

リファクタリングは後方互換性を最優先に設計されました:
- すべてのパブリックAPIは変更なし
- すべての関数シグネチャは同一
- すべての戻り値の型は同じ
- すべての動作は保持

---

## 非推奨機能

### 現在なし

V2で非推奨となった機能はありません。ただし、一部の内部実装の詳細が変更されました:

### 内部変更（ユーザー向けではない）

1. **fd_rg_utils.py** → **fd_rgモジュール**
   - 旧: `from tree_sitter_analyzer.mcp.tools import fd_rg_utils`
   - 新: `from tree_sitter_analyzer.mcp.tools import fd_rg`
   - **ステータス**: 旧インポートは引き続き動作（後方互換）

2. **SearchContentTool内部構造**
   - 旧: 単一の610行execute()メソッド
   - 新: 複数のコンポーネントを持つStrategy pattern
   - **ステータス**: 外部APIは変更なし

3. **UnifiedAnalysisEngine**
   - 旧: Singletonのみ
   - 新: Singleton + Dependency Injectionサポート
   - **ステータス**: Singleton動作は変更なし

---

## 新機能

### 1. Dependency Injectionサポート (UnifiedAnalysisEngine)

**新機能**: テスト用に依存性を注入できるようになりました

**Before (V1)**:
```python
# Singletonのみ利用可能
engine = UnifiedAnalysisEngine(project_root="/path/to/project")
# テスト用のモックを注入できない
```

**After (V2)**:
```python
# オプション1: Singleton（V1と同じ）
engine = UnifiedAnalysisEngine(project_root="/path/to/project")

# オプション2: Dependency Injection（新機能）
from tree_sitter_analyzer.core.analysis_engine import create_analysis_engine
from tree_sitter_analyzer.core.file_loader import FileLoader

loader = FileLoader(project_root="/path/to/project")
engine = create_analysis_engine(
    project_root="/path/to/project",
    file_loader=loader,
)
```

**メリット**:
- ✅ テストが容易（モックを注入可能）
- ✅ より柔軟（独立したインスタンスを作成可能）
- ✅ 後方互換（singletonは引き続き動作）

### 2. モジュール化されたfd_rg構造

**新機能**: fd_rg機能がモジュールに整理されました

**Before (V1)**:
```python
from tree_sitter_analyzer.mcp.tools import fd_rg_utils

# すべての関数が1つのファイルに
result = fd_rg_utils.build_fd_command(...)
```

**After (V2)**:
```python
# オプション1: 旧インポートを使用（後方互換）
from tree_sitter_analyzer.mcp.tools import fd_rg_utils
result = fd_rg_utils.build_fd_command(...)

# オプション2: 新しいモジュール構造を使用（推奨）
from tree_sitter_analyzer.mcp.tools.fd_rg import (
    FdCommandConfig,
    FdCommandBuilder,
    RgCommandConfig,
    RgCommandBuilder,
)

config = FdCommandConfig(roots=["."], pattern="*.py")
builder = FdCommandBuilder(config)
command = builder.build()
```

**メリット**:
- ✅ より良い整理
- ✅ コードを見つけやすい
- ✅ 型安全な設定
- ✅ 不変な設定（frozen dataclasses）

### 3. 改善されたSearchContentTool

**新機能**: 保守性向上のための内部リファクタリング

**Before (V1)**:
```python
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool

tool = SearchContentTool(...)
result = await tool.execute({"query": "class", "roots": ["."]})
```

**After (V2)**:
```python
# 同じAPI、より良い実装
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool

tool = SearchContentTool(...)
result = await tool.execute({"query": "class", "roots": ["."]})
```

**メリット**:
- ✅ 同じAPI（変更不要）
- ✅ より良いパフォーマンス（改善されたキャッシング）
- ✅ 保守が容易（strategy pattern）
- ✅ より良いエラーメッセージ

---

## 移行手順

### ステップ1: 依存関係の更新

変更は不要です。リファクタリング版は同じ依存関係を使用します。

### ステップ2: コードのレビュー

以下のパターンを使用しているか確認してください:

#### パターン1: fd_rg_utilsの直接使用

**現在のコード**:
```python
from tree_sitter_analyzer.mcp.tools import fd_rg_utils

command = fd_rg_utils.build_fd_command(
    pattern="*.py",
    roots=["."],
    extensions=["py"],
    # ... 多数のパラメータ
)
```

**推奨される移行**:
```python
from tree_sitter_analyzer.mcp.tools.fd_rg import FdCommandConfig, FdCommandBuilder

config = FdCommandConfig(
    roots=["."],
    pattern="*.py",
    extensions=["py"],
)
builder = FdCommandBuilder(config)
command = builder.build()
```

**移行する理由**:
- ✅ 型安全性
- ✅ 不変な設定
- ✅ より良いバリデーション
- ✅ テストが容易

#### パターン2: テストでのUnifiedAnalysisEngine

**現在のコード**:
```python
def test_analysis():
    engine = UnifiedAnalysisEngine(project_root="/tmp/test")
    # 依存性のモック化が困難
```

**推奨される移行**:
```python
from tree_sitter_analyzer.core.analysis_engine import create_analysis_engine
from unittest.mock import Mock

def test_analysis():
    mock_loader = Mock()
    engine = create_analysis_engine(
        project_root="/tmp/test",
        file_loader=mock_loader,
    )
    # モックの注入が容易
```

**移行する理由**:
- ✅ テストが容易
- ✅ より良い分離
- ✅ より多くの制御

#### パターン3: SearchContentToolの使用

**現在のコード**:
```python
tool = SearchContentTool(...)
result = await tool.execute({"query": "class", "roots": ["."]})
```

**移行不要**:
```python
# V2でも同じコードが動作
tool = SearchContentTool(...)
result = await tool.execute({"query": "class", "roots": ["."]})
```

**移行不要な理由**:
- ✅ APIは変更なし
- ✅ 動作は同一
- ✅ パフォーマンスは向上

### ステップ3: テストの実行

```bash
# 既存のテストを実行
pytest tests/

# すべてのテストは変更なしでパスするはず
```

### ステップ4: オプション: 新しいパターンの採用

新しいコードには新しいパターンの採用を検討してください:

1. **fd_rg_utilsの代わりにfd_rgモジュールを使用**
2. **テストにはcreate_analysis_engine()を使用**
3. **設定にはfrozen dataclassesを使用**

---

## 移行のテスト

### チェックリスト

- [ ] すべての既存テストがパス
- [ ] インポートエラーなし
- [ ] ランタイムエラーなし
- [ ] パフォーマンスは同等以上
- [ ] すべての機能が期待通りに動作

### テストコマンド

```bash
# すべてのテストを実行
pytest tests/

# 特定のテストスイートを実行
pytest tests/unit/
pytest tests/integration/
pytest tests/regression/

# カバレッジを確認
pytest --cov=tree_sitter_analyzer --cov-report=html

# ベンチマークを実行
python scripts/benchmark_search_content_tool.py
python scripts/benchmark_fd_rg.py
python scripts/benchmark_analysis_engine.py
```

### 期待される結果

| テストスイート | 期待される結果 |
|------------|-----------------|
| ユニットテスト | すべてパス |
| 統合テスト | すべてパス |
| 回帰テスト | すべてパス |
| パフォーマンス | 10%以上の劣化なし |
| カバレッジ | >80% |

---

## トラブルシューティング

### 問題1: インポートエラー

**症状**:
```python
ImportError: cannot import name 'FdCommandConfig'
```

**解決策**:
```python
# 正しいモジュールからインポートしていることを確認
from tree_sitter_analyzer.mcp.tools.fd_rg import FdCommandConfig

# fd_rg_utilsからではない
```

### 問題2: 型エラー

**症状**:
```python
TypeError: FdCommandConfig() missing required argument: 'roots'
```

**解決策**:
```python
# FdCommandConfigにはrootsパラメータが必要
config = FdCommandConfig(roots=["."])  # ✅ 正しい

# 以下ではない
config = FdCommandConfig()  # ❌ エラー
```

### 問題3: Singleton動作の変更

**症状**:
```python
# 同じインスタンスを期待しているが、異なるインスタンスを取得
engine1 = UnifiedAnalysisEngine(project_root="/tmp")
engine2 = UnifiedAnalysisEngine(project_root="/tmp")
assert engine1 is engine2  # 失敗
```

**解決策**:
```python
# 依存性を提供した場合、singletonはバイパスされる
# singleton動作が必要な場合は依存性を提供しない

# Singleton（同じインスタンス）
engine1 = UnifiedAnalysisEngine(project_root="/tmp")
engine2 = UnifiedAnalysisEngine(project_root="/tmp")
assert engine1 is engine2  # ✅ パス

# Non-singleton（異なるインスタンス）
engine1 = create_analysis_engine(project_root="/tmp", file_loader=loader1)
engine2 = create_analysis_engine(project_root="/tmp", file_loader=loader2)
assert engine1 is not engine2  # ✅ パス
```

---

## FAQ

### Q: コードを変更する必要がありますか？

**A**: いいえ。すべての既存コードは変更なしで引き続き動作します。

### Q: 新しいパターンに移行すべきですか？

**A**: 既存のコードについては、移行は不要です。新しいコードについては、より良い型安全性とテスト容易性のために新しいパターンの使用を推奨します。

### Q: パフォーマンスに影響はありますか？

**A**: パフォーマンスは同等以上であるべきです。リファクタリングによりキャッシングが改善され、不要な作業が削減されました。

### Q: 破壊的変更はありますか？

**A**: いいえ。リファクタリングは100%の後方互換性を維持しています。

### Q: 非推奨機能を使用しているかどうかはどうやって分かりますか？

**A**: V2には非推奨機能はありません。すべての機能は完全にサポートされています。

### Q: 古いパターンと新しいパターンを混在させることはできますか？

**A**: はい。同じコードベースで古いインポートと新しいインポートを使用できます。それらはシームレスに連携します。

---

## 移行タイムライン

### 即時（必須）

- ✅ なし - 即座のアクションは不要

### 短期（推奨）

- 新しいコードには新しいパターンの採用を検討
- テストをdependency injectionを使用するように更新
- より良い型安全性のためにfd_rgモジュールに移行

### 長期（オプション）

- 既存のコードを徐々に新しいパターンに移行
- 新しいパターンを参照するようにドキュメントを更新
- チームに新しいパターンをトレーニング

---

## サポート

移行中に問題が発生した場合:

1. このガイドを確認
2. [リファクタリングガイド](refactoring-guide.md)をレビュー
3. [APIドキュメント](../README.md)を確認
4. GitHubでissueを開く

---

## まとめ

**重要なポイント**:
- ✅ 100%後方互換
- ✅ 破壊的変更なし
- ✅ 非推奨機能なし
- ✅ 新機能はオプション
- ✅ パフォーマンスは同等以上
- ✅ すべてのテストは変更なしでパスするはず

**推奨事項**:
- 既存のコードはそのまま維持
- 新しいコードには新しいパターンを使用
- 都合の良いときに徐々に移行
