# Tree-sitter Analyzer

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-1358%20passed-brightgreen.svg)](#testing)
[![Coverage](https://img.shields.io/badge/coverage-74.54%25-green.svg)](#testing)
[![Quality](https://img.shields.io/badge/quality-enterprise%20grade-blue.svg)](#quality)
[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![GitHub Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer)

## 🚀 LLM トークン制限を突破し、AI にあらゆるサイズのコードファイルを理解させる

> **AI 時代のために設計された革命的なコード解析ツール**

想像してみてください：1419行以上の Java サービスクラスがあり、Claude や ChatGPT がトークン制限で解析できない状況を。今、Tree-sitter Analyzer により AI アシスタントは以下が可能になります：

- ⚡ **3秒で完全なコード構造概要を取得**
- 🎯 **任意の行範囲のコードスニペットを正確に抽出**
- 📍 **クラス、メソッド、フィールドの正確な位置をスマート特定**
- 🔗 **Claude Desktop、Cursor、Roo Code など AI IDE とのシームレス統合**

**もう大きなファイルで AI が困ることはありません！**

---

## 🚀 30秒クイック体験

### 🤖 AI ユーザー（Claude Desktop、Cursor、Roo Code など）

**📦 1. ワンクリックインストール**
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**⚙️ 2. AI クライアント設定**

**Claude Desktop 設定：**

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

**高度な設定（プロジェクトルート指定）：**
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

**その他の AI クライアント：**
- **Cursor**: 内蔵 MCP サポート、Cursor ドキュメントの設定を参照
- **Roo Code**: MCP プロトコルサポート、それぞれの設定ガイドを確認
- **その他 MCP 対応クライアント**: 同じサーバー設定を使用

**⚠️ 設定の注意：**
- **基本設定**: ツールがプロジェクトルートを自動検出（推奨）
- **高度な設定**: 特定のディレクトリを指定する場合は、絶対パスで `/absolute/path/to/your/project` を置換
- **使用回避**: `${workspaceFolder}` などの変数は一部のクライアントでサポートされない場合あり

**🎉 3. AI クライアントを再起動して巨大コードファイルの解析開始！**

### 💻 開発者（CLI）

```bash
# インストール
uv add "tree-sitter-analyzer[popular]"

# ファイル規模チェック（1419行の大型サービスクラス、瞬時完了）
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text

# 構造テーブル生成（1クラス、66メソッド、明確表示）
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full

# 正確なコード抽出
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 100 --end-line 105
```

---

## ❓ なぜ Tree-sitter Analyzer を選ぶのか？

### 🎯 **実際の痛点を解決**

**従来のアプローチの問題点：**
- ❌ 大型ファイルが LLM トークン制限を超過
- ❌ AI がコード構造を理解できない
- ❌ 手動でのファイル分割が必要
- ❌ コンテキスト喪失により不正確な解析

**Tree-sitter Analyzer の突破：**
- ✅ **スマート解析**: 完全なファイルを読まずに構造を理解
- ✅ **正確な位置決め**: 行単位で正確なコード抽出
- ✅ **AI ネイティブ**: LLM ワークフローに最適化
- ✅ **多言語サポート**: Java、Python、JavaScript/TypeScript など

### ✨ コアアドバンテージ

#### ⚡ **電光石火の解析速度**
```bash
# 1419行大型 Java サービスクラス解析結果（< 1秒）
Lines: 1419 | Classes: 1 | Methods: 66 | Fields: 9 | Imports: 8
```

#### 📊 **正確な構造テーブル**
| クラス名 | タイプ | 可視性 | 行範囲 | メソッド数 | フィールド数 |
|----------|--------|---------|---------|-------------|-------------|
| BigService | class | public | 17-1419 | 66 | 9 |

#### 🔄 **AI アシスタント三段階ワークフロー**
- **Step 1**: `check_code_scale` - ファイル規模と複雑さをチェック
- **Step 2**: `analyze_code_structure` - 詳細な構造テーブルを生成
- **Step 3**: `extract_code_section` - オンデマンドでコードスニペットを抽出

---

## 🛠️ 強力機能概要

### 📊 **コード構造解析**
完全なファイルを読まずに洞察を取得：
- クラス、メソッド、フィールド統計
- パッケージ情報とインポート依存関係
- 複雑度メトリクス
- 正確な行番号位置決め

### ✂️ **スマートコード抽出**
- 行範囲で正確に抽出
- 元のフォーマットとインデントを維持
- 位置メタデータを含む
- 大型ファイルの効率的処理をサポート

### 🔗 **AI アシスタント統合**
MCP プロトコルによる深い統合：
- Claude Desktop
- Cursor IDE  
- Roo Code
- その他の MCP サポート AI ツール

### 🌍 **多言語サポート**
- **Java** - Spring、JPA フレームワークを含む完全サポート
- **Python** - 型注釈、デコレータを含む完全サポート
- **JavaScript/TypeScript** - ES6+ 機能を含む完全サポート
- **C/C++、Rust、Go** - 基本サポート

---

## 📖 実用例

### 💬 AI IDE プロンプト（コピー&使用）

#### 🔍 **Step 1：ファイル規模チェック**

**プロンプト：**
```
MCP ツール check_code_scale でファイル規模を解析
パラメータ： {"file_path": "examples/BigService.java"}
```

**返却フォーマット：**
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

#### 📊 **Step 2：構造テーブル生成**

**プロンプト：**
```
MCP ツール analyze_code_structure で詳細構造を生成
パラメータ： {"file_path": "examples/BigService.java"}
```

**返却フォーマット：**
- 完全な Markdown テーブル
- クラス情報、メソッドリスト（行番号付き）、フィールドリストを含む
- メソッドシグネチャ、可視性、行範囲、複雑度などの詳細情報

#### ✂️ **Step 3：コードスニペット抽出**

**プロンプト：**
```
MCP ツール extract_code_section で指定コードセクションを抽出
パラメータ： {"file_path": "examples/BigService.java", "start_line": 100, "end_line": 105}
```

**返却フォーマット：**
```json
{
  "file_path": "examples/BigService.java",
  "range": {"start_line": 100, "end_line": 105},
  "content": "実際のコード内容...",
  "content_length": 245
}
```

#### 💡 **重要な注意点**
- **パラメータフォーマット**: snake_case を使用（`file_path`、`start_line`、`end_line`）
- **パス処理**: 相対パスはプロジェクトルートに自動解決
- **セキュリティ保護**: ツールが自動的にプロジェクト境界チェックを実行
- **ワークフロー**: Step 1 → 2 → 3 の順序で使用することを推奨

### 🛠️ CLI コマンド例

```bash
# クイック解析（1419行大型ファイル、瞬時完了）
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text

# 詳細構造テーブル（66メソッドが明確に表示）
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full

# 正確なコード抽出（メモリ使用監視コードスニペット）
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 100 --end-line 105

# サイレントモード（結果のみ表示）
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full --quiet
```

---

## 📦 インストールオプション

### 👤 **エンドユーザー**
```bash
# 基本インストール
uv add tree-sitter-analyzer

# 人気言語パッケージ（推奨）
uv add "tree-sitter-analyzer[popular]"

# MCP サーバーサポート
uv add "tree-sitter-analyzer[mcp]"

# 完全インストール
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

Tree-sitter Analyzer はプロジェクト境界を自動検出・保護：

- **自動検出**: `.git`、`pyproject.toml`、`package.json` などに基づく
- **CLI 制御**: `--project-root /path/to/project`
- **MCP 統合**: `TREE_SITTER_PROJECT_ROOT=/path/to/project` または自動検出を使用
- **セキュリティ保証**: プロジェクト境界内のファイルのみを解析

**推奨 MCP 設定：**

**オプション 1：自動検出（推奨）**
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

**オプション 2：手動プロジェクトルート指定**
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

## 🏆 エンタープライズ級品質保証

### 📊 **品質指標**
- **1,tests-1358%20passed** - 100% 成功率 ✅
- **74.54% コードカバレッジ** - 業界トップレベル
- **テスト失敗ゼロ** - 完全な CI/CD 対応
- **クロスプラットフォーム対応** - Windows、macOS、Linux

### ⚡ **最新品質成果（v0.9.4）**
- ✅ **テストスイート完全安定化** - すべての歴史的問題を修正
- ✅ **フォーマッタモジュール突破** - カバレッジが大幅に向上
- ✅ **エラーハンドリング最適化** - エンタープライズ級例外処理
- ✅ **100+ 新規包括テスト** - 重要モジュールをカバー

### ⚙️ **テスト実行**
```bash
# すべてのテスト実行
uv run pytest tests/ -v

# カバレッジレポート生成
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html

# 特定テスト実行
uv run pytest tests/test_mcp_server_initialization.py -v
```

### 📈 **カバレッジハイライト**
- **言語検出器**: 98.41%（優秀）
- **CLI メインエントリ**: 97.78%（優秀）
- **エラーハンドリング**: 82.76%（良好）
- **セキュリティフレームワーク**: 78%+（信頼性）

---

## 🤖 AI コラボレーションサポート

### ⚡ **AI 開発に最適化**

このプロジェクトは専門的な品質管理により AI 支援開発をサポート：

```bash
# AI システムのコード生成前チェック
uv run python check_quality.py --new-code-only
uv run python llm_code_checker.py --check-all

# AI 生成コードレビュー
uv run python llm_code_checker.py path/to/new_file.py
```

📖 **詳細ガイド**：
- [AI コラボレーションガイド](AI_COLLABORATION_GUIDE.md)
- [LLM コーディングガイドライン](LLM_CODING_GUIDELINES.md)

---

## 📚 完全ドキュメント

- **[ユーザー MCP セットアップガイド](MCP_SETUP_USERS.md)** - シンプルな設定ガイド
- **[開発者 MCP セットアップガイド](MCP_SETUP_DEVELOPERS.md)** - ローカル開発設定
- **[プロジェクトルート設定](PROJECT_ROOT_CONFIG.md)** - 完全設定リファレンス
- **[API ドキュメント](docs/api.md)** - 詳細 API リファレンス
- **[コントリビューションガイド](CONTRIBUTING.md)** - 貢献方法

---

## 🤝 コントリビューション

あらゆる形式の貢献を歓迎します！詳細は [コントリビューションガイド](CONTRIBUTING.md) をご確認ください。

### ⭐ **Star をお願いします！**

このプロジェクトがお役に立てば、GitHub で ⭐ をお願いします - 私たちにとって最大のサポートです！

---

## 📄 オープンソースライセンス

MIT ライセンス - 詳細は [LICENSE](LICENSE) ファイルを参照。

---

## 🎯 まとめ

Tree-sitter Analyzer は AI 時代の必須ツール：

- **コア痛点解決** - AI が大型ファイルのトークン制限を突破
- **エンタープライズ級品質** - 1,tests-1358%20passed、74.54% カバレッジ
- **すぐに使用可能** - 30秒設定、主要 AI クライアントサポート
- **多言語サポート** - Java、Python、JavaScript/TypeScript など
- **活発にメンテナンス** - v0.9.4 最新版、継続更新

**今すぐ体験** → [30秒クイック体験](#🚀-30秒クイック体験)

---

**🎯 大型コードベースと AI アシスタントに取り組む開発者のために構築**

*すべてのコード行を AI に理解させ、すべてのプロジェクトでトークン制限を突破*
