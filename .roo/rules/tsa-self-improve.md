# TSA Self-Improve Rule

tree-sitter-analyzerプロジェクトでの自律改善ルール。

## 適用条件

tree-sitter-analyzerプロジェクトで作業する場合、このルールを自動適用。

## 必須ルール

### 1. MCPツール優先

ファイル読込は tree-sitter-analyzer MCP使用:

```
✅ search_content → analyze_code_structure
❌ read_file (コードファイル)
```

### 2. Token節約

大規模分析時:

```
check_code_scale(file) → 評価
suppress_output=true + output_file → 結果保存
total_only=true → 検索件数のみ
```

### 3. TDD原則

```
1. SPEC  仕様定義
2. RED   テスト作成 (失敗確認)
3. GREEN 最小実装 (テスト成功)
4. REFACTOR 品質向上
```

### 4. Windows対応

```
❌ grep, find, cat, sed, awk
✅ rg, fd, PowerShell, Python
```

## ワークフロー

### 分析

```
search_content → check_code_scale → 推奨戦略に従う
```

### Spec定義

```
openspec/specs/{module}/spec.md 作成
```

### テスト作成

```
1. analyze_code_structure で対象理解
2. Specに基づきテスト設計
3. テストファイル作成
4. RED確認 (失敗すること)
```

### 実装

```
1. 最小実装
2. GREEN確認 (成功すること)
3. 品質チェック
```

## 品質ゲート

各変更後にパスすること:

```bash
uv run pytest tests/ -v           # 全テスト
uv run mypy tree_sitter_analyzer/ # 型チェック
uv run ruff check .               # リント
uv run python check_quality.py    # 品質
```

## カバレッジ目標

| 優先度 | カバレッジ | 対象 |
|--------|-----------|------|
| P0 | < 30% | 即座に改善 |
| P1 | 30-50% | 高優先 |
| P2 | 50-80% | 中優先 |
| P3 | > 80% | 機能拡張 |
