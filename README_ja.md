# Tree-sitter Analyzer

[![Pythonバージョン](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![ライセンス](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![テスト](https://img.shields.io/badge/tests-1504%20passed-brightgreen.svg)](#品質保証)
[![カバレッジ](https://img.shields.io/badge/coverage-74.30%25-green.svg)](#品質保証)
[![品質](https://img.shields.io/badge/quality-enterprise%20grade-blue.svg)](#品質保証)
[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![バージョン](https://img.shields.io/badge/version-1.2.0-blue.svg)](https://github.com/aimasteracc/tree-sitter-analyzer/releases)
[![GitHub Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer)

## 🚀 LLMトークン制限を突破し、AIにあらゆるサイズのコードファイルを理解させる

> **AI時代のために設計された革命的なコード解析ツール**

## 📋 目次

- [🚀 LLMトークン制限を突破](#-llmトークン制限を突破しaiにあらゆるサイズのコードファイルを理解させる)
- [📋 目次](#-目次)
- [💡 特別な理由](#-特別な理由)
- [📊 ライブデモと結果](#-ライブデモと結果)
- [🚀 30秒クイックスタート](#-30秒クイックスタート)
  - [🤖 AIユーザー（Claude Desktop、Cursorなど）](#-aiユーザーclaude-desktopcursorなど)
  - [💻 開発者（CLI）](#-開発者cli)
- [❓ Tree-sitter Analyzerを選ぶ理由](#-tree-sitter-analyzerを選ぶ理由)
- [📖 実際の使用例](#-実際の使用例)
- [🛠️ コア機能](#️-コア機能)
- [📦 インストールガイド](#-インストールガイド)
- [🔒 セキュリティと設定](#-セキュリティと設定)
- [🏆 品質保証](#-品質保証)
- [🤖 AIコラボレーションサポート](#-aiコラボレーションサポート)
- [📚 ドキュメント](#-ドキュメント)
- [🤝 貢献](#-貢献)
- [📄 ライセンス](#-ライセンス)

## 💡 特別な理由

想像してください：1419行以上のJavaサービスクラスがあり、ClaudeやChatGPTがトークン制限のために分析できません。今、Tree-sitter AnalyzerはAIアシスタントを可能にします：

- ⚡ **3秒で完全なコード構造概要を取得**
- 🎯 **任意の行範囲のコードスニペットを正確に抽出**  
- 📍 **クラス、メソッド、フィールドの正確な位置をスマートに特定**
- 🔗 **Claude Desktop、Cursor、Roo CodeなどのAI IDEとシームレスに統合**
- 🏗️ **統一要素管理** - すべてのコード要素（クラス、メソッド、フィールド、インポート）を一つの統一されたシステムで

**大きなファイルのためにAIが無力になることはもうありません！**

## 📊 ライブデモと結果

### ⚡ **電光石火の解析速度**
```bash
# 1419行の大型Javaサービスクラス解析結果（< 1秒）
Lines: 1419 | Classes: 1 | Methods: 66 | Fields: 9 | Imports: 8 | Packages: 1
Total Elements: 85 | Complexity: 348 (avg: 5.27, max: 15)
```

### 📊 **正確な構造テーブル**
| クラス名 | タイプ | 可視性 | 行範囲 | メソッド数 | フィールド数 |
|----------|--------|--------|--------|------------|--------------|
| BigService | class | public | 17-1419 | 66 | 9 |

### 🔄 **AIアシスタント3ステップワークフロー**
- **ステップ1**: `check_code_scale` - ファイルの規模と複雑さをチェック
- **ステップ2**: `analyze_code_structure` - 統一要素を含む詳細な構造テーブルを生成
- **ステップ3**: `extract_code_section` - オンデマンドでコードセクションを抽出

---

## 🚀 30秒クイックスタート

### 🤖 AIユーザー（Claude Desktop、Cursorなど）

**📦 1. ワンクリックインストール**
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**⚙️ 2. AIクライアントの設定**

**Claude Desktop設定：**

設定ファイルに以下を追加：
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`  
- **Linux**: `~/.config/claude/claude_desktop_config.json`

**基本設定（推奨）：**
```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": [
        "run", "--with", "tree-sitter-analyzer[mcp]",
        "python", "-m", "tree_sitter_analyzer.mcp.server"
      ]
    }
  }
}
```

**高度な設定（プロジェクトルートを指定）：**
```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": [
        "run", "--with", "tree-sitter-analyzer[mcp]",
        "python", "-m", "tree_sitter_analyzer.mcp.server"
      ],
      "env": {
        "TREE_SITTER_PROJECT_ROOT": "/absolute/path/to/your/project"
      }
    }
  }
}
```

**その他のAIクライアント：**
- **Cursor**: 組み込みMCPサポート、Cursorドキュメントの設定を参照
- **Roo Code**: MCPプロトコルをサポート、各設定ガイドを確認
- **その他のMCP互換クライアント**: 同じサーバー設定を使用

**⚠️ 設定注意事項：**
- **基本設定**: ツールが自動的にプロジェクトルートを検出（推奨）
- **高度な設定**: 特定のディレクトリを指定する必要がある場合、絶対パスで`/absolute/path/to/your/project`を置き換える
- **使用を避ける**: `${workspaceFolder}`などの変数は一部のクライアントでサポートされない場合があります

**🎉 3. AIクライアントを再起動して、大規模なコードファイルの分析を開始！**

### 💻 開発者（CLI）

```bash
# インストール
uv add "tree-sitter-analyzer[popular]"

# ファイル規模チェック（1419行の大型サービスクラス、瞬時完了）
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text

# 構造テーブル生成（1クラス、66メソッド、明確に表示）
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full

# 正確なコード抽出
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 100 --end-line 105
```

---

## ❓ Tree-sitter Analyzerを選ぶ理由

### 🎯 実際の痛みポイントを解決

**従来のアプローチのジレンマ：**
- ❌ 大きなファイルがLLMトークン制限を超える
- ❌ AIがコード構造を理解できない
- ❌ 手動でファイル分割が必要
- ❌ コンテキスト損失により不正確な分析

**Tree-sitter Analyzerのブレークスルー：**
- ✅ **スマート分析**: 完全なファイルを読まずに構造を理解
- ✅ **正確な位置特定**: 正確な行単位のコード抽出
- ✅ **AIネイティブ**: LLMワークフローに最適化
- ✅ **多言語サポート**: Java、Python、JavaScript/TypeScriptなど

## 📖 実際の使用例

### 💬 AI IDE プロンプト（テスト済み・検証済み、すぐに使用可能）

> **✅ テスト検証状況：** 以下のすべてのプロンプトは実際の環境でテスト・検証されており、100%の可用性を保証
> 
> **⚠️ 重要な注意事項：**
> - **ステップ0は必須** - 他のツールを使用する前に、必ずプロジェクトパスを設定してください
> - プロジェクト内のファイルには**相対パス**を使用（例：`examples/BigService.java`）
> - プロジェクト外のファイルには**絶対パス**を使用（例：`C:\git-public\tree-sitter-analyzer\examples\BigService.java`）
> - すべてのツールはWindowsとUnixスタイルのパスをサポート
> - プロジェクトパスはコードリポジトリのルートディレクトリを指す必要があります
> - MCP設定でプロジェクトパスを設定するか、動的に設定できます

#### 🔧 **ステップ0：プロジェクトパスの設定（最初に必須）**

**オプション1：MCP設定で構成**
```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": ["run", "python", "-m", "tree_sitter_analyzer.mcp.server"],
      "env": {
        "TREE_SITTER_PROJECT_ROOT": "/path/to/your/project"
      }
    }
  }
}
```

**オプション2：AIに直接伝える（推奨、より自然）**

**方法1：明確な設定要求**
```
プロジェクトルートディレクトリを設定してください、パスは：C:\git-public\tree-sitter-analyzer
```

**方法2：プロジェクト情報の提供**
```
私のプロジェクトは：C:\git-public\tree-sitter-analyzer
このパスをプロジェクトルートとして設定してください
```

**方法3：簡単な説明**
```
プロジェクトパス：C:\git-public\tree-sitter-analyzer
```

**AIは自動的に適切なツールを呼び出してパスを設定します、複雑なコマンド形式を覚える必要はありません**

#### 🔍 **ステップ1：ファイル規模をチェック**

**方法1：明確な分析要求**
```
このファイルを分析してください：examples/BigService.java
```

**方法2：分析ニーズの説明**
```
このJavaファイルの規模と構造を理解したい：examples/BigService.java
```

**方法3：簡単な要求**
```
このファイルを分析：examples/BigService.java
```

**絶対パスを使用する代替案：**
```
このファイルを分析してください：C:\git-public\tree-sitter-analyzer\examples\BigService.java
```

**戻り値の形式：**
```json
{
  "file_path": "examples/BigService.java",
  "language": "java",
  "metrics": {
    "lines_total": 1419,
    "lines_code": 907,
    "lines_comment": 246,
    "lines_blank": 267,
    "elements": {
      "classes": 1,
      "methods": 66,
      "fields": 9,
      "imports": 8,
      "packages": 1,
      "total": 85
    },
    "complexity": {
      "total": 348,
      "average": 5.27,
      "max": 15
    }
  }
}
```

#### 📊 **ステップ2：構造テーブル生成**

**方法1：明確なテーブル要求**
```
このファイルの詳細な構造テーブルを生成してください：examples/BigService.java
```

**方法2：テーブルニーズの説明**
```
このJavaファイルの完全な構造を見たい、すべてのクラス、メソッド、フィールドを含む：examples/BigService.java
```

**方法3：簡単な要求**
```
構造テーブルを生成：examples/BigService.java
```

**絶対パスを使用する代替案：**
```
詳細な構造テーブルを生成してください：C:\git-public\tree-sitter-analyzer\examples\BigService.java
```

**戻り値の形式：**
- 完全なMarkdownテーブル
- クラス情報、メソッドリスト（行番号付き）、フィールドリストを含む
- メソッドシグネチャ、可視性、行範囲、複雑さなどの詳細情報

#### ✂️ **ステップ3：コードスニペットの抽出**

**方法1：明確な抽出要求**
```
このファイルの93-105行目のコードを抽出してください：examples/BigService.java
```

**方法2：抽出ニーズの説明**
```
このJavaファイルの93行目から105行目のコード内容を見たい：examples/BigService.java
```

**方法3：簡単な要求**
```
93-105行目のコードを抽出：examples/BigService.java
```

**絶対パスを使用する代替案：**
```
コードスニペットを抽出してください：C:\git-public\tree-sitter-analyzer\examples\BigService.java、93-105行目
```

**戻り値の形式:**
```json
{
  "file_path": "examples/BigService.java",
  "range": {
    "start_line": 93,
    "end_line": 105,
    "start_column": null,
    "end_column": null
  },
  "content": "    private void checkMemoryUsage() {\n        Runtime runtime = Runtime.getRuntime();\n        long totalMemory = runtime.totalMemory();\n        long freeMemory = runtime.freeMemory();\n        long usedMemory = totalMemory - freeMemory;\n\n        System.out.println(\"Total Memory: \" + totalMemory);\n        System.out.println(\"Free Memory: \" + freeMemory);\n        System.out.println(\"Used Memory: \" + usedMemory);\n\n        if (usedMemory > totalMemory * 0.8) {\n            System.out.println(\"WARNING: High memory usage detected!\");\n        }\n",
  "content_length": 542
}
```

#### 🔍 **ステップ4：スマートクエリフィルタリング（v0.9.6+）**

**エラーハンドリングの強化（v0.9.7）：**
- ツール名識別を追加した`@handle_mcp_errors`デコレータの改善
- デバッグとトラブルシューティングのためのより良いエラーコンテキスト
- ファイルパスのセキュリティ検証の強化

**特定のメソッドを検索：**
```
このファイルのmainメソッドを探してください：examples/BigService.java
```

**認証関連メソッドを検索：**
```
認証関連のすべてのメソッドを見つけたい：examples/BigService.java
```

**パラメーターなしのパブリックメソッドを検索：**
```
パラメーターなしのパブリックgetterメソッドをすべて見つけてください：examples/BigService.java
```

**戻り値の形式：**
```json
{
  "success": true,
  "results": [
    {
      "capture_name": "method",
      "node_type": "method_declaration",
      "start_line": 1385,
      "end_line": 1418,
      "content": "public static void main(String[] args) {\n        System.out.println(\"BigService Demo Application\");\n        System.out.println(\"==========================\");\n\n        BigService service = new BigService();\n\n        // Test basic functions\n        System.out.println(\"\\n--- Testing Basic Functions ---\");\n        service.authenticateUser(\"testuser\", \"password123\");\n        service.createSession(\"testuser\");\n\n        // Test customer management\n        System.out.println(\"\\n--- Testing Customer Management ---\");\n        service.updateCustomerName(\"CUST001\", \"New Customer Name\");\n        Map<String, Object> customerInfo = service.getCustomerInfo(\"CUST001\");\n\n        // Test report generation\n        System.out.println(\"\\n--- Testing Report Generation ---\");\n        Map<String, Object> reportParams = new HashMap<>();\n        reportParams.put(\"start_date\", \"2024-01-01\");\n        reportParams.put(\"end_date\", \"2024-12-31\");\n        service.generateReport(\"sales\", reportParams);\n\n        // Test performance monitoring\n        System.out.println(\"\\n--- Testing Performance Monitoring ---\");\n        service.monitorPerformance();\n\n        // Test security check\n        System.out.println(\"\\n--- Testing Security Check ---\");\n        service.performSecurityCheck();\n\n        System.out.println(\"\\n--- Demo Completed ---\");\n        System.out.println(\"BigService demo application finished successfully.\");\n    }"
    }
  ],
  "count": 1,
  "file_path": "examples/BigService.java",
  "language": "java",
  "query": "methods"
}
```

#### 💡 **重要な注意事項**
- **自然言語**: 複雑なパラメーター形式を覚える必要はなく、自然言語でAIに直接伝える
- **パス処理**: 相対パスは自動的にプロジェクトルートに解決、絶対パスも完全にサポート
- **セキュリティ保護**: ツールは自動的にプロジェクト境界チェックを実行して安全を確保
- **ワークフロー**: 順序通りの使用を推奨：ステップ1 → 2 → 4（クエリフィルタリング）→ 3（正確な抽出）
- **スマート理解**: AIは自動的にあなたのニーズを理解し、適切なツールを呼び出します

### 🛠️ CLIコマンド例

```bash
# クイック分析（1419行の大ファイル、瞬時完了）
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text

# 詳細構造テーブル（66メソッドを明確に表示）
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full

# 正確なコード抽出（メモリ使用量監視コードスニペット）
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 100 --end-line 105

# 多言語サポートテスト（Pythonファイル）
uv run python -m tree_sitter_analyzer examples/sample.py --table=full

# 小ファイルクイック解析（54行Javaファイル）
uv run python -m tree_sitter_analyzer examples/MultiClass.java --advanced

# サイレントモード（結果のみ表示）
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full --quiet

# 🔍 クエリフィルタリング例（v0.9.6+）
# 特定のメソッドを検索
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=main"

# 認証関連メソッドを検索
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=~auth*"

# パラメーターなしのパブリックメソッドを検索
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "params=0,public=true"

# 静的メソッドを検索
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "static=true"

# フィルター構文ヘルプを表示
uv run python -m tree_sitter_analyzer --filter-help
```

---

## 🏗️ アーキテクチャ改善（v1.2.0+）

### 🔄 **統一要素管理システム**

Tree-sitter Analyzerは今、すべてのコード要素を統一されたシステムに統合する革命的な統一アーキテクチャを特徴としています：

#### **以前（レガシーアーキテクチャ）：**
- クラス、メソッド、フィールド、インポートの独立したコレクション
- 異なる解析モード間でのデータ構造の不整合
- 複雑なメンテナンスと潜在的な不整合

#### **現在（統一アーキテクチャ）：**
- **単一の`elements`リスト**: すべてのコード要素（クラス、メソッド、フィールド、インポート、パッケージ）を統一
- **一貫した要素タイプ**: 各要素に`element_type`プロパティがあり、識別が容易
- **簡素化されたAPI**: より明確なインターフェースと削減された複雑さ
- **より良い保守性**: すべてのコード要素の単一の真実の源

#### **利点：**
- ✅ **一貫性**: すべての解析モードでの統一されたデータ構造
- ✅ **シンプルさ**: 使用と理解がより簡単
- ✅ **拡張性**: 新しい要素タイプの追加が容易
- ✅ **パフォーマンス**: 最適化されたメモリ使用と処理
- ✅ **後方互換性**: 既存のAPIがシームレスに動作し続ける

#### **サポートされている要素タイプ：**
- `class` - クラスとインターフェース
- `function` - メソッドと関数  
- `variable` - フィールドと変数
- `import` - インポート文
- `package` - パッケージ宣言

---

## 🛠️ コア機能

### 📊 **コード構造分析**
完全なファイルを読まずに洞察を取得：
- クラス、メソッド、フィールド統計
- パッケージ情報とインポート依存関係
- 複雑さメトリクス
- 正確な行番号位置決め

### ✂️ **スマートコード抽出**
- 行範囲で正確に抽出
- 元の形式とインデントを維持
- 位置メタデータを含む
- 大ファイルの効率的な処理をサポート

### 🔍 **高度なクエリフィルタリング**
強力なコード要素クエリとフィルタリングシステム：
- **完全一致**: `--filter "name=main"` 特定のメソッドを検索
- **パターンマッチング**: `--filter "name=~auth*"` 認証関連メソッドを検索  
- **パラメーターフィルタリング**: `--filter "params=2"` 特定のパラメーター数のメソッドを検索
- **修飾子フィルタリング**: `--filter "static=true,public=true"` 静的パブリックメソッドを検索
- **複合条件**: `--filter "name=~get*,params=0,public=true"` 複数の条件を組み合わせ
- **CLI/MCP一貫性**: コマンドラインとAIアシスタントで同じフィルタリング構文

### 🔗 **AIアシスタント統合**
MCPプロトコルを通じた深い統合：
- Claude Desktop
- Cursor IDE  
- Roo Code
- その他のMCPサポートAIツール

### 🌍 **多言語サポート**
- **Java** - フルサポート、Spring、JPAフレームワークを含む
- **Python** - 完全サポート、型注釈、デコレーターを含む
- **JavaScript/TypeScript** - フルサポート、ES6+機能を含む
- **C/C++、Rust、Go** - 基本サポート

---

## 📦 インストールガイド

### 👤 **エンドユーザー**
```bash
# 基本インストール
uv add tree-sitter-analyzer

# 人気言語パッケージ（推奨）
uv add "tree-sitter-analyzer[popular]"

# MCPサーバーサポート
uv add "tree-sitter-analyzer[mcp]"

# フルインストール
uv add "tree-sitter-analyzer[all,mcp]"
```

### 👨‍💻 **開発者**
```bash
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer
uv sync --extra all --extra mcp
```

---

## 🔒 セキュリティと設定

### 🛡️ **プロジェクト境界保護**

Tree-sitter Analyzerは自動的にプロジェクト境界を検出・保護：

- **自動検出**: `.git`、`pyproject.toml`、`package.json`などに基づく
- **CLI制御**: `--project-root /path/to/project`
- **MCP統合**: `TREE_SITTER_PROJECT_ROOT=/path/to/project`または自動検出を使用
- **セキュリティ保証**: プロジェクト境界内のファイルのみ分析

**推奨MCP設定：**

**オプション1: 自動検出（推奨）**
```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": ["run", "--with", "tree-sitter-analyzer[mcp]", "python", "-m", "tree_sitter_analyzer.mcp.server"]
    }
  }
}
```

**オプション2: 手動プロジェクトルート指定**
```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": ["run", "--with", "tree-sitter-analyzer[mcp]", "python", "-m", "tree_sitter_analyzer.mcp.server"],
      "env": {"TREE_SITTER_PROJECT_ROOT": "/path/to/your/project"}
    }
  }
}
```

---

## 🏆 品質保証

### 📊 **品質メトリクス**
- **1,504テスト** - 100%合格率 ✅
- **74.30%コードカバレッジ** - 業界最高レベル
- **ゼロテスト失敗** - 完全なCI/CD対応
- **クロスプラットフォーム対応** - Windows、macOS、Linux

### ⚡ **最新の品質成果（v1.2.0）**
- ✅ **クロスプラットフォームパス互換性** - Windows短パス名とmacOSシンボリックリンクの違いを修正
- ✅ **Windows環境** - Windows APIを使用した堅牢なパス正規化を実装
- ✅ **macOS環境** - `/var`と`/private/var`シンボリックリンクの違いを修正
- ✅ **包括的テストカバレッジ** - 1504テスト、74.30%カバレッジ
- ✅ **GitFlow実装** - 開発/リリースブランチの専門的なブランチ戦略。詳細は[GitFlowドキュメント](GITFLOW_ja.md)を参照してください。

### ⚙️ **テスト実行**
```bash
# すべてのテストを実行
uv run pytest tests/ -v

# カバレッジレポート生成
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html --cov-report=term-missing

# 特定のテストを実行
uv run pytest tests/test_mcp_server_initialization.py -v
```

### 📈 **カバレッジハイライト**
- **言語検出器**: 98.41%（優秀）
- **CLIメインエントリ**: 94.36%（優秀）
- **クエリフィルタリングシステム**: 96.06%（優秀）
- **クエリサービス**: 86.25%（良好）
- **エラーハンドリング**: 82.76%（良好）

---

## 🤖 AIコラボレーションサポート

### ⚡ **AI開発に最適化**

このプロジェクトは専門的な品質管理でAI支援開発をサポート：

```bash
# AIシステムコード生成前チェック
uv run python check_quality.py --new-code-only
uv run python llm_code_checker.py --check-all

# AI生成コードレビュー
uv run python llm_code_checker.py path/to/new_file.py
```

📖 **詳細ガイド**:
- [AIコラボレーションガイド](AI_COLLABORATION_GUIDE.md)
- [LLMコーディングガイドライン](LLM_CODING_GUIDELINES.md)

---

## 📚 ドキュメント

- **[ユーザーMCPセットアップガイド](MCP_SETUP_USERS.md)** - シンプルな設定ガイド
- **[開発者MCPセットアップガイド](MCP_SETUP_DEVELOPERS.md)** - ローカル開発設定
- **[プロジェクトルート設定](PROJECT_ROOT_CONFIG.md)** - 完全な設定リファレンス
- **[APIドキュメント](docs/api.md)** - 詳細なAPIリファレンス
- **[貢献ガイド](CONTRIBUTING.md)** - 貢献方法

---

## 🤝 貢献

あらゆる形の貢献を歓迎します！詳細は[貢献ガイド](CONTRIBUTING.md)をご確認ください。

### ⭐ **スターをください！**

このプロジェクトがお役に立てば、GitHubで⭐をお願いします - これが私たちにとって最大のサポートです！

---

## 📄 ライセンス

MITライセンス - 詳細は[LICENSE](LICENSE)ファイルをご覧ください。

---

**🎯 大型コードベースとAIアシスタントを扱う開発者のために構築**

*すべてのコード行をAIに理解させ、すべてのプロジェクトでトークン制限を突破*

---

## ✅ プロンプトテスト検証

このドキュメントのすべてのAIプロンプトは実際の環境で徹底的にテスト・検証されており、以下を保証します：

- **100%可用性** - すべてのプロンプトが正しく動作
- **多言語サポート** - Java、Python、JavaScriptなどの主流言語をサポート
- **パス互換性** - 相対パスと絶対パスの両方が完全にサポート
- **Windows/Linux互換性** - クロスプラットフォームパス形式が自動的に処理
- **リアルタイム検証** - 実際のコードファイルを使用してテスト

**テスト環境：**
- オペレーティングシステム：Windows 10
- プロジェクト：tree-sitter-analyzer v1.2.0
- テストファイル：BigService.java (1419行)、sample.py (256行)、MultiClass.java (54行)
- テストツール：すべてのMCPツール（check_code_scale、analyze_code_structure、extract_code_section、query_code）

**🚀 今すぐ始める** → [30秒クイックスタート](#-30秒クイックスタート)
