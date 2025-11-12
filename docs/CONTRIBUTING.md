# Contributing to tree-sitter-analyzer

## 文書管理ガイドライン

### ディレクトリ構造と用途

#### `specs/` - 機能仕様書
- **目的**: プロジェクトの主要な機能仕様（Feature Specifications）を格納
- **対象**: プロジェクトの根幹をなす、永続的な設計文書
- **管理方針**: 
  - `specs/001-feature-name/` のようなサブディレクトリ構造で機能ごとにグループ化
  - `spec.md`, `plan.md` は恒久的に保持
  - `tasks.md` は完了後も履歴として保持（削除しない）

#### `docs/analysis/` - 分析結果
- **目的**: `speckit.analyze`やその他の分析ツールによる恒久的な分析結果を保存
- **対象**: 
  - プロジェクトのアーキテクチャ分析結果
  - 依存関係の分析レポート
  - コード品質メトリクス
  - パフォーマンス分析結果
  - セキュリティ監査結果
- **管理方針**: バージョン管理下で恒久的に管理

#### `.specify/` - 一時的な作業ファイル
- **目的**: `speckit`などのツールが生成する一時的な作業ファイルを格納
- **対象**: ブランチごとの短期的な仕様検討やタスク管理
- **管理方針**: 
  - `.gitignore`で追跡対象から除外
  - 対応するブランチがマージされれば削除可能

### 分析結果の文書化戦略

#### 恒久的な分析結果
- **保存場所**: `docs/analysis/`
- **命名規則**: 
  - `architecture_overview.md` - アーキテクチャの全体像
  - `dependency_analysis.md` - 依存関係の分析
  - `code_metrics_YYYY-MM-DD.md` - 日付付きのコードメトリクス
  - `performance_report_vX.X.X.md` - バージョン別パフォーマンスレポート

#### 一時的な分析結果
- **保存場所**: `.specify/` または `.temp/analysis/`
- **管理方針**: 作業完了後に削除

### speckit コマンドの使用ガイドライン

#### `speckit.analyze`
- **制約**: 読み取り専用（ファイル変更禁止）
- **目的**: spec.md, plan.md, tasks.md の一貫性と品質分析
- **実行タイミング**: `/tasks` 完了後
- **出力**: 構造化された分析レポート（ファイル書き込みなし）

#### 完了済みタスクファイルの取り扱い
- `tasks.md` は完了後も**削除しない**
- 履歴として保持し、将来の参考資料とする
- アーカイブディレクトリへの移動は行わない

### 文書間のナビゲーション

- [仕様書](../specs/) - プロジェクトの機能仕様
- [分析結果](analysis/) - 分析ツールによる結果
- [API文書](api/) - API仕様書
- [開発者ガイド](developer_guide.md) - 開発者向けガイド

## 開発ワークフロー

### 新機能開発
1. `specs/` に機能仕様を作成
2. `speckit.analyze` で一貫性チェック
3. 実装開始
4. 完了後、分析結果を `docs/analysis/` に保存

### バグ修正・リファクタリング
1. `.specify/` で一時的な作業ファイル管理
2. 修正完了後、`.specify/` ディレクトリを削除
3. 必要に応じて分析結果を `docs/analysis/` に保存

## コード品質

### テスト

すべての新機能と変更には適切なテストが必要です。

#### テスト要件
- **カバレッジ**: 新規コードは100%カバレッジ必須
- **既存テスト**: すべてのテストがパスすることを確認
- **テストタイプ**: 
  - ユニットテスト: 個別コンポーネントのテスト
  - 統合テスト: コンポーネント間の相互作用テスト
  - E2Eテスト: エンドツーエンドのワークフローテスト

#### テストの実行

```bash
# すべてのテストを実行
pytest

# カバレッジレポート付きで実行
pytest --cov=tree_sitter_analyzer --cov-report=term-missing

# 特定のテストファイルを実行
pytest tests/unit/test_specific_module.py

# 並列実行（高速化）
pytest -n auto
```

#### テストの書き方

詳細なテストガイドラインは [TESTING.md](TESTING.md) を参照してください。

**主要なポイント**:
- `tests/fixtures/` のヘルパーを活用
- Arrange-Act-Assert パターンに従う
- 明確で説明的なテスト名を使用
- 成功パスとエラーパス両方をテスト
- 外部依存関係はモック化

#### テストフィクスチャとユーティリティ

プロジェクトは再利用可能なテストユーティリティを提供しています:

```python
from tests.fixtures import coverage_helpers, data_generators, assertion_helpers

# モックデータの作成
node = coverage_helpers.create_mock_node("function_definition")
code = data_generators.generate_python_function("my_func")

# カスタムアサーション
assertion_helpers.assert_analysis_result_valid(result)
assertion_helpers.assert_coverage_threshold(85.0, 80.0, "module")
```

#### カバレッジターゲット

| モジュールカテゴリ | カバレッジ目標 | 優先度 |
|-------------------|---------------|--------|
| コアエンジン | ≥85% | クリティカル |
| 例外処理 | ≥90% | クリティカル |
| MCPインターフェース | ≥80% | 高 |
| CLIコマンド | ≥85% | 高 |
| フォーマッター | ≥80% | 中 |
| クエリモジュール | ≥85% | 中 |

### ドキュメント
- 公開APIの変更時は必ずドキュメントを更新
- 重要な設計決定は `docs/analysis/` に記録
- テストガイドライン: [TESTING.md](TESTING.md)
- API仕様書: [api/](api/)

## リリース管理

### バージョニング
- セマンティックバージョニングに従う
- 破壊的変更は major バージョンアップ

### リリースノート
- `CHANGELOG.md` を更新
- 重要な変更は `docs/analysis/` にも記録