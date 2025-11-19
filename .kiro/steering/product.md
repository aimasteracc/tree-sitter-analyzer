---
inclusion: always
---

# プロダクト概要

Tree-sitter Analyzerは、AI時代のエンタープライズグレードコード解析ツールです。本プロジェクトは、複数のプログラミング言語に対応した包括的なコード解析機能を提供し、AI アシスタント（Claude Desktop、Cursor、Roo Code等）との深い統合を実現します。

## ドメイン

### コード解析・静的解析ツール
- **Tree-sitter基盤**: 高精度なAST（抽象構文木）解析
- **多言語対応**: Java、Python、JavaScript、TypeScript、C#、PHP、Ruby、SQL、HTML、CSS、Markdownの11言語
- **AI統合**: MCP（Model Context Protocol）による AI アシスタントとのネイティブ統合
- **エンタープライズ対応**: 大規模コードベースでの高性能処理

### 主要ドメイン領域
- **静的コード解析**: 構造解析、複雑度計算、要素抽出
- **AI支援開発**: トークン制限突破、自然言語インタラクション
- **ファイル検索・コンテンツ検索**: fd/ripgrep統合による高性能検索
- **開発者ツール**: CLI、MCP、API の統合インターフェース

## 主要機能

### 🤖 深いAI統合
- **MCP プロトコルサポート**: Claude Desktop、Cursor、Roo Code でのネイティブサポート
- **SMART ワークフロー**: 体系的なAI支援分析手法
- **トークン制限突破**: 任意サイズのコードファイル処理
- **自然言語インタラクション**: 複雑な解析を自然言語で実行

### 🔍 強力な検索機能
- **インテリジェントファイル発見**: fd ベースの高性能検索
- **精密コンテンツ検索**: ripgrep 正規表現コンテンツ検索
- **二段階検索**: ファイル発見 + コンテンツ検索の組み合わせワークフロー
- **プロジェクト境界保護**: 自動セキュリティ境界設定

### 📊 インテリジェント解析
- **高速構造解析**: 完全読み込み不要のアーキテクチャ理解
- **精密コード抽出**: 行範囲指定によるコードスニペット抽出
- **複雑度解析**: 循環的複雑度メトリクス
- **統一要素システム**: 革新的な要素管理システム

### 🌍 エンタープライズ多言語サポート
- **Java**: Spring フレームワーク、JPA、エンタープライズ機能
- **Python**: 型アノテーション、デコレータ、モダンPython機能
- **C#**: クラス、インターフェース、レコード、プロパティ、async/await、属性、モダンC#機能
- **PHP**: クラス、インターフェース、トレイト、列挙型、名前空間、属性、マジックメソッド、モダンPHP 8+機能
- **Ruby**: クラス、モジュール、ミックスイン、ブロック、Proc、Lambda、メタプログラミング、Railsパターン
- **SQL**: テーブル、ビュー、ストアドプロシージャ、関数、トリガー、インデックス、専用出力フォーマット
- **JavaScript**: ES6+、React/Vue/Angular、JSX
- **TypeScript**: インターフェース、型、デコレータ、TSX/JSX、フレームワーク検出
- **HTML**: DOM構造解析、要素分類、属性抽出、階層関係
- **CSS**: セレクタ解析、プロパティ分類、スタイルルール抽出、インテリジェント分類
- **Markdown**: ヘッダー、コードブロック、リンク、画像、テーブル、タスクリスト、引用

## プログラム命名規則

### MCPツール命名
- **check_code_scale**: ファイル規模・複雑度チェック
- **analyze_code_structure**: コード構造解析・テーブル生成
- **extract_code_section**: 精密コードセクション抽出
- **list_files**: 高性能ファイル発見
- **search_content**: 正規表現コンテンツ検索
- **find_and_grep**: 二段階検索（ファイル発見→コンテンツ検索）
- **query_code**: tree-sitter クエリ実行
- **set_project_path**: プロジェクトルートパス設定

### CLIコマンド命名
- **tree-sitter-analyzer**: メインCLIエントリーポイント
- **tree-sitter-analyzer-mcp**: MCPサーバーエントリーポイント
- **list-files**: ファイル一覧CLI
- **search-content**: コンテンツ検索CLI
- **find-and-grep**: 検索・抽出CLI

### パッケージ命名例
- **tree_sitter_analyzer.core**: コアエンジン
- **tree_sitter_analyzer.mcp.tools**: MCPツール実装
- **tree_sitter_analyzer.languages**: 言語プラグイン
- **tree_sitter_analyzer.formatters**: 出力フォーマッター
- **tree_sitter_analyzer.cli.commands**: CLIコマンド実装
