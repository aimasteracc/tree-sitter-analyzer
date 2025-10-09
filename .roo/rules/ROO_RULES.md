# ROO規則 - Tree-Sitter-Analyzer MCP最適化ガイド

## 基本原則

### 1. ファイル読取の優先順位
- **禁止**: 標準の`read_file`ツールをコードファイルの読取に使用すること
- **推奨**: tree-sitter-analyzer MCPツールを使用してコードファイルを読取すること
- **理由**: tree-sitter-analyzer MCPは構造化された解析とトークン効率化を提供

### 2. Tree-Sitter-Analyzer MCP使用規則

#### 2.1 コード構造解析の最適化
```markdown
# 推奨パターン: suppress_output + output_file
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: analyze_code_structure
  arguments:
    file_path: "target/file.py"
    format_type: "full"
    suppress_output: true
    output_file: "structure_analysis.md"
```

**利点**:
- トークン消費を大幅削減
- 構造情報を外部ファイルに保存
- 後続の読取で詳細情報を取得可能

#### 2.2 ファイル一覧取得の最適化
```markdown
# 推奨パターン: suppress_output + output_file
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: list_files
  arguments:
    roots: ["src"]
    extensions: ["py", "js", "java"]
    suppress_output: true
    output_file: "file_list.json"
```

**利点**:
- 大量のファイル一覧でもトークン消費を最小化
- ファイル詳細情報（サイズ、更新日時等）を外部ファイルに保存
- count_onlyモードでも対応

#### 2.3 段階的コード解析戦略
1. **第1段階**: `analyze_code_structure`で構造概要を取得
2. **第2段階**: 生成されたファイルを`read_file`で読取
3. **第3段階**: 必要に応じて`extract_code_section`で詳細取得

#### 2.4 効率的なツール選択

##### コード読取用ツール
- `analyze_code_structure`: 全体構造の把握
- `extract_code_section`: 特定行範囲の抽出
- `query_code`: 特定要素の検索（関数、クラス等）

##### ファイル検索用ツール
- `list_files`: ファイル一覧取得（fd使用）
  - `count_only: true`でカウントのみ取得
  - `suppress_output + output_file`で大量ファイル対応
- `search_content`: コンテンツ検索（ripgrep使用）
- `find_and_grep`: 2段階検索（fd + ripgrep）

### 3. トークン最適化戦略

#### 3.1 出力抑制の活用
```markdown
# 大きなファイルの場合
suppress_output: true
output_file: "analysis_result.md"
```

#### 3.2 フォーマット選択
- `full`: 詳細解析（小〜中規模ファイル）
- `compact`: 簡潔表示（中〜大規模ファイル）
- `csv`: データ処理用
- `json`: プログラム処理用

#### 3.3 検索最適化
```markdown
# 大量結果が予想される場合
summary_only: true
group_by_file: true
total_only: true  # カウントのみ必要な場合
```

#### 3.4 検索ツールでのファイル出力最適化
```markdown
# find_and_grep と search_content でのトークン節約
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: find_and_grep
  arguments:
    roots: ["src"]
    pattern: "*XXXX060*"
    glob: true
    query: "項目名|lblKoumokuName"
    case: "insensitive"
    suppress_output: true
    output_file: "search_results.json"

# または search_content でも同様
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: search_content
  arguments:
    roots: ["src"]
    query: "項目名|lblKoumokuName"
    case: "insensitive"
    summary_only: true
    suppress_output: true
    output_file: "content_search.json"
```

**利点**:
- 大量の検索結果でもトークン消費を最小化
- 詳細な結果をファイルに保存して後で参照可能
- JSONまたはMarkdown形式で自動保存
- 既存の検索最適化オプションと組み合わせ可能

#### 3.5 日本語検索でのトークン爆発対策
```markdown
# 危険: 汎用的な日本語単語での無制限検索
query: "項目名"
context_before: 3
context_after: 3
# → 大量マッチでトークン爆発

# 安全: 段階的アプローチ
# ステップ1: まずカウントのみ確認
total_only: true

# ステップ2: 必要に応じて制限付きで詳細取得
max_count: 10
summary_only: true
# コンテキスト行は最小限に抑制
```

### 4. 具体的使用パターン

#### 4.1 関連ファイル一括検索（推奨パターン）
```markdown
# 画面ID、機能名、クラス名等で関連ファイルを一括検索
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: search_content
  arguments:
    roots: ["src"]
    query: "画面ID"  # 画面ID例
    case: "insensitive"
    summary_only: true
    suppress_output: true
    output_file: "content_search.json"
```

**利点**:
- Controller、Service、HTML、JavaScript、Mapperなど関連ファイルを一度に特定
- 機能全体の構成を素早く把握
- 後続の詳細解析対象を効率的に絞り込み

**適用場面**:
- 新機能の調査開始時
- バグ修正対象の特定
- 既存機能の理解
- リファクタリング範囲の確認

#### 4.2 新しいコードベース調査
```markdown
1. search_content で関連ファイル一括検索（4.1参照）
2. list_files で全体構造把握
3. analyze_code_structure で主要ファイル解析
4. extract_code_section で詳細確認
```

#### 4.3 バグ修正・機能追加
```markdown
1. search_content で関連コード一括検索（4.1参照）
2. analyze_code_structure で影響範囲確認
3. query_code で依存関係調査
4. extract_code_section で実装詳細取得
```

#### 4.4 リファクタリング
```markdown
1. search_content で対象機能の関連ファイル特定（4.1参照）
2. find_and_grep で詳細なコード特定
3. analyze_code_structure で構造解析
4. query_code で関数・クラス抽出
5. 段階的な変更実装
```

### 5. セキュリティとパフォーマンス

#### 5.1 プロジェクト境界
- 全てのMCPツールはプロジェクトルート内に制限
- `set_project_path`で明示的に境界設定可能

#### 5.2 リソース制限
- ファイルサイズ制限: `max_filesize`パラメータ使用
- 結果数制限: `limit`パラメータ使用
- タイムアウト: `timeout_ms`パラメータ使用

#### 5.3 キャッシュ活用
- tree-sitter解析結果は自動キャッシュ
- 同一ファイルの再解析は高速化

### 6. エラーハンドリング

#### 6.1 一般的なエラー対応
- ファイルが見つからない → `list_files`で存在確認
- 解析失敗 → 言語指定を明示的に設定
- メモリ不足 → `suppress_output: true`使用

#### 6.2 大規模ファイル対応
```markdown
# 大規模ファイルの場合
1. check_code_scale でサイズ確認
2. extract_code_section で部分読取
3. 必要に応じて複数回に分割
```

### 7. 言語別最適化

#### 7.1 Python
- クラス・関数定義: `query_code`で効率的抽出
- インポート解析: `search_content`でパターン検索

#### 7.2 JavaScript/TypeScript
- コンポーネント構造: `analyze_code_structure`で全体把握
- 型定義: `query_code`で型情報抽出

#### 7.3 Java
- パッケージ構造: `list_files`で階層確認
- クラス関係: `analyze_code_structure`で依存関係把握

### 8. 禁止事項

#### 8.1 非効率なパターン
- 大きなファイルでの`read_file`直接使用
- `suppress_output: false`での大量データ取得
- 不必要な`format_type: full`使用

#### 8.2 セキュリティ違反
- プロジェクトルート外へのアクセス試行
- 過度なリソース消費（無制限検索等）

#### 8.3 トークン爆発を引き起こす危険なパターン
- **汎用的な日本語単語での無制限検索**
  ```markdown
  # 危険な例: 「項目名」「データ」「処理」「画面」等の汎用語
  query: "項目名"
  context_before: 3
  context_after: 3
  # → 大量のマッチと膨大なコンテキスト出力でトークン爆発
  ```
- **コンテキスト行指定での大量マッチ検索**
- **出力制限なしでの広範囲検索**

### 9. ベストプラクティス

#### 9.1 効率的なワークフロー
1. **計画**: 必要な情報を明確化
2. **概要**: `analyze_code_structure`で全体把握
3. **詳細**: 必要な部分のみ`extract_code_section`
4. **検索**: `search_content`で関連コード発見
5. **実装**: 段階的な変更適用

#### 9.2 トークン節約
- `suppress_output: true`の積極活用
- `summary_only: true`での概要確認
- 適切な`format_type`選択

#### 9.3 品質保証
- 変更前の構造解析保存
- 影響範囲の事前確認
- 段階的テスト実行

### 10. 実用的な使用例

#### 10.1 大規模プロジェクトの初期調査
```markdown
# ステップ1: プロジェクト全体のファイル構造把握
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: list_files
  arguments:
    roots: ["."]
    extensions: ["py", "js", "ts", "java"]
    types: ["f"]
    limit: 100

# ステップ2: 主要ファイルの構造解析（トークン節約）
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: analyze_code_structure
  arguments:
    file_path: "src/main.py"
    format_type: "compact"
    suppress_output: true
    output_file: "main_structure.md"

# ステップ3: 生成されたファイルを読取
read_file:
  path: "main_structure.md"
```

#### 10.2 特定機能の実装場所特定
```markdown
# ステップ1: 関数名で検索
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: search_content
  arguments:
    roots: ["src"]
    query: "def process_data|function processData|processData\\s*\\("
    case: "insensitive"
    summary_only: true

# ステップ2: 該当ファイルの詳細解析
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: query_code
  arguments:
    file_path: "src/data_processor.py"
    query_key: "functions"
    filter: "name=~process*"
```

#### 10.3 バグ修正のための影響範囲調査
```markdown
# ステップ1: 問題のある関数を特定（トークン節約版）
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: find_and_grep
  arguments:
    roots: ["src"]
    extensions: ["py"]
    query: "calculate_total"
    context_before: 3
    context_after: 3
    suppress_output: true
    output_file: "bug_analysis.json"

# ステップ2: 依存関係の調査（トークン節約版）
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: search_content
  arguments:
    roots: ["src", "tests"]
    query: "import.*calculate_total|from.*calculate_total"
    group_by_file: true
    suppress_output: true
    output_file: "dependency_analysis.json"

# ステップ3: 保存された結果を読取
read_file:
  path: "bug_analysis.json"
read_file:
  path: "dependency_analysis.json"
```

#### 10.4 コードレビュー準備
```markdown
# ステップ1: 変更されたファイルの構造確認
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: analyze_code_structure
  arguments:
    file_path: "src/updated_module.py"
    format_type: "full"
    output_file: "review_structure.json"
    suppress_output: true

# ステップ2: 複雑度の高いメソッド特定
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: check_code_scale
  arguments:
    file_path: "src/updated_module.py"
```

### 11. 高度なテクニック

#### 11.1 条件付きファイル処理
```markdown
# 大きなファイルかどうかを事前チェック
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: check_code_scale
  arguments:
    file_path: "large_file.py"

# 結果に基づいて処理方法を選択
# - 小さい場合: analyze_code_structure (full)
# - 大きい場合: analyze_code_structure (suppress_output: true)
```

#### 11.2 段階的コード読取
```markdown
# ステップ1: 概要把握
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: analyze_code_structure
  arguments:
    file_path: "complex_module.py"
    format_type: "compact"

# ステップ2: 興味のある部分の詳細取得
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: extract_code_section
  arguments:
    file_path: "complex_module.py"
    start_line: 45
    end_line: 80
```

#### 11.3 パフォーマンス最適化検索
```markdown
# 大量の結果が予想される場合
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: search_content
  arguments:
    roots: ["src"]
    query: "TODO|FIXME|BUG"
    total_only: true  # カウントのみ取得

# 必要に応じて詳細取得（トークン節約版）
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: search_content
  arguments:
    roots: ["src"]
    query: "TODO|FIXME|BUG"
    max_count: 10
    summary_only: true
    suppress_output: true
    output_file: "todo_analysis.json"

# または find_and_grep での複合検索（トークン節約版）
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: find_and_grep
  arguments:
    roots: ["src"]
    extensions: ["py", "js", "java"]
    query: "TODO|FIXME|BUG"
    max_count: 20
    group_by_file: true
    suppress_output: true
    output_file: "comprehensive_todo.json"
```

### 12. トラブルシューティング

#### 12.1 メモリ不足対策
```markdown
# 問題: 大きなファイルでメモリ不足
# 解決策1: suppress_output使用
suppress_output: true
output_file: "temp_analysis.md"

# 解決策2: 部分読取
extract_code_section:
  start_line: 1
  end_line: 100
```

#### 12.2 検索結果が多すぎる場合
```markdown
# 問題: 検索結果が膨大
# 解決策1: summary_only使用
summary_only: true

# 解決策2: ファイル種別制限
include_globs: ["*.py"]
exclude_globs: ["*test*", "*__pycache__*"]

# 解決策3: 結果数制限
max_count: 20
```

#### 12.3 言語検出失敗
```markdown
# 問題: ファイル形式が正しく認識されない
# 解決策: 明示的に言語指定
language: "python"
# または
language: "javascript"
```

### 13. 統合ワークフロー例

#### 13.1 新機能開発フロー
```markdown
1. 要件分析
   - search_content で類似機能検索
   - analyze_code_structure で既存構造把握

2. 設計
   - query_code で関連クラス・関数抽出
   - find_and_grep でパターン調査

3. 実装
   - extract_code_section で参考コード取得
   - 段階的な実装とテスト

4. テスト
   - search_content でテストパターン検索
   - analyze_code_structure で新コード検証
```

#### 13.2 リファクタリングフロー
```markdown
1. 現状分析
   - analyze_code_structure で全体構造把握
   - check_code_scale で複雑度確認

2. 影響範囲調査
   - search_content で依存関係特定
   - find_and_grep で使用箇所検索

3. 段階的変更
   - extract_code_section で詳細確認
   - 小さな単位での変更実装

4. 検証
   - analyze_code_structure で変更後構造確認
   - search_content で残存問題検索
```

### 14. 日本語検索でのトークン爆発対策

#### 14.1 危険な汎用語リスト
以下の日本語単語は大量マッチを引き起こしやすく、注意が必要:
- **UI関連**: 「項目名」「画面」「ボタン」「フィールド」「入力」
- **データ関連**: 「データ」「情報」「値」「内容」「結果」
- **処理関連**: 「処理」「実行」「呼び出し」「取得」「設定」
- **汎用語**: 「名前」「ID」「番号」「コード」「種類」

#### 14.2 安全な検索戦略

##### 14.2.1 段階的検索アプローチ
```markdown
# ステップ1: 影響範囲の事前確認
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: search_content
  arguments:
    roots: ["src"]
    query: "項目名"
    total_only: true

# ステップ2: 結果数に応じた対応
# - 10件以下: 通常検索
# - 11-50件: summary_only + max_count制限
# - 51件以上: より具体的な検索条件に変更
```

##### 14.2.2 検索条件の具体化
```markdown
# 危険: 汎用的すぎる検索
query: "項目名"

# 安全: より具体的な検索
query: "項目名.*設定|項目名.*取得|setItemName|getItemName"
# または特定のコンテキストに限定
query: "class.*項目名|function.*項目名|def.*項目名"
```

##### 14.2.3 ファイル種別による制限
```markdown
# 危険: 全ファイル対象
roots: ["src"]

# 安全: ファイル種別を限定
include_globs: ["*.java", "*.py"]
exclude_globs: ["*.log", "*.txt", "*.md", "*test*"]
```

#### 14.3 トークン効率化テクニック

##### 14.3.1 出力制限の組み合わせ
```markdown
# 最も安全なパターン
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: search_content
  arguments:
    roots: ["src"]
    query: "項目名"
    case: "insensitive"
    max_count: 15          # 結果数制限
    summary_only: true     # 概要のみ
    group_by_file: true    # ファイル別グループ化
    include_globs: ["*.java", "*.py"]  # ファイル種別制限
    # context_before/afterは指定しない
```

##### 14.3.2 段階的詳細化
```markdown
# ステップ1: 概要把握（トークン節約版）
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: search_content
  arguments:
    roots: ["src"]
    query: "項目名"
    summary_only: true
    max_count: 20
    suppress_output: true
    output_file: "overview_search.json"

# ステップ2: 特定ファイルの詳細確認（必要な場合のみ）
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: search_content
  arguments:
    files: ["src/specific_file.java"]  # 特定ファイルのみ
    query: "項目名"
    context_before: 2
    context_after: 2
    max_count: 5
    suppress_output: true
    output_file: "detailed_search.json"

# ステップ3: 保存された結果を読取
read_file:
  path: "overview_search.json"
read_file:
  path: "detailed_search.json"
```

#### 14.4 実践的な対策例

##### 14.4.1 UI関連の調査
```markdown
# 危険なパターン
query: "画面"
context_before: 3
context_after: 3

# 安全なパターン
query: "画面.*ID|ScreenId|screen_id|画面クラス"
max_count: 20
summary_only: true
include_globs: ["*.java", "*.js", "*.vue"]
```

##### 14.4.2 データ処理の調査
```markdown
# 危険なパターン
query: "データ"

# 安全なパターン
query: "データ.*処理|DataProcessor|data_handler|データベース"
total_only: true  # まずカウントのみ確認
```

##### 14.4.3 機能特定の調査
```markdown
# 危険なパターン
query: "処理"
context_before: 5
context_after: 5

# 安全なパターン
# ステップ1: 特定の処理パターンに絞り込み
query: "処理.*メソッド|process.*function|def.*process"
summary_only: true

# ステップ2: 必要に応じて特定ファイルの詳細確認
```

#### 14.5 緊急時の対処法

##### 14.5.1 トークン爆発が発生した場合
1. **即座に検索を中止**（可能な場合）
2. **より具体的な検索条件に変更**
3. **`total_only: true`で影響範囲を事前確認**
4. **段階的に詳細化**

##### 14.5.2 代替アプローチ
```markdown
# 汎用語での検索が必要な場合の代替手法
# 1. ファイル一覧から対象を絞り込み
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: list_files
  arguments:
    roots: ["src"]
    pattern: "*Item*|*項目*"
    glob: true

# 2. 特定ファイルでの詳細検索
# 3. query_codeでの構造的検索
```

#### 14.6 予防策チェックリスト

検索実行前の確認事項:
- [ ] 検索語が汎用的すぎないか？
- [ ] `total_only: true`で事前確認したか？
- [ ] ファイル種別を適切に制限したか？
- [ ] `max_count`で結果数を制限したか？
- [ ] `context_before/after`は本当に必要か？
- [ ] `summary_only`で十分ではないか？

### 15. 新機能: 検索ツールでのファイル出力最適化

#### 15.1 対応ツール
- [`find_and_grep`](tree_sitter_analyzer/mcp/tools/find_and_grep_tool.py): ファイル検索 + コンテンツ検索の2段階検索
- [`search_content`](tree_sitter_analyzer/mcp/tools/search_content_tool.py): コンテンツ検索

#### 15.2 新パラメータ
- `output_file`: 結果をファイルに保存（拡張子自動検出）
- `suppress_output`: `output_file`指定時に詳細出力を抑制してトークン節約

#### 15.3 推奨使用パターン

##### 15.3.1 大量検索結果の処理
```markdown
# 従来の問題: 大量の検索結果でトークン爆発
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: find_and_grep
  arguments:
    roots: ["."]
    pattern: "*XXXX060*"
    query: "项目名|lblKoumokuName"
    # → 大量の出力でトークン消費

# 新しい解決策: ファイル出力でトークン節約
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: find_and_grep
  arguments:
    roots: ["."]
    pattern: "*XXXX060*"
    query: "项目名|lblKoumokuName"
    case: "insensitive"
    group_by_file: true
    suppress_output: true
    output_file: "search_results.json"

# 後で詳細を確認
read_file:
  path: "search_results.json"
```

##### 15.3.2 段階的検索戦略
```markdown
# ステップ1: 概要確認（トークン節約）
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: search_content
  arguments:
    roots: ["src"]
    query: "特定の機能名"
    summary_only: true
    suppress_output: true
    output_file: "phase1_overview.json"

# ステップ2: 詳細検索（必要な場合のみ）
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: find_and_grep
  arguments:
    roots: ["src"]
    extensions: ["java", "html", "js"]
    query: "特定の機能名"
    context_before: 3
    context_after: 3
    suppress_output: true
    output_file: "phase2_detailed.json"

# ステップ3: 結果の段階的確認
read_file:
  path: "phase1_overview.json"
# 必要に応じて詳細も確認
read_file:
  path: "phase2_detailed.json"
```

#### 15.4 ファイル形式の自動選択
- JSON形式: 構造化データとして保存、プログラム処理に適している
- Markdown形式: 人間が読みやすい形式、ドキュメント化に適している
- 拡張子は内容に基づいて自動決定

#### 15.5 既存オプションとの組み合わせ
```markdown
# 最適化された検索パターン
use_mcp_tool:
  server_name: tree-sitter-analyzer
  tool_name: find_and_grep
  arguments:
    roots: ["src"]
    pattern: "*Controller*"
    glob: true
    types: ["f"]
    extensions: ["java"]
    query: "特定のメソッド名"
    case: "insensitive"
    max_count: 50
    group_by_file: true
    summary_only: true      # 概要のみ
    suppress_output: true   # 出力抑制
    output_file: "controller_analysis.json"  # ファイル保存
```

## まとめ

ROOはtree-sitter-analyzer MCPツールを最大限活用し、効率的で安全なコード解析・編集を実現する。標準ツールよりもMCPツールを優先し、トークン効率化と構造化された解析を重視する。

**重要な原則**:
1. **コードファイル読取**: 必ずMCPツールを使用
2. **トークン節約**: `suppress_output: true` + `output_file`の活用
3. **段階的アプローチ**: 概要→詳細の順序で情報取得
4. **適切なツール選択**: 目的に応じた最適なMCPツール使用
5. **セキュリティ重視**: プロジェクト境界内での安全な操作
6. **日本語検索対策**: 汎用語での無制限検索を避け、段階的アプローチを採用
7. **NEW: 検索最適化**: `find_and_grep`と`search_content`でのファイル出力機能活用