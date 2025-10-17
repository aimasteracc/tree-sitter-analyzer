# 設定ファイルガイド

## 概要

互換性テストシステムでは、複数の設定ファイルを使用してテストの動作をカスタマイズします。このガイドでは、各設定ファイルの詳細な説明と使用方法を提供します。

## 📋 設定ファイル一覧

### 1. `cli_test_cases.json` - CLIテストケース設定
### 2. `mcp_test_cases.json` - MCPテストケース設定
### 3. `config.json` - 全体設定
### 4. `requirements.txt` - 依存関係設定

---

## 🎯 CLIテストケース設定 (`cli_test_cases.json`)

### 基本構造

```json
{
  "cli_test_cases": [...],
  "error_test_cases": [...],
  "test_categories": {...},
  "global_settings": {...}
}
```

### テストケース定義

#### 通常テストケース (`cli_test_cases`)

```json
{
  "test_id": "CLI-001-summary",
  "name": "basic_summary",
  "description": "基本サマリー出力",
  "template": "{file_path} --summary",
  "parameters": {
    "file_path": "examples/BigService.java"
  },
  "expected_success": true,
  "category": "basic",
  "timeout": 30
}
```

**フィールド説明:**

- `test_id` (必須): テストケースの一意識別子
- `name` (必須): テストケースの短縮名
- `description` (必須): テストケースの説明
- `template` (必須): コマンドテンプレート（パラメータ置換対応）
- `parameters` (オプション): テンプレートで使用するパラメータ
- `expected_success` (オプション): 期待される成功/失敗（デフォルト: true）
- `category` (オプション): テストカテゴリ（デフォルト: "default"）
- `timeout` (オプション): タイムアウト秒数（デフォルト: 30）

#### エラーテストケース (`error_test_cases`)

```json
{
  "test_id": "CLI-E001-invalid-file",
  "name": "error_invalid_file",
  "description": "存在しないファイル",
  "template": "{file_path} --summary",
  "parameters": {
    "file_path": "nonexistent/file.java"
  },
  "expected_success": false,
  "category": "error",
  "timeout": 10
}
```

### テンプレートシステム

#### パラメータ置換

テンプレート文字列内の `{parameter_name}` を、`parameters` オブジェクトの値で置換します。

```json
{
  "template": "{file_path} --table={format} --start-line {start_line}",
  "parameters": {
    "file_path": "examples/BigService.java",
    "format": "json",
    "start_line": "1"
  }
}
```

↓ 生成されるコマンド:
```bash
examples/BigService.java --table=json --start-line 1
```

#### 利用可能なパラメータ例

- `file_path`: 分析対象ファイルパス
- `format`: 出力フォーマット（full, compact, csv, json等）
- `start_line`, `end_line`: 行範囲指定
- `start_column`, `end_column`: 列範囲指定
- `query_key`: クエリキー（methods, class, field等）

### カテゴリ設定 (`test_categories`)

```json
{
  "test_categories": {
    "basic": {
      "description": "基本機能テスト",
      "priority": 1
    },
    "table": {
      "description": "テーブル出力テスト",
      "priority": 2
    },
    "error": {
      "description": "エラーハンドリングテスト",
      "priority": 7
    }
  }
}
```

**フィールド説明:**

- `description`: カテゴリの説明
- `priority`: 実行優先度（数値が小さいほど高優先度）

### グローバル設定 (`global_settings`)

```json
{
  "global_settings": {
    "default_timeout": 30,
    "max_retries": 3,
    "encoding": "utf-8",
    "log_level": "INFO"
  }
}
```

**フィールド説明:**

- `default_timeout`: デフォルトタイムアウト秒数
- `max_retries`: 最大リトライ回数
- `encoding`: 文字エンコーディング
- `log_level`: ログレベル（DEBUG, INFO, WARNING, ERROR）

---

## 🔄 MCPテストケース設定 (`mcp_test_cases.json`) ✨**新機能**

### 基本構造

```json
{
  "mcp_test_cases": [...],
  "error_test_cases": [...],
  "categories": {...}
}
```

### テストケース定義

#### 通常テストケース (`mcp_test_cases`)

```json
{
  "id": "MCP-001",
  "tool": "check_code_scale",
  "category": "analysis",
  "description": "コードスケール分析 - 基本テスト",
  "parameters": {
    "file_path": "examples/BigService.java",
    "include_complexity": true,
    "include_details": false,
    "include_guidance": true
  }
}
```

**フィールド説明:**

- `id` (必須): テストケースの一意識別子（MCP-XXX形式）
- `tool` (必須): 実行するMCPツール名
- `category` (必須): テストカテゴリ
- `description` (必須): テストケースの説明
- `parameters` (必須): ツールに渡すパラメータ

#### エラーテストケース (`error_test_cases`)

```json
{
  "id": "MCP-E001",
  "tool": "check_code_scale",
  "category": "analysis",
  "description": "存在しないファイルでのエラーテスト",
  "parameters": {
    "file_path": "nonexistent/file.java"
  },
  "expected_error": "FileNotFound"
}
```

### 対応MCPツール

#### 1. コード分析ツール (`analysis`)

```json
{
  "tool": "check_code_scale",
  "parameters": {
    "file_path": "examples/BigService.java",
    "language": "java",
    "include_complexity": true,
    "include_details": false,
    "include_guidance": true
  }
}
```

#### 2. 構造分析ツール (`structure`)

```json
{
  "tool": "analyze_code_structure",
  "parameters": {
    "file_path": "examples/Sample.java",
    "format_type": "full",
    "language": "java",
    "output_file": "structure_output.json",
    "suppress_output": false
  }
}
```

#### 3. コード抽出ツール (`extraction`)

```json
{
  "tool": "extract_code_section",
  "parameters": {
    "file_path": "examples/BigService.java",
    "start_line": 10,
    "end_line": 50,
    "start_column": 0,
    "end_column": 80,
    "format": "json"
  }
}
```

#### 4. クエリ実行ツール (`query`)

```json
{
  "tool": "query_code",
  "parameters": {
    "file_path": "examples/ModernJavaScript.js",
    "language": "javascript",
    "query_key": "methods",
    "query_string": "(function_declaration) @function",
    "filter": "name=main",
    "output_format": "json"
  }
}
```

#### 5. ファイル検索ツール (`search`)

```json
{
  "tool": "list_files",
  "parameters": {
    "roots": ["."],
    "pattern": "*.py",
    "glob": true,
    "types": ["f"],
    "extensions": ["py", "java"],
    "exclude": ["__pycache__", "*.pyc"],
    "depth": 3,
    "follow_symlinks": false,
    "hidden": false,
    "no_ignore": false,
    "size": ["+1K"],
    "changed_within": "1d",
    "limit": 100
  }
}
```

#### 6. コンテンツ検索ツール (`search`)

```json
{
  "tool": "search_content",
  "parameters": {
    "roots": ["tree_sitter_analyzer"],
    "files": ["specific_file.py"],
    "query": "def\\s+\\w+",
    "case": "smart",
    "fixed_strings": false,
    "word": false,
    "multiline": false,
    "include_globs": ["*.py"],
    "exclude_globs": ["*.log"],
    "context_before": 2,
    "context_after": 2,
    "max_count": 10,
    "total_only": false,
    "summary_only": false,
    "group_by_file": true
  }
}
```

#### 7. 複合検索ツール (`search`)

```json
{
  "tool": "find_and_grep",
  "parameters": {
    "roots": ["examples"],
    "pattern": "*.java",
    "glob": true,
    "extensions": ["java"],
    "exclude": ["*.tmp"],
    "depth": 2,
    "query": "public",
    "case": "smart",
    "context_before": 1,
    "context_after": 1,
    "total_only": false
  }
}
```

#### 8. プロジェクト管理ツール (`project`)

```json
{
  "tool": "set_project_path",
  "parameters": {
    "project_path": "/absolute/path/to/project"
  }
}
```

### カテゴリ設定 (`categories`)

```json
{
  "categories": {
    "analysis": {
      "name": "コード分析",
      "description": "コードの規模や複雑度を分析するツール",
      "tools": ["check_code_scale"]
    },
    "structure": {
      "name": "構造分析",
      "description": "コードの構造を分析し、表形式で出力するツール",
      "tools": ["analyze_code_structure"]
    },
    "extraction": {
      "name": "コード抽出",
      "description": "コードの特定部分を抽出するツール",
      "tools": ["extract_code_section"]
    },
    "query": {
      "name": "クエリ実行",
      "description": "tree-sitterクエリを実行してコード要素を検索するツール",
      "tools": ["query_code"]
    },
    "search": {
      "name": "検索機能",
      "description": "ファイルやコンテンツを検索するツール",
      "tools": ["list_files", "search_content", "find_and_grep"]
    },
    "project": {
      "name": "プロジェクト管理",
      "description": "プロジェクト設定を管理するツール",
      "tools": ["set_project_path"]
    }
  }
}
```

### MCPテスト実行オプション

#### カテゴリ別実行

```bash
# 分析機能のみ
uv run python mcp_test_direct.py --categories analysis

# 検索機能のみ
uv run python mcp_test_direct.py --categories search

# 複数カテゴリ
uv run python mcp_test_direct.py --categories analysis structure query
```

#### ツール指定実行

```bash
# 特定ツールのみ
uv run python mcp_test_direct.py --tools check_code_scale

# 複数ツール
uv run python mcp_test_direct.py --tools check_code_scale analyze_code_structure
```

#### テストID指定実行

```bash
# 特定テストケース
uv run python mcp_test_direct.py --test-ids MCP-001 MCP-002

# エラーテストケース
uv run python mcp_test_direct.py --test-ids MCP-E001
```

---

## ⚙️ 全体設定 (`config.json`)

### 基本構造

```json
{
  "test_settings": {...},
  "mcp_settings": {...},
  "cli_settings": {...},
  "comparison_settings": {...},
  "report_settings": {...}
}
```

### テスト設定 (`test_settings`)

```json
{
  "test_settings": {
    "timeout": 30,
    "max_retries": 3,
    "log_level": "INFO",
    "output_formats": ["json", "html"],
    "enable_performance_logging": true
  }
}
```

**フィールド説明:**

- `timeout`: デフォルトタイムアウト秒数
- `max_retries`: 失敗時の最大リトライ回数
- `log_level`: ログレベル
- `output_formats`: 出力フォーマット（json, html）
- `enable_performance_logging`: パフォーマンスログの有効化

### MCP設定 (`mcp_settings`) ✨**実装済み**

```json
{
  "mcp_settings": {
    "project_root_auto_detect": true,
    "normalize_paths": true,
    "handle_total_only_results": true,
    "test_case_file": "mcp_test_cases.json",
    "color_output": true,
    "progress_display": true,
    "category_summary": true,
    "tool_filtering": {
      "enabled": true,
      "default_tools": ["check_code_scale", "analyze_code_structure"],
      "exclude_tools": []
    },
    "execution_settings": {
      "timeout_per_test": 30,
      "delay_between_tests": 0.05,
      "max_parallel_tests": 1
    },
    "error_handling": {
      "continue_on_error": true,
      "log_errors": true,
      "save_error_details": true,
      "treat_expected_errors_as_success": true
    },
    "output_settings": {
      "save_individual_results": true,
      "generate_summary": true,
      "normalize_timestamps": true,
      "normalize_execution_times": true
    }
  }
}
```

**フィールド説明:**

- `project_root_auto_detect`: プロジェクトルートの自動検出
- `normalize_paths`: パスの正規化
- `handle_total_only_results`: total_only結果の処理
- `test_case_file`: MCPテストケースファイル名
- `color_output`: 色付きログの有効化
- `progress_display`: 進捗表示の有効化
- `category_summary`: カテゴリ別サマリーの表示
- `tool_filtering`: ツールフィルタリング設定
- `execution_settings`: 実行設定
- `error_handling`: エラーハンドリング設定
- `output_settings`: 出力設定

### CLI設定 (`cli_settings`)

```json
{
  "cli_settings": {
    "resolve_relative_paths": true,
    "normalize_output": true,
    "parse_json_output": true,
    "encoding": "utf-8"
  }
}
```

**フィールド説明:**

- `resolve_relative_paths`: 相対パスの解決
- `normalize_output`: 出力の正規化
- `parse_json_output`: JSON出力の解析
- `encoding`: 文字エンコーディング

### 比較設定 (`comparison_settings`)

```json
{
  "comparison_settings": {
    "tolerance": 0.001,
    "ignore_timestamps": true,
    "ignore_execution_times": true,
    "normalize_file_paths": true
  }
}
```

**フィールド説明:**

- `tolerance`: 数値比較の許容誤差
- `ignore_timestamps`: タイムスタンプの無視
- `ignore_execution_times`: 実行時間の無視
- `normalize_file_paths`: ファイルパスの正規化

### レポート設定 (`report_settings`)

```json
{
  "report_settings": {
    "generate_html": true,
    "generate_json": true,
    "include_winmerge_files": true,
    "compatibility_thresholds": {
      "excellent": 0.95,
      "good": 0.90,
      "acceptable": 0.80,
      "poor": 0.70
    }
  }
}
```

**フィールド説明:**

- `generate_html`: HTMLレポートの生成
- `generate_json`: JSONレポートの生成
- `include_winmerge_files`: WinMergeファイルの生成
- `compatibility_thresholds`: 互換性評価の閾値

---

## 📦 依存関係設定 (`requirements.txt`)

```txt
# Tree-sitter Analyzer 互換性テスト用依存関係
httpx>=0.24.0
deepdiff>=6.0.0
pytest>=7.0.0
pytest-asyncio>=0.21.0
tree-sitter-analyzer[mcp]>=1.6.1
colorama>=0.4.6
```

**パッケージ説明:**

- `httpx`: HTTP通信ライブラリ
- `deepdiff`: 深い差分比較
- `pytest`: テストフレームワーク
- `pytest-asyncio`: 非同期テスト対応
- `tree-sitter-analyzer[mcp]`: メインパッケージ（MCP機能付き）
- `colorama`: 色付きログ対応

---

## 🔧 カスタマイズ例

### CLIテストケースの追加

```json
{
  "test_id": "CLI-021-custom-test",
  "name": "custom_analysis",
  "description": "カスタム分析テスト",
  "template": "{file_path} --custom-option {option_value}",
  "parameters": {
    "file_path": "examples/CustomFile.java",
    "option_value": "special"
  },
  "expected_success": true,
  "category": "custom",
  "timeout": 45
}
```

### MCPテストケースの追加

```json
{
  "id": "MCP-021",
  "tool": "check_code_scale",
  "category": "custom",
  "description": "カスタムコード分析テスト",
  "parameters": {
    "file_path": "examples/CustomFile.java",
    "include_complexity": true,
    "include_details": true,
    "include_guidance": false
  }
}
```

### 新しいカテゴリの追加

#### CLIテストカテゴリ
```json
{
  "test_categories": {
    "custom": {
      "description": "カスタム機能テスト",
      "priority": 8
    }
  }
}
```

#### MCPテストカテゴリ
```json
{
  "categories": {
    "custom": {
      "name": "カスタム機能",
      "description": "カスタム機能のテスト",
      "tools": ["check_code_scale", "analyze_code_structure"]
    }
  }
}
```

### タイムアウト設定の調整

```json
{
  "global_settings": {
    "default_timeout": 60,
    "max_retries": 5
  },
  "mcp_settings": {
    "execution_settings": {
      "timeout_per_test": 45,
      "delay_between_tests": 0.1
    }
  }
}
```

---

## 🚨 注意事項

### 1. JSON構文の正確性

- JSONファイルは厳密な構文に従います
- 末尾のカンマは禁止
- 文字列は必ずダブルクォートで囲みます

### 2. テストID命名規則

#### CLIテスト
- 通常テスト: `CLI-XXX-description`
- エラーテスト: `CLI-EXXX-description`

#### MCPテスト
- 通常テスト: `MCP-XXX`
- エラーテスト: `MCP-EXXX`
- 一意性を保ちます

### 3. ファイルパス指定

- プロジェクトルートからの相対パスを推奨
- Windows/Linux両対応のため、スラッシュ（/）を使用

### 4. パラメータ命名

- 英数字とアンダースコア（_）のみ使用します
- 予約語（template, test_id等）は避けます

---

## 🔍 設定検証

### JSON構文チェック

```bash
# 構文チェック
python -m json.tool cli_test_cases.json
python -m json.tool config.json

# テストケースローダーでの検証
uv run python test_case_loader.py
```

### 設定の動作確認

#### CLIテスト
```bash
# 設定ファイルの読み込み確認
uv run python cli_test.py --list-categories

# 特定カテゴリの動作確認
uv run python cli_test.py --categories basic --verbose
```

#### MCPテスト
```bash
# MCPテストケースの確認
uv run python mcp_test_direct.py --categories analysis --verbose

# 利用可能なツールの確認
uv run python mcp_test_direct.py --tools check_code_scale --verbose

# 色付きログの動作確認
uv run python mcp_test_direct.py --test-ids MCP-001
```

---

## 📚 参考資料

- [JSON公式仕様](https://www.json.org/json-ja.html)
- [tree-sitter-analyzer CLI リファレンス](../../README.md)
- [tree-sitter-analyzer MCP ドキュメント](../../docs/api/mcp_tools_specification.md)
- [colorama ドキュメント](https://pypi.org/project/colorama/)
- [MCPテストケース設定例](mcp_test_cases.json)
- [アーキテクチャ図](ARCHITECTURE_DIAGRAMS.md)
- [簡素化バージョン管理ガイド](SIMPLE_VERSION_GUIDE.md)
- [メインREADME](README.md)

## 📋 実装状況

現在のconfig.jsonには以下の設定が実装されています：

### ✅ 実装済み設定
- `test_settings`: 基本テスト設定
- `mcp_settings`: MCP関連の全設定項目
- `cli_settings`: CLI関連設定
- `comparison_settings`: 比較処理設定
- `report_settings`: レポート生成設定

### 🔄 設定の使用状況
- **mcp_test_direct.py**: `mcp_settings`を使用
- **cli_test.py**: `cli_settings`を使用
- **compare_*.py**: `comparison_settings`を使用
- **unified_report.py**: `report_settings`を使用
- **config_manager.py**: 全設定の統合管理

### 📈 設定の拡張性
新しい設定項目は以下の手順で追加できます：
1. `config.json`に新しい設定セクションを追加
2. `config_manager.py`に読み込みメソッドを追加
3. 対応するスクリプトで設定を使用
4. このガイドドキュメントを更新