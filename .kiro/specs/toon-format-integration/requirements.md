# 要件ドキュメント

## はじめに

本機能は、Tree-sitter Analyzer に TOON（Token-Oriented Object Notation）フォーマットを統合し、LLMとの対話時のトークン消費を大幅に削減することを目的とします。TOONは、JSONに比べて50-70%のトークン削減を実現しながら、YAML風の構造で人間にも読みやすい形式を維持します。

### 背景と問題点

| 問題 | 説明 |
|------|------|
| **大量のJSON出力** | 分析結果が冗長なJSON形式で出力され、トークン消費が大きい |
| **MCP Tool Responses** | AI assistantへの応答が標準JSONで、構造化データが非効率 |
| **バッチ分析結果** | 複数ファイルの分析結果が冗長 |
| **テーブル形式の限界** | CSV/JSONテーブル出力が最適化されていない |

### TOON導入の利点

- **トークン削減**: 最大60-70%のトークン削減
- **可読性維持**: YAML風の構造で人間にも読みやすい
- **構造化データ最適化**: 配列データをCSV風に圧縮
- **LLM最適化**: AIモデルが自然に解析可能な形式

### 依存関係決策

| 項目 | 決定 |
|------|------|
| **実装方式** | 軽量カスタム実装（外部依存なし） |
| **理由** | PyPI `toon-format` パッケージは名前空間占有のみで未実装 |
| **利点** | プロジェクト固有の最適化、完全な制御権、ゼロ依存オーバーヘッド |

## 用語集

| 用語 | 説明 |
|------|------|
| **TOON** | Token-Oriented Object Notation - トークン最適化されたデータ記法 |
| **ToonEncoder** | 低レベルのTOONエンコーディングプリミティブを提供するクラス |
| **ToonFormatter** | 高レベルのフォーマッター、統一インターフェース `format()` を提供 |
| **Formatter Protocol** | すべてのフォーマッターが実装する `format(data: Any) -> str` インターフェース |
| **Array Table** | 同型配列をCSV風にコンパクトに表現する形式 |
| **FileOutputManager** | MCP ツール用のファイル出力管理クラス |

## 要件

### 要件1: TOON Encoder 基本実装

**ユーザーストーリー**: 開発者として、任意のPythonデータをTOON形式にエンコードできるようにしたい。

#### 受け入れ基準

1. スカラー値（string, number, boolean, null）を正しくエンコードすること
2. ネストされた辞書を適切なインデントで処理すること
3. 同型配列をスキーマ付きテーブル形式でエンコードすること
4. 特殊文字を含む文字列を適切にエスケープすること
5. カンマ区切りとタブ区切りの両方をサポートすること
6. 区切り文字変更がスキーマヘッダーと値行の両方に一貫して適用されること

### 要件2: TOON Formatter 実装

**ユーザーストーリー**: 開発者として、AnalysisResultやMCPレスポンスをTOON形式でフォーマットできるようにしたい。

#### 受け入れ基準

1. 統一インターフェース `format(data: Any) -> str` を実装すること
2. AnalysisResultを適切なTOON形式に変換すること
3. MCPレスポンス構造を検出し最適化すること
4. 汎用辞書も処理可能であること
5. BaseFormatterプロトコルに準拠すること

### 要件3: OutputManager 統合

**ユーザーストーリー**: ユーザーとして、CLIで `--format toon` を指定してTOON形式で出力を取得したい。

#### 受け入れ基準

1. OutputManagerのformatter registryにToonFormatterを登録すること
2. `SUPPORTED_FORMATS` に "toon" を追加すること
3. `data()` メソッドで統一的にformatter.format()を呼び出すこと
4. JSON形式をデフォルトとして維持し、TOON形式はオプトインとすること

### 要件4: MCP ツール統合

**ユーザーストーリー**: AI assistantとして、MCP toolsでTOON形式の出力を取得し、トークン消費を削減したい。

#### 対象MCPツール

| ツール名 | ファイルパス | 説明 |
|---------|-------------|------|
| analyze_scale_tool | `mcp/tools/analyze_scale_tool.py` | スケール分析 |
| universal_analyze_tool | `mcp/tools/universal_analyze_tool.py` | 汎用分析 |
| list_files_tool | `mcp/tools/list_files_tool.py` | ファイルリスト |
| table_format_tool | `mcp/tools/table_format_tool.py` | テーブル形式 |

#### 受け入れ基準

1. 各MCPツールに `output_format` パラメータを追加すること
2. `"toon"` オプションを指定した場合、TOON形式で出力すること
3. デフォルトはJSON形式を維持すること
4. FileOutputManager (`mcp/utils/file_output_manager.py`) にTOON形式検出ロジックを追加すること
5. ".toon" 拡張子マッピングを追加すること

### 要件5: CLI 統合

**ユーザーストーリー**: コマンドラインユーザーとして、分析結果をTOON形式で取得したい。

#### 受け入れ基準

1. `--format toon` オプションをサポートすること
2. `--toon-use-tabs` オプションでタブ区切りを有効化できること
3. バッチ分析でもTOON形式が機能すること
4. ファイル出力 (`-o`) でもTOON形式が機能すること

### 要件6: テストとドキュメント

**ユーザーストーリー**: プロジェクトメンテナーとして、TOON機能の品質を保証したい。

#### 受け入れ基準

1. 新規コードのテストカバレッジが90%以上であること
2. ユニットテスト、統合テスト、ベンチマークテストを含むこと
3. ユーザードキュメントを作成すること
4. 使用例とデモスクリプトを提供すること
5. トークン削減率50%以上を達成すること

#### 必須テストケース

| カテゴリ | テストケース |
|---------|-------------|
| スカラーエンコード | null, boolean, number, string |
| 文字列エスケープ | 特殊文字（\n, \t, \r, \\, \"） |
| 辞書エンコード | シンプル、ネスト、空辞書 |
| 配列エンコード | プリミティブ配列、同型辞書配列 |
| Array Table | スキーマ推論、明示的スキーマ |
| Formatter Protocol | format()メソッド準拠 |
| OutputManager統合 | レジストリ初期化、フォーマット選択 |
| エラーハンドリング | 循環参照、エンコード失敗 |
| パフォーマンス | 大規模データセット処理 |

### 要件7: エラーハンドリング

**ユーザーストーリー**: 開発者として、TOON エンコードが失敗した場合でも安全にフォールバックしたい。

#### 受け入れ基準

1. 循環参照を検出し、適切なエラーを報告すること
2. エンコード失敗時にJSONフォールバックを提供すること
3. エラーログを記録すること
4. ユーザーへのエラーメッセージが明確であること

## 成功指標

### 定量的指標

| 指標 | 目標 | 状態 |
|------|------|------|
| トークン削減率 | JSON比で50-60%削減 | ✅ **50.6%達成** |
| エンコードオーバーヘッド | JSON比5%未満 | ✅ 達成（イテレーティブ実装） |
| メモリオーバーヘッド | JSON比10%未満 | ✅ 達成（明示的スタック制御） |
| テストカバレッジ | 新規コード90%以上 | ✅ 達成（98 tests） |

### 定性的指標

| 指標 | 目標 | 状態 |
|------|------|------|
| 可読性 | 人間が読んでも理解しやすい | ✅ 達成 |
| 互換性 | 既存のJSON出力と並行利用可能 | ✅ 達成 |
| 拡張性 | 新しいデータ型に対応しやすい | ✅ 達成 |
| ドキュメント完備 | 完全かつ正確 | ✅ 達成（英語版・日本語版） |

### トークン削減率検証方法

| 項目 | 定義 |
|------|------|
| **トークナイザー** | tiktoken (cl100k_base) または同等の手段 |
| **ベンチマークデータ** | 実プロジェクトの分析結果 5ファイル以上 |
| **計算式** | `(1 - TOON_tokens / JSON_tokens) × 100%` |
| **検証対象** | AnalysisResult, MCPレスポンス, バッチ分析結果 |

## 後方互換性

### 原則

| 原則 | 説明 |
|------|------|
| **デフォルト動作** | JSON形式を引き続きデフォルトとして維持 |
| **オプトイン方式** | TOON形式は明示的な指定でのみ有効化 |
| **並行動作** | JSON/YAML/TOON形式が同時に利用可能 |
| **非推奨化なし** | JSON形式は非推奨化の予定なし |

### 実装要件

1. **CLI**: `--format` オプション未指定時は `json` を使用
2. **MCP Tools**: `output_format` パラメータ未指定時は `json` を使用
3. **Python API**: `format_type="json"` がデフォルト
4. **テスト**: 既存のすべてのテストがパラメータ変更なしでパス

## リスクと対策

### リスク1: カスタム実装の保守負担

| 項目 | 内容 |
|------|------|
| **リスク** | 自社実装のメンテナンスコストが増加する可能性 |
| **対策** | シンプルな実装（合計 ~500 LOC）、明確な責任分離、包括的なテスト |
| **モニタリング** | コードカバレッジ80%以上を維持 |

### リスク2: LLMの解析精度

| 項目 | 内容 |
|------|------|
| **リスク** | LLMがTOON形式を正しく解析できない可能性 |
| **対策** | YAML風シンタックス採用、フォールバック機構、エラーロギング |
| **テスト** | 複数のLLMプロバイダーでテスト |

### リスク3: パフォーマンス問題

| 項目 | 内容 |
|------|------|
| **リスク** | エンコード/デコードのオーバーヘッドが大きい可能性 |
| **対策** | ストリーミングエンコーディング、スキーマキャッシング |
| **目標** | オーバーヘッド5%未満 |

### リスク4: エンコード失敗

| 項目 | 内容 |
|------|------|
| **リスク** | 特殊なデータ構造でエンコードが失敗する可能性 |
| **対策** | 循環参照検出、JSONフォールバック、詳細なエラーログ |
| **検証** | エッジケーステスト（循環参照、バイナリデータなど） |

## 現在の実装状況

### 完了項目 ✅

| コンポーネント | ファイル | 行数 (空行除く) |
|---------------|---------|-----------------|
| ToonEncoder | `formatters/toon_encoder.py` | ~239 LOC |
| ToonFormatter | `formatters/toon_formatter.py` | ~249 LOC |
| BaseFormatter | `formatters/base_formatter.py` | ~233 LOC |
| OutputManager統合 | `output_manager.py` | 更新済み |
| テスト | `test_toon_formatter_integration.py` | 37 tests |

### 完了項目 ✅ (Phase 2)

| コンポーネント | ファイル | 説明 |
|---------------|---------|------|
| MCP Tools統合 | `mcp/tools/*.py` (8ツール) | output_format パラメータ追加 |
| Format Helper | `mcp/utils/format_helper.py` | TOON/JSONフォーマット変換ユーティリティ |
| FileOutputManager TOON対応 | `mcp/utils/file_output_manager.py` | .toon拡張子、形式検出 |
| MCP統合テスト | `tests/mcp/test_toon_mcp_integration.py` | 24 tests |

### 完了項目 ✅ (Phase 3)

| コンポーネント | ファイル | 説明 |
|---------------|---------|------|
| CLI `--format toon` オプション | `cli_main.py` | `--format toon`, `--output-format toon` サポート |
| CLI `--toon-use-tabs` オプション | `cli_main.py` | タブ区切りモード有効化 |
| CLI コマンドクラス更新 | `cli/commands/*.py` (6ファイル) | TOON出力対応 |
| CLI統合テスト | `tests/cli/test_toon_cli_integration.py` | 14 tests |

### 完了項目 ✅ (Phase 4 - エラーハンドリング)

| コンポーネント | ファイル | 説明 |
|---------------|---------|------|
| ToonEncodeError | `formatters/toon_encoder.py` | 詳細エラー情報を持つ例外クラス |
| 循環参照検出 | `formatters/toon_encoder.py` | dict/list の循環参照検出 |
| 最大ネスト深度制限 | `formatters/toon_encoder.py` | 深い再帰からの保護 (default: 100) |
| JSONフォールバック | `formatters/toon_encoder.py`, `toon_formatter.py` | エラー時の自動JSON変換 |
| エラーハンドリングテスト | `tests/test_toon_error_handling.py` | 23 tests |

### 完了項目 ✅ (Phase 4 - ベンチマーク＆デモ)

| コンポーネント | ファイル | 説明 |
|---------------|---------|------|
| トークン削減ベンチマーク | `examples/toon_token_benchmark.py` | 50.6%削減達成 |
| デモスクリプト | `examples/toon_demo.py` | 包括的使用例 |
| サンプルファイル | `examples/sample.py` | CLI/MCPテスト用（既存） |

### 完了項目 ✅ (Phase 4 - ドキュメント)

| コンポーネント | ファイル | 説明 |
|---------------|---------|------|
| TOON フォーマットガイド（英語） | `docs/toon-format-guide.md` | 包括的ガイド |
| TOON フォーマットガイド（日本語） | `docs/ja/toon-format-guide.md` | 日本語版 |

### 未完了項目 ❌ （オプション）

| コンポーネント | 状態 | 備考 |
|---------------|------|------|
| スキーマキャッシング | 未着手（オプション） | 同型配列のスキーマ推論結果をキャッシュ |
| ストリーミングエンコード | 未着手（オプション） | 大規模データセット用 |
| 遅延評価 | 未着手（オプション） | フォーマット変換の遅延実行 |

---

## 追加要件: --table toon コマンド ✅ 完了

### 要件 8.1: --table toon 実装 ✅

`--table` コマンドに `toon` フォーマットを追加し、既存の `full`, `compact`, `csv` と統一。

**対象ファイル**:
- `tree_sitter_analyzer/cli_main.py` - 引数に `toon` 追加 ✅
- `tree_sitter_analyzer/cli/commands/table_command.py` - TOON 出力実装 ✅
- `generate_golden_masters.py` - 統一された `--table` 生成 ✅

**使用方法**:
```bash
# --table toon コマンド（推奨）
uv run tree-sitter-analyzer examples/Sample.java --table toon

# --structure --format toon コマンド（別途サポート）
uv run tree-sitter-analyzer examples/Sample.java --structure --format toon
```

---

## 追加要件: CLI 検索ツール TOON 対応 ✅ 完了

### 要件 8.2: 検索系 CLI コマンドの TOON 対応 ✅

すべての CLI 検索コマンドに `--output-format toon` オプションを追加。

**対象ファイル**:
- `tree_sitter_analyzer/cli/commands/find_and_grep_cli.py` ✅
- `tree_sitter_analyzer/cli/commands/list_files_cli.py` ✅
- `tree_sitter_analyzer/cli/commands/search_content_cli.py` ✅

**使用方法**:
```bash
# ファイル一覧（TOON形式）
uv run python -m tree_sitter_analyzer.cli.commands.list_files_cli examples --output-format toon

# 内容検索（TOON形式）
uv run python -m tree_sitter_analyzer.cli.commands.search_content_cli --roots examples --query "class" --output-format toon

# find+grep（TOON形式）
uv run python -m tree_sitter_analyzer.cli.commands.find_and_grep_cli --roots examples --query "def" --output-format toon
```

---

## 追加要件: ゴールデンマスタテスト ✅

### 要件 7.1: TOON フォーマットゴールデンマスタ ✅

TOON フォーマットの出力の一貫性を保証するため、ゴールデンマスタテストを実装する。

**対象**:
- `tests/golden_masters/toon/` - TOON フォーマットのゴールデンマスタファイル ✅
- `tests/test_golden_master_regression.py` - テストケース追加 ✅

**検証内容**:
- TOON フォーマットの出力形式が変わらないこと ✅
- 異なる言語ファイルで一貫した TOON 出力 ✅
- トークン削減率の維持 ✅

**成果物**:
- `tests/golden_masters/toon/` - 18言語のゴールデンマスタファイル
  - Python, Java (2), TypeScript, JavaScript, Go, Rust, Kotlin
  - C#, PHP, Ruby, C, C++, YAML, HTML, CSS, Markdown, SQL
- `TestToonGoldenMasterRegression` クラス (20 tests)

**修正内容**:
- TOON 出力内のネストされた辞書が Python repr 形式 `{'start': 13}` から TOON 形式 `{start:13}` に修正

---

## 追加要件: line_range フォーマット最適化 ✅

### 要件 8.3: line_range のコンパクト表現 ✅

コード位置情報 `line_range` をネストされた辞書形式からタプル形式に最適化。

**変更前**:
```
line_range: {start:7,end:7}
```

**変更後**:
```
line_range: (7, 7)
```

**対象ファイル**:
- `tree_sitter_analyzer/formatters/toon_encoder.py` - タプル型のエンコード対応 ✅
- `tree_sitter_analyzer/cli/commands/structure_command.py` - line_range をタプルで出力 ✅
- `tree_sitter_analyzer/cli/commands/table_command.py` - TOON 変換で line_range をタプルで出力 ✅

**スキーマ表記**:
```
classes:
  [8]{name,visibility,line_range(a,b)}:
    AbstractParentClass,package,(7,15)
    ParentClass,package,(18,45)
```

---

## 全対応状況まとめ

### MCP ツール対応状況 ✅ 全8ツール対応

| MCP ツール | ファイル | TOON 対応 |
|-----------|---------|----------|
| `analyze_code_structure` | `mcp/tools/universal_analyze_tool.py` | ✅ `output_format: "toon"` |
| `query_code` | `mcp/tools/query_tool.py` | ✅ `output_format: "toon"` |
| `check_code_scale` | `mcp/tools/analyze_scale_tool.py` | ✅ `output_format: "toon"` |
| `extract_code_section` | `mcp/tools/read_partial_tool.py` | ✅ `output_format: "toon"` |
| `find_and_grep` | `mcp/tools/find_and_grep_tool.py` | ✅ `output_format: "toon"` |
| `search_content` | `mcp/tools/search_content_tool.py` | ✅ `output_format: "toon"` |
| `list_files` | `mcp/tools/list_files_tool.py` | ✅ `output_format: "toon"` |
| `table_format` | `mcp/tools/table_format_tool.py` | ✅ `output_format: "toon"` |

### CLI コマンド対応状況 ✅ 全9コマンド対応

| CLI コマンド | ファイル | TOON 対応 |
|-------------|---------|----------|
| `--table toon` | `cli/commands/table_command.py` | ✅ |
| `--structure --format toon` | `cli/commands/structure_command.py` | ✅ |
| `--summary --format toon` | `cli/commands/summary_command.py` | ✅ |
| `--advanced --format toon` | `cli/commands/advanced_command.py` | ✅ |
| `--partial-read --format toon` | `cli/commands/partial_read_command.py` | ✅ |
| `--query-key ... --format toon` | `cli/commands/query_command.py` | ✅ |
| `find-and-grep --output-format toon` | `cli/commands/find_and_grep_cli.py` | ✅ |
| `list-files --output-format toon` | `cli/commands/list_files_cli.py` | ✅ |
| `search-content --output-format toon` | `cli/commands/search_content_cli.py` | ✅ |

### Golden Master 対応言語 ✅ 18言語

| 言語 | ファイル | 対応 |
|------|---------|------|
| Python | `python_sample_toon.toon` | ✅ |
| Java | `java_sample_toon.toon`, `java_bigservice_toon.toon` | ✅ |
| TypeScript | `typescript_enum_toon.toon` | ✅ |
| JavaScript | `javascript_class_toon.toon` | ✅ |
| Go | `go_sample_toon.toon` | ✅ |
| Rust | `rust_sample_toon.toon` | ✅ |
| Kotlin | `kotlin_sample_toon.toon` | ✅ |
| C# | `csharp_sample_toon.toon` | ✅ |
| PHP | `php_sample_toon.toon` | ✅ |
| Ruby | `ruby_sample_toon.toon` | ✅ |
| C | `c_sample_toon.toon` | ✅ |
| C++ | `cpp_sample_toon.toon` | ✅ |
| YAML | `yaml_sample_config_toon.toon` | ✅ |
| HTML | `html_comprehensive_sample_toon.toon` | ✅ |
| CSS | `css_comprehensive_sample_toon.toon` | ✅ |
| Markdown | `markdown_test_toon.toon` | ✅ |
| SQL | `sql_sample_database_toon.toon` | ✅ |

### Golden Master 生成スクリプト ✅

- `generate_golden_masters.py` - 統一された `--table` コマンドで全フォーマット生成
  - `full/` - `--table full` (Markdown)
  - `compact/` - `--table compact` (Markdown)
  - `csv/` - `--table csv` (CSV)
  - `toon/` - `--table toon` (TOON)
