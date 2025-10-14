# set_project_path ツール仕様書

**作成日**: 2025-10-12  
**バージョン**: 1.0.0  
**対象ツール**: `set_project_path`  
**実装ファイル**: `tree_sitter_analyzer/mcp/server.py`

## 概要

`set_project_path`ツールは、MCPサーバーのプロジェクト境界を動的に変更するためのツールです。セキュリティ境界の再設定、全ツールとリソースの同期更新、プロジェクト統計の再計算を一括で実行し、複数プロジェクト間での安全な切り替えを可能にします。

## 機能仕様

### 1. 基本機能

#### 1.1 プロジェクト境界設定
- **動的境界変更**: 実行時のプロジェクトルート変更
- **セキュリティ検証**: 新しいパスの存在確認と権限検証
- **一括更新**: 全ツールとリソースの同期更新
- **状態管理**: サーバー全体の一貫した状態維持

#### 1.2 セキュリティ機能
- **パス検証**: 絶対パスの存在確認
- **ディレクトリ検証**: 指定パスがディレクトリであることの確認
- **権限確認**: 読み取り権限の検証
- **境界保護**: 新しい境界内でのファイルアクセス制限

#### 1.3 同期更新機能
- **全ツール更新**: 8つのMCPツールの同期更新
- **リソース更新**: プロジェクト統計リソースの再初期化
- **エンジン更新**: 分析エンジンとセキュリティバリデーターの再構築
- **状態一貫性**: 全コンポーネントの状態同期

### 2. 入力仕様

#### 2.1 必須パラメータ

| パラメータ | 型 | 説明 | 制約 |
|------------|----|----|------|
| `project_path` | string | プロジェクトルートの絶対パス | 必須、存在するディレクトリ |

#### 2.2 入力スキーマ
```json
{
  "type": "object",
  "properties": {
    "project_path": {
      "type": "string",
      "description": "Absolute path to the project root"
    }
  },
  "required": ["project_path"],
  "additionalProperties": false
}
```

#### 2.3 入力検証
- **型検証**: project_pathが文字列であることの確認
- **存在確認**: 指定パスが存在することの確認
- **ディレクトリ検証**: 指定パスがディレクトリであることの確認
- **権限確認**: 読み取り権限があることの確認

### 3. 出力仕様

#### 3.1 成功時の出力
```json
{
  "status": "success",
  "project_root": "/absolute/path/to/project"
}
```

#### 3.2 出力フィールド

| フィールド | 型 | 説明 |
|------------|----|----|
| `status` | string | 実行ステータス（"success"） |
| `project_root` | string | 設定されたプロジェクトルートパス |

### 4. エラーハンドリング

#### 4.1 エラーケース

| エラー種別 | 条件 | エラーメッセージ例 |
|------------|------|-------------------|
| パラメータ不足 | project_pathが未指定 | "project_path parameter is required and must be a string" |
| 型エラー | project_pathが文字列でない | "project_path parameter is required and must be a string" |
| パス不存在 | 指定パスが存在しない | "Project path does not exist: /path/to/nonexistent" |
| ディレクトリエラー | 指定パスがファイル | "Project path does not exist: /path/to/file.txt" |

#### 4.2 エラーレスポンス形式
```json
{
  "error": "ValueError: Project path does not exist: /invalid/path",
  "type": "ValueError"
}
```

### 5. 実装詳細

#### 5.1 実行フロー
```
1. 入力検証
   ├── パラメータ存在確認
   ├── 型検証
   └── パス存在・ディレクトリ確認

2. プロジェクト境界更新
   ├── SecurityValidator更新
   ├── AnalysisEngine再構築
   └── PathResolver更新

3. ツール同期更新
   ├── QueryTool.set_project_path()
   ├── ReadPartialTool.set_project_path()
   ├── TableFormatTool.set_project_path()
   ├── AnalyzeScaleTool.set_project_path()
   ├── ListFilesTool.set_project_path()
   ├── SearchContentTool.set_project_path()
   ├── FindAndGrepTool.set_project_path()
   └── UniversalAnalyzeTool.set_project_path() (存在時)

4. リソース更新
   └── ProjectStatsResource.set_project_path()

5. 成功レスポンス返却
```

#### 5.2 コンポーネント更新詳細

**BaseMCPTool継承ツールの更新**:
```python
def set_project_path(self, project_path: str) -> None:
    self.project_root = project_path
    self.security_validator = SecurityValidator(project_path)
    self.path_resolver = PathResolver(project_path)
```

**分析エンジン特化ツールの追加更新**:
- QueryTool: QueryService再構築
- TableFormatTool: AnalysisEngine再構築
- AnalyzeScaleTool: AnalysisEngine再構築

### 6. セキュリティ仕様

#### 6.1 境界保護
- **新境界適用**: 指定パス以下のみアクセス可能
- **既存セッション無効化**: 旧境界でのキャッシュクリア
- **権限継承**: 新境界での権限設定適用

#### 6.2 検証プロセス
- **事前検証**: パス存在・権限確認
- **事後検証**: 全ツールの境界設定確認
- **一貫性保証**: 部分的更新失敗時のロールバック

### 7. パフォーマンス特性

#### 7.1 実行時間
- **通常ケース**: < 100ms（ローカルディスク）
- **ネットワークドライブ**: < 500ms
- **大規模プロジェクト**: 初回統計計算で追加時間

#### 7.2 メモリ使用量
- **ベースライン**: 既存ツール状態維持
- **追加使用量**: 新しいエンジンインスタンス分
- **最適化**: 旧インスタンスの適切な解放

### 8. 使用例

#### 8.1 基本的な使用例
```json
{
  "project_path": "/home/user/projects/my-app"
}
```

**レスポンス**:
```json
{
  "status": "success",
  "project_root": "/home/user/projects/my-app"
}
```

#### 8.2 プロジェクト切り替えワークフロー
```json
// Step 1: プロジェクトA → プロジェクトB
{
  "project_path": "/projects/project-b"
}

// Step 2: プロジェクトBでの作業
// 全ツールが新しい境界で動作

// Step 3: プロジェクトA復帰
{
  "project_path": "/projects/project-a"
}
```

#### 8.3 エラーケース例
```json
// 存在しないパス
{
  "project_path": "/nonexistent/path"
}
```

**エラーレスポンス**:
```json
{
  "error": "ValueError: Project path does not exist: /nonexistent/path"
}
```

### 9. 統合仕様

#### 9.1 他ツールとの連携
- **即座反映**: 設定後の全ツール呼び出しで新境界適用
- **状態同期**: 全ツールで一貫したプロジェクト状態
- **キャッシュ管理**: 境界変更時の適切なキャッシュクリア

#### 9.2 リソースとの連携
- **統計更新**: ProjectStatsResourceの即座更新
- **メタデータ同期**: プロジェクト情報の一貫性保証

### 10. テスト仕様

#### 10.1 単体テスト
- **正常ケース**: 有効なパスでの設定成功
- **エラーケース**: 無効なパス、権限不足、型エラー
- **境界テスト**: 空文字列、null、非文字列

#### 10.2 統合テスト
- **ツール連携**: 設定後の他ツール動作確認
- **リソース連携**: 統計情報の更新確認
- **セキュリティ**: 境界保護の動作確認

#### 10.3 パフォーマンステスト
- **実行時間**: 100ms以内での完了
- **メモリ効率**: 適切なリソース解放
- **並行性**: 複数クライアントでの安全性

### 11. 制限事項

#### 11.1 技術的制限
- **絶対パス必須**: 相対パスは受け付けない
- **ディレクトリ限定**: ファイルパスは無効
- **権限依存**: 読み取り権限が必要

#### 11.2 運用制限
- **頻繁な変更非推奨**: パフォーマンス影響を考慮
- **大規模プロジェクト**: 初回統計計算に時間要
- **ネットワークドライブ**: レスポンス時間の増加

### 12. 今後の拡張

#### 12.1 予定機能
- **相対パス対応**: 現在のプロジェクトからの相対指定
- **プロジェクト履歴**: 最近使用したプロジェクトの管理
- **バッチ設定**: 複数プロジェクトの一括設定

#### 12.2 最適化計画
- **遅延初期化**: 必要時のみエンジン再構築
- **差分更新**: 変更部分のみの更新
- **キャッシュ戦略**: 効率的なキャッシュ管理

## 結論

`set_project_path`ツールは、MCPサーバーの動的なプロジェクト境界管理を実現する重要なツールです。セキュリティ、一貫性、パフォーマンスを両立し、複数プロジェクト環境での柔軟な作業を可能にします。