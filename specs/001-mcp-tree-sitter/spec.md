# Feature Specification: Tree-sitter Analyzer MCP Server

**Feature Branch**: `001-mcp-tree-sitter`  
**Created**: 2025-10-12  
**Status**: Draft  
**Input**: User description: "既存のMCPサーバー機能の包括的な仕様 - Tree-sitter Analyzerの全MCPツール（check_code_scale、analyze_code_structure、extract_code_section、query_code、list_files、search_content、find_and_grep、set_project_path）とリソース（code_file、project_stats）の統合仕様"

## 関連仕様書

- **[002-language-abstraction-spec.md](../002-language-abstraction-spec.md)**: 言語処理の抽象化と拡張性に関する仕様。
- **[003-html-css-support-spec.md](../003-html-css-support-spec.md)**: HTML/CSSの特殊サポートに関する仕様。
- **[004-formatter-extension-spec.md](../004-formatter-extension-spec.md)**: フォーマッター拡張に関する仕様。
- **[005-implementation-plan.md](../005-implementation-plan.md)**: 実装計画とマイグレーション手順。

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - AI統合コード解析 (Priority: P1)

AI開発者（Claude Desktop、Cursor、Roo Codeユーザー）が、自然言語でコード解析タスクを実行し、大規模プロジェクトでも効率的に構造理解とコード抽出を行う。

**Why this priority**: AI統合はプロジェクトの核心的価値提案であり、従来のCLIツールとの差別化要因である。

**Independent Test**: MCPサーバーを起動し、単一のcheck_code_scaleコマンドでファイル解析を実行し、適切な解析戦略の推奨を受け取ることで完全にテスト可能。

**Acceptance Scenarios**:

1. **Given** AI開発者がClaude Desktopを使用している、**When** 大規模Javaファイルに対してcheck_code_scaleを実行する、**Then** ファイルサイズ、複雑度、推奨解析戦略が返される
2. **Given** プロジェクトルートが設定されている、**When** analyze_code_structureを実行する、**Then** クラス、メソッド、フィールドの構造化テーブルが生成される

---

### User Story 2 - 高性能ファイル検索・コンテンツ検索 (Priority: P2)

開発者が大規模プロジェクトで特定のファイルやコード要素を高速に発見し、プロジェクト境界内で安全に検索を実行する。

**Why this priority**: エンタープライズ環境での実用性を決定する基盤機能であり、セキュリティ制約も含む。

**Independent Test**: list_filesとsearch_contentツールを使用して、特定の拡張子のファイルを検索し、その中から特定のパターンを含むコードを発見できることで独立してテスト可能。

**Acceptance Scenarios**:

1. **Given** プロジェクトに複数言語のファイルが存在する、**When** list_filesで.javaファイルのみを検索する、**Then** Java ファイルのリストが高速に返される
2. **Given** 大規模プロジェクトが存在する、**When** search_contentで特定のメソッド名を検索する、**Then** 該当するコード箇所がコンテキスト付きで返される

---

### User Story 3 - 精密コード抽出・クエリ実行 (Priority: P3)

開発者が特定のコード範囲を正確に抽出し、Tree-sitterクエリを使用して構造化されたコード要素を取得する。

**Why this priority**: 高度な解析機能として、基本的な検索・構造解析の上に構築される付加価値機能。

**Independent Test**: extract_code_sectionで特定の行範囲を抽出し、query_codeで特定のコード要素（メソッド、クラスなど）を構造化して取得できることで独立してテスト可能。

**Acceptance Scenarios**:

1. **Given** 大規模なJavaScriptファイルが存在する、**When** extract_code_sectionで特定の関数部分を抽出する、**Then** 指定した行範囲のコードが正確に返される
2. **Given** TypeScriptファイルが存在する、**When** query_codeでメソッド定義を検索する、**Then** 構造化されたメソッド情報（名前、パラメータ、戻り値型）が返される

---

### User Story 4 - 統合ワークフロー・プロジェクト管理 (Priority: P4)

開発者がプロジェクト境界を設定し、複数のツールを組み合わせた複合的な解析ワークフローを実行する。

**Why this priority**: 個別ツールの組み合わせによる高度なワークフローは、基本機能が安定してから実装すべき機能。

**Independent Test**: set_project_pathでプロジェクトルートを設定し、find_and_grepで2段階検索（ファイル検索→コンテンツ検索）を実行できることで独立してテスト可能。

**Acceptance Scenarios**:

1. **Given** 複数のプロジェクトディレクトリが存在する、**When** set_project_pathで特定のプロジェクトを設定する、**Then** 以降のツール実行がそのプロジェクト境界内に制限される
2. **Given** プロジェクトルートが設定されている、**When** find_and_grepで特定の拡張子のファイル内から特定のパターンを検索する、**Then** ファイル検索とコンテンツ検索が統合された結果が返される

---

### Edge Cases

- 非常に大きなファイル（10MB以上）に対するcheck_code_scale実行時の適切な警告とトークン最適化戦略の提示
- プロジェクト境界外のファイルアクセス試行時のセキュリティエラーハンドリング
- 不正なTree-sitterクエリ実行時の適切なエラーメッセージ表示
- ネットワーク切断やファイルシステムエラー時の適切なフォールバック処理
- 同時実行される複数のMCPツール呼び出し時のリソース競合回避

### Error Handling Specifications

**ツール別エラーハンドリング動作**:

- **extract_code_section**: 存在しないファイルに対して例外を投げず、`{"success": false, "error": "file does not exist"}`形式のレスポンスを返す
- **list_files**: 存在しないディレクトリに対して`ValueError`を投げ、`error_handler.py`により`AnalysisError`にラップされる
- **search_content**: 存在しないファイルに対して`ValueError`を投げ、`error_handler.py`により`AnalysisError`にラップされる
- **analyze_code_structure**: ファイル解析エラー時は構造化されたエラーレスポンスを返す
- **query_code**: 不正なクエリに対して詳細なエラーメッセージを含む`AnalysisError`を投げる

**エラーレスポンス形式**:
- 成功時: `{"success": true, ...}`
- 失敗時: `{"success": false, "error": "詳細なエラーメッセージ", ...}`
- 例外時: `AnalysisError`例外（内部`ValueError`等がラップされる）

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: システムはModel Context Protocol (MCP) v1.0仕様に完全準拠したサーバーとして動作しなければならない
- **FR-002**: システムは8つの主要ツール（check_code_scale、analyze_code_structure、extract_code_section、query_code、list_files、search_content、find_and_grep、set_project_path）を提供しなければならない
- **FR-003**: システムは2つのリソースタイプ（code_file、project_stats）へのURIベースアクセスを提供しなければならない
- **FR-004**: システムはプロジェクト境界保護により、設定されたプロジェクトルート外へのファイルアクセスを防止しなければならない
- **FR-005**: システムはfd（ファイル検索）とripgrep（コンテンツ検索）を活用した高性能検索を提供しなければならない
- **FR-006**: システムはJava、JavaScript、TypeScript、Python、Markdownの5言語に対する完全なTree-sitter解析サポートを提供しなければならない
- **FR-007**: システムはファイルサイズに応じた適応的解析戦略（直接読み取り vs 構造解析）を自動選択しなければならない
- **FR-008**: システムはトークン制限を考慮した出力最適化（suppress_output、output_file）を提供しなければならない
- **FR-009**: システムは構造化されたエラーレスポンスと適切なログ記録を提供しなければならない
- **FR-010**: システムは非同期処理によりAIアシスタントとの効率的な統合を実現しなければならない

### Key Entities

- **MCPServer**: Model Context Protocolサーバーの実装、ツール管理、セキュリティ検証、プロジェクト境界管理を担当
- **AnalysisTool**: 各種解析ツールの基底クラス、共通インターフェース、エラーハンドリングを提供
- **SecurityValidator**: ファイルパス検証、プロジェクト境界チェック、安全性確保を担当
- **CodeElement**: Tree-sitter解析結果の統一表現、言語非依存の構造化データ
- **ProjectContext**: プロジェクトルート、言語設定、解析設定の管理

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: AI開発者が単一のMCPツール呼び出しで基本的なコード解析タスクを3秒以内に完了できる
- **SC-002**: システムが10,000ファイル規模のプロジェクトで検索・解析を5秒以内に実行できる
- **SC-003**: プロジェクト境界保護により、不正なファイルアクセス試行の100%を阻止できる
- **SC-004**: 大規模ファイル（1MB以上）に対する解析で適切なトークン最適化戦略が自動適用される
- **SC-005**: 5つのサポート言語すべてで構造解析の精度が95%以上を達成する
- **SC-006**: MCPプロトコル準拠により、Claude Desktop、Cursor、Roo Codeでの統合成功率が100%となる
- **SC-007**: エラー発生時に開発者が問題を特定・解決するための十分な情報が提供される
- **SC-008**: 複数ツールの組み合わせワークフローが単一ツール実行の2倍以内の時間で完了する

### Non-Functional Requirements

- **パフォーマンス**: 単一ツール実行は3秒以内、複合ワークフローは10秒以内
- **スケーラビリティ**: 10,000ファイル、100MB総サイズのプロジェクトまで対応
- **セキュリティ**: プロジェクト境界外アクセスの完全阻止、入力検証の徹底
- **可用性**: MCPサーバーの99.9%稼働率、適切なエラー回復機能
- **互換性**: MCP v1.0仕様準拠、主要AIプラットフォームとの統合保証

### Assumptions

- ユーザーはPython 3.10以上の環境でMCPサーバーを実行する
- プロジェクトファイルは標準的なUTF-8エンコーディングを使用する
- fd（ファイル検索）とripgrep（コンテンツ検索）がシステムにインストールされている
- AIアシスタントはMCPプロトコルv1.0に対応している
- 解析対象のコードファイルは構文的に有効である（パースエラーは適切にハンドリング）
