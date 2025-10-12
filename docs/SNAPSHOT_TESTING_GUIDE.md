# スナップショットテスト実行ガイド

## 概要

このガイドでは、tree-sitter-analyzerプロジェクトのスナップショットテスト体制の使用方法について説明します。

## 目的

- **回帰検出**: PyPiパッケージを基準とした新実装の回帰検出
- **品質保証**: アーキテクチャ変更時の安全性確保
- **自動化**: CI/CDパイプラインでの自動テスト実行

## テスト体制の構成

### 1. ディレクトリ構造

```
test_snapshots/
├── README.md                    # 概要説明
├── baselines/                   # PyPiパッケージによるベースライン
│   ├── java/                   # Java言語のスナップショット
│   ├── python/                 # Python言語のスナップショット
│   ├── javascript/             # JavaScript言語のスナップショット
│   ├── typescript/             # TypeScript言語のスナップショット
│   ├── html/                   # HTML言語のスナップショット
│   └── markdown/               # Markdown言語のスナップショット
├── current/                    # 現在の実装による出力
├── diffs/                      # 差分レポート
├── config/                     # テスト設定
└── reports/                    # テストレポート
```

### 2. 設定ファイル

- **test_cases.json**: テストケース定義
- **comparison_rules.json**: 比較ルール設定

## 基本的な使用方法

### 1. ベースライン生成

```bash
# PyPiパッケージを使用してベースライン生成
python scripts/generate_snapshots.py --mode baseline --verbose
```

### 2. 現在の実装テスト

```bash
# 現在の実装でスナップショット生成
python scripts/generate_snapshots.py --mode current --verbose
```

### 3. 回帰テスト実行

```bash
# 全回帰テスト実行
pytest tests/test_snapshot_regression.py -v

# 言語別テスト実行
pytest tests/test_snapshot_regression.py::test_snapshot_regression_by_language[java] -v

# スナップショットマーカーでテスト実行
pytest -m "snapshot" -v
```

### 4. 両方を一度に実行

```bash
# ベースラインと現在実装の両方を生成
python scripts/generate_snapshots.py --mode both --verbose
```

## 詳細な使用方法

### テストケースの追加

新しいテストケースを追加する場合：

1. **ファイル準備**: `examples/`フォルダに対象ファイルを配置
2. **設定更新**: `test_snapshots/config/test_cases.json`に新しいテストケースを追加

```json
{
  "name": "新しいテストケース",
  "file_path": "examples/new_test_file.java",
  "description": "新機能のテスト",
  "test_formats": ["json", "csv"],
  "test_queries": ["class", "methods", "fields"]
}
```

### 比較ルールのカスタマイズ

`test_snapshots/config/comparison_rules.json`で比較ルールを調整：

```json
{
  "strict_fields": ["elements.classes", "elements.methods"],
  "tolerance_fields": {
    "complexity.total": {
      "type": "percentage",
      "threshold": 5.0
    }
  },
  "ignore_fields": ["timestamp", "execution_time"]
}
```

### 結果の解釈

#### 成功例
```
=== スナップショット回帰テスト結果 ===
総テスト数: 12
成功: 12
失敗: 0
重要な問題: 0
警告: 0

全てのテストが成功しました。
```

#### 警告例
```
=== スナップショット回帰テスト結果 ===
総テスト数: 12
成功: 10
失敗: 2
重要な問題: 0
警告: 3

一部のテストが失敗しました。
```

#### 重要な問題例
```
=== スナップショット回帰テスト結果 ===
総テスト数: 12
成功: 8
失敗: 4
重要な問題: 2
警告: 5

重要な回帰が検出されました！
```

## CI/CD統合

### GitHub Actions

プルリクエスト時に自動実行：

```yaml
# .github/workflows/snapshot-regression.yml
name: Snapshot Regression Tests
on:
  pull_request:
    branches: [ main, develop ]
```

### 手動実行

GitHub Actionsで手動実行：

1. GitHubリポジトリの「Actions」タブを開く
2. 「Snapshot Regression Tests」ワークフローを選択
3. 「Run workflow」をクリック
4. 必要に応じて「Generate new baseline snapshots」をチェック

## トラブルシューティング

### よくある問題

#### 1. ベースラインファイルが見つからない

**症状**: `スナップショットファイルが見つかりません`

**解決方法**:
```bash
# ベースラインを再生成
python scripts/generate_snapshots.py --mode baseline --verbose
```

#### 2. MCPツール実行エラー

**症状**: `MCPツール実行エラー`

**解決方法**:
```bash
# 依存関係を再インストール
uv sync --all-extras
uv pip install tree-sitter-analyzer[mcp]
```

#### 3. 大量の差分が検出される

**症状**: 予期しない大量の差分

**解決方法**:
1. 比較ルールの確認
2. 無視フィールドの追加
3. 許容範囲の調整

### デバッグ方法

#### 詳細ログの有効化

```bash
# 詳細ログ付きで実行
python scripts/generate_snapshots.py --mode both --verbose
```

#### 個別ファイルのテスト

```bash
# 特定のファイルのみテスト
pytest tests/test_snapshot_regression.py::test_snapshot_regression_by_language[java] -v -s
```

#### 差分の詳細確認

```bash
# 差分ファイルの確認
cat test_snapshots/diffs/summary.json
ls test_snapshots/diffs/detailed/
```

## ベストプラクティス

### 1. 定期的なベースライン更新

- メジャーリリース前にベースラインを更新
- 意図的な変更後はベースラインを再生成

### 2. 段階的なテスト実行

1. **開発中**: 個別ファイルでのテスト
2. **プルリクエスト**: 全体テストの実行
3. **リリース前**: 包括的な回帰テスト

### 3. 結果の適切な解釈

- **重要な問題**: 即座に修正が必要
- **警告**: レビューして判断
- **情報**: 参考程度

### 4. 設定の適切な管理

- テストケースの定期的な見直し
- 比較ルールの最適化
- 無視フィールドの適切な設定

## 高度な使用方法

### カスタムクエリの追加

新しいクエリタイプを追加：

```json
{
  "test_queries": ["class", "methods", "custom_query"]
}
```

### パフォーマンステスト

```bash
# パフォーマンス測定付きテスト
time python scripts/generate_snapshots.py --mode current
```

### バッチ処理

```bash
# 複数言語の一括処理
for lang in java python javascript; do
  pytest tests/test_snapshot_regression.py::test_snapshot_regression_by_language[$lang] -v
done
```

## まとめ

スナップショットテスト体制により、以下が実現されます：

- **安全なリファクタリング**: 回帰の早期検出
- **品質保証**: 一貫した出力の保証
- **開発効率**: 自動化されたテスト実行
- **信頼性**: PyPiパッケージとの互換性確保

定期的なテスト実行と適切な設定管理により、プロジェクトの品質を維持できます。