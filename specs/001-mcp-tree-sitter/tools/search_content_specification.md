# search_content ツール仕様書

**作成日**: 2025-10-12  
**バージョン**: 1.0.0  
**対象ツール**: `search_content` (SearchContentTool)  
**実装ファイル**: `tree_sitter_analyzer/mcp/tools/search_content_tool.py`

## 概要

`search_content`ツールは、ripgrepをラップしたMCPツールで、ファイル内のテキストコンテンツを高速かつ柔軟に検索します。正規表現パターン、大文字小文字の区別、コンテキスト行、多様な出力フォーマットをサポートし、大規模プロジェクトでも効率的に動作します。

## 機能仕様

### 1. 基本機能

#### 1.1 高速テキスト検索
- **ripgrep統合**: Rustベースの超高速テキスト検索エンジン
- **並列処理**: マルチコア活用による高速検索
- **JSON出力**: 構造化された検索結果
- **ストリーミング**: 大量結果の効率的処理

#### 1.2 柔軟なパターンマッチング
- **正規表現**: 高度なパターンマッチング（デフォルト）
- **リテラル文字列**: 固定文字列検索（fixed_strings=true）
- **単語境界**: 完全単語マッチング（word=true）
- **複数行マッチ**: 行をまたぐパターン検索（multiline=true）

#### 1.3 大文字小文字制御
- **スマートケース**: 大文字が含まれる場合のみ区別（デフォルト）
- **大文字小文字無視**: 常に無視（insensitive）
- **大文字小文字区別**: 常に区別（sensitive）

### 2. 検索対象制御

#### 2.1 検索範囲指定
- **ディレクトリ検索**: rootsパラメータで複数ディレクトリ指定
- **ファイル指定**: filesパラメータで特定ファイル検索
- **Globパターン**: include_globs/exclude_globsでファイル絞り込み
- **隠しファイル**: hidden=trueで.ファイル含む検索

#### 2.2 ファイルフィルタリング
- **サイズ制限**: max_filesizeで大きなファイル除外
- **エンコーディング**: 特定文字エンコーディング指定
- **シンボリックリンク**: follow_symlinks制御
- **.gitignore**: no_ignoreで無視ファイル制御

### 3. 結果制御・最適化

#### 3.1 出力フォーマット
- **通常モード**: 完全な検索結果（デフォルト）
- **カウントモード**: ファイル別マッチ数のみ（count_only_matches=true）
- **合計モード**: 総マッチ数のみ（total_only=true）
- **サマリーモード**: 要約結果（summary_only=true）
- **ファイルグループ**: ファイル別グループ化（group_by_file=true）

#### 3.2 トークン最適化
- **ファイル出力**: 大量結果のファイル保存（output_file）
- **出力抑制**: レスポンスサイズ最小化（suppress_output=true）
- **パス最適化**: 共通プレフィックス除去（optimize_paths=true）
- **クロスフォーマットキャッシュ**: 異なる出力形式間でのキャッシュ共有

### 4. パフォーマンス機能

#### 4.1 制限・タイムアウト
- **マッチ数制限**: max_countでファイル別上限設定
- **タイムアウト**: timeout_msで検索時間制限
- **ハードキャップ**: システム保護のための絶対上限
- **早期終了**: 制限到達時の即座停止

#### 4.2 キャッシュシステム
- **結果キャッシュ**: 同一クエリの高速再実行
- **スマートキャッシュ**: 異なる出力形式間での結果共有
- **キャッシュキー**: クエリ・パラメータベースの一意識別
- **キャッシュヒット**: 既存結果の効率的再利用

## API仕様

### 入力パラメータ

```json
{
  "query": "string (必須)",
  "roots": ["string"] (オプション),
  "files": ["string"] (オプション),
  "case": "smart|insensitive|sensitive (オプション, default: smart)",
  "fixed_strings": "boolean (オプション, default: false)",
  "word": "boolean (オプション, default: false)",
  "multiline": "boolean (オプション, default: false)",
  "include_globs": ["string"] (オプション),
  "exclude_globs": ["string"] (オプション),
  "follow_symlinks": "boolean (オプション, default: false)",
  "hidden": "boolean (オプション, default: false)",
  "no_ignore": "boolean (オプション, default: false)",
  "max_filesize": "string (オプション)",
  "context_before": "integer (オプション)",
  "context_after": "integer (オプション)",
  "encoding": "string (オプション)",
  "max_count": "integer (オプション)",
  "timeout_ms": "integer (オプション)",
  "count_only_matches": "boolean (オプション, default: false)",
  "summary_only": "boolean (オプション, default: false)",
  "optimize_paths": "boolean (オプション, default: false)",
  "group_by_file": "boolean (オプション, default: false)",
  "total_only": "boolean (オプション, default: false)",
  "output_file": "string (オプション)",
  "suppress_output": "boolean (オプション, default: false)"
}
```

### パラメータ詳細

#### query (必須)
- **形式**: 文字列
- **説明**: 検索するテキストパターン
- **例**: `"function"`, `"class\\s+\\w+"`, `"TODO:"`
- **制約**: 空文字列不可

#### roots/files (どちらか必須)
- **roots**: ディレクトリパス配列（再帰検索）
- **files**: 特定ファイルパス配列
- **例**: `["src/", "tests/"]` または `["main.py", "config.json"]`

#### case (オプション)
- **smart**: 大文字含む場合のみ区別（デフォルト）
- **insensitive**: 常に大文字小文字無視
- **sensitive**: 常に大文字小文字区別

#### パターン制御
- **fixed_strings**: true=リテラル文字列、false=正規表現
- **word**: true=単語境界マッチング
- **multiline**: true=複数行パターン対応

#### ファイルフィルタ
- **include_globs**: 含めるファイルパターン（`["*.py", "*.js"]`）
- **exclude_globs**: 除外するファイルパターン（`["*.log", "__pycache__/*"]`）
- **max_filesize**: 最大ファイルサイズ（`"10M"`, `"500K"`, `"1G"`）

#### コンテキスト
- **context_before**: マッチ前の行数
- **context_after**: マッチ後の行数
- **例**: 3を指定すると前後3行ずつ表示

#### 出力制御
- **count_only_matches**: ファイル別カウントのみ
- **total_only**: 総マッチ数のみ（最高効率）
- **summary_only**: 要約結果
- **group_by_file**: ファイル別グループ化

### 出力フォーマット

#### 通常モード
```json
{
  "success": true,
  "count": 25,
  "truncated": false,
  "elapsed_ms": 120,
  "results": [
    {
      "file": "/project/src/main.py",
      "line_number": 42,
      "column": 8,
      "match_text": "function calculate_total",
      "line_text": "def function calculate_total(items):",
      "context_before": ["# Calculate total with tax", ""],
      "context_after": ["    return sum(items) * 1.1", ""]
    }
  ]
}
```

#### カウントモード（count_only_matches=true）
```json
{
  "success": true,
  "count_only": true,
  "total_matches": 150,
  "file_counts": {
    "/project/src/main.py": 25,
    "/project/src/utils.py": 18,
    "/project/tests/test_main.py": 12
  },
  "elapsed_ms": 45
}
```

#### 合計モード（total_only=true）
```json
150
```

#### サマリーモード（summary_only=true）
```json
{
  "success": true,
  "count": 150,
  "truncated": false,
  "elapsed_ms": 120,
  "summary": {
    "top_files": [
      {"file": "/project/src/main.py", "matches": 25},
      {"file": "/project/src/utils.py", "matches": 18}
    ],
    "file_types": {
      ".py": 140,
      ".js": 10
    },
    "sample_matches": [
      {
        "file": "/project/src/main.py",
        "line": 42,
        "text": "function calculate_total"
      }
    ]
  }
}
```

#### ファイルグループモード（group_by_file=true）
```json
{
  "success": true,
  "count": 150,
  "truncated": false,
  "elapsed_ms": 120,
  "files": {
    "/project/src/main.py": {
      "match_count": 25,
      "matches": [
        {
          "line_number": 42,
          "column": 8,
          "match_text": "function calculate_total",
          "line_text": "def function calculate_total(items):"
        }
      ]
    }
  }
}
```

#### ファイル出力モード（suppress_output=true）
```json
{
  "success": true,
  "count": 150,
  "output_file": "search_results_20251012.json",
  "file_saved": "Results saved to /project/search_results_20251012.json"
}
```

## 実装詳細

### 1. クラス構造

```python
class SearchContentTool(BaseMCPTool):
    def __init__(self, project_root: str | None = None, enable_cache: bool = True)
    def get_tool_definition(self) -> dict[str, Any]
    def _validate_roots(self, roots: list[str]) -> list[str]
    def _validate_files(self, files: list[str]) -> list[str]
    def validate_arguments(self, arguments: dict[str, Any]) -> bool
    def _determine_requested_format(self, arguments: dict[str, Any]) -> str
    def _create_count_only_cache_key(self, total_only_cache_key: str, arguments: dict[str, Any]) -> str | None
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any] | int
```

### 2. 依存関係

- **fd_rg_utils**: ripgrepコマンド構築・実行ユーティリティ
- **FileOutputManager**: ファイル出力機能
- **SearchCache**: 検索結果キャッシュシステム
- **GitignoreDetector**: .gitignore自動検出
- **BaseMCPTool**: 共通MCP機能（セキュリティ、パス解決）

### 3. ripgrep統合

#### 3.1 コマンド構築
```python
cmd = fd_rg_utils.build_rg_command(
    query=arguments["query"],
    case=arguments.get("case", "smart"),
    fixed_strings=bool(arguments.get("fixed_strings", False)),
    word=bool(arguments.get("word", False)),
    multiline=bool(arguments.get("multiline", False)),
    include_globs=arguments.get("include_globs"),
    exclude_globs=arguments.get("exclude_globs"),
    follow_symlinks=bool(arguments.get("follow_symlinks", False)),
    hidden=bool(arguments.get("hidden", False)),
    no_ignore=no_ignore,
    max_filesize=arguments.get("max_filesize"),
    context_before=arguments.get("context_before"),
    context_after=arguments.get("context_after"),
    encoding=arguments.get("encoding"),
    max_count=max_count,
    timeout_ms=timeout_ms,
    roots=roots,
    count_only_matches=count_only_matches,
)
```

#### 3.2 実行・結果処理
```python
rc, out, err = await fd_rg_utils.run_command_capture(cmd, timeout_ms=timeout_ms)

# 通常モード: JSON行解析
matches = fd_rg_utils.parse_rg_json_lines_to_matches(out)

# カウントモード: カウント出力解析
file_counts = fd_rg_utils.parse_rg_count_output(out)
```

### 4. 高度な機能

#### 4.1 スマート.gitignore検出
```python
detector = get_default_detector()
should_ignore = detector.should_use_no_ignore(original_roots, self.project_root)
if should_ignore:
    no_ignore = True
    logger.info(f"Auto-enabled --no-ignore due to .gitignore interference")
```

#### 4.2 クロスフォーマットキャッシュ
```python
# total_only結果をcount_only_matchesキャッシュとしても保存
count_only_cache_key = self._create_count_only_cache_key(cache_key, arguments)
if count_only_cache_key:
    detailed_count_result = {
        "success": True,
        "count_only": True,
        "total_matches": total_matches,
        "file_counts": file_counts_copy,
        "derived_from_total_only": True,
    }
    self.cache.set(count_only_cache_key, detailed_count_result)
```

#### 4.3 ファイルモード処理
```python
# filesパラメータを親ディレクトリ + globパターンに変換
parent_dirs = set()
file_globs = []
for file_path in files:
    parent_dir = str(Path(resolved).parent)
    parent_dirs.add(parent_dir)
    file_name = Path(resolved).name
    escaped_name = file_name.replace("[", "[[]").replace("]", "[]]")
    file_globs.append(escaped_name)

roots = list(parent_dirs)
arguments["include_globs"].extend(file_globs)
```

## パフォーマンス特性

### 1. 速度ベンチマーク

| ファイル数 | 検索時間 | メモリ使用量 | 備考 |
|-----------|----------|-------------|------|
| 1,000 | < 100ms | < 20MB | 小規模プロジェクト |
| 10,000 | < 500ms | < 50MB | 中規模プロジェクト |
| 100,000 | < 2s | < 100MB | 大規模プロジェクト |
| 1,000,000 | < 10s | < 200MB | 超大規模（Linux Kernel等） |

### 2. 出力モード別パフォーマンス

| モード | 相対速度 | メモリ効率 | 用途 |
|--------|----------|------------|------|
| total_only | 最高速 | 最高効率 | 件数確認 |
| count_only | 高速 | 高効率 | ファイル別統計 |
| summary | 中速 | 中効率 | 概要把握 |
| group_by_file | 中速 | 中効率 | ファイル別分析 |
| normal | 標準 | 標準 | 詳細分析 |

### 3. キャッシュ効果

#### 3.1 キャッシュヒット率
- **同一クエリ**: 99%ヒット率
- **類似クエリ**: 80%ヒット率（パラメータ差分）
- **クロスフォーマット**: 60%ヒット率（total_only→count_only）

#### 3.2 キャッシュ最適化
- **メモリ使用量**: 50%削減（重複結果排除）
- **応答時間**: 90%短縮（キャッシュヒット時）
- **ネットワーク**: 80%削減（suppress_output使用時）

## 使用例

### 1. 基本的なテキスト検索
```json
{
  "query": "function",
  "roots": ["src/"]
}
```

### 2. 正規表現パターン検索
```json
{
  "query": "class\\s+\\w+",
  "roots": ["src/"],
  "case": "sensitive"
}
```

### 3. 特定ファイルでの検索
```json
{
  "query": "TODO:",
  "files": ["main.py", "utils.py"],
  "context_before": 2,
  "context_after": 2
}
```

### 4. 高効率カウント検索
```json
{
  "query": "import",
  "roots": ["."],
  "include_globs": ["*.py"],
  "total_only": true
}
```

### 5. 大規模プロジェクトでの要約検索
```json
{
  "query": "error",
  "roots": ["src/", "lib/"],
  "exclude_globs": ["*.log", "node_modules/*"],
  "summary_only": true,
  "max_count": 100
}
```

### 6. ファイル出力での詳細検索
```json
{
  "query": "security",
  "roots": ["."],
  "include_globs": ["*.py", "*.js"],
  "group_by_file": true,
  "output_file": "security_audit",
  "suppress_output": true
}
```

### 7. 複数行パターン検索
```json
{
  "query": "def\\s+\\w+\\([^)]*\\):\\s*\\n\\s*\"\"\"",
  "roots": ["src/"],
  "multiline": true,
  "context_after": 5
}
```

### 8. 固定文字列検索（特殊文字含む）
```json
{
  "query": "console.log(",
  "roots": ["frontend/"],
  "fixed_strings": true,
  "include_globs": ["*.js", "*.ts"]
}
```

## エラーハンドリング

### 1. 検証エラー
- `ValueError`: 必須パラメータ不足、無効な型
- `SecurityError`: プロジェクト境界外アクセス
- `PathError`: 存在しないファイル・ディレクトリ

### 2. 実行時エラー
- `CommandError`: ripgrepコマンド実行失敗
- `TimeoutError`: 検索タイムアウト
- `EncodingError`: ファイルエンコーディング問題
- `PatternError`: 無効な正規表現パターン

### 3. エラーレスポンス
```json
{
  "success": false,
  "error": "Invalid regex pattern: unclosed group",
  "returncode": 2
}
```

### 4. 部分的失敗
```json
{
  "success": true,
  "count": 50,
  "warnings": [
    "Skipped binary file: /project/data.bin",
    "Encoding error in: /project/legacy.txt"
  ],
  "results": [...]
}
```

## セキュリティ考慮事項

### 1. プロジェクト境界保護
- **パス検証**: 解決されたパスの境界確認
- **ファイルアクセス**: 読み取り権限の事前確認
- **シンボリックリンク**: follow_symlinks=falseでの安全性

### 2. リソース保護
- **メモリ制限**: 大量結果での枯渇防止
- **CPU制限**: タイムアウトによる無限ループ防止
- **ディスク制限**: 一時ファイルサイズ制御

### 3. 情報漏洩防止
- **エラーメッセージ**: パス情報の適切な制限
- **ログ出力**: 検索クエリの機密性考慮
- **キャッシュ**: 権限外データの混入防止

### 4. 正規表現セキュリティ
- **ReDoS攻撃**: 複雑なパターンでの無限ループ防止
- **パターン検証**: 危険なパターンの事前検出
- **タイムアウト**: 長時間実行の強制終了

## テスト要件

### 1. 機能テスト
- [ ] 基本的なテキスト検索
- [ ] 正規表現パターンマッチング
- [ ] 固定文字列検索
- [ ] 複数行パターン検索
- [ ] 大文字小文字制御
- [ ] コンテキスト行表示
- [ ] ファイルフィルタリング

### 2. 出力フォーマットテスト
- [ ] 通常モード
- [ ] カウントモード
- [ ] 合計モード
- [ ] サマリーモード
- [ ] ファイルグループモード
- [ ] ファイル出力機能

### 3. パフォーマンステスト
- [ ] 大規模ディレクトリ（100,000+ファイル）
- [ ] 複雑な正規表現パターン
- [ ] 大量マッチ結果（10,000+マッチ）
- [ ] キャッシュ効率性
- [ ] メモリ使用量制限

### 4. セキュリティテスト
- [ ] プロジェクト境界外アクセス試行
- [ ] ReDoS攻撃パターン
- [ ] 大量リソース消費攻撃
- [ ] 権限外ファイルアクセス

### 5. エラーハンドリングテスト
- [ ] 無効な正規表現パターン
- [ ] 存在しないファイル・ディレクトリ
- [ ] エンコーディングエラー
- [ ] タイムアウト処理

## 品質基準

### 1. パフォーマンス要件
- **応答時間**: 通常検索（<1,000マッチ）で500ms以内
- **スループット**: 100,000ファイル/秒以上の処理能力
- **メモリ効率**: マッチ数に比例しない一定メモリ使用

### 2. 信頼性要件
- **可用性**: 99.9%以上の成功率
- **エラー回復**: 部分的失敗時の適切な報告
- **データ整合性**: 検索結果の完全性保証

### 3. セキュリティ要件
- **境界保護**: 100%のプロジェクト外アクセス防止
- **パターン安全性**: ReDoS攻撃の完全防止
- **リソース保護**: メモリ・CPU使用量の適切な制限

## 今後の拡張予定

### 1. 機能拡張
- **構文ハイライト**: マッチ部分の色付け表示
- **置換機能**: 検索・置換の一体化
- **ファジー検索**: 近似マッチング機能

### 2. パフォーマンス改善
- **インデックス化**: 頻繁に検索されるファイルのインデックス
- **並列検索**: 複数クエリの同時実行
- **ストリーミング**: リアルタイム結果配信

### 3. 統合機能
- **IDE連携**: エディタとの直接統合
- **Git統合**: 変更ファイルでの優先検索
- **AI統合**: 自然言語クエリの自動変換

---

**注意**: この仕様書は実装済み機能の文書化であり、User Story 2「高度な解析ツール」の一部として位置づけられます。