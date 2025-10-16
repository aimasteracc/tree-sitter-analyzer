# Tree-sitter Analyzer MCP Tools API Specification

**Version**: 1.0.0  
**Date**: 2025-10-12  
**Protocol**: Model Context Protocol (MCP) v1.0

## Overview

Tree-sitter Analyzer MCPサーバーは、AI統合コード解析のための8つの専門ツールと2つのリソースを提供します。すべてのツールはMCP v1.0仕様に準拠し、統一されたエラーハンドリングとセキュリティ機能を実装しています。

## Server Information

- **Name**: `tree-sitter-analyzer`
- **Version**: `1.6.1`
- **Protocol Version**: `2024-11-05`
- **Capabilities**: `tools`, `resources`, `logging`

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
      "enum": ["java", "javascript", "typescript", "python", "markdown", "html", "css"]
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
      "enum": ["full", "compact", "csv", "json", "html"],
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
      "description": "定義済みクエリキー",
      "enum": ["methods", "classes", "functions", "imports", "variables", "comments"]
    },
    "query_string": {
      "type": "string",
      "description": "カスタムTree-sitterクエリ文字列"
    },
    "filter": {
      "type": "string",
      "description": "結果フィルター式（例: 'name=main', 'name=~get*,public=true'）"
    },
    "output_format": {
      "type": "string",
      "enum": ["json", "summary"],
      "default": "json",
      "description": "出力フォーマット"
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
              "start_column": {"type": "integer"},
              "end_column": {"type": "integer"}
            }
          }
        }
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
**Languages**: Java, JavaScript, TypeScript, Python, Markdown, HTML, CSS

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
      "command": "uv",
      "args": [
        "run",
        "--with",
        "tree-sitter-analyzer[mcp]",
        "python",
        "-m",
        "tree_sitter_analyzer.mcp.server"
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
        "command": "python",
        "args": ["-m", "tree_sitter_analyzer.mcp.server"],
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
    command: python -m tree_sitter_analyzer.mcp.server
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

## Version History

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

## Support & Documentation

- **GitHub**: https://github.com/your-org/tree-sitter-analyzer
- **Documentation**: https://tree-sitter-analyzer.readthedocs.io/
- **Issues**: https://github.com/your-org/tree-sitter-analyzer/issues
- **Discussions**: https://github.com/your-org/tree-sitter-analyzer/discussions

## License

MIT License - 詳細は LICENSE ファイルを参照してください。