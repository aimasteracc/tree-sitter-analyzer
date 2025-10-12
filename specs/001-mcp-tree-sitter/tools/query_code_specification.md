# query_code ツール仕様書

**作成日**: 2025-10-12  
**バージョン**: 1.0.0  
**対象ツール**: `query_code` (QueryTool)  
**実装ファイル**: `tree_sitter_analyzer/mcp/tools/query_tool.py`

## 概要

`query_code`ツールは、tree-sitterクエリエンジンを使用してコードファイルから特定のコード要素を抽出するMCPツールです。事前定義されたクエリキーとカスタムクエリ文字列の両方をサポートし、フィルタリング、複数出力フォーマット、ファイル出力機能を提供します。

## 機能仕様

### 1. 基本機能

#### 1.1 クエリ実行方式
- **事前定義クエリ**: 言語別の標準クエリキー（`methods`, `class`, `functions`等）
- **カスタムクエリ**: tree-sitter構文による自由なクエリ文字列
- **言語自動検出**: ファイル拡張子による言語の自動判定
- **統合QueryService**: CLI/MCP共通のクエリ実行エンジン

#### 1.2 フィルタリング機能
- **名前フィルタ**: `name=main` による完全一致
- **パターンマッチ**: `name=~get*` によるワイルドカード検索
- **複合条件**: `name=~get*,public=true` による複数条件組み合わせ
- **属性フィルタ**: ノード属性による詳細フィルタリング

#### 1.3 出力フォーマット
- **json** (デフォルト): 完全な構造化データ
- **summary**: 要約形式（キャプチャ別グループ化）

#### 1.4 ファイル出力機能
- **自動拡張子検出**: JSON形式での自動保存
- **トークン最適化**: `suppress_output`による大容量結果対応
- **柔軟な命名**: カスタムファイル名またはデフォルト命名

### 2. 対応言語とクエリ

#### 2.1 サポート言語
- **Java**: `.java` - クラス、メソッド、フィールド、インターフェース
- **JavaScript**: `.js`, `.mjs`, `.jsx` - 関数、クラス、変数、エクスポート
- **TypeScript**: `.ts`, `.tsx`, `.d.ts` - 型定義、インターフェース、モジュール
- **Python**: `.py` - 関数、クラス、デコレータ、インポート
- **Markdown**: `.md` - ヘッダー、リンク、コードブロック

#### 2.2 事前定義クエリキー例
```
Java: class, methods, fields, interfaces, constructors
JavaScript: functions, classes, variables, exports, imports
TypeScript: interfaces, types, modules, declarations
Python: functions, classes, decorators, imports
Markdown: headers, links, code_blocks
```

### 3. セキュリティ機能

#### 3.1 プロジェクト境界保護
- **パス検証**: 絶対パス・相対パス両方の安全性確認
- **境界制限**: プロジェクトルート外へのアクセス防止
- **パストラバーサル防止**: `../`等の危険なパターンの検出

#### 3.2 入力検証
- **必須パラメータ**: file_path, query_key/query_string の存在確認
- **相互排他**: query_keyとquery_stringの同時指定防止
- **ファイル存在**: 対象ファイルの存在確認
- **言語サポート**: 対応言語の確認

## API仕様

### 入力パラメータ

```json
{
  "file_path": "string (必須)",
  "language": "string (オプション)",
  "query_key": "string (query_stringと相互排他)",
  "query_string": "string (query_keyと相互排他)",
  "filter": "string (オプション)",
  "output_format": "string (デフォルト: json)",
  "output_file": "string (オプション)",
  "suppress_output": "boolean (デフォルト: false)"
}
```

#### パラメータ詳細

| パラメータ | 型 | 必須 | 説明 |
|------------|----|----|------|
| `file_path` | string | ✓ | 解析対象ファイルパス（相対/絶対） |
| `language` | string | - | プログラミング言語（自動検出可能） |
| `query_key` | string | ※ | 事前定義クエリキー |
| `query_string` | string | ※ | カスタムtree-sitterクエリ |
| `filter` | string | - | フィルタ式（例: `name=main`） |
| `output_format` | string | - | 出力形式（`json`, `summary`） |
| `output_file` | string | - | 出力ファイル名 |
| `suppress_output` | boolean | - | 出力抑制（ファイル出力時） |

※ `query_key`または`query_string`のいずれか必須

### 出力形式

#### JSON形式（デフォルト）
```json
{
  "success": true,
  "results": [
    {
      "capture_name": "method",
      "node_type": "method_declaration",
      "start_line": 10,
      "end_line": 15,
      "start_column": 4,
      "end_column": 5,
      "content": "public void example() {\n    // method body\n}"
    }
  ],
  "count": 1,
  "file_path": "src/Example.java",
  "language": "java",
  "query": "methods"
}
```

#### Summary形式
```json
{
  "success": true,
  "query_type": "methods",
  "language": "java",
  "total_count": 3,
  "captures": {
    "method": {
      "count": 3,
      "items": [
        {
          "name": "example",
          "line_range": "10-15",
          "node_type": "method_declaration"
        }
      ]
    }
  }
}
```

#### ファイル出力時（suppress_output=true）
```json
{
  "success": true,
  "count": 3,
  "file_path": "src/Example.java",
  "language": "java",
  "query": "methods",
  "output_file_path": "/project/Example_query_methods.json",
  "file_saved": true
}
```

### エラー応答

```json
{
  "success": false,
  "error": "エラーメッセージ",
  "file_path": "src/Example.java",
  "language": "java"
}
```

## 使用例

### 1. 事前定義クエリの使用

```json
{
  "file_path": "src/Example.java",
  "query_key": "methods",
  "output_format": "summary"
}
```

### 2. カスタムクエリの使用

```json
{
  "file_path": "src/Component.jsx",
  "query_string": "(function_declaration name: (identifier) @func_name)",
  "filter": "name=~handle*"
}
```

### 3. ファイル出力とトークン最適化

```json
{
  "file_path": "src/LargeFile.py",
  "query_key": "functions",
  "output_file": "functions_analysis",
  "suppress_output": true
}
```

## パフォーマンス特性

### 1. 処理速度
- **小規模ファイル** (< 1MB): < 100ms
- **中規模ファイル** (1-10MB): < 500ms  
- **大規模ファイル** (> 10MB): < 2秒

### 2. メモリ使用量
- **パーサー**: ファイルサイズの2-3倍
- **結果保持**: 抽出要素数に比例
- **最適化**: suppress_outputによる大幅削減

### 3. トークン効率
- **通常出力**: 結果数 × 平均200トークン
- **Summary形式**: 通常の30-50%削減
- **suppress_output**: 90%以上削減

## エラーハンドリング

### 1. 入力検証エラー
- **必須パラメータ不足**: `file_path is required`
- **相互排他違反**: `Cannot provide both query_key and query_string`
- **無効なパス**: `Invalid or unsafe file path`

### 2. ファイル処理エラー
- **ファイル不存在**: `File not found: {path}`
- **言語検出失敗**: `Could not detect language for file`
- **パース失敗**: `Failed to parse file`

### 3. クエリ実行エラー
- **クエリ不存在**: `Query '{key}' not found for language '{lang}'`
- **構文エラー**: `Invalid query syntax`
- **実行失敗**: `Query execution failed`

## セキュリティ考慮事項

### 1. パス検証
- プロジェクトルート外アクセスの完全防止
- シンボリックリンク追跡の制限
- パストラバーサル攻撃の検出

### 2. リソース制限
- ファイルサイズ制限（設定可能）
- クエリ実行時間制限
- メモリ使用量監視

### 3. 情報漏洩防止
- エラーメッセージでのパス情報制限
- ログ出力の適切な制御
- 機密情報の除外

## 統合テスト要件

### 1. 基本機能テスト
- [ ] 全対応言語での事前定義クエリ実行
- [ ] カスタムクエリの正常実行
- [ ] フィルタリング機能の動作確認
- [ ] 出力フォーマットの正確性

### 2. エラーハンドリングテスト
- [ ] 無効な入力パラメータの適切な処理
- [ ] ファイル不存在時の適切なエラー
- [ ] セキュリティ違反の適切な拒否

### 3. パフォーマンステスト
- [ ] 大規模ファイルでの処理時間確認
- [ ] メモリ使用量の適切性
- [ ] トークン最適化の効果測定

### 4. 統合テスト
- [ ] 他ツールとの連携動作
- [ ] ファイル出力機能の完全性
- [ ] エンドツーエンドワークフローの確認

## 実装品質指標

### 1. コードカバレッジ
- **目標**: 95%以上
- **重点**: エラーハンドリング、セキュリティ機能

### 2. パフォーマンス指標
- **応答時間**: 95%のリクエストが2秒以内
- **メモリ効率**: ファイルサイズの5倍以下
- **トークン効率**: suppress_output時90%削減

### 3. 信頼性指標
- **エラー率**: 0.1%以下
- **セキュリティ違反**: 0件
- **データ整合性**: 100%

---

**更新履歴**:
- 2025-10-12: 初版作成（v1.0.0）