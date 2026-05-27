# Tree-sitter Analyzer MCP Tools API Specification

**Version**: 1.13.0
**Date**: 2026-05-15
**Protocol**: Model Context Protocol (MCP) v1.0

## Overview

Tree-sitter Analyzer MCPサーバーは、AI統合コード解析のための55の専門ツール、2つのリソース、および2つのSMART workflowプロンプトを提供します。すべてのツールはMCP v1.0仕様に準拠し、統一されたエラーハンドリングとセキュリティ機能を実装しています。

### v1.13.0 Changes
- **40 new autonomous-development tools**: AST cache + CodeGraph parity + pre-edit safety + decision journal — see [Autonomous Development Tools (v1.13.0)](#autonomous-development-tools-v1130) section below for the full catalogue
- **`set_project_path` complemented (not removed)**: still works as a runtime tool for switching project root mid-session; new preferred path for startup config is the `TREE_SITTER_PROJECT_ROOT` env var or `--project-root` CLI flag. Registered via `server_utils/tool_registration.py` (bypass), not the canonical `_tool_registry.py`, which is why it doesn't appear in parity contract tests.
- **check_project_health tool**: Project-wide health report now returns compact `agent_summary` plus `agent_backlog` with MCP and CLI commands for autonomous agents
- **smart_context tool**: Single-call file profile combining health, exports, structure, dependencies, tests, edit risk, and compact `agent_summary`
- **safe_to_edit tool**: Pre-edit risk assessment — risk_level (safe/caution/dangerous), blast radius, test proximity, pre-edit checklist, and compact `agent_summary`
- **refactoring_suggestions tool**: AST-based refactoring suggestions with exact line ranges, extraction targets, priority scoring, class-split `recipe` guidance, and a compact `agent_summary` with next step, suggested tests, and stop condition
- **Extraction plans**: `check_file_health` returns compact `agent_summary`; D/F grade files also get structured extraction_plan with AST-based line numbers
- **36% schema compression**: tool descriptions reduced from 6858→4385 tokens (2.2% of 200K context)
- **Tool routing guide**: `get_project_overview` now returns compact `agent_summary` and `tool_routing` decision table for AI agents
- **list_agent_skills tool**: Project-local `.agents/skills` inventory with trigger text, read order, scripts, context needs, side effects, and completion-guidance gaps
- **get_agent_workflow tool**: MCP parity for the CLI SMART workflow pack, including safe-edit, retrieval, trace, and queue-boundary commands
- **advise_parser_readiness tool**: Local parser/plugin roadmap advisor using parser dependencies, plugin entry points, loader mappings, tests, golden masters, and upstream parser-risk signals
- **Response optimization**: `check_code_scale` caps `available_queries` at 15 (was 80+)

## Server Information

- **Name**: `tree-sitter-analyzer`
- **Version**: `1.13.0`
- **Protocol Version**: `2024-11-05`
- **Capabilities**: `tools`, `resources`, `logging`, `prompts`

## Authentication & Security

### Project Boundary Protection
すべてのツールは自動的にプロジェクト境界を検証し、不正なファイルアクセスを防止します。

### Input Validation
- パストラバーサル攻撃の防御
- ヌルバイト注入の防止
- Unicode正規化攻撃の対策
- 入力サイズ制限の適用

### Error Sanitization
エラーレスポンスから機密情報を自動的に除去し、安全なデバッグ情報のみを提供します。

## Tools

### 1. check_code_scale

**Purpose**: ファイル規模とコード複雑度の事前評価

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "file_path": {
      "type": "string",
      "description": "分析対象ファイルのパス"
    },
    "language": {
      "type": "string",
      "description": "プログラミング言語（自動検出可能）",
      "enum": ["java", "python", "javascript", "typescript", "go", "rust", "c", "cpp", "kotlin", "csharp", "ruby", "php", "swift", "sql", "html", "css", "yaml", "markdown"]
    },
    "include_complexity": {
      "type": "boolean",
      "description": "複雑度メトリクスを含める",
      "default": true
    },
    "include_details": {
      "type": "boolean",
      "description": "詳細要素情報を含める",
      "default": false
    },
    "include_guidance": {
      "type": "boolean",
      "description": "LLM解析ガイダンスを含める",
      "default": true
    }
  },
  "required": ["file_path"]
}
```

**Output Schema**:
```json
{
  "type": "object",
  "properties": {
    "success": {"type": "boolean"},
    "file_info": {
      "type": "object",
      "properties": {
        "path": {"type": "string"},
        "size_bytes": {"type": "integer"},
        "line_count": {"type": "integer"},
        "language": {"type": "string"}
      }
    },
    "scale_assessment": {
      "type": "object",
      "properties": {
        "category": {"type": "string", "enum": ["small", "medium", "large", "very_large"]},
        "recommended_strategy": {"type": "string"},
        "token_estimate": {"type": "integer"}
      }
    },
    "complexity_metrics": {
      "type": "object",
      "properties": {
        "total_elements": {"type": "integer"},
        "classes": {"type": "integer"},
        "methods": {"type": "integer"},
        "functions": {"type": "integer"}
      }
    },
    "llm_guidance": {
      "type": "object",
      "properties": {
        "recommended_approach": {"type": "string"},
        "workflow_steps": {"type": "array", "items": {"type": "string"}},
        "suggested_queries": {"type": "array", "items": {"type": "string"}},
        "available_queries": {"type": "array", "items": {"type": "string"}},
        "token_optimization": {"type": "string"}
      }
    }
  }
}
```

**Performance**: < 3秒  
**Security**: プロジェクト境界保護、パス検証

### 2. analyze_code_structure

**Purpose**: コード構造の詳細解析とテーブル形式出力

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "file_path": {
      "type": "string",
      "description": "分析対象ファイルのパス"
    },
    "format_type": {
      "type": "string",
      "description": "出力フォーマット",
      "enum": ["full", "compact", "csv"],
      "default": "full"
    },
    "language": {
      "type": "string",
      "description": "プログラミング言語（自動検出可能）"
    },
    "output_file": {
      "type": "string",
      "description": "出力ファイル名（オプション）"
    },
    "suppress_output": {
      "type": "boolean",
      "description": "レスポンス出力を抑制（トークン最適化）",
      "default": false
    },
    "output_format": {
      "type": "string",
      "enum": ["json", "toon"],
      "description": "出力フォーマット: 'toon' (デフォルト、50-70%トークン削減) または 'json'",
      "default": "toon"
    }
  },
  "required": ["file_path"]
}
```

**Output Schema**:
```json
{
  "type": "object",
  "properties": {
    "success": {"type": "boolean"},
    "analysis_result": {
      "type": "object",
      "properties": {
        "file_path": {"type": "string"},
        "language": {"type": "string"},
        "total_elements": {"type": "integer"},
        "format_type": {"type": "string"}
      }
    },
    "table_output": {
      "type": "string",
      "description": "フォーマット済みテーブル出力"
    },
    "next_steps": {
      "type": "array",
      "items": {"type": "string"},
      "description": "次のアクション提案（複雑度ホットスポットの抽出など）"
    },
    "output_file_path": {
      "type": "string",
      "description": "作成された出力ファイルのパス"
    }
  }
}
```

**Performance**: < 3秒  
**Token Optimization**: `suppress_output=true` + `output_file` でトークン使用量を大幅削減

### 3. extract_code_section

**Purpose**: 指定行範囲のコード抽出

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "file_path": {
      "type": "string",
      "description": "対象ファイルのパス"
    },
    "start_line": {
      "type": "integer",
      "description": "開始行番号（1ベース）",
      "minimum": 1
    },
    "end_line": {
      "type": "integer",
      "description": "終了行番号（1ベース、オプション）",
      "minimum": 1
    },
    "start_column": {
      "type": "integer",
      "description": "開始列番号（0ベース、オプション）",
      "minimum": 0
    },
    "end_column": {
      "type": "integer",
      "description": "終了列番号（0ベース、オプション）",
      "minimum": 0
    },
    "format": {
      "type": "string",
      "description": "出力フォーマット",
      "enum": ["text", "json", "raw"],
      "default": "text"
    },
    "output_file": {
      "type": "string",
      "description": "出力ファイル名（オプション）"
    },
    "suppress_output": {
      "type": "boolean",
      "description": "レスポンス出力を抑制",
      "default": false
    }
  },
  "required": ["file_path", "start_line"]
}
```

**Output Schema**:
```json
{
  "type": "object",
  "properties": {
    "success": {"type": "boolean"},
    "partial_content_result": {
      "type": "object",
      "properties": {
        "file_path": {"type": "string"},
        "start_line": {"type": "integer"},
        "end_line": {"type": "integer"},
        "total_lines": {"type": "integer"},
        "content": {"type": "string"},
        "format": {"type": "string"}
      }
    },
    "output_file_path": {
      "type": "string",
      "description": "作成された出力ファイルのパス"
    }
  }
}
```

**Performance**: < 3秒  
**Encoding**: 自動エンコーディング検出とUTF-8変換

### 4. query_code

**Purpose**: Tree-sitterクエリによるコード要素抽出

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "file_path": {
      "type": "string",
      "description": "対象ファイルのパス"
    },
    "language": {
      "type": "string",
      "description": "プログラミング言語（自動検出可能）"
    },
    "query_key": {
      "type": "string",
      "description": "定義済みクエリキー。共通: 'methods', 'classes', 'functions', 'imports', 'variables'。言語固有例: 'spring_service' (Java), 'decorator' (Python), 'goroutine' (Go), 'trait' (Rust), 'namespace' (C++/C#), 'interface' (TS/Kotlin)。無効なキーは利用可能な全クエリ一覧を返す"
    },
    "query_string": {
      "type": "string",
      "description": "カスタムTree-sitterクエリ文字列"
    },
    "filter": {
      "type": "string",
      "description": "結果フィルター式（例: 'name=main', 'name=~get*,public=true'）"
    },
    "result_format": {
      "type": "string",
      "enum": ["json", "summary"],
      "default": "json",
      "description": "結果フォーマット"
    },
    "output_format": {
      "type": "string",
      "enum": ["json", "toon"],
      "default": "toon",
      "description": "出力フォーマット: 'toon' (デフォルト、50-70%トークン削減) または 'json'"
    },
    "output_file": {
      "type": "string",
      "description": "出力ファイル名（オプション）"
    },
    "suppress_output": {
      "type": "boolean",
      "description": "レスポンス出力を抑制",
      "default": false
    }
  },
  "required": ["file_path"],
  "anyOf": [
    {"required": ["query_key"]},
    {"required": ["query_string"]}
  ]
}
```

**Output Schema**:
```json
{
  "type": "object",
  "properties": {
    "success": {"type": "boolean"},
    "query_result": {
      "type": "object",
      "properties": {
        "file_path": {"type": "string"},
        "language": {"type": "string"},
        "query_type": {"type": "string"},
        "total_matches": {"type": "integer"},
        "matches": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": {"type": "string"},
              "type": {"type": "string"},
              "start_line": {"type": "integer"},
              "end_line": {"type": "integer"},
              "line_span": {"type": "integer"},
              "start_column": {"type": "integer"},
              "end_column": {"type": "integer"}
            }
          }
        }
      }
    },
    "next_steps": {
      "type": "array",
      "items": {"type": "string"},
      "description": "次のアクション提案（extract_code_sectionでコード抽出など）"
    },
    "available_queries": {
      "type": "object",
      "description": "無効なquery_key指定時に返される利用可能クエリ一覧（カテゴリ別）"
    },
    "productive_queries": {
      "type": "array",
      "items": {"type": "string"},
      "description": "結果が空の際に結果が存在するクエリキー一覧"
    },
    "output_file_path": {
      "type": "string",
      "description": "作成された出力ファイルのパス"
    }
  }
}
```

**Performance**: < 3秒
**Languages**: Java, Python, JavaScript, TypeScript, Go, Rust, C, C++, Kotlin, C#, Ruby, PHP, SQL, HTML, CSS, YAML, Markdown (17 languages)

#### HTML/CSS Language Support

**HTML Analysis Features**:
- DOM構造解析とHTML要素の階層関係抽出
- 要素分類システム（structure, heading, text, list, media, form, table, metadata）
- 属性解析とセマンティック要素の識別
- `MarkupElement`データモデルによる正確な表現

**CSS Analysis Features**:
- CSSセレクタとプロパティの包括的解析
- プロパティ分類システム（layout, box_model, typography, background, transition, interactivity）
- CSS変数（カスタムプロパティ）とメディアクエリの解析
- `StyleElement`データモデルによる構造化表現

**New Format Type**: `html`
- HTML/CSS専用の構造化テーブル出力
- Web開発ワークフローに最適化されたフォーマット
- `HtmlFormatter`による専用フォーマッティング

### 5. list_files

**Purpose**: 高性能ファイル検索（fd統合）

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "roots": {
      "type": "array",
      "items": {"type": "string"},
      "description": "検索対象ディレクトリパス"
    },
    "pattern": {
      "type": "string",
      "description": "ファイル名パターン（glob使用時）"
    },
    "glob": {
      "type": "boolean",
      "default": false,
      "description": "パターンをglobとして扱う"
    },
    "types": {
      "type": "array",
      "items": {"type": "string"},
      "description": "ファイルタイプ（'f'=ファイル, 'd'=ディレクトリ, 'l'=シンボリックリンク）"
    },
    "extensions": {
      "type": "array",
      "items": {"type": "string"},
      "description": "ファイル拡張子（ドットなし）"
    },
    "exclude": {
      "type": "array",
      "items": {"type": "string"},
      "description": "除外パターン"
    },
    "depth": {
      "type": "integer",
      "description": "最大検索深度"
    },
    "follow_symlinks": {
      "type": "boolean",
      "default": false,
      "description": "シンボリックリンクを追跡"
    },
    "hidden": {
      "type": "boolean",
      "default": false,
      "description": "隠しファイルを含める"
    },
    "no_ignore": {
      "type": "boolean",
      "default": false,
      "description": ".gitignoreを無視"
    },
    "size": {
      "type": "array",
      "items": {"type": "string"},
      "description": "ファイルサイズフィルター（例: '+10M', '-1K'）"
    },
    "changed_within": {
      "type": "string",
      "description": "変更時間フィルター（例: '1d', '2h'）"
    },
    "changed_before": {
      "type": "string",
      "description": "変更前時間フィルター"
    },
    "full_path_match": {
      "type": "boolean",
      "default": false,
      "description": "フルパスでマッチング"
    },
    "absolute": {
      "type": "boolean",
      "default": true,
      "description": "絶対パスで返す"
    },
    "limit": {
      "type": "integer",
      "description": "最大結果数（デフォルト2000、最大10000）"
    },
    "count_only": {
      "type": "boolean",
      "default": false,
      "description": "カウントのみ返す"
    },
    "output_file": {
      "type": "string",
      "description": "出力ファイル名（オプション）"
    },
    "suppress_output": {
      "type": "boolean",
      "description": "レスポンス出力を抑制",
      "default": false
    }
  },
  "required": ["roots"]
}
```

**Performance**: < 3秒（10,000ファイル対応）  
**Backend**: fd (fast directory traversal)

### 6. search_content

**Purpose**: 高性能コンテンツ検索（ripgrep統合）

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "roots": {
      "type": "array",
      "items": {"type": "string"},
      "description": "検索対象ディレクトリパス"
    },
    "files": {
      "type": "array",
      "items": {"type": "string"},
      "description": "検索対象ファイルパス"
    },
    "query": {
      "type": "string",
      "description": "検索クエリ（テキストまたは正規表現）"
    },
    "case": {
      "type": "string",
      "enum": ["smart", "insensitive", "sensitive"],
      "default": "smart",
      "description": "大文字小文字の扱い"
    },
    "fixed_strings": {
      "type": "boolean",
      "default": false,
      "description": "リテラル文字列として扱う"
    },
    "word": {
      "type": "boolean",
      "default": false,
      "description": "単語境界でマッチング"
    },
    "multiline": {
      "type": "boolean",
      "default": false,
      "description": "複数行マッチングを許可"
    },
    "include_globs": {
      "type": "array",
      "items": {"type": "string"},
      "description": "含めるファイルパターン"
    },
    "exclude_globs": {
      "type": "array",
      "items": {"type": "string"},
      "description": "除外ファイルパターン"
    },
    "follow_symlinks": {
      "type": "boolean",
      "default": false,
      "description": "シンボリックリンクを追跡"
    },
    "hidden": {
      "type": "boolean",
      "default": false,
      "description": "隠しファイルを検索"
    },
    "no_ignore": {
      "type": "boolean",
      "default": false,
      "description": ".gitignoreを無視"
    },
    "max_filesize": {
      "type": "string",
      "description": "最大ファイルサイズ（例: '10M'）"
    },
    "context_before": {
      "type": "integer",
      "description": "マッチ前のコンテキスト行数"
    },
    "context_after": {
      "type": "integer",
      "description": "マッチ後のコンテキスト行数"
    },
    "encoding": {
      "type": "string",
      "description": "ファイルエンコーディング"
    },
    "max_count": {
      "type": "integer",
      "description": "ファイルあたりの最大マッチ数"
    },
    "timeout_ms": {
      "type": "integer",
      "description": "タイムアウト（ミリ秒）"
    },
    "count_only_matches": {
      "type": "boolean",
      "default": false,
      "description": "マッチ数のみ返す"
    },
    "summary_only": {
      "type": "boolean",
      "default": false,
      "description": "サマリーのみ返す（トークン最適化）"
    },
    "optimize_paths": {
      "type": "boolean",
      "default": false,
      "description": "パス最適化"
    },
    "group_by_file": {
      "type": "boolean",
      "default": false,
      "description": "ファイル別グループ化（トークン最適化）"
    },
    "total_only": {
      "type": "boolean",
      "default": false,
      "description": "総数のみ返す（最大トークン最適化）"
    },
    "output_file": {
      "type": "string",
      "description": "出力ファイル名（オプション）"
    },
    "suppress_output": {
      "type": "boolean",
      "description": "レスポンス出力を抑制",
      "default": false
    }
  },
  "required": ["query"],
  "anyOf": [
    {"required": ["roots"]},
    {"required": ["files"]}
  ]
}
```

**Performance**: < 3秒  
**Backend**: ripgrep (fastest text search)  
**Token Optimization**: 5段階の最適化レベル

### 7. find_and_grep

**Purpose**: 2段階統合検索（fd + ripgrep）

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "roots": {
      "type": "array",
      "items": {"type": "string"},
      "description": "検索対象ディレクトリパス"
    },
    "pattern": {
      "type": "string",
      "description": "[ファイル段階] ファイル名パターン"
    },
    "glob": {
      "type": "boolean",
      "default": false,
      "description": "[ファイル段階] パターンをglobとして扱う"
    },
    "types": {
      "type": "array",
      "items": {"type": "string"},
      "description": "[ファイル段階] ファイルタイプ"
    },
    "extensions": {
      "type": "array",
      "items": {"type": "string"},
      "description": "[ファイル段階] ファイル拡張子"
    },
    "exclude": {
      "type": "array",
      "items": {"type": "string"},
      "description": "[ファイル段階] 除外パターン"
    },
    "depth": {
      "type": "integer",
      "description": "[ファイル段階] 最大検索深度"
    },
    "follow_symlinks": {
      "type": "boolean",
      "default": false,
      "description": "[ファイル段階] シンボリックリンクを追跡"
    },
    "hidden": {
      "type": "boolean",
      "default": false,
      "description": "[ファイル段階] 隠しファイルを含める"
    },
    "no_ignore": {
      "type": "boolean",
      "default": false,
      "description": "[ファイル段階] .gitignoreを無視"
    },
    "size": {
      "type": "array",
      "items": {"type": "string"},
      "description": "[ファイル段階] ファイルサイズフィルター"
    },
    "changed_within": {
      "type": "string",
      "description": "[ファイル段階] 変更時間フィルター"
    },
    "changed_before": {
      "type": "string",
      "description": "[ファイル段階] 変更前時間フィルター"
    },
    "full_path_match": {
      "type": "boolean",
      "default": false,
      "description": "[ファイル段階] フルパスでマッチング"
    },
    "file_limit": {
      "type": "integer",
      "description": "[ファイル段階] 最大ファイル数"
    },
    "sort": {
      "type": "string",
      "enum": ["path", "mtime", "size"],
      "description": "[ファイル段階] ソート順"
    },
    "query": {
      "type": "string",
      "description": "[コンテンツ段階] 検索クエリ"
    },
    "case": {
      "type": "string",
      "enum": ["smart", "insensitive", "sensitive"],
      "default": "smart",
      "description": "[コンテンツ段階] 大文字小文字の扱い"
    },
    "fixed_strings": {
      "type": "boolean",
      "default": false,
      "description": "[コンテンツ段階] リテラル文字列として扱う"
    },
    "word": {
      "type": "boolean",
      "default": false,
      "description": "[コンテンツ段階] 単語境界でマッチング"
    },
    "multiline": {
      "type": "boolean",
      "default": false,
      "description": "[コンテンツ段階] 複数行マッチングを許可"
    },
    "include_globs": {
      "type": "array",
      "items": {"type": "string"},
      "description": "[コンテンツ段階] 含めるファイルパターン"
    },
    "exclude_globs": {
      "type": "array",
      "items": {"type": "string"},
      "description": "[コンテンツ段階] 除外ファイルパターン"
    },
    "max_filesize": {
      "type": "string",
      "description": "[コンテンツ段階] 最大ファイルサイズ"
    },
    "context_before": {
      "type": "integer",
      "description": "[コンテンツ段階] マッチ前のコンテキスト行数"
    },
    "context_after": {
      "type": "integer",
      "description": "[コンテンツ段階] マッチ後のコンテキスト行数"
    },
    "encoding": {
      "type": "string",
      "description": "[コンテンツ段階] ファイルエンコーディング"
    },
    "max_count": {
      "type": "integer",
      "description": "[コンテンツ段階] ファイルあたりの最大マッチ数"
    },
    "timeout_ms": {
      "type": "integer",
      "description": "[コンテンツ段階] タイムアウト（ミリ秒）"
    },
    "count_only_matches": {
      "type": "boolean",
      "default": false,
      "description": "マッチ数のみ返す"
    },
    "summary_only": {
      "type": "boolean",
      "default": false,
      "description": "サマリーのみ返す（トークン最適化）"
    },
    "optimize_paths": {
      "type": "boolean",
      "default": false,
      "description": "パス最適化"
    },
    "group_by_file": {
      "type": "boolean",
      "default": false,
      "description": "ファイル別グループ化（トークン最適化）"
    },
    "total_only": {
      "type": "boolean",
      "default": false,
      "description": "総数のみ返す（最大トークン最適化）"
    },
    "output_file": {
      "type": "string",
      "description": "出力ファイル名（オプション）"
    },
    "suppress_output": {
      "type": "boolean",
      "description": "レスポンス出力を抑制",
      "default": false
    }
  },
  "required": ["roots", "query"]
}
```

**Performance**: < 10秒（複合ワークフロー）  
**Algorithm**: 2段階最適化検索

## Resources

### 1. code_file

**URI Pattern**: `code://file/{file_path}`

**Description**: ファイル内容への直接アクセス

**Response Schema**:
```json
{
  "type": "object",
  "properties": {
    "uri": {"type": "string"},
    "mimeType": {"type": "string"},
    "text": {"type": "string"},
    "metadata": {
      "type": "object",
      "properties": {
        "file_path": {"type": "string"},
        "size_bytes": {"type": "integer"},
        "line_count": {"type": "integer"},
        "language": {"type": "string"},
        "encoding": {"type": "string"}
      }
    }
  }
}
```

### 2. project_stats

**URI Pattern**: `code://stats/{stats_type}`

**Description**: プロジェクト統計情報

**Stats Types**:
- `overview`: プロジェクト概要
- `languages`: 言語別統計
- `complexity`: 複雑度メトリクス
- `files`: ファイル統計

**Response Schema**:
```json
{
  "type": "object",
  "properties": {
    "uri": {"type": "string"},
    "mimeType": {"type": "string"},
    "text": {"type": "string"},
    "metadata": {
      "type": "object",
      "properties": {
        "stats_type": {"type": "string"},
        "generated_at": {"type": "string"},
        "project_path": {"type": "string"}
      }
    }
  }
}
```

## Error Handling

### Standard Error Response

すべてのツールは統一されたエラーレスポンス形式を使用します：

```json
{
  "success": false,
  "error": {
    "type": "MCPToolError",
    "message": "エラーメッセージ",
    "code": "TOOL_EXECUTION_FAILED",
    "tool": "tool_name",
    "timestamp": "2025-10-12T13:45:00.000Z",
    "context": {
      "execution_stage": "validation",
      "input_params": {
        "file_path": "/path/to/file.py"
      }
    }
  }
}
```

### Error Types

- **MCPToolError**: ツール実行エラー
- **MCPValidationError**: 入力検証エラー
- **MCPTimeoutError**: タイムアウトエラー
- **SecurityError**: セキュリティ違反
- **FileRestrictionError**: ファイルアクセス制限
- **PathTraversalError**: パストラバーサル攻撃

### Error Context Sanitization

エラーレスポンスは自動的に機密情報を除去します：
- パスワード、トークン、キーの隠蔽
- 長いテキストの切り詰め
- 内部パス情報の除去
- スタックトレースのフィルタリング

## Performance Specifications

### Response Time Targets

- **単一ツール実行**: < 3秒
- **複合ワークフロー**: < 10秒
- **大規模
プロジェクト**: < 5秒（10,000ファイル）

### Memory Usage

- **小規模ファイル**: < 10MB
- **大規模ファイル**: < 50MB（suppress_output使用時）
- **プロジェクト検索**: < 100MB

### Scalability Limits

- **最大ファイルサイズ**: 100MB
- **最大検索結果**: 10,000件
- **最大プロジェクトファイル数**: 100,000件
- **同時実行**: 5リクエスト

## Token Optimization Strategies

### Level 1: Basic Optimization
- `count_only=true`: カウントのみ返す
- `summary_only=true`: サマリーのみ返す

### Level 2: Output Suppression
- `suppress_output=true` + `output_file`: ファイル出力でトークン削減

### Level 3: Content Filtering
- `max_count`: 結果数制限
- `limit`: ファイル数制限

### Level 4: Grouping
- `group_by_file=true`: ファイル別グループ化

### Level 5: Maximum Optimization
- `total_only=true`: 総数のみ（最大90%トークン削減）

## Usage Examples

### Basic Code Analysis Workflow

```bash
# Step 1: Check file scale
{
  "tool": "check_code_scale",
  "arguments": {
    "file_path": "src/main.py",
    "include_guidance": true
  }
}

# Step 2: Analyze structure (if recommended)
{
  "tool": "analyze_code_structure",
  "arguments": {
    "file_path": "src/main.py",
    "format_type": "full"
  }
}

# Step 3: Extract specific sections
{
  "tool": "extract_code_section",
  "arguments": {
    "file_path": "src/main.py",
    "start_line": 10,
    "end_line": 50
  }
}
```

### Large Project Search Workflow

```bash
# Step 1: Find relevant files
{
  "tool": "list_files",
  "arguments": {
    "roots": ["src/"],
    "extensions": ["py", "java"],
    "limit": 1000
  }
}

# Step 2: Search content with optimization
{
  "tool": "search_content",
  "arguments": {
    "roots": ["src/"],
    "query": "class.*Service",
    "include_globs": ["*.py"],
    "summary_only": true,
    "max_count": 20
  }
}

# Step 3: Integrated search for precision
{
  "tool": "find_and_grep",
  "arguments": {
    "roots": ["src/"],
    "extensions": ["py"],
    "query": "def process_",
    "group_by_file": true
  }
}
```

### Token-Optimized Large File Analysis

```bash
# For files > 1000 lines
{
  "tool": "analyze_code_structure",
  "arguments": {
    "file_path": "large_file.py",
    "format_type": "json",
    "suppress_output": true,
    "output_file": "analysis_result.json"
  }
}

# Query specific elements
{
  "tool": "query_code",
  "arguments": {
    "file_path": "large_file.py",
    "query_key": "methods",
    "output_format": "summary"
  }
}
```

## Security Guidelines

### Input Validation
- すべての入力パラメータは厳格に検証されます
- パストラバーサル攻撃は自動的に検出・防御されます
- ファイルサイズとパス長の制限が適用されます

### Project Boundary Enforcement
- プロジェクト外へのアクセスは自動的に拒否されます
- シンボリックリンクトラバーサルは防御されます
- 相対パスは安全に正規化されます

### Information Disclosure Prevention
- エラーメッセージから機密情報を除去します
- ログ出力は自動的にサニタイズされます
- デバッグ情報は制御された形式で提供されます

## Integration Examples

### Claude Desktop Integration

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uvx",
      "args": [
        "--from", "tree-sitter-analyzer[mcp]",
        "tree-sitter-analyzer-mcp"
      ]
    }
  }
}
```

### Cursor Integration

```json
{
  "mcp": {
    "servers": {
      "tree-sitter-analyzer": {
        "command": "uvx",
        "args": [
          "--from", "tree-sitter-analyzer[mcp]",
          "tree-sitter-analyzer-mcp"
        ],
        "env": {
          "PROJECT_ROOT": "${workspaceFolder}"
        }
      }
    }
  }
}
```

### Roo Code Integration

```yaml
mcp_servers:
  - name: tree-sitter-analyzer
    command: uvx --from tree-sitter-analyzer[mcp] tree-sitter-analyzer-mcp
    working_directory: ${workspace}
    capabilities:
      - tools
      - resources
      - logging
```

## Troubleshooting

### Common Issues

#### Tool Execution Timeout
```json
{
  "error": {
    "type": "MCPTimeoutError",
    "message": "Tool execution timed out after 30 seconds"
  }
}
```
**Solution**: 使用 `max_count`, `limit`, または `summary_only` でデータ量を制限

#### File Access Denied
```json
{
  "error": {
    "type": "SecurityError",
    "message": "Access denied: Path outside project boundary"
  }
}
```
**Solution**: サーバー起動時に `TREE_SITTER_PROJECT_ROOT` 環境変数または `--project-root` フラグでプロジェクトルートを正しく設定（推奨）。`set_project_path` ランタイムツールでセッション中のプロジェクト切り替えも可能。

#### Memory Limit Exceeded
```json
{
  "error": {
    "type": "MCPToolError",
    "message": "Memory usage exceeded limit"
  }
}
```
**Solution**: `suppress_output=true` + `output_file` でメモリ使用量を削減

### Performance Optimization Tips

1. **大規模ファイル**: 常に `check_code_scale` で事前評価
2. **検索操作**: `total_only=true` で事前に結果数を確認
3. **トークン制限**: `suppress_output` + `output_file` を活用
4. **複数ファイル**: `group_by_file=true` で重複を削減
5. **プロジェクト検索**: 適切な `include_globs` で範囲を限定

---

## Project-Level Tools (v1.11.0)

### 8. list_agent_skills

**Purpose**: Inspect project-local `.agents/skills` before choosing a skill. Returns trigger text, read order, support files, scripts, context needs, side effects, gaps such as missing completion guidance, and a validation summary that separates blocking gaps from caution-level and optional metadata gaps.

**Input**:

```json
{
  "skills_root": ".agents/skills",
  "output_format": "toon"
}
```

`skills_root` is optional and must stay inside the configured project root. The CLI parity path is:

```bash
uv run tree-sitter-analyzer agent-skills --format json
uv run tree-sitter-analyzer --agent-skills --agent-skills-root .agents/skills --format json
```

**Output**: `success`, `inventory`, `skills_root`, `skill_count`, per-skill metadata (`description`, `agent_trigger`, `read_order`, `support_files`, `scripts`, `requires_context`, `side_effects`, `model_invocation_enabled`, `completion_guidance_present`, `gaps`), aggregate `gaps`, `validation` (`status`, grouped gaps, counts, `next_fix`), compact `agent_summary`, and `toon_content`.

**SMART Workflow**: Call before `agent-workflow` when the queue item may benefit from a project-local skill.

### 9. get_agent_workflow

**Purpose**: Return the SMART workflow pack as an MCP tool so agents can plan a queue item without leaving the MCP surface. The pack includes `current_phase`, `phase_order`, `current_step`, `recommended_commands`, set/map/analyze/retrieve/trace steps, MCP tool names, CLI parity commands, stop conditions, and queue-boundary verification commands.

**Input**:

```json
{
  "target_path": "tree_sitter_analyzer/mcp/server.py",
  "output_format": "toon"
}
```

`target_path` is optional and must stay inside the configured project root when provided. The CLI parity path is:

```bash
uv run tree-sitter-analyzer agent-workflow --format json
uv run tree-sitter-analyzer agent-workflow tree_sitter_analyzer/mcp/server.py --format json
```

**Output**: `success`, `workflow`, `workflow_mode`, `project_root`, optional `target_path`, `current_phase`, `phase_order`, `current_step`, `routing`, `recommended_commands`, `steps` with `mcp_tools`, `cli_commands`, and `handoff` (`to`, `condition`, `goal`, `transition_command`) in JSON mode, `queue_boundary_commands`, `sprint_contract` (mode/scope/transition/evaluator checks), compact `agent_summary`, and `toon_content`. When `target_path` is provided, `agent_summary.queue_ledger_command` points to the scoped `change-impact --agent-summary-only` command that emits the queue ledger. TOON mode omits full structured `steps` and returns the compact decision surface, current step, and a `handoffs:` block.

**SMART Workflow**: Call before opening a fresh task queue. Pair with `list_agent_skills` when the queue item may benefit from a project-local skill.

### 10. advise_parser_readiness

**Purpose**: Advise the next language parser/plugin slice before opening roadmap work. The tool is local and offline: it reads `pyproject.toml`, parser dependencies, plugin entry points, `LanguageLoader` mappings, unit tests, and golden masters. For installed parser packages, it also checks package metadata and local artifacts for package version, project URLs, derived maintenance URLs, binding ABI, parser semantic version, packaged `grammar.json`, and scanner files, then leaves maintenance as an explicit online follow-up.

**Input**:

```json
{
  "language": "swift",
  "include_supported": false,
  "output_format": "toon"
}
```

`language` is optional. When omitted, the tool reports parser packages that are declared locally but do not yet have a plugin. The CLI parity path is:

```bash
uv run tree-sitter-analyzer parser-readiness --format json
uv run tree-sitter-analyzer parser-readiness swift --format json
uv run tree-sitter-analyzer --parser-readiness --parser-readiness-include-supported --format toon
```

**Output**: `success`, `advisor`, `project_root`, `wiki_inspired_signals`, `implemented_languages`, `parser_packages`, per-language `readiness` records (`status`, `score`, `requirements`, `signals`, `next_steps`, `verification_commands`), ranked `recommendations`, compact `agent_summary`, and `toon_content`.

**SMART Workflow**: Use in the **Map (M)** step before adding a new language plugin so parser dependency, loader, plugin, fixture, local parser-artifact, and upstream maintenance gaps are explicit.

### 11. get_project_overview

**Purpose**: One-call project portrait for AI agents — language distribution, file counts, largest files, optional health summary.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "include_health": {
      "type": "boolean",
      "description": "Include health grades for top-10 largest source files (slower)",
      "default": false
    },
    "max_depth": {
      "type": "integer",
      "description": "Max directory depth to scan (default: 5)",
      "default": 5
    },
    "output_format": {
      "type": "string",
      "enum": ["json", "toon"],
      "default": "toon"
    }
  }
}
```

**Output**:
```json
{
  "success": true,
  "project_root": "/path/to/project",
  "summary": {
    "total_files": 150,
    "source_files": 80,
    "non_source_files": 70,
    "total_lines": 45000,
    "languages_count": 5
  },
  "language_distribution": {"python": 60, "javascript": 15, "typescript": 5},
  "largest_source_files": [{"path": "src/main.py", "language": "python", "lines": 800}],
  "smart_workflow_hint": "Next: call check_code_scale on any interesting file..."
}
```

**SMART Workflow**: Use as the **Map (M)** step when exploring a new project.

### 12. check_project_health

**Purpose**: Score all project source files and return an agent-ready backlog of the weakest files.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "min_grade": {
      "type": "string",
      "enum": ["A", "B", "C", "D", "F"],
      "default": "D"
    },
    "max_files": {"type": "integer", "default": 20},
    "output_format": {"type": "string", "enum": ["json", "toon"], "default": "toon"}
  }
}
```

**Output**:
```json
{
  "success": true,
  "project_root": "/path/to/project",
  "total_files": 150,
  "grade_distribution": {"A": 60, "B": 55, "C": 25, "D": 8, "F": 2},
  "top_refactoring_targets": [
    {"file": "src/legacy.py", "grade": "F", "score": 18.0, "action": "refactoring_suggestions(file_path='src/legacy.py')"}
  ],
  "agent_backlog": [
    {
      "file": "src/legacy.py",
      "priority": "critical",
      "recommended_mcp_command": "refactoring_suggestions(file_path='src/legacy.py')",
      "recommended_cli_command": "uv run python -m tree_sitter_analyzer src/legacy.py --refactor --format json",
      "safety_mcp_command": "safe_to_edit(file_path='src/legacy.py')",
      "safety_cli_command": "uv run python -m tree_sitter_analyzer src/legacy.py --safe-to-edit --format json",
      "post_edit_commands": [
        "uv run python -m tree_sitter_analyzer src/legacy.py --file-health --format json",
        "uv run python -m tree_sitter_analyzer --change-impact --format json",
        "uv run pytest -q"
      ]
    }
  ]
}
```

**CLI Parity**: `uv run python -m tree_sitter_analyzer --project-health --format json`

**SMART Workflow**: Use before autonomous improvement loops to choose the next highest-value queue item.

### 13. check_file_health

**Purpose**: Score a single file's code health (A-F grade) across 7 dimensions.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "file_path": {"type": "string", "description": "Path to the source file"},
    "output_format": {"type": "string", "enum": ["json", "toon"], "default": "toon"}
  },
  "required": ["file_path"]
}
```

**Output**:
```json
{
  "success": true,
  "file_path": "src/main.py",
  "grade": "B",
  "total_score": 82.5,
  "dimensions": {
    "lines": 95.0,
    "complexity": 72.0,
    "dependencies": 100.0,
    "duplication": 85.0,
    "structure": 90.0,
    "git_hotspot": 100.0
  },
  "agent_summary": {
    "risk": "medium",
    "grade": "C",
    "weakest_dimension": "complexity",
    "weakest_score": 28.0,
    "target_smell": "high_complexity",
    "target_line": 42,
    "target_symbol": "run_pipeline",
    "target_detail": "Complexity score: 28/100; inspect 'run_pipeline' at L42",
    "verification_command": "uv run python -m tree_sitter_analyzer src/main.py --file-health --format json"
  },
  "recommendation": "File is in good shape. No immediate action needed."
}
```

**SMART Workflow**: Use in the **Analyze (A)** step to quickly identify files needing refactoring. The compact `agent_summary` elevates the weakest dimension and score, plus the first actionable smell with its line, symbol, and detail when available, so agents can open the right function before reading the whole file.

### 14. analyze_dependencies

**Purpose**: Project-level dependency graph analysis with 4 modes.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "mode": {
      "type": "string",
      "enum": ["blast_radius", "file_deps", "cycles", "summary"],
      "default": "summary"
    },
    "file_path": {
      "type": "string",
      "description": "Required for blast_radius and file_deps modes"
    },
    "output_format": {"type": "string", "enum": ["json", "toon"], "default": "toon"}
  }
}
```

**Modes**:
- `summary` — Project-wide stats: hub files, high-dependency files
- `blast_radius` — Impact analysis: how many files affected by changing this one
- `file_deps` — Direct dependencies and dependents of a file
- `cycles` — Detect circular dependencies

**SMART Workflow**: Use in the **Trace (T)** step to understand change impact.

### 15. analyze_change_impact

**Purpose**: Git-aware change impact analysis combining git diff with dependency graph.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "mode": {
      "type": "string",
      "enum": ["diff", "staged", "branch"],
      "default": "diff",
      "description": "diff=unstaged, staged=staged, branch=vs main"
    },
    "include_tests": {
      "type": "boolean",
      "default": true,
      "description": "Find related test files"
    },
    "scope_paths": {
      "type": "array",
      "items": {"type": "string"},
      "default": [],
      "description": "Optional git pathspecs limiting diff, impact, and test mapping to the current edit queue"
    },
    "output_format": {"type": "string", "enum": ["json", "toon"], "default": "toon"}
  }
}
```

**Output**: compact `agent_summary` (risk, next step, verification command, scope hint, stop condition), changed files (including untracked files in `diff` mode), optional `scope_paths` / `scope_filtered` when queue-scoped analysis is requested, optional `queue_ledger` for scoped dirty worktrees (`scoped_changed_count`, `out_of_scope_changed_count`, previews, and a compact handoff string), affected downstream files (via blast radius), related test files to run (`tests_to_run` is display-limited and paired with `tests_to_run_count` / `tests_to_run_omitted_count`), `test_required`, `test_runner`, `default_test_command`, copy-pasteable `test_command`, pytest compatibility fields (`pytest_required`, `pytest_command`), copy-pasteable `verification_command`, `verification_reason`, risk level (low/medium/high), diff stat.

**SMART Workflow**: Call AFTER editing code to understand what's affected and what tests to run. On large dirty worktrees, pass `scope_paths` (CLI: `--change-impact-scope PATH...`) for the current queue so agents get focused feedback before the final boundary check. Scoped responses include `queue_ledger` so handoffs can say how many changed files belong to the queue and how many dirty files are outside it. CLI mode parity is available with `--change-impact-mode diff|staged|branch`, and test discovery can be skipped with `--change-impact-no-tests` when a caller only needs changed/affected files. Follow `verification_command` for fast feedback during development; docs-only changes may set `test_required=false` and recommend `git diff --check`. Python projects keep `pytest_command`; Node, Go, Rust, Java/Maven/Gradle, and similar projects can surface their native default test command. Run the full suite before release/PR when risk remains high.

---

## Autonomous Development Tools (v1.13.0)

The v1.13.0 release adds 40 specialised tools for autonomous-agent workflows: AST cache + FTS5 indexing, function-level CodeGraph parity (callers/callees/blast-radius/visualise), pre-edit safety verdicts, anti-pattern / dead-code / route detection, architectural-constraint enforcement, and a persistent decision journal. All tools default to TOON output for 50-70% token savings versus JSON. Tools are listed alphabetically.

### 16. ast_cache

**Purpose**: Pre-indexed AST cache with FTS5 search and incremental sync (CodeGraph parity). The only tool that persists AST data across sessions — other codegraph tools build on top of this cache.

**Input**:
```json
{
  "mode": "index",
  "file_path": "tree_sitter_analyzer/mcp/server.py",
  "query": "AnalyzeScaleTool",
  "limit": 50,
  "max_files": 5000,
  "force": false,
  "output_format": "toon"
}
```

Modes: `index` (project or single file), `lookup` (cached parse data for a file), `search` (FTS5-ranked symbol search; LIKE fallback when FTS5 unavailable), `sync` (incremental — detect changes via content hash), `changes` (preview without re-indexing), `stats` (cache statistics), `invalidate` (remove cached entry). `fts_search` is accepted as a deprecated alias for `search`.

**CLI Parity**: `uv run python -m tree_sitter_analyzer --ast-cache index --format json`

**SMART Workflow**: Run once at session start in the **Map (M)** step. All codegraph_* tools (resolve, navigate, xref, symbol_search, dependency_matrix, sitemap, class_hierarchy) require this index.

### 17. ast_diff

**Purpose**: Structural AST-level diff between two code versions. Detects signature changes, body changes, renamed functions, and added/removed classes or imports — far more precise than textual diff.

**Input**:
```json
{
  "mode": "diff_git",
  "file_path": "tree_sitter_analyzer/mcp/server.py",
  "old_ref": "HEAD~1",
  "new_ref": "HEAD",
  "output_format": "toon"
}
```

Modes: `diff_files` (two file paths), `diff_strings` (two source strings), `diff_git` (a file between two git refs).

**CLI Parity**: `uv run python -m tree_sitter_analyzer --ast-diff --ast-diff-mode diff_git --ast-diff-file PATH --ast-diff-old-ref REF --ast-diff-new-ref REF --format json`

**SMART Workflow**: Use during code review and PR analysis when text diff is too noisy — surfaces semantic-only changes.

### 18. batch_search

**Purpose**: Execute multiple ripgrep searches in parallel — significantly faster than calling `search_content` sequentially. Maximum 10 queries per batch.

**Input**:
```json
{
  "queries": [
    {"query": "AnalyzeScaleTool", "include_globs": ["*.py"]},
    {"query": "QueryTool", "include_globs": ["*.py"]},
    {"query": "SearchContentTool", "include_globs": ["*.py"]}
  ]
}
```

Use when searching for 3+ patterns at once (cross-cutting refactor verification, multi-symbol usage scan). Do not use for single or paired searches — the parallel overhead is not worth it.

**CLI Parity**: `uv run python -m tree_sitter_analyzer --batch-search --batch-search-file queries.json --format json`

### 19. build_project_index

**Purpose**: Rebuild the persistent project index from scratch and save it to disk. Returns `build_duration_ms`, `files_scanned`, `languages_found`, and `index_saved_to` path.

**Input**:
```json
{
  "roots": ["src", "tests"],
  "add_notes": "Initial setup"
}
```

Call when project structure changed significantly, `get_project_summary` returns stale data, or setting up tree-sitter-analyzer in a new project. Do NOT call every session — the index auto-loads and stays fresh for 24 hours.

**CLI Parity**: `uv run python -m tree_sitter_analyzer --build-project-index --format json`

### 20. check_constraints

**Purpose**: Evaluate `architectural-constraints.yml` against the cached call graph. Returns violations + a `UNSAFE`/`CAUTION`/`SAFE` verdict consumed by `safe_to_edit` and `analyze_change_impact`. MUST call after schema or topology changes.

**Input**:
```json
{
  "path_filter": "tree_sitter_analyzer/mcp/",
  "severity_min": "warning",
  "output_format": "toon"
}
```

**CLI Parity**: `uv run python -m tree_sitter_analyzer --check-constraints --format json`

**SMART Workflow**: Call in the **Trace (T)** step before approving architectural changes.

### 21. check_tools

**Purpose**: Verify that `fd` and `ripgrep` are installed, executable, and at the minimum required version. Returns per-tool `available`, `version`, `failure_mode` (`not_installed`/`timeout`/`permission_denied`/`wrong_version`/`unknown`), `recommended_fix`, and an `agent_summary.next_step` routed by `failure_mode`.

**Input**:
```json
{}
```

Call when `list_files`, `search_content`, or `find_and_grep` return unexpected empty results, when setting up in a new environment, or when diagnosing missing files. Verdict vocabulary: `SAFE` / `WARN` / `ERROR` / `NOT_FOUND`. The verdict is a hard environment-readiness gate — agents must surface `recommended_fix` instead of proceeding past a non-SAFE verdict.

**CLI Parity**: `uv run python -m tree_sitter_analyzer --check-tools --format json`

### 22. code_patterns

**Purpose**: Detect anti-patterns, code smells, and security issues in a file. Categories: `smells` (god_class, long_method, deep_nesting), `security` (sql_injection, hardcoded_secret, eval_usage), `anti_patterns` (mutable_defaults, bare_except, print_statements). Use BEFORE editing to know what to fix.

**Input**:
```json
{
  "file_path": "tree_sitter_analyzer/mcp/server.py",
  "categories": ["smells", "security"],
  "severity_threshold": "warning",
  "output_format": "toon"
}
```

**CLI Parity**: `uv run python -m tree_sitter_analyzer FILE --code-patterns --format json`

**SMART Workflow**: Pair with `refactoring_suggestions` — `code_patterns` lists smells faster; `refactoring_suggestions` provides extraction recipes.

### 23. codegraph_ast_path

**Purpose**: AST path/scope navigation — answer "what is at line X of file Y?" (CodeGraph parity). The only tool that gives line-level AST scope navigation.

**Input**:
```json
{
  "mode": "path",
  "file_path": "tree_sitter_analyzer/mcp/server.py",
  "line": 42,
  "max_depth": 20,
  "output_format": "toon"
}
```

Modes: `path` (full AST path from root to node at line), `scope` (innermost enclosing function/class + siblings), `outline` (hierarchical file outline), `siblings` (declarations at same scope level).

**CLI Parity**: `uv run python -m tree_sitter_analyzer --ast-path --ast-path-file FILE --ast-path-line N --format json`

### 24. codegraph_autoindex

**Purpose**: Transparent AST cache auto-indexing lifecycle (CodeGraph parity). Modes: `status` (check index state), `warm` (trigger index — idempotent), `reset` (force re-index on next access).

**Input**:
```json
{
  "mode": "status",
  "max_files": 5000,
  "output_format": "toon"
}
```

Other codegraph_* tools auto-warm on first call; this tool gives explicit control over the lifecycle.

**CLI Parity**: `uv run python -m tree_sitter_analyzer --autoindex --autoindex-mode status --format json`

### 25. codegraph_call_graph

**Purpose**: Function-level call graph (CodeGraph parity). The first call on a project builds the full graph (2-5s on medium repos); subsequent calls within the session are fast.

**Input**:
```json
{
  "mode": "callers",
  "function_name": "AnalyzeScaleTool.execute",
  "file_path": "tree_sitter_analyzer/mcp/tools/analyze_scale_tool.py",
  "depth": 3,
  "output_format": "toon"
}
```

Modes: `callers` (who calls X), `callees` (what does X call), `chain` (transitive call chain), `summary` (stats), `all_functions` (list all discovered functions).

**CLI Parity**: `uv run python -m tree_sitter_analyzer --call-graph --call-graph-mode callers --call-graph-function NAME --format json`

### 26. codegraph_call_path

**Purpose**: Find execution paths between two functions via BFS on call edges (CodeGraph parity). Unlike `callers`/`callees` (direct edges), this finds the full path from source to target.

**Input**:
```json
{
  "source_function": "main",
  "target_function": "AnalyzeScaleTool.execute",
  "max_depth": 8,
  "max_paths": 5,
  "direction": "forward",
  "output_format": "toon"
}
```

**CLI Parity**: `uv run python -m tree_sitter_analyzer --call-path --call-path-source SRC --call-path-target TGT --format json`

### 27. codegraph_callees

**Purpose**: Find all functions called by the given function (CodeGraph parity). Returns callee name, file, line, and language.

**Input**:
```json
{
  "function_name": "AnalyzeScaleTool.execute",
  "file_path": "tree_sitter_analyzer/mcp/tools/analyze_scale_tool.py",
  "include_activation": false,
  "output_format": "toon"
}
```

**CLI Parity**: `uv run python -m tree_sitter_analyzer --call-graph --call-graph-mode callees --call-graph-function NAME --format json`

### 28. codegraph_callers

**Purpose**: Find all functions that call the given function (CodeGraph parity). Returns caller name, file, line, and language.

**Input**:
```json
{
  "function_name": "AnalyzeScaleTool.execute",
  "file_path": "tree_sitter_analyzer/mcp/tools/analyze_scale_tool.py",
  "include_activation": false,
  "output_format": "toon"
}
```

**CLI Parity**: `uv run python -m tree_sitter_analyzer --call-graph --call-graph-mode callers --call-graph-function NAME --format json`

### 29. codegraph_class_hierarchy

**Purpose**: Class inheritance hierarchy analysis (CodeGraph parity). Requires `ast_cache` index to be built first.

**Input**:
```json
{
  "mode": "subclasses",
  "class_name": "BaseMCPTool",
  "max_depth": 6,
  "output_format": "toon"
}
```

Modes: `subclasses` (descendants), `superclasses` (ancestors), `tree` (full subtree rooted at a class), `impact` (risk analysis for modifying a base class), `all` (list all discovered classes), `summary` (hierarchy statistics).

**CLI Parity**: `uv run python -m tree_sitter_analyzer --class-hierarchy --class-hierarchy-mode subclasses --class-hierarchy-class NAME --format json`

### 30. codegraph_complexity_heatmap

**Purpose**: Cyclomatic complexity heatmap per function + project-wide analysis (CodeGraph parity). Ranks functions by complexity, identifies hotspots, produces risk distribution (low 1-5, medium 6-10, high 11-20, critical 20+).

**Input**:
```json
{
  "mode": "project",
  "file_path": "tree_sitter_analyzer/mcp/server.py",
  "function_name": "execute",
  "directory": "tree_sitter_analyzer/mcp",
  "max_files": 5000,
  "output_format": "toon"
}
```

Modes: `project` (full heatmap), `file` (single file), `function` (named function).

**CLI Parity**: `uv run python -m tree_sitter_analyzer --codegraph-complexity-heatmap --format json`

### 31. codegraph_dead_code

**Purpose**: Dead code analysis with transitive dead functions, unused imports, and unreferenced variables. Extends basic orphan detection with flood-fill from entry points to find entire dead call chains.

**Input**:
```json
{
  "mode": "all",
  "include_test_files": false,
  "max_dead": 100,
  "max_imports": 100,
  "max_variables": 100,
  "output_format": "toon"
}
```

**CLI Parity**: `uv run python -m tree_sitter_analyzer --dead-code --format json`

**SMART Workflow**: Run periodically as part of project hygiene to surface dead code that survived refactoring.

### 32. codegraph_dependency_matrix

**Purpose**: Module coupling analysis from pre-indexed AST cache. Requires `ast_cache` index.

**Input**:
```json
{
  "mode": "hotspots",
  "file_path": "tree_sitter_analyzer/mcp/server.py",
  "top_k": 20,
  "threshold": 0.5,
  "output_format": "toon"
}
```

Modes: `summary` (stats), `matrix` (all pairs), `hotspots` (top-K coupling), `file` (coupling for one file), `unstable` (high-instability modules).

**CLI Parity**: `uv run python -m tree_sitter_analyzer --dependency-matrix --dependency-matrix-mode hotspots --format json`

### 33. codegraph_full_index

**Purpose**: One-shot complete project intelligence index (CodeGraph parity). Runs AST parse + call edges + FTS5 + incremental sync + cross-file resolution in a single call. Agents call this once at session start — all codegraph_* tools become instant afterward.

**Input**:
```json
{
  "mode": "incremental",
  "max_files": 5000,
  "resolve_synapse": true,
  "output_format": "toon"
}
```

Modes: `full` (force re-index), `incremental` (only process changes).

**CLI Parity**: `uv run python -m tree_sitter_analyzer --full-index --full-index-mode incremental --format json`

**SMART Workflow**: Recommended first command of any agent session targeting a fresh checkout.

### 34. codegraph_impact

**Purpose**: Function-level blast radius analysis (CodeGraph parity). Provides transitive reachability and quantified risk scoring (0-100).

**Input**:
```json
{
  "mode": "function_impact",
  "function_name": "AnalyzeScaleTool.execute",
  "file_path": "tree_sitter_analyzer/mcp/tools/analyze_scale_tool.py",
  "depth": 3,
  "output_format": "toon"
}
```

Modes: `function_impact` (transitive callers/callees + risk for one function), `blast_radius` (aggregate impact for multiple functions via `function_names`), `risk_score` (quantified 0-100 risk).

**CLI Parity**: `uv run python -m tree_sitter_analyzer --codegraph-impact --codegraph-impact-mode function_impact --codegraph-impact-function NAME --format json`

### 35. codegraph_import_graph

**Purpose**: File-level import dependency graph (CodeGraph parity). Requires `ast_cache` index.

**Input**:
```json
{
  "mode": "blast_radius",
  "file_path": "tree_sitter_analyzer/mcp/server.py",
  "max_depth": 4,
  "output_format": "toon"
}
```

Modes: `summary` (project overview), `deps` (what a file imports), `dependents` (who imports a file), `blast_radius` (transitive impact), `cycles` (circular imports), `coupling` (import hotspots).

**CLI Parity**: `uv run python -m tree_sitter_analyzer --import-graph --import-graph-mode blast_radius --import-graph-file PATH --format json`

### 36. codegraph_incremental_sync

**Purpose**: Incremental AST cache sync using content-hash comparison (CodeGraph parity). Only re-parses files whose SHA-256 hash differs.

**Input**:
```json
{
  "mode": "sync",
  "max_files": 5000,
  "output_format": "toon"
}
```

Modes: `sync` (detect + re-index changed files), `changes` (preview only — no re-index), `status` (indexed-vs-on-disk file counts).

**CLI Parity**: `uv run python -m tree_sitter_analyzer --incremental-sync --incremental-sync-mode sync --format json`

### 37. codegraph_metrics

**Purpose**: Aggregated project intelligence dashboard (CodeGraph parity). Combines AST cache stats, call graph metrics, complexity distribution, route counts, and file-health into a single project card. All data from pre-indexed caches — instant response.

**Input**:
```json
{
  "sections": ["ast_cache", "call_graph", "complexity", "routes", "health"],
  "output_format": "toon"
}
```

Suggests which tools to run first if any underlying index is empty.

**CLI Parity**: `uv run python -m tree_sitter_analyzer --codegraph-metrics --format json`

### 38. codegraph_navigate

**Purpose**: Unified symbol navigation hub (CodeGraph parity). Combines go-to-definition, find-references, and call hierarchy (callers + callees) in a single call — replaces 3-4 separate tool calls for "understand this symbol".

**Input**:
```json
{
  "symbol": "AnalyzeScaleTool",
  "mode": "full",
  "file_path": "tree_sitter_analyzer/mcp/tools/analyze_scale_tool.py",
  "depth": 3,
  "output_format": "toon"
}
```

Modes: `definition`, `references`, `hierarchy`, `full`. Requires `ast_cache` index.

**CLI Parity**: `uv run python -m tree_sitter_analyzer --codegraph-navigate --codegraph-navigate-symbol NAME --format json`

### 39. codegraph_overview

**Purpose**: Project-wide call graph intelligence (CodeGraph parity). Identifies entry points (public API), dead code, hub functions, call-depth distribution, and module coupling.

**Input**:
```json
{
  "max_entry_points": 50,
  "max_hubs": 20,
  "max_dead": 30,
  "max_coupled_files": 20,
  "output_format": "toon"
}
```

**CLI Parity**: `uv run python -m tree_sitter_analyzer --codegraph-overview --format json`

**SMART Workflow**: Use in the **Map (M)** step to identify the public API surface and hotspots.

### 40. codegraph_pr_review

**Purpose**: AI-powered PR review combining AST diff + semantic classification + call graph blast radius. Produces per-file risk verdict, change categories (`api_change`, `refactor`, `feature`), affected API surface, and actionable review notes. Supports local diff modes and GitHub PR URLs.

**Input**:
```json
{
  "mode": "branch",
  "pr_url": "https://github.com/owner/repo/pull/123",
  "include_call_graph": true,
  "output_format": "toon"
}
```

Unlike `analyze_change_impact` (test-focused), this produces reviewer-oriented structured analysis.

**CLI Parity**: `uv run python -m tree_sitter_analyzer --pr-review --pr-review-mode branch --format json`

### 41. codegraph_resolve

**Purpose**: Go-to-definition and find-all-references (CodeGraph parity). Resolves symbol names to definition locations using the pre-indexed AST cache. Supports qualified names (`module.Class.method`). Requires `ast_cache` index.

**Input**:
```json
{
  "mode": "definition",
  "symbol": "AnalyzeScaleTool.execute",
  "output_format": "toon"
}
```

Modes: `definition`, `references`.

**CLI Parity**: `uv run python -m tree_sitter_analyzer --symbol-resolve --symbol-resolve-symbol NAME --format json`

### 42. codegraph_similarity

**Purpose**: AST-structural clone detection — finds duplicate and near-duplicate functions using tree-sitter fingerprints. Detects structural clones (same AST shape, different names) and textual clones (copy-paste).

**Input**:
```json
{
  "mode": "groups",
  "min_lines": 6,
  "min_group_size": 2,
  "max_groups": 50,
  "use_cache": true,
  "output_format": "toon"
}
```

**CLI Parity**: `uv run python -m tree_sitter_analyzer --code-similarity --format json`

### 43. codegraph_sitemap

**Purpose**: Hierarchical project code map (CodeGraph parity). Generates a browsable directory→file→class→function structure with signatures, complexity metrics, and public API surface. Requires `ast_cache` index.

**Input**:
```json
{
  "mode": "api",
  "language": "python",
  "directory": "tree_sitter_analyzer",
  "max_files": 5000,
  "output_format": "toon"
}
```

Modes: `full` (complete map), `api` (public API only), `module` (per-module metrics), `flat` (flat symbol list).

**CLI Parity**: `uv run python -m tree_sitter_analyzer --codegraph-sitemap --codegraph-sitemap-mode api --format json`

### 44. codegraph_symbol_search

**Purpose**: Instant FTS5-powered symbol search across the pre-indexed project (CodeGraph parity). Finds classes, functions, methods, and variables by name in microseconds. Supports exact, wildcard (`*`), and fuzzy (`~`) matching. Requires `ast_cache` index.

**Input**:
```json
{
  "query": "AnalyzeScale*",
  "language": "python",
  "kind": "class",
  "limit": 50,
  "output_format": "toon"
}
```

**CLI Parity**: `uv run python -m tree_sitter_analyzer --symbol-search --symbol-search-query QUERY --format json`

### 45. codegraph_visualize

**Purpose**: Export the project call graph as a Mermaid flowchart diagram (CodeGraph parity). Renders caller→callee edges as a text diagram that works in GitHub READMEs, PRs, and Markdown.

**Input**:
```json
{
  "mode": "function",
  "file_path": "tree_sitter_analyzer/mcp/tools/analyze_scale_tool.py",
  "function": "AnalyzeScaleTool.execute",
  "depth": 3,
  "max_edges": 200,
  "direction": "forward",
  "output_format": "toon"
}
```

Modes: `full` (all edges), `file` (single-file scope), `function` (transitive chain from seed).

**CLI Parity**: `uv run python -m tree_sitter_analyzer --codegraph-visualize --codegraph-visualize-mode function --codegraph-visualize-function NAME --format json`

### 46. codegraph_uml

**Purpose**: Export UML-style Mermaid diagrams from indexed project intelligence. First-phase diagrams are `class` (inheritance), `package` (package/import dependencies), `component` (top-level component dependencies), and `sequence` (static call-path approximation).

**Input**:
```json
{
  "diagram": "class",
  "source": "handler",
  "target": "repository",
  "max_edges": 200,
  "max_depth": 8,
  "max_paths": 3,
  "package_depth": 2,
  "include_external_bases": true,
  "output_format": "toon"
}
```

Modes: `class`, `package`, `component`, `sequence`. Sequence diagrams require `source` and `target`; they are static call-path approximations, not runtime traces.

**CLI Parity**: `uv run python -m tree_sitter_analyzer --uml class --format json`

### 47. codegraph_xref

**Purpose**: Instant multi-dimension cross-reference from pre-indexed AST cache (CodeGraph parity). For a symbol: definition + callers + callees + import dependents + file blast radius. For a file: all symbols + deps. Requires `ast_cache` index.

**Input**:
```json
{
  "mode": "symbol",
  "symbol": "AnalyzeScaleTool",
  "file_path": "tree_sitter_analyzer/mcp/tools/analyze_scale_tool.py",
  "include_callers": true,
  "include_callees": true,
  "include_imports": true,
  "include_file_deps": true,
  "output_format": "toon"
}
```

**CLI Parity**: `uv run python -m tree_sitter_analyzer --codegraph-xref --codegraph-xref-mode symbol --codegraph-xref-symbol NAME --format json`

### 48. decision_journal

**Purpose**: Persistent journal of architectural decisions. Records every decision with title, rationale, verdict, scope, alternatives considered, related symbols, and tags. The only registered MCP tool that persists *reasoning* across sessions. Storage: `<project_root>/.ast-cache/decision_journal.db`.

**Input**:
```json
{
  "mode": "record",
  "title": "Prefer env+CLI flag over set_project_path for startup",
  "rationale": "Env TREE_SITTER_PROJECT_ROOT / --project-root configures the root once at startup, before the security validator and cache are warmed. The set_project_path tool still works for runtime project switching but should not be the default UX.",
  "verdict": "SAFE",
  "scope_paths": ["tree_sitter_analyzer/mcp/server.py"],
  "alternatives": ["remove set_project_path entirely (rejected — runtime switching has real use cases)"],
  "related_symbols": ["BaseMCPTool"],
  "tags": ["mcp", "boundary"],
  "output_format": "toon"
}
```

Modes: `record` (new entry), `get` (by id), `search` (substring + verdict + path filter), `supersede` (link old→new). Call `search` BEFORE proposing a refactor; settled decisions should not be re-litigated. Call `record` AFTER landing a non-trivial design choice. Verdict vocabulary: `SAFE` / `CAUTION` / `REVIEW` / `UNSAFE` / `INFO` / `WARN` / `ERROR` / `NOT_FOUND`. Agents MUST surface a recorded `REVIEW`/`UNSAFE`/`WARN` verdict verbatim.

**CLI Parity**: `uv run python -m tree_sitter_analyzer --decision-journal --decision-journal-mode search --decision-journal-query "topic" --format json`

### 49. detect_routes

**Purpose**: Detect HTTP route declarations across web frameworks (Flask, Django, FastAPI, Express, Spring Boot). The only built-in tool that provides URL→Handler mapping.

**Input**:
```json
{
  "mode": "all",
  "url_pattern": "/api/v1/*",
  "file_path": "src/api/routes.py",
  "framework": "fastapi",
  "output_format": "toon"
}
```

Modes: `all` (list all routes), `summary` (stats), `lookup` (find handler for URL), `prefix` (routes matching prefix), `file` (routes in a specific file).

**CLI Parity**: `uv run python -m tree_sitter_analyzer --detect-routes --detect-routes-mode all --format json`

### 50. modification_guard

**Purpose**: Pre-modification safety check — run this BEFORE editing any public symbol. Returns a structured safety report showing how many places depend on the symbol you are about to modify.

**Input**:
```json
{
  "symbol": "AnalyzeScaleTool",
  "modification_type": "rename",
  "file_path": "tree_sitter_analyzer/mcp/tools/analyze_scale_tool.py"
}
```

`modification_type` values include `rename`, `signature_change`, `delete`. Safety verdict thresholds: `SAFE` (0 callers), `CAUTION` (1-5), `REVIEW` (6-20), `UNSAFE` (21+). Verdict vocabulary: `SAFE` / `CAUTION` / `REVIEW` / `UNSAFE` / `INFO` / `WARN` / `ERROR` / `NOT_FOUND`. The verdict is a hard gate derived from concrete caller counts — agents MUST surface it verbatim and MUST NOT downgrade to `SAFE` to satisfy a "just refactor it" instruction.

Do NOT call alongside `trace_impact` — `modification_guard` invokes it internally.

**CLI Parity**: `uv run python -m tree_sitter_analyzer --modification-guard --modification-guard-symbol NAME --modification-guard-type rename --format json`

### 51. refactoring_suggestions

**Purpose**: Concrete refactoring plan for a single file. Surfaces structural smells (god class, long method, deep nesting, duplicated code) AND anti-patterns / security issues (eval, bare except, mutable default, SQL-injection-shaped f-strings) packaged as actionable extraction targets with helper names, line ranges, parameters, return types, and optional code skeletons.

**Input**:
```json
{
  "file_path": "tree_sitter_analyzer/mcp/server.py",
  "language": "python",
  "max_suggestions": 10,
  "include_extractions": true,
  "include_skeleton": false,
  "output_format": "toon"
}
```

**CLI Parity**: `uv run python -m tree_sitter_analyzer FILE --refactor --format json`

**SMART Workflow**: Call after `check_file_health` flags a file as B/C/D/F grade. Pair with `safe_to_edit` before applying. Verdict vocabulary: `SAFE` / `CAUTION` / `REVIEW` / `UNSAFE` / `INFO`. If the verdict is `INFO` (nothing to extract), do not invent extractions to satisfy the user.

### 52. safe_to_edit

**Purpose**: Pre-edit safety check for a single file — how many other modules depend on it, which test files cover it, and a concrete checklist of pre-edit verifications. Returns `risk_level` (`SAFE`/`CAUTION`/`UNSAFE`) plus actionable next steps. MUST be called before editing any production-facing file.

**Input**:
```json
{
  "file_path": "tree_sitter_analyzer/mcp/server.py",
  "edit_type": "modify",
  "output_format": "toon"
}
```

**CLI Parity**: `uv run python -m tree_sitter_analyzer FILE --safe-to-edit --format json`

**SMART Workflow**: Use in the **Trace (T)** step before any edit to a public-facing module or utility. Pair with `modification_guard` for symbol-level rename impact.

### 53. semantic_classify

**Purpose**: Classify code changes into semantic categories with risk assessment. Returns dominant category, risk level, confidence, and per-hunk classification.

**Input**:
```json
{
  "mode": "classify_file",
  "file_path": "tree_sitter_analyzer/mcp/server.py",
  "old_ref": "HEAD~1",
  "new_ref": "HEAD",
  "output_format": "toon"
}
```

Modes: `classify_string` (two code strings), `classify_file` (file between git refs).

**CLI Parity**: `uv run python -m tree_sitter_analyzer --semantic-classify --semantic-classify-mode classify_file --semantic-classify-file PATH --format json`

### 54. smart_context

**Purpose**: One-shot file orientation: combines `check_file_health` grade, exported symbols (the file's public API), upstream/downstream dependencies, associated test files, and edit-risk estimate into a single envelope. Designed as the first tool an agent calls when handed an unfamiliar file — replaces 3-4 separate calls (`extract_code_section` + `check_file_health` + `analyze_dependencies` + `safe_to_edit`) with one.

**Input**:
```json
{
  "file_path": "tree_sitter_analyzer/mcp/server.py",
  "output_format": "toon"
}
```

**CLI Parity**: `uv run python -m tree_sitter_analyzer FILE --smart-context --format json`

**SMART Workflow**: First tool when picking up an unfamiliar file. Includes compact `agent_summary` (risk, next step, verification command, stop condition).

### 55. symbol_lineage

**Purpose**: Symbol lineage: definition → callers → downstream files → risk. Shows what breaks if you change a symbol. Combines AST references with the file dependency graph. SLOW — traverses AST references plus the full dependency graph (5-15s per symbol on medium repos); cache via `build_project_index`.

**Input**:
```json
{
  "symbol": "AnalyzeScaleTool",
  "max_depth": 3,
  "output_format": "toon"
}
```

**CLI Parity**: `uv run python -m tree_sitter_analyzer --symbol-lineage --symbol-lineage-symbol NAME --format json`

### 56. trace_impact

**Purpose**: Find every caller and usage site of a symbol across the entire project. REQUIRED before modifying any public function, class, or variable.

**Input**:
```json
{
  "symbol": "AnalyzeScaleTool",
  "file_path": "tree_sitter_analyzer/mcp/tools/analyze_scale_tool.py",
  "project_root": "/path/to/project",
  "case_sensitive": true,
  "word_match": true,
  "max_results": 200,
  "exclude_patterns": ["**/tests/fixtures/**"]
}
```

Provide `file_path` when available — this filters results to the same language and eliminates cross-language false positives. Set `word_match=true` (the default) to avoid substring noise.

**CLI Parity**: `uv run python -m tree_sitter_analyzer --trace-impact --trace-impact-symbol NAME --format json`

**SMART Workflow**: Use BEFORE renaming, removing, or changing the signature of any public symbol. Skip for private/internal methods (single-underscore prefix) within the same file — impact is local and visible in context.

---

## MCP Prompts (v1.11.0)

### smart_analyze
Guided single-file analysis prompt. AI agents call this to get step-by-step SMART workflow instructions for analyzing a specific file.

### smart_explore
Guided project exploration prompt. AI agents call this to discover how to explore a new project systematically.

---

## Error Response Format (v1.11.0)

All error responses now include actionable recovery guidance:

```json
{
  "success": false,
  "error": "File not found: /path/to/missing.py",
  "error_type": "FileNotFoundError",
  "error_category": "file_not_found",
  "recovery_hint": "The file does not exist at the given path. Verify the path or use list_files to discover files.",
  "suggested_tool": "list_files"
}
```

Categories: `file_not_found`, `language_unsupported`, `project_not_set`, `security_violation`, `missing_parameter`, `validation_error`, `resource_exhausted`, `timeout`, `unknown`

### v1.0.0 (2025-10-12)
- 初回リリース
- 8つのMCPツールと2つのリソース
- 統一されたエラーハンドリング
- セキュリティ境界保護
- トークン最適化機能
- HTML/CSS言語サポート
  - 完全なHTML DOM構造解析
  - CSS セレクタとプロパティの包括的解析
  - 要素分類システム（HTML: 8カテゴリ、CSS: 6カテゴリ）
  - 新しい`html`フォーマットタイプ
- FormatterRegistry拡張システム
  - 動的フォーマッター管理
  - プラグインベースの拡張可能アーキテクチャ
- 新しいデータモデル（MarkupElement, StyleElement）
  - HTML要素の階層関係とセマンティック情報
  - CSSルールの構造化表現
- 全MCPツールでの`set_project_path`メソッド統一実装
  - SearchContentToolとFindAndGrepToolに新規追加
  - 動的プロジェクトパス変更の統一サポート
  - FileOutputManager統合による設計一貫性確保

### v1.11.0 (2026-05-14)
- **3 new project-level tools** exposed to AI agents
  - `get_project_overview` — One-call project portrait (language distribution, file counts, health summary)
  - `check_file_health` — A-F grade scoring per file (size, complexity, dependencies, duplication, structure, git_hotspot)
  - `analyze_dependencies` — 4 modes: blast_radius, file_deps, cycles, summary
- **MCP Prompts** for SMART workflow self-discovery
  - `smart_analyze` — Guided single-file analysis prompt
  - `smart_explore` — Guided project exploration prompt
- **AI-agent-friendly error responses** with `recovery_hint` and `suggested_tool` fields
- **Error responses no longer leak `arguments`** — reduces token waste and sensitive path exposure

## Support & Documentation

- **GitHub**: https://github.com/your-org/tree-sitter-analyzer
- **Documentation**: https://tree-sitter-analyzer.readthedocs.io/
- **Issues**: https://github.com/your-org/tree-sitter-analyzer/issues
- **Discussions**: https://github.com/your-org/tree-sitter-analyzer/discussions

## License

MIT License - 詳細は LICENSE ファイルを参照してください。
