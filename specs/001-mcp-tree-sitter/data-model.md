# Data Model: Tree-sitter Analyzer MCP Server

**Feature**: Tree-sitter Analyzer MCP Server  
**Date**: 2025-10-12  
**Phase**: 1 - Data Model Design

## 関連仕様書

- **[002-language-abstraction-spec.md](../002-language-abstraction-spec.md)**: `ILanguagePlugin` と `LanguagePluginFactory` による言語処理の抽象化。
- **[003-html-css-support-spec.md](../003-html-css-support-spec.md)**: `MarkupElement` と `StyleElement` モデルの導入。
- **[004-formatter-extension-spec.md](../004-formatter-extension-spec.md)**: `IFormatter` と `FormatterRegistry` によるフォーマッター拡張。

---

## 概要

Tree-sitter Analyzer MCPサーバーのデータモデルは、MCPプロトコル準拠のツールとリソースを統一的に管理し、AI統合環境での効率的なコード解析を実現する。

## 核心エンティティ

### 1. MCPServer
**役割**: MCPプロトコルサーバーの中核実装  
**責任**: ツール管理、リソース提供、セキュリティ制御、プロジェクト境界管理

**属性**:
- `project_root: Path` - プロジェクトルートディレクトリ
- `security_validator: SecurityValidator` - セキュリティ検証インスタンス
- `tools: Dict[str, BaseMCPTool]` - 登録済みMCPツール
- `resources: Dict[str, MCPResource]` - 利用可能リソース
- `is_initialized: bool` - 初期化状態

**関係**:
- 1対多: MCPTool（8つのツール管理）
- 1対多: MCPResource（2つのリソース管理）
- 1対1: SecurityValidator（セキュリティ制御）

### 2. BaseMCPTool
**役割**: 全MCPツールの基底クラス  
**責任**: 共通インターフェース、エラーハンドリング、実行制御

**属性**:
- `name: str` - ツール名
- `description: str` - ツール説明
- `project_root: Path` - プロジェクト境界
- `input_schema: Dict[str, Any]` - 入力スキーマ定義

**メソッド**:
- `execute(arguments: Dict[str, Any]) -> Dict[str, Any]` - ツール実行
- `get_tool_definition() -> Dict[str, Any]` - MCP定義取得
- `validate_input(arguments: Dict[str, Any]) -> bool` - 入力検証

**継承関係**:
```
BaseMCPTool
├── AnalyzeScaleTool (check_code_scale)
├── TableFormatTool (analyze_code_structure)
├── ReadPartialTool (extract_code_section)
├── QueryTool (query_code)
├── ListFilesTool (list_files)
├── SearchContentTool (search_content)
└── FindAndGrepTool (find_and_grep)
```

### 3. SecurityValidator
**役割**: セキュリティ制約の実装と検証  
**責任**: ファイルパス検証、プロジェクト境界保護、アクセス制御

**属性**:
- `project_root: Path` - 許可されたプロジェクト境界
- `allowed_extensions: Set[str]` - 許可ファイル拡張子
- `blocked_paths: Set[str]` - ブロック対象パス

**メソッド**:
- `validate_file_path(file_path: str) -> Tuple[bool, str]` - ファイルパス検証
- `is_within_project(path: Path) -> bool` - プロジェクト境界チェック
- `sanitize_path(path: str) -> Path` - パス正規化

### 4. CodeElement
**役割**: Tree-sitter解析結果の統一表現  
**責任**: 言語非依存の構造化データ表現、メタデータ管理

**属性**:
- `element_type: str` - 要素タイプ（class、method、field等）
- `name: str` - 要素名
- `start_line: int` - 開始行
- `end_line: int` - 終了行
- `start_column: int` - 開始列
- `end_column: int` - 終了列
- `language: str` - プログラミング言語
- `metadata: Dict[str, Any]` - 言語固有メタデータ

**状態遷移**:
```
Raw Text → Tree-sitter Parse → CodeElement → Formatted Output
```

### 5. ProjectContext
**役割**: プロジェクト設定とコンテキスト管理  
**責任**: プロジェクト境界、言語設定、解析設定の統合管理

**属性**:
- `root_path: Path` - プロジェクトルート
- `supported_languages: Set[str]` - サポート言語
- `analysis_config: Dict[str, Any]` - 解析設定
- `cache_enabled: bool` - キャッシュ有効性
- `performance_mode: str` - パフォーマンスモード

## データフロー

### 1. ツール実行フロー
```
AI Request → MCP Server → Security Validation → Tool Execution → Result Processing → AI Response
```

**詳細ステップ**:
1. **リクエスト受信**: MCPプロトコル経由でツール呼び出し
2. **セキュリティ検証**: ファイルパス、パラメータの安全性確認
3. **ツール実行**: 対応するMCPツールの実行
4. **結果処理**: 出力形式変換、トークン最適化
5. **レスポンス送信**: 構造化されたJSON応答

### 2. リソースアクセスフロー
```
URI Request → Resource Resolution → Security Check → Content Retrieval → Response
```

**リソースタイプ**:
- `code://file/{file_path}` - ファイル内容アクセス
- `code://stats/{stats_type}` - プロジェクト統計アクセス

### 3. エラーハンドリングフロー
```
Error Detection → Error Classification → Structured Response → Logging
```

## 検証ルール

### 1. ファイルパス検証
```python
def validate_file_path(file_path: str) -> Tuple[bool, str]:
    """
    ファイルパスの安全性を検証
    
    検証項目:
    - プロジェクト境界内であること
    - 存在するファイルであること
    - 読み取り権限があること
    - 許可された拡張子であること
    """
```

### 2. 入力パラメータ検証
```python
def validate_input(arguments: Dict[str, Any]) -> bool:
    """
    ツール入力パラメータの検証
    
    検証項目:
    - 必須パラメータの存在
    - データ型の正確性
    - 値の範囲チェック
    - 形式の妥当性
    """
```

### 3. 出力形式検証
```python
def validate_output(result: Dict[str, Any]) -> bool:
    """
    ツール出力の検証
    
    検証項目:
    - MCPプロトコル準拠
    - JSON形式の妥当性
    - 必須フィールドの存在
    - データ整合性
    """
```

## パフォーマンス考慮事項

### 1. メモリ管理
- **大規模ファイル**: 段階的読み込み、部分処理
- **キャッシュ戦略**: 解析結果の効率的キャッシュ
- **ガベージコレクション**: 適切なリソース解放

### 2. 並行処理
- **非同期実行**: asyncio基盤の並行ツール実行
- **リソース競合**: ファイルアクセスの排他制御
- **スレッドセーフ**: 共有状態の安全な管理

### 3. スケーラビリティ
- **プロジェクトサイズ**: 10,000ファイルまで対応
- **同時接続**: 複数AI統合環境からの同時アクセス
- **レスポンス時間**: 3秒以内の応答保証

## セキュリティ制約

### 1. アクセス制御
- **プロジェクト境界**: 設定されたルート外へのアクセス禁止
- **ファイル権限**: 読み取り専用アクセス
- **パストラバーサル**: ディレクトリトラバーサル攻撃防止

### 2. 入力検証
- **SQLインジェクション**: 該当なし（ファイルベース）
- **コマンドインジェクション**: 外部コマンド実行時の検証
- **パス操作**: 悪意のあるパス操作の防止

### 3. 監査ログ
- **アクセスログ**: 全ファイルアクセスの記録
- **エラーログ**: セキュリティ違反の詳細記録
- **パフォーマンスログ**: 実行時間とリソース使用量

## 拡張性設計

### 1. 新言語サポート
- **プラグインアーキテクチャ**: 言語固有プラグインの追加
- **統一インターフェース**: CodeElementによる言語非依存表現
- **後方互換性**: 既存機能への影響なし

### 2. 新ツール追加
- **BaseMCPTool継承**: 標準インターフェース準拠
- **自動登録**: 動的ツール発見と登録
- **設定管理**: ツール固有設定の管理

### 3. 新リソースタイプ
- **URI拡張**: 新しいリソースURI形式
- **アクセスパターン**: 統一されたアクセス制御
- **キャッシュ戦略**: リソース固有キャッシュ

この統一データモデルにより、Tree-sitter Analyzer MCPサーバーは一貫性のある、拡張可能で、セキュアなコード解析プラットフォームを提供する。