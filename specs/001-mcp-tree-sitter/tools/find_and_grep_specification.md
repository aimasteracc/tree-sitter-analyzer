# find_and_grep ツール仕様書

**作成日**: 2025-10-12  
**バージョン**: 1.0.0  
**対象ツール**: `find_and_grep`  
**実装ファイル**: `tree_sitter_analyzer/mcp/tools/find_and_grep_tool.py`

## 概要

`find_and_grep`ツールは、2段階検索アルゴリズムを使用して高精度なファイル検索とコンテンツ検索を実現するMCPツールです。第1段階でfd（ファイル検索）により対象ファイルを絞り込み、第2段階でripgrep（コンテンツ検索）により精密な文字列検索を実行します。大規模プロジェクトでの効率的な検索と、トークン最適化機能を提供します。

## 機能仕様

### 1. 基本機能

#### 1.1 2段階検索アルゴリズム
- **第1段階（fd）**: ファイル名・属性・メタデータによるファイル絞り込み
- **第2段階（ripgrep）**: 絞り込まれたファイル内でのコンテンツ検索
- **統合最適化**: 段階間でのパフォーマンス最適化とメタデータ連携
- **安全制限**: 各段階での結果数制限とタイムアウト保護

#### 1.2 高度なフィルタリング機能
- **ファイル属性フィルタ**: 拡張子、サイズ、更新日時、権限
- **パターンマッチング**: glob/regex両対応のファイル名検索
- **コンテンツフィルタ**: 大小文字、単語境界、マルチライン対応
- **除外パターン**: .gitignore連携と柔軟な除外設定

#### 1.3 トークン最適化機能
- **total_only**: 総マッチ数のみ返却（最高効率）
- **summary_only**: 要約形式での結果表示
- **group_by_file**: ファイル別グループ化によるトークン削減
- **suppress_output**: ファイル出力時の詳細結果抑制

### 2. 入力仕様

#### 2.1 必須パラメータ

| パラメータ | 型 | 説明 | 制約 |
|------------|----|----|------|
| `roots` | array[string] | 検索対象ディレクトリ | 必須、プロジェクト境界内 |
| `query` | string | 検索クエリ文字列 | 必須、非空文字列 |

#### 2.2 ファイル検索段階パラメータ（fd）

| パラメータ | 型 | デフォルト | 説明 |
|------------|----|-----------|----|
| `pattern` | string | - | ファイル名パターン（glob/regex） |
| `glob` | boolean | false | パターンをglob形式として扱う |
| `types` | array[string] | - | ファイル種別（f,d,l,x,e） |
| `extensions` | array[string] | - | 拡張子フィルタ（ドット不要） |
| `exclude` | array[string] | - | 除外パターン |
| `depth` | integer | - | 最大検索深度 |
| `follow_symlinks` | boolean | false | シンボリックリンク追跡 |
| `hidden` | boolean | false | 隠しファイル含む |
| `no_ignore` | boolean | false | .gitignore無視 |
| `size` | array[string] | - | サイズフィルタ（+10M, -1K等） |
| `changed_within` | string | - | 更新期間内（1d, 2h等） |
| `changed_before` | string | - | 更新期間前 |
| `full_path_match` | boolean | false | フルパス対象マッチング |
| `file_limit` | integer | 2000 | 最大ファイル数（上限10000） |
| `sort` | enum | - | ソート方式（path/mtime/size） |

#### 2.3 コンテンツ検索段階パラメータ（ripgrep）

| パラメータ | 型 | デフォルト | 説明 |
|------------|----|-----------|----|
| `case` | enum | "smart" | 大小文字（smart/insensitive/sensitive） |
| `fixed_strings` | boolean | false | リテラル文字列検索 |
| `word` | boolean | false | 単語境界マッチング |
| `multiline` | boolean | false | マルチライン検索 |
| `include_globs` | array[string] | - | 追加包含パターン |
| `exclude_globs` | array[string] | - | 除外パターン |
| `max_filesize` | string | - | 最大ファイルサイズ |
| `context_before` | integer | - | 前後コンテキスト行数 |
| `context_after` | integer | - | 後コンテキスト行数 |
| `encoding` | string | - | 文字エンコーディング |
| `max_count` | integer | - | 最大マッチ数 |
| `timeout_ms` | integer | - | タイムアウト（ミリ秒） |

#### 2.4 出力制御パラメータ

| パラメータ | 型 | デフォルト | 説明 |
|------------|----|-----------|----|
| `count_only_matches` | boolean | false | マッチ数のみ返却 |
| `summary_only` | boolean | false | 要約形式返却 |
| `optimize_paths` | boolean | false | パス最適化 |
| `group_by_file` | boolean | false | ファイル別グループ化 |
| `total_only` | boolean | false | 総数のみ返却（最優先） |
| `output_file` | string | - | ファイル出力名 |
| `suppress_output` | boolean | false | 詳細出力抑制 |

#### 2.5 入力スキーマ
```json
{
  "type": "object",
  "properties": {
    "roots": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Directory paths to search in. Must be within project boundaries."
    },
    "query": {
      "type": "string", 
      "description": "Text pattern to search for in the found files."
    },
    // ... 他のパラメータ
  },
  "required": ["roots", "query"],
  "additionalProperties": false
}
```

### 3. 出力仕様

#### 3.1 標準出力形式
```json
{
  "success": true,
  "count": 42,
  "results": [
    {
      "file": "/path/to/file.py",
      "line_number": 15,
      "column": 8,
      "content": "matching line content",
      "context_before": ["line 13", "line 14"],
      "context_after": ["line 16", "line 17"]
    }
  ],
  "meta": {
    "searched_file_count": 150,
    "truncated": false,
    "fd_elapsed_ms": 45,
    "rg_elapsed_ms": 123
  }
}
```

#### 3.2 total_only出力（最優先）
```json
42
```

#### 3.3 count_only_matches出力
```json
{
  "success": true,
  "count_only": true,
  "total_matches": 42,
  "file_counts": {
    "/path/to/file1.py": 15,
    "/path/to/file2.py": 27
  },
  "meta": { /* メタデータ */ }
}
```

#### 3.4 summary_only出力
```json
{
  "success": true,
  "summary_only": true,
  "summary": {
    "total_matches": 42,
    "file_count": 8,
    "top_files": [
      {"file": "/path/to/file1.py", "matches": 15},
      {"file": "/path/to/file2.py", "matches": 12}
    ],
    "sample_matches": [
      {"file": "/path/to/file1.py", "line": 15, "content": "sample"}
    ]
  },
  "meta": { /* メタデータ */ }
}
```

#### 3.5 group_by_file出力
```json
{
  "success": true,
  "count": 42,
  "files": [
    {
      "file": "/path/to/file1.py",
      "match_count": 15,
      "matches": [
        {"line_number": 15, "content": "match1"},
        {"line_number": 23, "content": "match2"}
      ]
    }
  ],
  "meta": { /* メタデータ */ }
}
```

### 4. 実行フロー

#### 4.1 2段階検索プロセス
```
1. 入力検証・パラメータ正規化
   ├── roots検証（セキュリティ境界確認）
   ├── query検証（非空文字列確認）
   └── パラメータ型・範囲検証

2. 第1段階：fd実行（ファイル検索）
   ├── fdコマンド構築
   ├── .gitignore自動検出
   ├── fd実行・結果取得
   ├── ファイルリスト後処理（ソート・制限）
   └── 検索対象ファイル確定

3. 第2段階：ripgrep実行（コンテンツ検索）
   ├── ファイル特化glob生成
   ├── ripgrepコマンド構築
   ├── ripgrep実行・結果取得
   └── JSON解析・構造化

4. 結果後処理・最適化
   ├── トークン最適化適用
   ├── ファイル出力処理
   ├── suppress_output処理
   └── 最終レスポンス生成
```

#### 4.2 .gitignore自動検出
```python
# 自動検出ロジック
if not no_ignore:
    detector = get_default_detector()
    should_ignore = detector.should_use_no_ignore(roots, project_root)
    if should_ignore:
        no_ignore = True  # 自動的に--no-ignoreを有効化
```

#### 4.3 ファイル特化検索最適化
```python
# fd結果からripgrep用glob生成
for file_path in fd_results:
    file_name = Path(file_path).name
    escaped_name = file_name.replace("[", "[[]").replace("]", "[]]")
    file_globs.append(escaped_name)

# 親ディレクトリをrootsとして使用
rg_roots = list(set(Path(f).parent for f in fd_results))
```

### 5. パフォーマンス特性

#### 5.1 実行時間目標
- **小規模検索**（<100ファイル）: < 500ms
- **中規模検索**（100-1000ファイル）: < 2秒
- **大規模検索**（1000+ファイル）: < 5秒
- **タイムアウト保護**: 30秒上限

#### 5.2 メモリ効率
- **結果制限**: 10,000マッチ上限
- **ファイル制限**: 2,000ファイル上限（設定可能）
- **ストリーミング処理**: 大容量ファイルの段階的処理
- **メモリ解放**: 段階間での適切なリソース管理

#### 5.3 トークン最適化効果
- **total_only**: 99%削減（数値のみ）
- **summary_only**: 90%削減（要約のみ）
- **group_by_file**: 70%削減（重複パス除去）
- **suppress_output**: 95%削減（ファイル出力時）

### 6. セキュリティ仕様

#### 6.1 境界保護
- **プロジェクト境界**: 指定roots内のみアクセス
- **パストラバーサル防止**: 相対パス・シンボリックリンク制御
- **権限確認**: 読み取り権限の事前確認
- **サンドボックス**: 外部コマンド実行の安全制御

#### 6.2 リソース保護
- **実行時間制限**: プロセスタイムアウト
- **メモリ制限**: 結果サイズ上限
- **ファイルサイズ制限**: 検索対象ファイルサイズ制限
- **並行実行制御**: 同時実行数制限

### 7. エラーハンドリング

#### 7.1 エラーケース

| エラー種別 | 条件 | 対応 |
|------------|------|------|
| パラメータエラー | 必須パラメータ不足 | ValueError例外 |
| セキュリティエラー | 境界外アクセス | セキュリティ例外 |
| fdエラー | ファイル検索失敗 | エラーレスポンス |
| ripgrepエラー | コンテンツ検索失敗 | エラーレスポンス |
| タイムアウト | 実行時間超過 | タイムアウトエラー |

#### 7.2 エラーレスポンス形式
```json
{
  "success": false,
  "error": "fd failed: No such file or directory",
  "returncode": 1,
  "stage": "fd"
}
```

### 8. 使用例

#### 8.1 基本的な検索
```json
{
  "roots": ["src/", "tests/"],
  "query": "function calculateTotal"
}
```

#### 8.2 Python関数の高精度検索
```json
{
  "roots": ["."],
  "extensions": ["py"],
  "query": "def calculate.*total",
  "case": "insensitive",
  "context_before": 2,
  "context_after": 2
}
```

#### 8.3 大規模プロジェクトでのトークン最適化
```json
{
  "roots": ["."],
  "query": "TODO",
  "total_only": true
}
```

#### 8.4 詳細検索とファイル出力
```json
{
  "roots": ["src/"],
  "pattern": "*.ts",
  "glob": true,
  "query": "interface.*Config",
  "output_file": "interface_search",
  "suppress_output": true
}
```

#### 8.5 時間制限付き検索
```json
{
  "roots": ["."],
  "changed_within": "7d",
  "query": "bug|error|exception",
  "case": "insensitive",
  "summary_only": true
}
```

### 9. 統合仕様

#### 9.1 他ツールとの連携
- **list_files**: ファイル一覧→コンテンツ検索の連携
- **search_content**: 単純検索→高精度検索の段階的利用
- **extract_code_section**: 検索結果→コード抽出の連携
- **set_project_path**: 動的境界変更への対応

#### 9.2 ワークフロー統合
```
1. find_and_grep（概要把握）
   ↓
2. extract_code_section（詳細確認）
   ↓
3. query_code（構造解析）
```

### 10. テスト仕様

#### 10.1 単体テスト
- **2段階検索**: fd→ripgrepの正常連携
- **パラメータ検証**: 全パラメータの型・範囲確認
- **エラーハンドリング**: 各段階でのエラー処理
- **最適化機能**: トークン削減効果の確認

#### 10.2 統合テスト
- **大規模プロジェクト**: 10,000+ファイルでの性能
- **複雑クエリ**: 正規表現・マルチライン検索
- **境界テスト**: セキュリティ境界の保護確認
- **並行実行**: 複数クライアントでの安定性

#### 10.3 パフォーマンステスト
- **実行時間**: 目標時間内での完了
- **メモリ使用量**: 制限内でのメモリ使用
- **トークン効率**: 最適化機能の効果測定

### 11. 制限事項

#### 11.1 技術的制限
- **外部依存**: fd・ripgrepコマンドが必要
- **プラットフォーム**: Unix系OSでの最適化
- **ファイルサイズ**: 200MB上限
- **結果数**: 10,000マッチ上限

#### 11.2 運用制限
- **大規模検索**: 初回実行時の時間要
- **複雑パターン**: 正規表現の性能影響
- **ネットワークドライブ**: レスポンス時間増加
- **権限依存**: ファイル読み取り権限必要

### 12. 今後の拡張

#### 12.1 予定機能
- **インクリメンタル検索**: 段階的結果表示
- **検索履歴**: 過去の検索パターン管理
- **結果キャッシュ**: 同一検索の高速化
- **並列検索**: 複数ディレクトリの並行処理

#### 12.2 最適化計画
- **インデックス化**: 事前インデックスによる高速化
- **差分検索**: 変更ファイルのみの検索
- **圧縮出力**: 結果の効率的な圧縮
- **ストリーミング**: リアルタイム結果配信

## 結論

`find_and_grep`ツールは、2段階検索アルゴリズムにより高精度かつ高効率なファイル・コンテンツ検索を実現します。大規模プロジェクトでの実用性とトークン最適化を両立し、複雑な検索要件に対応する包括的な検索ソリューションを提供します。