# MCP統合仕様

**文書番号:** SPEC-003  
**バージョン:** 1.0  
**作成日:** 2025-11-03  
**最終更新:** 2025-11-03

---

## 1. 概要

本文書は、Tree-sitter AnalyzerのModel Context Protocol (MCP)統合の詳細仕様を記述する。MCPサーバーの実装、ツール定義、AI統合パターンを明確化する。

---

## 2. MCP概要

### 2.1 MCPとは

**Model Context Protocol (MCP)** は、AI言語モデル（LLM）とツールを統合するための標準プロトコル。

**主要特徴:**
- ✅ 標準化されたツール登録
- ✅ 型安全なパラメータ定義
- ✅ 非同期通信対応
- ✅ 複数トランスポート（stdio, websocket）

---

### 2.2 Tree-sitter AnalyzerのMCP統合の目的

**ユーザー価値:**
1. **AI駆動の開発**: Claude, Cursorなどで直接コード解析
2. **リアルタイム分析**: チャット内でコードメトリクス取得
3. **統合開発環境**: IDEとAIのシームレス連携

**技術的利点:**
- MCPの標準化されたインターフェース
- 複数AIツールへの自動対応
- 拡張性の高いツール追加

---

## 3. MCPサーバーアーキテクチャ

### 3.1 全体構造

```
┌─────────────────────────────────────────────┐
│           AI Client (Claude/Cursor)          │
└─────────────────────────────────────────────┘
                    ↕ MCP Protocol (stdio)
┌─────────────────────────────────────────────┐
│     TreeSitterAnalyzerMCPServer              │
│  ┌──────────────────────────────────────┐  │
│  │   Transport Layer                     │  │
│  │   - stdio (mcp.server.stdio)          │  │
│  └──────────────────────────────────────┘  │
│  ┌──────────────────────────────────────┐  │
│  │   Tool Registry                       │  │
│  │   - analyze_file                      │  │
│  │   - analyze_code                      │  │
│  │   - extract_elements                  │  │
│  │   - execute_query                     │  │
│  │   - validate_file                     │  │
│  │   - get_supported_languages           │  │
│  │   - get_available_queries             │  │
│  │   - get_framework_info                │  │
│  └──────────────────────────────────────┘  │
│  ┌──────────────────────────────────────┐  │
│  │   Resource Registry                   │  │
│  │   - code://file/{file_path}           │  │
│  │   - code://stats/{stats_type}         │  │
│  └──────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│              API Facade (api.py)             │
│         (統一インターフェース)                 │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│           AnalysisEngine                     │
│         (コア解析機能)                        │
└─────────────────────────────────────────────┘
```

---

### 3.2 TreeSitterAnalyzerMCPServer実装

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

class TreeSitterAnalyzerMCPServer:
    """Tree-sitter Analyzer MCPサーバー"""
    
    def __init__(self):
        self.name = "tree-sitter-analyzer"
        self.version = __version__
        self.server = None
    
    def create_server(self) -> Server:
        """MCPサーバーの生成と設定"""
        server = Server(self.name)
        
        @server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            """利用可能なツールをリスト"""
            return [
                Tool(
                    name="analyze_file",
                    description="ファイルを包括的に解析",
                    inputSchema={...}
                ),
                Tool(
                    name="analyze_code",
                    description="コードを直接解析",
                    inputSchema={...}
                ),
                # 他のツール定義...
            ]
        
        @server.call_tool()
        async def handle_call_tool(
            name: str,
            arguments: dict[str, Any]
        ) -> list[TextContent]:
            """ツール呼び出しを処理"""
            # API facadeを通じて実行
            if name == "analyze_file":
                result = api.analyze_file(**arguments)
            elif name == "analyze_code":
                result = api.analyze_code(**arguments)
            # ... 他のツール処理
            
            return [
                TextContent(
                    type="text",
                    text=json.dumps(result, indent=2, ensure_ascii=False)
                )
            ]
        
        @server.list_resources()
        async def handle_list_resources() -> list[Resource]:
            """利用可能なリソースをリスト"""
            return [...]
        
        @server.read_resource()
        async def handle_read_resource(uri: str) -> str:
            """リソースを読み取り"""
            # リソースURIに基づいてデータを返す
            return json.dumps(...)
        
        return server
    
    async def run(self):
        """MCPサーバー起動"""
        server = self.create_server()
        
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, options)
```

**重要な設計ポイント:**
- ✅ API facadeを使用した統一的なアクセス
- ✅ デコレータベースのハンドラー登録
- ✅ stdioトランスポートのみ（シンプル）
- ✅ 非同期I/O（asyncio）

---

## 4. MCPツール仕様

### 4.1 ツール1: analyze_file

#### 概要
単一ファイルの詳細解析を実行し、要素、クエリ結果、メトリクス情報を返す。

#### 入力スキーマ
```json
{
  "type": "object",
  "properties": {
    "file_path": {
      "type": "string",
      "description": "解析するファイルのパス（絶対パスまたは相対パス）"
    },
    "language": {
      "type": "string",
      "description": "プログラミング言語（省略時は自動検出）"
    },
    "queries": {
      "type": "array",
      "items": {"type": "string"},
      "description": "実行するクエリ名のリスト（省略時は全クエリ）"
    },
    "include_elements": {
      "type": "boolean",
      "description": "要素抽出を含めるか（デフォルト: true）",
      "default": true
    },
    "include_queries": {
      "type": "boolean",
      "description": "クエリを実行するか（デフォルト: true）",
      "default": true
    }
  },
  "required": ["file_path"]
}
```

#### 出力スキーマ
```json
{
  "type": "object",
  "properties": {
    "success": {
      "type": "boolean",
      "description": "解析が成功したか"
    },
    "file_info": {
      "type": "object",
      "properties": {
        "path": {"type": "string"},
        "exists": {"type": "boolean"}
      }
    },
    "language_info": {
      "type": "object",
      "properties": {
        "language": {"type": "string"},
        "detected": {"type": "boolean"}
      }
    },
    "ast_info": {
      "type": "object",
      "properties": {
        "node_count": {"type": "integer"},
        "line_count": {"type": "integer"}
      }
    },
    "elements": {
      "type": "array",
      "description": "抽出されたコード要素",
      "items": {
        "type": "object",
        "properties": {
          "name": {"type": "string"},
          "type": {"type": "string"},
          "start_line": {"type": "integer"},
          "end_line": {"type": "integer"},
          "raw_text": {"type": "string"},
          "language": {"type": "string"}
        }
      }
    },
    "query_results": {
      "type": "object",
      "description": "クエリ実行結果"
    }
  }
}
```

#### 実装
API facadeの`analyze_file()`を直接呼び出す：
```python
@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "analyze_file":
        result = api.analyze_file(
            file_path=arguments["file_path"],
            language=arguments.get("language"),
            queries=arguments.get("queries"),
            include_elements=arguments.get("include_elements", True),
            include_queries=arguments.get("include_queries", True)
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
```

---

### 4.2 ツール2: analyze_code

#### 概要
ファイルを介さず、コード文字列を直接解析する。

#### 入力スキーマ
```json
{
  "type": "object",
  "properties": {
    "source_code": {
      "type": "string",
      "description": "解析するソースコード"
    },
    "language": {
      "type": "string",
      "description": "プログラミング言語"
    },
    "queries": {
      "type": "array",
      "items": {"type": "string"},
      "description": "実行するクエリ名のリスト"
    },
    "include_elements": {
      "type": "boolean",
      "description": "要素抽出を含めるか",
      "default": true
    },
    "include_queries": {
      "type": "boolean",
      "description": "クエリを実行するか",
      "default": true
    }
  },
  "required": ["source_code", "language"]
}
```

#### 出力スキーマ
`analyze_file`と同じ構造

---

### 4.3 ツール3: extract_elements

#### 概要
ファイルからコード要素（クラス、関数等）のみを抽出。

#### 入力スキーマ
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
      "description": "プログラミング言語（省略時は自動検出）"
    },
    "element_types": {
      "type": "array",
      "items": {"type": "string"},
      "description": "抽出する要素タイプ（省略時は全て）"
    }
  },
  "required": ["file_path"]
}
```

---

### 4.4 ツール4: execute_query

#### 概要
特定のクエリを実行する。

#### 入力スキーマ
```json
{
  "type": "object",
  "properties": {
    "file_path": {
      "type": "string",
      "description": "対象ファイルのパス"
    },
    "query_name": {
      "type": "string",
      "description": "実行するクエリ名"
    },
    "language": {
      "type": "string",
      "description": "プログラミング言語（省略時は自動検出）"
    }
  },
  "required": ["file_path", "query_name"]
}
```

---

### 4.5 ツール5: validate_file

#### 概要
ファイルの構文を検証する。

#### 入力スキーマ
```json
{
  "type": "object",
  "properties": {
    "file_path": {
      "type": "string",
      "description": "対象ファイルのパス"
    }
  },
  "required": ["file_path"]
}
```

---

### 4.6 ツール6: get_supported_languages

#### 概要
サポートされている言語のリストを取得。

#### 入力スキーマ
```json
{
  "type": "object",
  "properties": {}
}
```

#### 出力スキーマ
```json
{
  "languages": ["python", "java", "javascript", ...],
  "total": 8
}
```

---

### 4.7 ツール7: get_available_queries

#### 概要
特定言語で利用可能なクエリのリストを取得。

#### 入力スキーマ
```json
{
  "type": "object",
  "properties": {
    "language": {
      "type": "string",
      "description": "プログラミング言語名"
    }
  },
  "required": ["language"]
}
```

---

### 4.8 ツール8: get_framework_info

#### 概要
フレームワーク情報（バージョン等）を取得。

#### 入力スキーマ
```json
{
  "type": "object",
  "properties": {}
}
```

---

## 5. AI統合パターン

### 5.1 Claude Desktop統合

#### 設定ファイル: `claude_desktop_config.json`
```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": [
        "run",
        "python",
        "-m",
        "tree_sitter_analyzer.interfaces.mcp_server"
      ]
    }
  }
}
```

**注意:** `tree_sitter_analyzer.interfaces.mcp_server`モジュールを直接起動します。

#### 使用例（Claude内）
```
User: このファイルのコード要素を教えて
      /path/to/my_file.py

Claude: [analyze_fileツールを使用]
        
        このファイルの解析結果:
        - 言語: Python
        - AST ノード数: 245
        - 総行数: 180行
        
        コード要素:
        - クラス: MyClass (15-45行)
        - 関数: process_data (50-80行)
        - 関数: validate_input (85-95行)
```

---

### 5.2 Cursor統合

#### 設定ファイル: `.cursor/mcp-config.json`
```json
{
  "mcpServers": [
    {
      "name": "tree-sitter-analyzer",
      "command": "uv",
      "args": [
        "run",
        "python",
        "-m",
        "tree_sitter_analyzer.interfaces.mcp_server"
      ]
    }
  ]
}
```

#### 使用例（Cursor内）
```
User: このファイルで定義されている関数をリストして

Cursor: [extract_elementsツールを使用]
        
        定義されている要素:
        - 関数: initialize() (10-25行)
        - 関数: process() (30-60行)
        - 関数: cleanup() (65-75行)
        - クラス: DataProcessor (80-150行)
```

---

### 5.3 VS Code Extension統合（将来計画）

#### extension.json
```json
{
  "contributes": {
    "mcpServers": [
      {
        "id": "tree-sitter-analyzer",
        "name": "Tree-sitter Analyzer",
        "command": "tree-sitter-analyzer-mcp"
      }
    ]
  }
}
```

---

## 6. プロトコル詳細

### 6.1 リクエストフォーマット

#### 標準MCPリクエスト
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "analyze_file",
    "arguments": {
      "file_path": "/path/to/file.py",
      "include_ast": false
    }
  }
}
```

---

### 6.2 レスポンスフォーマット

#### 成功レスポンス
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "解析結果:\n総行数: 100\n..."
      },
      {
        "type": "resource",
        "resource": {
          "uri": "file:///path/to/file.py.json",
          "mimeType": "application/json",
          "text": "{...詳細データ...}"
        }
      }
    ]
  }
}
```

#### エラーレスポンス
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32603,
    "message": "Internal error",
    "data": {
      "error": "FileNotFoundError: /path/to/file.py"
    }
  }
}
```

---

## 7. パフォーマンス最適化

### 7.1 キャッシュ戦略

**CacheServiceによる3層キャッシュ:**
- L1キャッシュ（LRU）: 高速アクセス用
- L2キャッシュ（TTL）: 中期保存用
- L3キャッシュ（LRU）: 長期保存用

**実装:**
```python
# CacheServiceはAnalysisEngineで自動的に使用される
engine = get_engine()
# キャッシュは内部で自動管理
result = engine.analyze_file(file_path)
```

**効果:**
- 同一ファイルの繰り返し要求: 10-100倍高速化
- セッション単位のキャッシュ保持
- TTLによる自動期限切れ

---

### 7.2 API Facadeによる統一的アクセス

**利点:**
- CLIとMCPで同じロジックを共有
- キャッシュの効果的な利用
- 保守性の向上

```python
# MCPサーバー内での使用
result = api.analyze_file(file_path)  # キャッシュ自動利用

# CLIでの使用
result = api.analyze_file(file_path)  # 同じキャッシュを共有
```

---

## 8. エラーハンドリング

### 8.1 エラー分類

| エラータイプ | コード | 説明 | ユーザー対応 |
|------------|------|------|------------|
| **FileNotFoundError** | N/A | ファイルが存在しない | パス確認 |
| **UnsupportedLanguageError** | N/A | 未対応言語 | 対応言語確認 |
| **ParseError** | N/A | パース失敗 | 構文エラー修正 |
| **PermissionError** | N/A | ファイルアクセス不可 | 権限確認 |
| **Exception** | N/A | 一般的なエラー | バグ報告 |

**注意:** MCPプロトコルでは、エラーはJSON-RPC標準のエラーコードではなく、
`success: false`フィールドとエラーメッセージで返されます。

---

### 8.2 エラー処理実装

```python
@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    """ツール呼び出しを処理"""
    try:
        # API呼び出し
        if name == "analyze_file":
            result = api.analyze_file(**arguments)
        # ... 他のツール
        
        # 成功時のレスポンス
        return [
            TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]
    
    except Exception as e:
        # エラー時のレスポンス
        log_error(f"Tool call error for {name}: {e}")
        error_result = {
            "error": str(e),
            "tool": name,
            "arguments": arguments,
            "success": False
        }
        return [
            TextContent(
                type="text",
                text=json.dumps(error_result, indent=2, ensure_ascii=False)
            )
        ]
```

**特徴:**
- すべてのエラーをキャッチして適切なJSON形式で返す
- ログにエラー詳細を記録
- クライアントには理解しやすいメッセージを返す

---

## 9. セキュリティ

### 9.1 パス検証

**SecurityValidatorによる検証:**
```python
from tree_sitter_analyzer.security import SecurityValidator

validator = SecurityValidator()

# パストラバーサル防止
is_safe = validator.validate_path(file_path)
```

**ProjectBoundaryManagerによるプロジェクト境界管理:**
```python
from tree_sitter_analyzer.security.boundary_manager import ProjectBoundaryManager

manager = ProjectBoundaryManager(project_root)
is_within_project = manager.is_path_within_project(file_path)
```

---

### 9.2 安全な実装

**MCPサーバー内での使用:**
- API facadeが内部でセキュリティチェックを実施
- 不正なパスは自動的に拒否される
- ログに不正アクセス試行を記録

```python
# API facadeが自動的にセキュリティチェック
result = api.analyze_file(file_path)  # 内部で検証済み
```

---

## 10. テスト戦略

### 10.1 単体テスト

**API facadeのテスト:**
```python
import pytest
from tree_sitter_analyzer import api

def test_analyze_file_api():
    # Arrange
    test_file = "tests/fixtures/sample.py"
    
    # Act
    result = api.analyze_file(test_file, language="python")
    
    # Assert
    assert result["success"] is True
    assert result["language_info"]["language"] == "python"
    assert "elements" in result
```

---

### 10.2 統合テスト

**MCPサーバーのE2Eテスト:**
```python
import pytest
from tree_sitter_analyzer.interfaces.mcp_server import TreeSitterAnalyzerMCPServer

@pytest.mark.asyncio
async def test_mcp_server_analyze_file():
    # Arrange
    server = TreeSitterAnalyzerMCPServer()
    server.create_server()
    
    # Act - ツールを呼び出し
    # (実際のMCPプロトコル経由でテスト)
    
    # Assert
    # レスポンスの検証
```

---

### 10.3 パフォーマンステスト

**レスポンスタイムの検証:**
```python
import time
import pytest

def test_analyze_file_performance():
    start = time.time()
    result = api.analyze_file("tests/fixtures/large_file.py")
    duration = time.time() - start
    
    # 1秒以内に完了することを確認
    assert duration < 1.0
    assert result["success"] is True
```

---

## 11. ドキュメントとサポート

### 11.1 ユーザー向けドキュメント

**クイックスタート:**
- Claude Desktop統合手順
- Cursor統合手順
- 基本的なツール使用例

**コマンド:**
```bash
# MCPサーバー起動
uv run python -m tree_sitter_analyzer.interfaces.mcp_server

# または
python start_mcp_server.py
```

**詳細ガイド:**
- 全ツールのリファレンス
- API facadeの使用方法
- トラブルシューティング

---

### 11.2 開発者向けドキュメント

**新ツール追加ガイド:**

1. **API facadeに関数を追加** (`api.py`)
```python
def new_analysis_function(param: str) -> dict[str, Any]:
    """新しい解析機能"""
    # 実装
    pass
```

2. **MCPサーバーにツールを登録** (`mcp_server.py`)
```python
@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        # ... 既存のツール
        Tool(
            name="new_tool",
            description="新しいツール",
            inputSchema={...}
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "new_tool":
        result = api.new_analysis_function(**arguments)
        return [TextContent(type="text", text=json.dumps(result))]
```

3. **テストの作成**
4. **ドキュメントの更新**

---

## 12. 改訂履歴

| バージョン | 日付 | 変更内容 | 承認者 |
|-----------|------|---------|--------|
| 1.0 | 2025-11-03 | 初版作成 | aisheng.yu |

---

**最終更新:** 2025-11-03  
**管理者:** aisheng.yu  
**連絡先:** aimasteracc@gmail.com
