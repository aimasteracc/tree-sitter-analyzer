# Tree-sitter Analyzer MCP Server - 用語集

**Version**: 1.0.0  
**Date**: 2025-10-12  
**Purpose**: プロジェクト全体で使用される技術用語の統一定義

## 核心概念

### MCP (Model Context Protocol)
AIアシスタントとツール間の標準通信プロトコル。Claude Desktop、Cursor、Roo Codeなどで使用される。

### Tree-sitter
構文解析ライブラリ。増分解析と多言語サポートを提供し、コードの構造的理解を可能にする。

### コード解析 (Code Analysis)
Tree-sitterを使用したソースコードの構文・構造解析の総称。静的解析の一種。

### 構造解析 (Structure Analysis)
コードの階層構造（クラス、メソッド、フィールド等）を抽出・分析する処理。

## パフォーマンス指標

### 高速処理
- **単一ツール実行**: 3秒以内
- **複合ワークフロー**: 10秒以内
- **大規模プロジェクト**: 1,000ファイル、100MB総サイズまで

### 効率的処理
- **メモリ使用量**: 通常<200MB、ピーク<500MB
- **同時処理**: 20+同時操作サポート
- **キャッシュ効率**: 90%以上のキャッシュヒット率

## セキュリティ用語

### プロジェクト境界 (Project Boundary)
設定されたプロジェクトルート外へのファイルアクセスを防止するセキュリティ機能。

### 境界保護 (Boundary Protection)
パストラバーサル攻撃やディレクトリ脱出を防ぐ多層防御システム。

### セキュリティ検証 (Security Validation)
入力パラメータの検証、パス正規化、権限チェックを含む包括的検証プロセス。

## ツール分類

### 基盤ツール
- **check_code_scale**: ファイル規模評価・解析戦略推奨
- **set_project_path**: プロジェクト境界設定

### 検索ツール
- **list_files**: fd統合高速ファイル検索
- **search_content**: ripgrep統合コンテンツ検索
- **find_and_grep**: 2段階統合検索

### 解析ツール
- **analyze_code_structure**: 構造解析・テーブル生成
- **extract_code_section**: 部分コード抽出
- **query_code**: Tree-sitterクエリ実行

## 出力最適化

### Token最適化
LLMのトークン制限に対応した出力制御機能群。

- **suppress_output**: 詳細出力の抑制
- **summary_only**: 要約のみ出力
- **total_only**: 総数のみ出力
- **group_by_file**: ファイル別グループ化

### ファイル出力
大規模結果の外部ファイル保存機能。JSON、CSV、Markdown形式対応。

## エラーハンドリング

### 構造化エラーレスポンス
```json
{
  "success": false,
  "error": "詳細なエラーメッセージ",
  "error_type": "AnalysisError"
}
```

### 例外ベースエラー
`AnalysisError`による統一例外処理。内部例外のラッピングと適切なログ記録。

## 品質指標

### テストカバレッジ
- **ユニットテスト**: 95%以上
- **統合テスト**: 25/25成功
- **エンドツーエンドテスト**: 8/8成功

### 互換性
- **MCP準拠**: Model Context Protocol v1.0完全準拠
- **Python**: 3.10, 3.11, 3.12, 3.13対応
- **プラットフォーム**: Windows, Linux, macOS

## 略語・頭字語

| 略語 | 正式名称 | 説明 |
|------|----------|------|
| MCP | Model Context Protocol | AI統合プロトコル |
| AST | Abstract Syntax Tree | 抽象構文木 |
| CLI | Command Line Interface | コマンドライン界面 |
| API | Application Programming Interface | アプリケーション間界面 |
| URI | Uniform Resource Identifier | 統一資源識別子 |
| JSON | JavaScript Object Notation | データ交換形式 |
| CSV | Comma-Separated Values | カンマ区切り値 |
| UTF-8 | 8-bit Unicode Transformation Format | 文字エンコーディング |
| ReDoS | Regular Expression Denial of Service | 正規表現DoS攻撃 |

## バージョン履歴

- **v1.0.0** (2025-10-12): 初版作成、基本用語定義