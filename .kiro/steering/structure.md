---
inclusion: always
---

# プロジェクト構造

## ルートパッケージ

`tree_sitter_analyzer` - AI時代のエンタープライズグレードコード解析ツール

## ソース構成

### メインソース (`tree_sitter_analyzer/`)

```
tree_sitter_analyzer/
├── core/                    # コアエンジン
│   ├── analysis_engine.py   # 統合解析エンジン
│   ├── cache_service.py     # キャッシュサービス
│   ├── engine.py           # レガシーエンジン
│   ├── parser.py           # パーサー
│   ├── query_filter.py     # クエリフィルタ
│   ├── query_service.py    # クエリサービス
│   └── query.py            # クエリ実行
├── mcp/                    # MCPサーバー実装
│   ├── server.py           # MCPサーバーメイン
│   ├── tools/              # MCPツール群
│   │   ├── analyze_scale_tool.py
│   │   ├── find_and_grep_tool.py
│   │   ├── list_files_tool.py
│   │   ├── query_tool.py
│   │   ├── search_content_tool.py
│   │   ├── table_format_tool.py
│   │   └── universal_analyze_tool.py
│   ├── resources/          # MCPリソース
│   └── utils/              # MCPユーティリティ
├── languages/              # 言語プラグイン
│   ├── java_plugin.py      # Java言語サポート
│   ├── python_plugin.py    # Python言語サポート
│   ├── javascript_plugin.py # JavaScript言語サポート
│   ├── typescript_plugin.py # TypeScript言語サポート
│   ├── csharp_plugin.py    # C#言語サポート
│   ├── php_plugin.py       # PHP言語サポート
│   ├── ruby_plugin.py      # Ruby言語サポート
│   ├── sql_plugin.py       # SQL言語サポート
│   ├── html_plugin.py      # HTML言語サポート
│   ├── css_plugin.py       # CSS言語サポート
│   └── markdown_plugin.py  # Markdown言語サポート
├── formatters/             # 出力フォーマッター
│   ├── base_formatter.py   # ベースフォーマッター
│   ├── java_formatter.py   # Java専用フォーマッター
│   ├── python_formatter.py # Python専用フォーマッター
│   ├── csharp_formatter.py # C#専用フォーマッター
│   ├── php_formatter.py    # PHP専用フォーマッター
│   ├── ruby_formatter.py   # Ruby専用フォーマッター
│   ├── sql_formatters.py   # SQL専用フォーマッター
│   ├── html_formatter.py   # HTML専用フォーマッター
│   ├── markdown_formatter.py # Markdown専用フォーマッター
│   └── formatter_registry.py # フォーマッター登録
├── cli/                    # CLIインターフェース
│   ├── commands/           # CLIコマンド実装
│   │   ├── advanced_command.py
│   │   ├── structure_command.py
│   │   ├── table_command.py
│   │   ├── query_command.py
│   │   ├── find_and_grep_cli.py
│   │   ├── list_files_cli.py
│   │   └── search_content_cli.py
│   └── argument_validator.py # 引数検証
├── queries/                # Tree-sitterクエリ
│   ├── java.py             # Javaクエリ定義
│   ├── python.py           # Pythonクエリ定義
│   ├── javascript.py       # JavaScriptクエリ定義
│   ├── typescript.py       # TypeScriptクエリ定義
│   ├── csharp.py           # C#クエリ定義
│   ├── php.py              # PHPクエリ定義
│   ├── ruby.py             # Rubyクエリ定義
│   ├── sql.py              # SQLクエリ定義
│   ├── html.py             # HTMLクエリ定義
│   ├── css.py              # CSSクエリ定義
│   └── markdown.py         # Markdownクエリ定義
├── security/               # セキュリティモジュール
│   ├── validator.py        # セキュリティ検証
│   ├── boundary_manager.py # プロジェクト境界管理
│   └── regex_checker.py    # 正規表現安全性チェック
├── plugins/                # プラグインシステム
│   ├── base.py             # プラグインベースクラス
│   └── manager.py          # プラグインマネージャー
├── interfaces/             # インターフェース層
│   ├── cli_adapter.py      # CLIアダプター
│   └── mcp_adapter.py      # MCPアダプター
└── utils/                  # ユーティリティ
    ├── logging.py          # ログ設定
    └── tree_sitter_compat.py # Tree-sitter互換性
```

### テストソース (`tests/`)

```
tests/
├── unit/                   # 単体テスト
├── integration/            # 統合テスト
├── mcp/                   # MCPサーバーテスト
├── security/              # セキュリティテスト
├── test_languages/        # 言語プラグインテスト
├── test_core/             # コアエンジンテスト
├── test_data/             # テストデータ
│   ├── sample.css
│   ├── sample.html
│   ├── test_class.js
│   ├── test_class.py
│   └── test_enum.ts
└── fixtures/              # テストフィクスチャ
```

## 主要アーキテクチャパターン

### プラグインアーキテクチャ
- **言語プラグインシステム**: 各言語が独立したプラグインとして実装
- **動的プラグイン発見**: Entry Pointsによる自動プラグイン検出
- **統一インターフェース**: `LanguagePlugin`ベースクラスによる一貫したAPI
- **拡張性**: 新しい言語サポートの容易な追加

### MCPプロトコル統合
- **非同期処理**: 全てのMCPツールは`async/await`パターンを使用
- **エラーハンドリング**: MCPエラーレスポンスの標準化
- **リソース管理**: ファイルハンドルやプロセスの適切なクリーンアップ
- **セキュリティ**: パス検証とサンドボックス化の徹底

### 統一要素システム
- **単一要素リスト**: 全てのコード要素（クラス、メソッド、フィールド、インポート、パッケージ）の統一管理
- **一貫した要素タイプ**: 各要素が`element_type`属性を持つ
- **簡素化されたAPI**: より明確なインターフェースと複雑性の削減
- **保守性の向上**: 全てのコード要素の単一情報源

### フォーマッターレジストリパターン
- **動的フォーマッター管理**: Registry パターンによる動的フォーマッター管理システム
- **プラグインベース拡張**: `IFormatter`インターフェースによる新しいフォーマッターの容易な追加
- **言語固有フォーマッター**: 各言語専用の最適化されたフォーマッター
- **戦略パターン**: フォーマット戦略の動的選択

### セキュリティフレームワーク
- **多層防御**: パストラバーサル、ReDoS攻撃、入力インジェクションに対する7層防御
- **プロジェクト境界管理**: シンボリックリンク保護付きの厳格なプロジェクト境界制御
- **リアルタイム監視**: 正規表現パフォーマンス監視とReDoS攻撃防止
- **包括的入力サニタイゼーション**: 全ての入力に対する検証とサニタイゼーション

## 命名規則

### ファイル命名規則
- **プラグインファイル**: `{language}_plugin.py` (例: `java_plugin.py`, `python_plugin.py`)
- **フォーマッターファイル**: `{language}_formatter.py` (例: `java_formatter.py`, `sql_formatters.py`)
- **クエリファイル**: `{language}.py` (例: `java.py`, `python.py`)
- **MCPツールファイル**: `{function}_tool.py` (例: `query_tool.py`, `search_content_tool.py`)
- **CLIコマンドファイル**: `{command}_command.py` または `{tool}_cli.py`

### クラス命名規則
- **プラグインクラス**: `{Language}Plugin` (例: `JavaPlugin`, `PythonPlugin`)
- **フォーマッタークラス**: `{Language}Formatter` (例: `JavaFormatter`, `SQLFullFormatter`)
- **MCPツールクラス**: `{Function}Tool` (例: `QueryTool`, `SearchContentTool`)
- **エンジンクラス**: `{Function}Engine` (例: `UnifiedAnalysisEngine`)

### パッケージ命名規則
- **メインパッケージ**: `tree_sitter_analyzer`
- **サブパッケージ**: snake_case (例: `mcp.tools`, `cli.commands`)
- **モジュール**: snake_case (例: `analysis_engine`, `query_service`)

### 設定とエントリーポイント
- **Entry Points**: `tree_sitter_analyzer.plugins` でプラグイン自動発見
- **CLIスクリプト**: `tree-sitter-analyzer`, `tree-sitter-analyzer-mcp`
- **MCPサーバー**: `tree_sitter_analyzer.mcp.server:main_sync`
