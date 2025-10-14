# list_files ツール仕様書

**作成日**: 2025-10-12  
**バージョン**: 1.0.0  
**対象ツール**: `list_files` (ListFilesTool)  
**実装ファイル**: `tree_sitter_analyzer/mcp/tools/list_files_tool.py`

## 概要

`list_files`ツールは、fdコマンドをラップしたMCPツールで、高度なフィルタリングオプションを使用してファイルとディレクトリを効率的に検索・一覧表示します。プロジェクト境界内での安全なファイル探索機能を提供し、大規模プロジェクトでも高速に動作します。

## 機能仕様

### 1. 基本機能

#### 1.1 高速ファイル検索
- **fd統合**: Rustベースの高速ファイル検索エンジン
- **並列処理**: マルチコア活用による高速検索
- **インクリメンタル結果**: 大量ファイルでも応答性維持
- **メモリ効率**: 大規模ディレクトリでも一定メモリ使用量

#### 1.2 柔軟なパターンマッチング
- **Globパターン**: シェル形式のワイルドカード（`*.py`, `test_*`）
- **正規表現**: 高度なパターンマッチング（`.*\.py$`）
- **フルパスマッチ**: ディレクトリ構造を含むマッチング
- **大文字小文字**: 自動判定またはオプション指定

#### 1.3 包括的フィルタリング
- **ファイルタイプ**: files, directories, symlinks, executable, empty
- **拡張子フィルタ**: 複数拡張子の同時指定
- **サイズフィルタ**: バイト、KB、MB、GB単位での範囲指定
- **時間フィルタ**: 変更日時による絞り込み
- **除外パターン**: 不要ファイル・ディレクトリの除外

### 2. セキュリティ機能

#### 2.1 プロジェクト境界保護
- **境界検証**: 指定されたrootsのプロジェクト内確認
- **パス正規化**: 相対パス・絶対パスの安全な処理
- **アクセス制御**: プロジェクト外へのアクセス防止

#### 2.2 .gitignore統合
- **自動検出**: .gitignoreファイルの存在確認
- **スマート無視**: 適切な場合の自動--no-ignore適用
- **干渉回避**: .gitignoreによる検索結果への影響最小化

### 3. パフォーマンス最適化

#### 3.1 結果制限
- **デフォルト制限**: 2,000件の結果上限
- **ハードキャップ**: 10,000件の絶対上限
- **カウントモード**: 件数のみの高速取得
- **早期終了**: 制限到達時の処理停止

#### 3.2 トークン最適化
- **ファイル出力**: 大量結果のファイル保存
- **suppress_output**: レスポンスサイズの最小化
- **メタデータ選択**: 必要な情報のみの取得

## API仕様

### 入力パラメータ

```json
{
  "roots": ["string"] (必須),
  "pattern": "string (オプション)",
  "glob": "boolean (オプション, default: false)",
  "types": ["string"] (オプション),
  "extensions": ["string"] (オプション)",
  "exclude": ["string"] (オプション),
  "depth": "integer (オプション)",
  "follow_symlinks": "boolean (オプション, default: false)",
  "hidden": "boolean (オプション, default: false)",
  "no_ignore": "boolean (オプション, default: false)",
  "size": ["string"] (オプション),
  "changed_within": "string (オプション)",
  "changed_before": "string (オプション)",
  "full_path_match": "boolean (オプション, default: false)",
  "absolute": "boolean (オプション, default: true)",
  "limit": "integer (オプション, default: 2000, max: 10000)",
  "count_only": "boolean (オプション, default: false)",
  "output_file": "string (オプション)",
  "suppress_output": "boolean (オプション, default: false)"
}
```

### パラメータ詳細

#### roots (必須)
- **形式**: 文字列配列
- **説明**: 検索対象のディレクトリパス
- **例**: `["."]`, `["src/", "tests/"]`, `["/project/module"]`
- **制約**: プロジェクト境界内のパスのみ

#### pattern (オプション)
- **形式**: 文字列
- **説明**: ファイル/ディレクトリ名のパターン
- **例**: `"*.py"` (glob), `"test_*"` (glob), `".*\\.js$"` (regex)

#### types (オプション)
- **形式**: 文字列配列
- **値**: `f`(files), `d`(directories), `l`(symlinks), `x`(executable), `e`(empty)
- **例**: `["f"]` (ファイルのみ), `["f", "d"]` (ファイルとディレクトリ)

#### size (オプション)
- **形式**: 文字列配列
- **フォーマット**: `+10M`(10MB以上), `-1K`(1KB未満), `100B`(100バイト)
- **単位**: B, K, M, G
- **例**: `["+1M", "-100M"]` (1MB以上100MB未満)

#### 時間フィルタ
- **changed_within**: `"1d"`, `"2h"`, `"30m"`, `"1w"`
- **changed_before**: 同上フォーマット
- **説明**: ファイル変更時刻による絞り込み

### 出力フォーマット

#### 通常モード
```json
{
  "success": true,
  "count": 150,
  "truncated": false,
  "elapsed_ms": 45,
  "results": [
    {
      "path": "/absolute/path/to/file.py",
      "is_dir": false,
      "size_bytes": 1024,
      "mtime": 1697123456,
      "ext": "py"
    }
  ]
}
```

#### カウントモード
```json
{
  "success": true,
  "count_only": true,
  "total_count": 1500,
  "truncated": false,
  "elapsed_ms": 12
}
```

#### ファイル出力モード（suppress_output=true）
```json
{
  "success": true,
  "count": 1500,
  "output_file": "/project/file_list_20251012.json",
  "message": "File list results saved to /project/file_list_20251012.json"
}
```

## 実装詳細

### 1. クラス構造

```python
class ListFilesTool(BaseMCPTool):
    def get_tool_definition(self) -> dict[str, Any]
    def _validate_roots(self, roots: list[str]) -> list[str]
    def validate_arguments(self, arguments: dict[str, Any]) -> bool
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]
```

### 2. 依存関係

- **fd_rg_utils**: fdコマンド構築・実行ユーティリティ
- **FileOutputManager**: ファイル出力機能
- **GitignoreDetector**: .gitignore自動検出
- **BaseMCPTool**: 共通MCP機能（セキュリティ、パス解決）

### 3. fdコマンド統合

#### 3.1 コマンド構築
```python
cmd = fd_rg_utils.build_fd_command(
    pattern=pattern,
    glob=glob_mode,
    types=file_types,
    extensions=extensions,
    exclude=exclude_patterns,
    depth=max_depth,
    follow_symlinks=follow_links,
    hidden=include_hidden,
    no_ignore=ignore_gitignore,
    size=size_filters,
    changed_within=time_filter,
    changed_before=time_filter,
    full_path_match=full_path,
    absolute=True,
    limit=result_limit,
    roots=validated_roots
)
```

#### 3.2 実行・結果処理
```python
rc, out, err = await fd_rg_utils.run_command_capture(cmd)
lines = out.decode("utf-8", errors="replace").splitlines()
```

### 4. 結果処理

#### 4.1 メタデータ取得
```python
for path_str in lines:
    path_obj = Path(path_str)
    is_dir = path_obj.is_dir()
    size_bytes = path_obj.stat().st_size if not is_dir else None
    mtime = int(path_obj.stat().st_mtime)
    ext = path_obj.suffix[1:] if path_obj.suffix else None
```

#### 4.2 セキュリティ検証
- パス正規化による境界確認
- 存在確認とアクセス権限チェック
- 悪意のあるパスパターンの検出

## パフォーマンス特性

### 1. 速度ベンチマーク

| ファイル数 | 検索時間 | メモリ使用量 |
|-----------|----------|-------------|
| 1,000 | < 50ms | < 10MB |
| 10,000 | < 200ms | < 20MB |
| 100,000 | < 1s | < 50MB |
| 1,000,000 | < 5s | < 100MB |

### 2. スケーラビリティ

#### 2.1 大規模プロジェクト対応
- **Node.js**: 100,000+ ファイル（node_modules含む）
- **Linux Kernel**: 70,000+ ファイル
- **Chromium**: 300,000+ ファイル

#### 2.2 制限とキャップ
- **デフォルト制限**: 2,000件（調整可能）
- **ハードキャップ**: 10,000件（安全性確保）
- **メモリ制限**: 100MB以下（大規模検索時）

### 3. 最適化技術

#### 3.1 fd最適化
- **並列ディレクトリ走査**: マルチスレッド活用
- **早期終了**: 制限到達時の即座停止
- **インクリメンタル出力**: 結果の段階的取得

#### 3.2 結果処理最適化
- **遅延評価**: メタデータの必要時取得
- **バッチ処理**: 複数ファイルの一括処理
- **メモリプール**: オブジェクト再利用

## 使用例

### 1. 基本的なファイル検索
```json
{
  "roots": ["src/"],
  "pattern": "*.py",
  "glob": true
}
```

### 2. 複合条件での検索
```json
{
  "roots": [".", "tests/"],
  "extensions": ["js", "ts"],
  "types": ["f"],
  "size": ["+1K", "-1M"],
  "changed_within": "7d"
}
```

### 3. 大規模プロジェクトでのカウント
```json
{
  "roots": ["."],
  "count_only": true,
  "exclude": ["node_modules", ".git", "*.tmp"]
}
```

### 4. 詳細検索とファイル出力
```json
{
  "roots": ["src/", "lib/"],
  "pattern": "test_*",
  "glob": true,
  "types": ["f"],
  "output_file": "test_files_list",
  "suppress_output": true
}
```

### 5. 隠しファイルを含む完全検索
```json
{
  "roots": ["."],
  "hidden": true,
  "no_ignore": true,
  "depth": 3,
  "limit": 5000
}
```

## エラーハンドリング

### 1. 検証エラー
- `ValueError`: 必須パラメータ不足、無効な型
- `SecurityError`: プロジェクト境界外アクセス
- `PathError`: 存在しないディレクトリ指定

### 2. 実行時エラー
- `CommandError`: fdコマンド実行失敗
- `TimeoutError`: 検索タイムアウト
- `PermissionError`: ディレクトリアクセス権限不足

### 3. エラーレスポンス
```json
{
  "success": false,
  "error": "Invalid root '/outside/project': Path is outside project boundaries",
  "returncode": 1
}
```

## セキュリティ考慮事項

### 1. プロジェクト境界保護
- **絶対パス検証**: 解決されたパスの境界確認
- **シンボリックリンク**: follow_symlinks=falseでの安全性
- **パストラバーサル**: `../`パターンの検出・防止

### 2. リソース保護
- **結果制限**: メモリ枯渇防止
- **実行時間制限**: 無限ループ防止
- **並列制限**: システムリソース保護

### 3. 情報漏洩防止
- **エラーメッセージ**: パス情報の適切な制限
- **ログ出力**: 機密情報の除外
- **結果フィルタ**: 権限外ファイルの除外

## テスト要件

### 1. 機能テスト
- [ ] 基本的なファイル検索
- [ ] Globパターンマッチング
- [ ] 正規表現パターンマッチング
- [ ] 複数フィルタの組み合わせ
- [ ] カウントモード
- [ ] ファイル出力機能

### 2. パフォーマンステスト
- [ ] 大規模ディレクトリ（10,000+ファイル）
- [ ] 深いディレクトリ構造（10+レベル）
- [ ] 複雑なパターンマッチング
- [ ] 並列検索の効率性

### 3. セキュリティテスト
- [ ] プロジェクト境界外アクセス試行
- [ ] パストラバーサル攻撃
- [ ] シンボリックリンク悪用
- [ ] リソース枯渇攻撃

### 4. エラーハンドリングテスト
- [ ] 存在しないディレクトリ
- [ ] 権限不足ディレクトリ
- [ ] 無効なパターン
- [ ] fdコマンド実行失敗

## 品質基準

### 1. パフォーマンス要件
- **応答時間**: 通常検索（<1,000ファイル）で100ms以内
- **スループット**: 10,000ファイル/秒以上の処理能力
- **メモリ効率**: ファイル数に比例しない一定メモリ使用

### 2. 信頼性要件
- **可用性**: 99.9%以上の成功率
- **エラー回復**: 部分的失敗時の適切な報告
- **データ整合性**: 検索結果の完全性保証

### 3. セキュリティ要件
- **境界保護**: 100%のプロジェクト外アクセス防止
- **権限確認**: 適切なファイルアクセス権限チェック
- **監査ログ**: セキュリティイベントの記録

## 今後の拡張予定

### 1. 機能拡張
- **コンテンツプレビュー**: ファイル内容の部分表示
- **重複検出**: 同名・同サイズファイルの検出
- **統計情報**: ファイルタイプ別統計の提供

### 2. パフォーマンス改善
- **インデックス化**: 頻繁に検索されるディレクトリのインデックス
- **キャッシュ機能**: 検索結果の一時保存
- **ストリーミング**: リアルタイム結果配信

### 3. 統合機能
- **IDE連携**: エディタとの直接統合
- **CI/CD統合**: ビルドプロセスでの活用
- **監視連携**: ファイル変更監視との統合

---

**注意**: この仕様書は実装済み機能の文書化であり、User Story 2「高度な解析ツール」の一部として位置づけられます。