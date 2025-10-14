# MCPリソース仕様書

**作成日**: 2025-10-12  
**バージョン**: 1.0.0  
**対象リソース**: `code_file`, `project_stats`  
**実装ファイル**: `tree_sitter_analyzer/mcp/resources/`

## 概要

MCPリソースは、Model Context Protocolを通じてコードファイルとプロジェクト統計情報への動的アクセスを提供します。URIベースの識別システムにより、クライアントは必要な情報を効率的に取得できます。2つの主要リソース（`code_file`、`project_stats`）が、ファイル内容アクセスとプロジェクト分析データの提供を担当します。

## リソース一覧

### 1. code_file リソース
- **目的**: コードファイル内容への動的アクセス
- **URI形式**: `code://file/{file_path}`
- **実装**: `CodeFileResource`

### 2. project_stats リソース
- **目的**: プロジェクト統計・分析データの提供
- **URI形式**: `code://stats/{stats_type}`
- **実装**: `ProjectStatsResource`

## code_file リソース仕様

### 1. 基本機能

#### 1.1 ファイルアクセス機能
- **動的読み取り**: URI指定によるファイル内容の即座取得
- **エンコーディング検出**: 自動文字エンコーディング判定
- **安全な読み取り**: エラーハンドリングと例外処理
- **パス検証**: セキュリティを考慮したパス検証

#### 1.2 URI処理
- **パターンマッチング**: 正規表現による厳密なURI検証
- **パス抽出**: URIからファイルパスの安全な抽出
- **形式検証**: URI形式の妥当性確認

### 2. URI仕様

#### 2.1 URI形式
```
code://file/{file_path}
```

#### 2.2 URI例
```
code://file/src/main/java/Example.java
code://file/scripts/helper.py
code://file/test.js
code://file/docs/README.md
```

#### 2.3 パス制約
- **相対パス**: プロジェクトルートからの相対パス
- **パストラバーサル禁止**: `..`を含むパス不可
- **null文字禁止**: `\x00`文字の使用不可
- **非空制約**: 空文字列パス不可

### 3. 実装詳細

#### 3.1 クラス構造
```python
class CodeFileResource:
    def __init__(self) -> None
    def get_resource_info(self) -> dict[str, Any]
    def matches_uri(self, uri: str) -> bool
    def _extract_file_path(self, uri: str) -> str
    def _validate_file_path(self, file_path: str) -> None
    async def _read_file_content(self, file_path: str) -> str
    async def read_resource(self, uri: str) -> str
```

#### 3.2 セキュリティ検証
```python
def _validate_file_path(self, file_path: str) -> None:
    # 空パスチェック
    if not file_path:
        raise ValueError("File path cannot be empty")
    
    # null文字チェック
    if "\x00" in file_path:
        raise ValueError("File path contains null bytes")
    
    # パストラバーサルチェック
    if ".." in file_path:
        raise ValueError(f"Path traversal not allowed: {file_path}")
```

#### 3.3 エンコーディング処理
```python
async def _read_file_content(self, file_path: str) -> str:
    # encoding_utilsを使用した安全な読み取り
    content, encoding = read_file_safe(file_path)
    return content
```

### 4. エラーハンドリング

#### 4.1 エラー種別

| エラー種別 | 条件 | 例外型 |
|------------|------|--------|
| URI形式エラー | 無効なURI形式 | ValueError |
| パス検証エラー | 危険なパス | ValueError |
| ファイル不存在 | ファイルが存在しない | FileNotFoundError |
| 権限エラー | 読み取り権限なし | PermissionError |
| OS エラー | その他のOSエラー | OSError |

#### 4.2 エラーレスポンス例
```python
# URI形式エラー
ValueError("Invalid URI format: invalid://uri")

# パストラバーサルエラー  
ValueError("Path traversal not allowed: ../../../etc/passwd")

# ファイル不存在エラー
FileNotFoundError("File not found: nonexistent.py")
```

### 5. 使用例

#### 5.1 基本的な使用例
```python
# リソースインスタンス作成
resource = CodeFileResource()

# ファイル内容読み取り
content = await resource.read_resource("code://file/src/main.py")
```

#### 5.2 URI検証例
```python
# 有効なURI
assert resource.matches_uri("code://file/src/example.java")

# 無効なURI
assert not resource.matches_uri("invalid://file/example.java")
```

## project_stats リソース仕様

### 1. 基本機能

#### 1.1 統計生成機能
- **概要統計**: プロジェクト全体の基本情報
- **言語統計**: 言語別ファイル・行数・割合
- **複雑度統計**: コード複雑度メトリクス
- **ファイル統計**: ファイル別詳細情報

#### 1.2 動的分析
- **リアルタイム分析**: 要求時の最新データ生成
- **言語検出**: 自動言語判定とサポート確認
- **メトリクス計算**: 複雑度・サイズ・更新日時の算出

### 2. URI仕様

#### 2.1 URI形式
```
code://stats/{stats_type}
```

#### 2.2 サポート統計種別

| 統計種別 | 説明 | URI例 |
|----------|------|-------|
| `overview` | プロジェクト概要 | `code://stats/overview` |
| `languages` | 言語別統計 | `code://stats/languages` |
| `complexity` | 複雑度統計 | `code://stats/complexity` |
| `files` | ファイル別統計 | `code://stats/files` |

### 3. 出力仕様

#### 3.1 overview統計
```json
{
  "total_files": 150,
  "total_lines": 12500,
  "languages": ["java", "python", "javascript"],
  "project_path": "/path/to/project",
  "last_updated": "2025-10-12T13:00:00.000Z"
}
```

#### 3.2 languages統計
```json
{
  "languages": [
    {
      "name": "java",
      "file_count": 45,
      "line_count": 8500,
      "percentage": 68.0
    },
    {
      "name": "python", 
      "file_count": 25,
      "line_count": 3000,
      "percentage": 24.0
    }
  ],
  "total_languages": 2,
  "last_updated": "2025-10-12T13:00:00.000Z"
}
```

#### 3.3 complexity統計
```json
{
  "average_complexity": 12.5,
  "max_complexity": 45,
  "total_files_analyzed": 70,
  "files_by_complexity": [
    {
      "file": "src/complex/Service.java",
      "language": "java",
      "complexity": 45
    }
  ],
  "last_updated": "2025-10-12T13:00:00.000Z"
}
```

#### 3.4 files統計
```json
{
  "files": [
    {
      "path": "src/main/Service.java",
      "language": "java",
      "line_count": 250,
      "size_bytes": 8500,
      "modified": "2025-10-12T10:30:00.000Z"
    }
  ],
  "total_count": 150,
  "last_updated": "2025-10-12T13:00:00.000Z"
}
```

### 4. 実装詳細

#### 4.1 クラス構造
```python
class ProjectStatsResource:
    def __init__(self) -> None
    def set_project_path(self, project_path: str) -> None
    def get_resource_info(self) -> dict[str, Any]
    def matches_uri(self, uri: str) -> bool
    def _extract_stats_type(self, uri: str) -> str
    def _validate_project_path(self) -> None
    async def _generate_overview_stats(self) -> dict[str, Any]
    async def _generate_languages_stats(self) -> dict[str, Any]
    async def _generate_complexity_stats(self) -> dict[str, Any]
    async def _generate_files_stats(self) -> dict[str, Any]
    async def read_resource(self, uri: str) -> str
```

#### 4.2 プロジェクトパス管理
```python
def set_project_path(self, project_path: str) -> None:
    if not isinstance(project_path, str):
        raise TypeError("Project path must be a string")
    if not project_path:
        raise ValueError("Project path cannot be empty")
    self._project_path = project_path
```

#### 4.3 言語検出統合
```python
def _is_supported_code_file(self, file_path: Path) -> bool:
    try:
        language = detect_language_from_file(str(file_path))
        return is_language_supported(language)
    except Exception:
        return False
```

### 5. パフォーマンス特性

#### 5.1 実行時間目標
- **overview**: < 2秒（中規模プロジェクト）
- **languages**: < 3秒（詳細分析）
- **complexity**: < 10秒（複雑度計算）
- **files**: < 5秒（ファイル情報収集）

#### 5.2 メモリ効率
- **ストリーミング処理**: 大規模プロジェクト対応
- **段階的分析**: 必要な統計のみ生成
- **キャッシュ戦略**: 分析結果の効率的管理

### 6. エラーハンドリング

#### 6.1 エラー種別

| エラー種別 | 条件 | 例外型 |
|------------|------|--------|
| URI形式エラー | 無効なURI | ValueError |
| 統計種別エラー | 未サポート種別 | ValueError |
| プロジェクトパスエラー | パス未設定 | ValueError |
| ディレクトリエラー | 存在しないパス | FileNotFoundError |

#### 6.2 エラーレスポンス例
```python
# 未サポート統計種別
ValueError("Unsupported statistics type: invalid. Supported types: overview, languages, complexity, files")

# プロジェクトパス未設定
ValueError("Project path not set. Call set_project_path() first.")
```

## 統合仕様

### 1. MCPサーバー統合

#### 1.1 リソース登録
```python
# server.pyでの統合
@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    resources = []
    
    # code_file リソース
    code_file_info = self.code_file_resource.get_resource_info()
    resources.append(Resource(
        uri=code_file_info["uri_template"],
        name=code_file_info["name"],
        description=code_file_info["description"],
        mimeType=code_file_info["mime_type"]
    ))
    
    # project_stats リソース
    stats_info = self.project_stats_resource.get_resource_info()
    resources.append(Resource(
        uri=stats_info["uri_template"],
        name=stats_info["name"], 
        description=stats_info["description"],
        mimeType=stats_info["mime_type"]
    ))
    
    return resources
```

#### 1.2 リソースアクセス処理
```python
@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    if self.code_file_resource.matches_uri(uri):
        return await self.code_file_resource.read_resource(uri)
    elif self.project_stats_resource.matches_uri(uri):
        return await self.project_stats_resource.read_resource(uri)
    else:
        raise ValueError(f"Unknown resource URI: {uri}")
```

### 2. セキュリティ統合

#### 2.1 境界保護
- **プロジェクト境界**: set_project_pathによる動的境界設定
- **パス検証**: SecurityValidatorとの連携
- **アクセス制御**: 境界内ファイルのみアクセス許可

#### 2.2 権限管理
- **読み取り専用**: ファイル内容の読み取りのみ許可
- **メタデータアクセス**: ファイル統計情報の安全な提供
- **エラー情報制限**: セキュリティ情報の漏洩防止

### 3. ツール連携

#### 3.1 ワークフロー統合
```
1. set_project_path（境界設定）
   ↓
2. code://stats/overview（概要把握）
   ↓
3. find_and_grep（詳細検索）
   ↓
4. code://file/{found_file}（ファイル内容確認）
```

#### 3.2 相互補完
- **リソース→ツール**: 統計情報からツール実行パラメータ生成
- **ツール→リソース**: 検索結果からファイル内容アクセス
- **動的更新**: プロジェクト変更時の統計自動更新

## テスト仕様

### 1. 単体テスト

#### 1.1 code_fileリソーステスト
- **URI処理**: 正常・異常パターンの検証
- **ファイル読み取り**: エンコーディング・エラー処理
- **セキュリティ**: パストラバーサル・権限テスト

#### 1.2 project_statsリソーステスト
- **統計生成**: 各統計種別の正確性検証
- **言語検出**: 多言語プロジェクトでの動作確認
- **パフォーマンス**: 大規模プロジェクトでの実行時間

### 2. 統合テスト

#### 2.1 MCPサーバー統合
- **リソース登録**: 正常な登録・一覧取得
- **アクセス処理**: URI経由でのリソースアクセス
- **エラーハンドリング**: 統合レベルでのエラー処理

#### 2.2 セキュリティ統合
- **境界保護**: プロジェクト外アクセスの防止
- **権限確認**: 適切な権限チェック
- **情報漏洩防止**: エラーメッセージの安全性

### 3. パフォーマンステスト

#### 3.1 スケーラビリティ
- **大規模プロジェクト**: 10,000+ファイルでの動作
- **メモリ使用量**: 効率的なメモリ管理
- **並行アクセス**: 複数クライアントでの安定性

#### 3.2 レスポンス時間
- **ファイルアクセス**: < 100ms（通常ファイル）
- **統計生成**: 目標時間内での完了
- **キャッシュ効果**: 繰り返しアクセスの高速化

## 制限事項

### 1. 技術的制限

#### 1.1 ファイルサイズ制限
- **最大ファイルサイズ**: 実装依存（通常100MB程度）
- **メモリ制約**: 大容量ファイルの段階的処理
- **タイムアウト**: 長時間処理の制限

#### 1.2 言語サポート制限
- **サポート言語**: tree-sitter対応言語のみ
- **複雑度計算**: 言語別実装の差異
- **メタデータ精度**: 言語検出の精度依存

### 2. 運用制限

#### 2.1 パフォーマンス制約
- **大規模プロジェクト**: 初回統計生成の時間要
- **ネットワークドライブ**: アクセス速度の影響
- **並行処理**: 同時アクセス数の制限

#### 2.2 セキュリティ制約
- **読み取り専用**: ファイル変更不可
- **境界制限**: プロジェクト外アクセス不可
- **権限依存**: ファイルシステム権限に依存

## 今後の拡張

### 1. 予定機能

#### 1.1 キャッシュ機能
- **統計キャッシュ**: 計算済み統計の保存
- **差分更新**: 変更ファイルのみ再計算
- **TTL管理**: 適切なキャッシュ有効期限

#### 1.2 高度な統計
- **依存関係分析**: モジュール間依存の可視化
- **品質メトリクス**: コード品質指標の追加
- **履歴統計**: 時系列でのプロジェクト変化

### 2. 最適化計画

#### 2.1 パフォーマンス最適化
- **並列処理**: ファイル分析の並列化
- **インクリメンタル分析**: 差分のみの効率的分析
- **メモリ最適化**: 大規模プロジェクト対応

#### 2.2 機能拡張
- **カスタム統計**: ユーザー定義メトリクス
- **フィルタリング**: 統計対象の柔軟な制御
- **エクスポート**: 統計データの外部出力

## 結論

MCPリソースは、コードファイルアクセスとプロジェクト統計の動的提供により、AIアシスタントの効果的なコード理解を支援します。セキュリティ、パフォーマンス、拡張性を考慮した設計により、大規模プロジェクトでの実用的な利用を実現します。