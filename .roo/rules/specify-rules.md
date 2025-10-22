# tree-sitter-analyzer Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-10-22

## Active Technologies
- Python 3.10+ + mcp (Model Context Protocol), tree-sitter, asyncio, pathlib (001-mcp-tree-sitter)

## Project Structure
```
tree_sitter_analyzer/
├── core/           # コアエンジン
├── mcp/            # MCPサーバー実装
├── plugins/        # 言語プラグイン
├── formatters/     # 出力フォーマッター
├── utils/          # ユーティリティ
└── queries/        # Tree-sitterクエリ
tests/
├── unit/           # 単体テスト
├── integration/    # 統合テスト
├── mcp/           # MCPサーバーテスト
└── fixtures/      # テストデータ
```

## Commands
```bash
# 開発環境セットアップ
uv add --dev pre-commit && uv run pre-commit install

# 品質チェック
uv run pre-commit run --all-files
uv run black --check --line-length=88 .
uv run ruff check .
uv run mypy tree_sitter_analyzer/
uv run pytest tests/

# テスト実行
cd src; pytest; ruff check .
```

## Code Style
Python 3.10+: 詳細なコーディング規約は以下のルールファイルを参照:
- [コード品質基準](./code-quality-standards.md) - pre-commit設定に基づく包括的な品質ルール
- [プロジェクト固有ベストプラクティス](./project-best-practices.md) - tree-sitter-analyzer特有の設計パターン

## 品質基準

### 必須要件
- **型ヒント**: 全ての関数・メソッドに型ヒントを追加
- **docstring**: パブリックAPI全てにGoogle形式のdocstringを記述
- **エラーハンドリング**: 適切な例外処理とログ出力
- **非同期処理**: asyncio使用時の適切なリソース管理
- **セキュリティ**: パス検証とサンドボックス化の徹底
- **テストカバレッジ**: 80%以上を目標

### コードフォーマット
- **Black**: 行長88文字、Python 3.10+
- **Ruff**: 自動修正有効、フォーマット併用
- **isort**: Black互換プロファイル

### リンティング
- **MyPy**: 型チェック（examples/, scripts/, compatibility_test/除く）
- **Flake8**: 追加プラグイン（bugbear, comprehensions, simplify）
- **Bandit**: セキュリティチェック（tests/除く）
- **pydocstyle**: Google規約（一部エラー無視）

## Recent Changes
- 001-mcp-tree-sitter: Added Python 3.10+ + mcp (Model Context Protocol), tree-sitter, asyncio, pathlib
- 2025-10-22: Added comprehensive code quality standards and project-specific best practices

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->