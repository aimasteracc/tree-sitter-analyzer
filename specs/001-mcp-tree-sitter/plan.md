# Implementation Plan: Tree-sitter Analyzer MCP Server

**Branch**: `001-mcp-tree-sitter` | **Date**: 2025-10-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-mcp-tree-sitter/spec.md`

## Summary

Tree-sitter Analyzer MCPサーバーは、Model Context Protocol (MCP) を通じてコード解析機能を提供するPythonライブラリです。大規模コードファイルのLLMトークン制限問題を解決し、8つのツールと2つのリソースを通じて効率的なコード分析を実現します。

## Technical Context

**Language/Version**: Python 3.10+ (3.10, 3.11, 3.12, 3.13対応)
**Primary Dependencies**:
- mcp>=1.12.3 (Model Context Protocol)
- tree-sitter>=0.25.0 (コード解析エンジン)
- tree-sitter-java, tree-sitter-python, tree-sitter-javascript, tree-sitter-markdown (言語パーサー)
- chardet>=5.0.0 (エンコーディング検出)
- cachetools>=5.0.0 (キャッシュ機能)
- psutil>=5.9.8 (システム情報)

**Storage**: ファイルベース（キャッシュ、中間ファイル出力）
**Testing**: pytest (統合テスト、ユニットテスト、MCPプロトコルテスト)
**Target Platform**: クロスプラットフォーム（Windows, Linux, macOS）
**Project Type**: ライブラリ + MCPサーバー
**Performance Goals**:
- 大規模ファイル（>10k行）の効率的解析
- トークン最適化（summary_only, suppress_output機能）
- キャッシュによる高速化

**Constraints**:
- セキュリティ境界管理（プロジェクトルート制限）
- メモリ効率（大規模ファイル対応）
- エラーハンドリング（構造化レスポンス）

**Scale/Scope**:
- 8つのMCPツール
- 6言語サポート（Java, Python, JavaScript, TypeScript, Markdown, C/C++）
- 2つのMCPリソース

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

[Gates determined based on constitution file]

## Project Structure

### Documentation (this feature)

```
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```
tree_sitter_analyzer/
├── __init__.py                    # パッケージエントリーポイント
├── __main__.py                    # CLI実行エントリー
├── api.py                         # 公開API
├── cli_main.py                    # CLIメイン処理
├── constants.py                   # 定数定義
├── exceptions.py                  # カスタム例外
├── encoding_utils.py              # エンコーディング処理
├── file_handler.py                # ファイル操作
├── language_detector.py           # 言語検出
├── language_loader.py             # 言語ローダー
├── models.py                      # データモデル
├── output_manager.py              # 出力管理
├── project_detector.py            # プロジェクト検出
├── query_loader.py                # クエリローダー
├── table_formatter.py             # テーブル形式出力
├── utils.py                       # ユーティリティ
├── core/                          # コア解析エンジン
│   ├── __init__.py
│   ├── analysis_engine.py         # 統合解析エンジン
│   ├── cache_service.py           # キャッシュサービス
│   ├── engine.py                  # レガシーエンジン
│   ├── parser.py                  # パーサー
│   ├── query.py                   # クエリ処理
│   ├── query_filter.py            # クエリフィルター
│   └── query_service.py           # クエリサービス
├── formatters/                    # 言語別フォーマッター
│   ├── __init__.py
│   ├── formatter_factory.py
│   ├── java_formatter.py
│   ├── javascript_formatter.py
│   ├── language_formatter_factory.py
│   ├── markdown_formatter.py
│   ├── python_formatter.py
│   └── typescript_formatter.py
├── interfaces/                    # インターフェース層
│   ├── __init__.py
│   ├── cli.py                     # CLI インターフェース
│   ├── cli_adapter.py             # CLI アダプター
│   ├── mcp_adapter.py             # MCP アダプター
│   └── mcp_server.py              # レガシーMCPサーバー
├── languages/                     # 言語プラグイン
│   ├── __init__.py
│   ├── markdown_plugin.py
│   └── typescript_plugin.py
├── mcp/                           # MCP実装（メイン）
│   ├── __init__.py                # MCPメタデータ
│   ├── server.py                  # MCPサーバー実装
│   ├── resources/                 # MCPリソース
│   │   ├── __init__.py
│   │   ├── code_file_resource.py  # コードファイルリソース
│   │   └── project_stats_resource.py # プロジェクト統計リソース
│   ├── tools/                     # MCPツール
│   │   ├── __init__.py
│   │   ├── analyze_scale_tool.py  # check_code_scale
│   │   ├── base_tool.py           # ベースツール
│   │   ├── fd_rg_utils.py         # fd/rg ユーティリティ
│   │   ├── find_and_grep_tool.py  # find_and_grep
│   │   ├── list_files_tool.py     # list_files
│   │   ├── query_tool.py          # query_code
│   │   ├── read_partial_tool.py   # extract_code_section
│   │   ├── search_content_tool.py # search_content
│   │   ├── table_format_tool.py   # analyze_code_structure
│   │   └── universal_analyze_tool.py # レガシーツール
│   └── utils/                     # MCPユーティリティ
│       ├── __init__.py
│       ├── error_handler.py       # エラーハンドリング
│       ├── file_output_manager.py # ファイル出力管理
│       ├── gitignore_detector.py  # .gitignore検出
│       ├── path_resolver.py       # パス解決
│       └── search_cache.py        # 検索キャッシュ
├── plugins/                       # プラグインシステム
│   ├── __init__.py
│   ├── base.py                    # ベースプラグイン
│   └── manager.py                 # プラグインマネージャー
├── queries/                       # 言語別クエリ
│   ├── __init__.py
│   ├── java.py
│   ├── javascript.py
│   ├── markdown.py
│   ├── python.py
│   └── typescript.py
└── security/                      # セキュリティ
    ├── __init__.py
    ├── boundary_manager.py        # 境界管理
    ├── regex_checker.py           # 正規表現チェック
    └── validator.py               # バリデーター

tests/                             # テストスイート
├── __init__.py
├── conftest.py                    # pytest設定
├── test_*.py                      # ユニットテスト（多数）
├── mcp/                           # MCPテスト
│   ├── __init__.py
│   ├── test_integration.py        # MCP統合テスト
│   ├── test_server.py             # MCPサーバーテスト
│   ├── test_user_story_*.py       # ユーザーストーリーテスト
│   └── test_resources/            # リソーステスト
│       └── test_*.py
├── security/                      # セキュリティテスト
│   └── test_mcp_security.py
├── test_core/                     # コアテスト
│   └── test_*.py
├── test_formatters/               # フォーマッターテスト
│   └── test_*.py
├── test_languages/                # 言語テスト
│   └── test_*.py
└── test_plugins/                  # プラグインテスト
    └── test_*.py

specs/                             # 仕様書
└── 001-mcp-tree-sitter/
    ├── spec.md                    # 機能仕様
    ├── plan.md                    # 実装計画（このファイル）
    ├── data-model.md              # データモデル
    ├── quickstart.md              # クイックスタート
    ├── tasks.md                   # タスク定義
    ├── implementation_status.md   # 実装状況
    ├── test_environment_status.md # テスト環境状況
    └── contracts/                 # APIコントラクト
        └── mcp-tools-api.json
```

**Structure Decision**: 単一プロジェクト構造を採用。MCPサーバー機能は`tree_sitter_analyzer/mcp/`に集約し、既存のコード解析機能と統合。プラグインベースのアーキテクチャにより言語サポートを拡張可能。

## Architecture Overview

### Core Components

1. **MCP Server** (`tree_sitter_analyzer/mcp/server.py`)
   - Model Context Protocol実装
   - 8つのツールと2つのリソースを提供
   - セキュリティ境界管理
   - 非同期処理対応

2. **Analysis Engine** (`tree_sitter_analyzer/core/analysis_engine.py`)
   - Tree-sitterベースのコード解析
   - 統合解析エンジン
   - キャッシュ機能

3. **Tools** (`tree_sitter_analyzer/mcp/tools/`)
   - `check_code_scale`: コードスケール分析
   - `analyze_code_structure`: 構造解析
   - `extract_code_section`: 部分読み取り
   - `query_code`: クエリ実行
   - `list_files`: ファイル一覧
   - `search_content`: コンテンツ検索
   - `find_and_grep`: 2段階検索
   - `set_project_path`: プロジェクトパス設定

4. **Resources** (`tree_sitter_analyzer/mcp/resources/`)
   - `code://file/{file_path}`: コードファイルアクセス
   - `code://stats/{stats_type}`: プロジェクト統計

### Error Handling Strategy

- **構造化エラーレスポンス**: `success`/`error`フィールド
- **例外ベースエラー**: `AnalysisError`ラッピング
- **ツール別エラーハンドリング**: 実装に応じた適切な方式

### Performance Optimizations

- **Token最適化**: `suppress_output`, `summary_only`, `total_only`
- **ファイル出力**: 大規模結果の外部ファイル保存
- **キャッシュ**: 解析結果とクエリ結果のキャッシュ
- **段階的検索**: 数量確認→詳細検索の段階的アプローチ

## Implementation Status

### Completed Features

- ✅ **MCPサーバー基盤**: 完全実装済み
- ✅ **8つのMCPツール**: 全て実装済み
- ✅ **2つのMCPリソース**: 完全実装済み
- ✅ **セキュリティ機能**: 境界管理、バリデーション
- ✅ **エラーハンドリング**: 部分的実装（3/8ツール）
- ✅ **パフォーマンス最適化**: Token節約機能
- ✅ **テストスイート**: 統合テスト、ユニットテスト

### Current Issues

1. **エラーハンドリング不統一**: 5つのツールでエラーハンドリングテスト未実装
2. **APIコントラクト不整合**: 全ツールで`success`/`error`フィールド未統一
3. **仕様書の不完全性**: 実装詳細の文書化不足

## Complexity Tracking

*実装済み機能の複雑性管理*

| 複雑性要因 | 必要性 | 簡素化を避けた理由 |
|-----------|--------|-------------------|
| 8つのMCPツール | LLMトークン制限問題解決 | 単一ツールでは機能不足、用途別最適化が必要 |
| プラグインアーキテクチャ | 言語拡張性 | 直接実装では保守性が低下 |
| 2段階エラーハンドリング | ツール特性に応じた最適化 | 統一方式では柔軟性不足 |
| キャッシュシステム | 大規模ファイル性能 | 毎回解析では実用性が低い |
