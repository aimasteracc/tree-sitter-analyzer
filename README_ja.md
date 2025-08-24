# Tree-sitter Analyzer

[![Pythonバージョン](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![ライセンス](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![テスト](https://img.shields.io/badge/1504-brightgreen.svg)](#品質保証)
[![カバレッジ](https://img.shields.io/badge/coverage-74.30%25-green.svg)](#品質保証)
[![品質](https://img.shields.io/badge/quality-enterprise%20grade-blue.svg)](#品質保証)
[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![バージョン](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/aimasteracc/tree-sitter-analyzer/releases)
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

**大きなファイルのためにAIが無力になることはもうありません！**

## 📊 ライブデモと結果

### ⚡ **電光石火の解析速度**
```bash
# 1419行の大型Javaサービスクラス解析結果（< 1秒）
Lines: 1419 | Classes: 1 | Methods: 66 | Fields: 9 | Imports: 8
```

### 📊 **正確な構造テーブル**
| クラス名 | タイプ | 可視性 | 行範囲 | メソッド数 | フィールド数 |
|----------|--------|--------|--------|------------|--------------|
| BigService | class | public | 17-1419 | 66 | 9 |

### 🔄 **AIアシスタント3ステップワークフロー**
- **ステップ1**: `check_code_scale` - ファイルの規模と複雑さをチェック
- **ステップ2**: `analyze_code_structure` - 詳細な構造テーブルを生成
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

### 💬 AI IDE プロンプト（コピーして使用）

#### 🔍 **ステップ1: ファイル規模をチェック**

**プロンプト：**
```
MCPツールcheck_code_scaleを使用してファイル規模を分析
パラメーター: {"file_path": "examples/BigService.java"}
```

**戻り値の形式：**
```json
{
  "file_path": "examples/BigService.java",
  "language": "java",
  "metrics": {
    "lines_total": 1419,
    "lines_code": 1419,
    "elements": {
      "classes": 1,
      "methods": 66,
      "fields": 9
    }
  }
}
```

#### 📊 **ステップ2: 構造テーブル生成**

**プロンプト：**
```
MCPツールanalyze_code_structureを使用して詳細な構造を生成
パラメーター: {"file_path": "examples/BigService.java"}
```

**戻り値の形式：**
- 完全なMarkdownテーブル
- クラス情報、メソッドリスト（行番号付き）、フィールドリストを含む
- メソッドシグネチャ、可視性、行範囲、複雑さなどの詳細情報

#### ✂️ **ステップ3: コードスニペットの抽出**

**プロンプト：**
```
MCPツールextract_code_sectionを使用して指定されたコードセクションを抽出
パラメーター: {"file_path": "examples/BigService.java", "start_line": 100, "end_line": 105}
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

#### 🔍 **ステップ4: スマートクエリフィルタリング（v0.9.6+）**

**エラーハンドリングの強化（v0.9.7）：**
- ツール名識別を追加した`@handle_mcp_errors`デコレータの改善
- デバッグとトラブルシューティングのためのより良いエラーコンテキスト
- ファイルパスのセキュリティ検証の強化

**特定のメソッドを検索：**
```
MCPツールquery_codeを使用してコード要素を正確に検索
パラメーター: {"file_path": "examples/BigService.java", "query_key": "methods", "filter": "name=main"}
```

**認証関連メソッドを検索：**
```
MCPツールquery_codeを使用して認証メソッドを検索
パラメーター: {"file_path": "examples/BigService.java", "query_key": "methods", "filter": "name=~auth*"}
```

**パラメーターなしのパブリックメソッドを検索：**
```
MCPツールquery_codeを使用してgetterメソッドを検索
パラメーター: {"file_path": "examples/BigService.java", "query_key": "methods", "filter": "params=0,public=true"}
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
      "content": "public static void main(String[] args) { ... }"
    }
  ],
  "count": 1
}
```

#### 💡 **重要な注意事項**
- **パラメーター形式**: スネークケースを使用（`file_path`、`start_line`、`end_line`）
- **パス処理**: 相対パスは自動的にプロジェクトルートに解決
- **セキュリティ保護**: ツールは自動的にプロジェクト境界チェックを実行
- **ワークフロー**: 順序通りの使用を推奨：ステップ1 → 2 → 4（クエリフィルタリング）→ 3（正確な抽出）
- **フィルター構文**: `name=値`、`name=~パターン*`、`params=数字`、`static/public/private=true/false`をサポート

### 🛠️ CLIコマンド例

```bash
# クイック分析（1419行の大ファイル、瞬時完了）
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text

# 詳細構造テーブル（66メソッドを明確に表示）
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full

# 正確なコード抽出（メモリ使用量監視コードスニペット）
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 100 --end-line 105

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
- **74.44%コードカバレッジ** - 業界最高レベル
- **ゼロテスト失敗** - 完全なCI/CD対応
- **クロスプラットフォーム対応** - Windows、macOS、Linux

### ⚡ **最新の品質成果（v1.0.0）**
- ✅ **クロスプラットフォームパス互換性** - Windows短パス名とmacOSシンボリックリンクの違いを修正
- ✅ **Windows環境** - Windows APIを使用した堅牢なパス正規化を実装
- ✅ **macOS環境** - `/var`と`/private/var`シンボリックリンクの違いを修正
- ✅ **包括的テストカバレッジ** - 1504テスト、74.44%カバレッジ
- ✅ **GitFlow実装** - 開発/リリースブランチの専門的なブランチ戦略。詳細は[GitFlowドキュメント](GITFLOW_ja.md)を参照してください。

### ⚙️ **テスト実行**
```bash
# すべてのテストを実行
uv run pytest tests/ -v

# カバレッジレポート生成
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html

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

**🚀 今すぐ始める** → [30秒クイックスタート](#-30秒クイックスタート)
