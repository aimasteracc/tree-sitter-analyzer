# Tree-sitter Analyzer MCP Tools API Specification

**Version**: 1.13.0
**Date**: 2026-05-15
**Protocol**: Model Context Protocol (MCP) v1.0

## Overview

Tree-sitter Analyzer MCPサーバーは、AI統合コード解析のための18の専門ツール、2つのリソース、および2つのSMART workflowプロンプトを提供します。すべてのツールはMCP v1.0仕様に準拠し、統一されたエラーハンドリングとセキュリティ機能を実装しています。

### v1.13.0 Changes
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

### 8. set_project_path

**Purpose**: プロジェクト境界の動的設定

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "project_path": {
      "type": "string",
      "description": "プロジェクトルートの絶対パス"
    }
  },
  "required": ["project_path"]
}
```

**Output Schema**:
```json
{
  "type": "object",
  "properties": {
    "success": {"type": "boolean"},
    "project_path": {"type": "string"},
    "previous_path": {"type": "string"},
    "security_validation": {
      "type": "object",
      "properties": {
        "path_exists": {"type": "boolean"},
        "is_directory": {"type": "boolean"},
        "is_accessible": {"type": "boolean"}
      }
    }
  }
}
```

**Security**: 厳格なパス検証とアクセス制御

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
**Solution**: `set_project_path` でプロジェクトルートを正しく設定

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

### 9. list_agent_skills

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

### 10. get_agent_workflow

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

### 11. advise_parser_readiness

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

### 12. get_project_overview

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

### 13. check_project_health

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

### 14. check_file_health

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

### 15. analyze_dependencies

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

### 16. analyze_change_impact

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
