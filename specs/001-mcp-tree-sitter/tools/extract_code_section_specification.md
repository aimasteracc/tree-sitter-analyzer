# extract_code_section ツール仕様書

**作成日**: 2025-10-12  
**バージョン**: 1.0.0  
**対象ツール**: `extract_code_section` (ReadPartialTool)  
**実装ファイル**: `tree_sitter_analyzer/mcp/tools/read_partial_tool.py`

## 概要

`extract_code_section`ツールは、コードファイルから指定された行・列範囲の部分的なコンテンツを抽出するMCPツールです。精密なコード抽出機能を提供し、大規模ファイルの特定部分のみを効率的に取得できます。

## 機能仕様

### 1. 基本機能

#### 1.1 精密範囲指定
- **行範囲**: 1ベースの開始行・終了行指定
- **列範囲**: 0ベースの開始列・終了列指定（オプション）
- **部分抽出**: 指定範囲のみの効率的な読み込み
- **柔軟性**: 終了行未指定時はファイル末尾まで読み込み

#### 1.2 複数出力フォーマット
- **text** (デフォルト): CLI互換のヘッダー付きフォーマット
- **json**: 構造化されたJSONデータ
- **raw**: 抽出されたコンテンツのみ（メタデータなし）

#### 1.3 ファイル出力機能
- **自動拡張子検出**: コンテンツ形式に基づく拡張子自動設定
- **トークン最適化**: `suppress_output`による大容量ファイル対応
- **柔軟な命名**: カスタムファイル名またはデフォルト命名

### 2. セキュリティ機能

#### 2.1 プロジェクト境界保護
- **パス検証**: 絶対パス・相対パス両方の安全性確認
- **境界制限**: プロジェクトルート外へのアクセス防止
- **パストラバーサル防止**: `../`等の危険なパターンの検出

#### 2.2 入力検証
- **必須パラメータ**: file_path, start_line の存在確認
- **数値範囲**: 行番号・列番号の妥当性検証
- **ファイル存在**: 対象ファイルの存在確認

## API仕様

### 入力パラメータ

```json
{
  "file_path": "string (必須)",
  "start_line": "integer (必須, >= 1)",
  "end_line": "integer (オプション, >= start_line)",
  "start_column": "integer (オプション, >= 0)",
  "end_column": "integer (オプション, >= 0)",
  "format": "string (オプション, enum: [text, json, raw], default: text)",
  "output_file": "string (オプション)",
  "suppress_output": "boolean (オプション, default: false)"
}
```

### 出力フォーマット

#### 基本レスポンス
```json
{
  "file_path": "string",
  "range": {
    "start_line": "integer",
    "end_line": "integer|null",
    "start_column": "integer|null",
    "end_column": "integer|null"
  },
  "content_length": "integer",
  "partial_content_result": "string (suppress_output=false時のみ)",
  "output_file_path": "string (output_file指定時)",
  "file_saved": "boolean (output_file指定時)"
}
```

#### フォーマット別出力例

**text フォーマット**:
```
--- Partial Read Result ---
File: example.py
Range: Line 10-20
Characters read: 245
{
  "file_path": "example.py",
  "range": {...},
  "content": "extracted code content",
  "content_length": 245
}
```

**json フォーマット**:
```json
{
  "file_path": "example.py",
  "range": {
    "start_line": 10,
    "end_line": 20,
    "start_column": null,
    "end_column": null
  },
  "content": "extracted code content",
  "content_length": 245
}
```

**raw フォーマット**:
```
extracted code content
```

## 実装詳細

### 1. クラス構造

```python
class ReadPartialTool(BaseMCPTool):
    def __init__(self, project_root: str = None)
    def get_tool_schema(self) -> dict[str, Any]
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]
    def _read_file_partial(self, ...) -> str | None
    def validate_arguments(self, arguments: dict[str, Any]) -> bool
    def get_tool_definition(self) -> dict[str, Any]
```

### 2. 依存関係

- **file_handler.read_file_partial**: 実際のファイル読み込み処理
- **FileOutputManager**: ファイル出力機能
- **BaseMCPTool**: 共通MCP機能（セキュリティ、パス解決）
- **PerformanceMonitor**: パフォーマンス測定

### 3. エラーハンドリング

#### 3.1 検証エラー
- `ValueError`: 必須パラメータ不足、無効な範囲指定
- `FileNotFoundError`: ファイル不存在（内部でValueErrorに変換）
- `SecurityError`: プロジェクト境界外アクセス試行

#### 3.2 実行時エラー
- `RuntimeError`: ファイル読み込み失敗
- `IOError`: ファイル出力失敗（非致命的、エラー情報を結果に含める）

## パフォーマンス特性

### 1. 効率性
- **部分読み込み**: 指定範囲のみの読み込みによるメモリ効率
- **ストリーミング**: 大容量ファイルでも一定メモリ使用量
- **キャッシュ**: 同一ファイルの複数範囲アクセス時の最適化

### 2. スケーラビリティ
- **大容量ファイル**: GBサイズファイルでも安定動作
- **高精度抽出**: 1文字単位での精密な範囲指定
- **並列処理**: 複数ファイルの同時処理対応

## 使用例

### 1. 基本的な行範囲抽出
```json
{
  "file_path": "src/main.py",
  "start_line": 50,
  "end_line": 100
}
```

### 2. 列範囲を含む精密抽出
```json
{
  "file_path": "src/utils.js",
  "start_line": 25,
  "end_line": 25,
  "start_column": 10,
  "end_column": 50
}
```

### 3. ファイル出力付きraw抽出
```json
{
  "file_path": "config/settings.json",
  "start_line": 1,
  "end_line": 20,
  "format": "raw",
  "output_file": "extracted_config",
  "suppress_output": true
}
```

### 4. 大容量ファイルのトークン最適化
```json
{
  "file_path": "data/large_dataset.py",
  "start_line": 1000,
  "end_line": 2000,
  "format": "json",
  "output_file": "dataset_section",
  "suppress_output": true
}
```

## テスト要件

### 1. 機能テスト
- [ ] 基本的な行範囲抽出
- [ ] 列範囲を含む精密抽出
- [ ] 3つの出力フォーマット検証
- [ ] ファイル出力機能
- [ ] トークン最適化（suppress_output）

### 2. エラーハンドリングテスト
- [ ] 必須パラメータ不足
- [ ] 無効な範囲指定
- [ ] 存在しないファイル
- [ ] プロジェクト境界外アクセス

### 3. パフォーマンステスト
- [ ] 大容量ファイル（>10MB）での動作
- [ ] 精密範囲指定の正確性
- [ ] メモリ使用量の効率性

### 4. 統合テスト
- [ ] 他のツールとの連携
- [ ] 複数フォーマットでの一貫性
- [ ] セキュリティ境界の確認

## 品質基準

### 1. 精度要件
- **範囲指定精度**: 100%（指定された範囲の完全一致）
- **文字エンコーディング**: UTF-8完全対応
- **改行コード**: クロスプラットフォーム対応

### 2. パフォーマンス要件
- **応答時間**: 通常ファイル（<1MB）で1秒以内
- **メモリ効率**: ファイルサイズに比例しない一定メモリ使用
- **スループット**: 並列処理時の性能劣化最小化

### 3. 信頼性要件
- **エラー回復**: 部分的失敗時の適切なエラー報告
- **データ整合性**: 抽出内容の完全性保証
- **セキュリティ**: プロジェクト境界の厳格な保護

## 今後の拡張予定

### 1. 機能拡張
- **構文認識抽出**: Tree-sitterを活用した構文単位での抽出
- **差分抽出**: 複数バージョン間の差分部分抽出
- **圧縮出力**: 大容量抽出結果の圧縮保存

### 2. パフォーマンス改善
- **インデックス化**: 頻繁にアクセスされるファイルのインデックス作成
- **並列化**: 複数範囲の並列抽出
- **ストリーミング出力**: リアルタイム抽出結果配信

---

**注意**: この仕様書は実装済み機能の文書化であり、User Story 2「高度な解析ツール」の一部として位置づけられます。