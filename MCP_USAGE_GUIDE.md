# Tree-sitter Analyzer MCP サーバー使用ガイド

tree-sitter-analyzerをMCP (Model Context Protocol) サーバーとして使用する方法

## MCPサーバーとしての機能

tree-sitter-analyzerは、AI アシスタント（Claude Desktop等）がコード解析を直接実行できるMCPサーバーとして動作します。

### 提供されるツール

1. **analyze_code_scale** - コードの規模と複雑性メトリクスを取得
2. **format_table** - テーブル形式の解析結果を生成
3. **read_code_partial** - ファイルの特定行範囲を抽出
4. **analyze_code_universal** - 自動言語検出による汎用コード解析

## インストール方法

### PyPIからのインストール（推奨）

```bash
# MCPサポート付きでインストール
pip install "tree-sitter-analyzer[mcp]"

# 人気言語 + MCPサポート
pip install "tree-sitter-analyzer[popular,mcp]"

# 全機能 + MCPサポート
pip install "tree-sitter-analyzer[all,mcp]"
```

### uvを使用したインストール

```bash
# MCPサポート付きでインストール
uv add "tree-sitter-analyzer[mcp]"

# 人気言語 + MCPサポート
uv add "tree-sitter-analyzer[popular,mcp]"
```

## Claude Desktop での設定

### 設定ファイルの場所

- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/claude/claude_desktop_config.json`

### 設定例

#### 方法1: pipでインストールした場合

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "python",
      "args": [
        "-m", 
        "tree_sitter_analyzer.mcp.server"
      ]
    }
  }
}
```

#### 方法2: uvでインストールした場合（推奨）

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

#### 方法3: 仮想環境を使用する場合

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "/path/to/your/venv/bin/python",
      "args": [
        "-m", 
        "tree_sitter_analyzer.mcp.server"
      ]
    }
  }
}
```

## 使用例

### 1. コード規模解析

```
ファイル examples/Sample.java のコード規模を解析してください
```

MCPツール呼び出し:
```json
{
  "tool": "analyze_code_scale",
  "arguments": {
    "file_path": "examples/Sample.java",
    "include_complexity": true,
    "include_details": true
  }
}
```

### 2. テーブル形式の解析

```
examples/Sample.java の詳細な解析結果をテーブル形式で表示してください
```

MCPツール呼び出し:
```json
{
  "tool": "format_table",
  "arguments": {
    "file_path": "examples/Sample.java",
    "format_type": "full"
  }
}
```

### 3. 部分的なコード読み込み

```
examples/Sample.java の84行目から86行目を読み込んでください
```

MCPツール呼び出し:
```json
{
  "tool": "read_code_partial",
  "arguments": {
    "file_path": "examples/Sample.java",
    "start_line": 84,
    "end_line": 86
  }
}
```

## 対応言語

- **Java** - 完全サポート
- **Python** - 完全サポート
- **JavaScript** - 完全サポート
- **TypeScript** - 完全サポート
- **C/C++** - 基本サポート
- **Rust** - 基本サポート
- **Go** - 基本サポート

## トラブルシューティング

### MCPサーバーが起動しない

1. **依存関係の確認**
   ```bash
   pip show tree-sitter-analyzer
   pip show mcp
   ```

2. **手動でサーバーを起動してテスト**
   ```bash
   python -m tree_sitter_analyzer.mcp.server
   ```

3. **ログの確認**
   - Claude Desktop のログを確認
   - サーバーのエラーメッセージを確認

### パスの問題

1. **絶対パスを使用**
   ```json
   {
     "command": "/usr/bin/python3",
     "args": ["-m", "tree_sitter_analyzer.mcp.server"]
   }
   ```

2. **仮想環境のPythonを指定**
   ```json
   {
     "command": "/path/to/venv/bin/python",
     "args": ["-m", "tree_sitter_analyzer.mcp.server"]
   }
   ```

### 権限の問題

- ファイルの読み取り権限を確認
- Pythonの実行権限を確認

## 利点

### AIアシスタントとの統合
- コード解析結果を直接AIが利用可能
- 大きなファイルの効率的な解析
- 正確な位置情報による精密な操作

### 開発ワークフローの改善
- コードレビューの自動化
- リファクタリングの支援
- ドキュメント生成の支援

### パフォーマンス
- Tree-sitterによる高速解析
- キャッシュ機能による効率化
- 部分読み込みによるメモリ効率

## 高度な使用例

### 複数ファイルの解析

```
プロジェクト内の全てのJavaファイルの規模を解析し、
最も複雑なクラスを特定してください
```

### リファクタリング支援

```
このメソッドが長すぎます。
適切な分割ポイントを提案してください
```

### コードレビュー

```
このクラスの設計について、
SOLID原則の観点から評価してください
```

このガイドに従って、tree-sitter-analyzerをMCPサーバーとして効果的に活用できます。