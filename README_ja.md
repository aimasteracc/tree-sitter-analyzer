# 🌳 Tree-sitter Analyzer

**[English](README.md)** | **日本語** | **[简体中文](README_zh.md)**

[![Pythonバージョン](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![ライセンス](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![テスト](https://img.shields.io/badge/tests-3370%20passed-brightgreen.svg)](#8--品質保証)
[![カバレッジ](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer)
[![品質](https://img.shields.io/badge/quality-enterprise%20grade-blue.svg)](#8--品質保証)
[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![バージョン](https://img.shields.io/badge/version-1.9.2-blue.svg)](https://github.com/aimasteracc/tree-sitter-analyzer/releases)
[![zread](https://img.shields.io/badge/Ask_Zread-_.svg?style=flat&color=00b0aa&labelColor=000000&logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCAxNiAxNiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTQuOTYxNTYgMS42MDAxSDIuMjQxNTZDMS44ODgxIDEuNjAwMSAxLjYwMTU2IDEuODg2NjQgMS42MDE1NiAyLjI0MDFWNC45NjAxQzEuNjAxNTYgNS4zMTM1NiAxLjg4ODEgNS42MDAxIDIuMjQxNTYgNS42MDAxSDQuOTYxNTZDNS4zMTUwMiA1LjYwMDEgNS42MDE1NiA1LjMxMzU2IDUuNjAxNTYgNC45NjAxVjIuMjQwMUM1LjYwMTU2IDEuODg2NjQgNS4zMTUwMiAxLjYwMDEgNC45NjE1NiAxLjYwMDFaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik00Ljk2MTU2IDEwLjM5OTlIMi4yNDE1NkMxLjg4ODEgMTAuMzk5OSAxLjYwMTU2IDEwLjY4NjQgMS42MDE1NiAxMS4wMzk5VjEzLjc1OTlDMS42MDE1NiAxNC4xMTM0IDEuODg4MSAxNC4zOTk5IDIuMjQxNTYgMTQuMzk5OUg0Ljk2MTU2QzUuMzE1MDIgMTQuMzk5OSA1LjYwMTU2IDE0LjExMzQgNS42MDE1NiAxMy43NTk5VjExLjAzOTlDNS42MDE1NiAxMC42ODY0IDUuMzE1MDIgMTAuMzk5OSA0Ljk2MTU2IDEwLjM5OTlaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik0xMy43NTg0IDEuNjAwMUgxMS4wMzg0QzEwLjY4NSAxLjYwMDEgMTAuMzk4NCAxLjg4NjY0IDEwLjM5ODQgMi4yNDAxVjQuOTYwMUMxMC4zOTg0IDUuMzEzNTYgMTAuNjg1IDUuNjAwMSAxMS4wMzg0IDUuNjAwMUgxMy43NTg0QzE0LjExMTkgNS42MDAxIDE0LjM5ODQgNS4zMTM1NiAxNC4zOTg0IDQuOTYwMVYyLjI0MDFDMTQuMzk4NCAxLjg4NjY0IDE0LjExMTkgMS42MDAxIDEzLjc1ODQgMS42MDAxWiIgZmlsbD0iI2ZmZiIvPgo8cGF0aCBkPSJNNCAxMkwxMiA0TDQgMTJaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik00IDEyTDEyIDQiIHN0cm9rZT0iI2ZmZiIgc3Ryb2tlLXdpZHRoPSIxLjUiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIvPgo8L3N2Zz4K&logoColor=ffffff)](https://zread.ai/aimasteracc/tree-sitter-analyzer)
[![GitHub Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer)

## 🚀 AI時代のエンタープライズグレードコード解析ツール

> **深いAI統合 · 強力なファイル検索 · 多言語サポート · インテリジェントなコード解析**

## 📋 目次

- [1. 💡 主な特徴](#1--主な特徴)
- [2. 📋 前提条件（全ユーザー必読）](#2--前提条件全ユーザー必読)
- [3. 🚀 クイックスタート](#3--クイックスタート)
  - [3.1 🤖 AIユーザー（Claude Desktop、Cursorなど）](#31--aiユーザーclaude-desktopcursorなど)
  - [3.2 💻 CLIユーザー（コマンドラインツール）](#32--cliユーザーコマンドラインツール)
  - [3.3 👨‍💻 開発者（ソース開発）](#33--開発者ソース開発)
- [4. 📖 使用ワークフローと例](#4--使用ワークフローと例)
  - [4.1 🔄 AIアシスタントSMARTワークフロー](#41--aiアシスタントsmartワークフロー)
- [5. 🤖 MCP完全ツールリスト](#5--mcp完全ツールリスト)
- [6. ⚡ 完全なCLIコマンド](#6--完全なcliコマンド)
- [7. 🛠️ コア機能](#7-️-コア機能)
- [8. 🏆 品質保証](#8--品質保証)
- [9. 📚 ドキュメントとサポート](#9--ドキュメントとサポート)
- [10. 🤝 貢献とライセンス](#10--貢献とライセンス)

---

## 1. 💡 主な特徴

Tree-sitter Analyzerは、AI時代のために設計されたエンタープライズグレードのコード解析ツールで、以下を提供します：

| 機能カテゴリ | コア機能 | 主な利点 |
|-------------|---------|---------|
| **🤖 深いAI統合** | • MCPプロトコルサポート<br>• SMARTワークフロー<br>• トークン制限の突破<br>• 自然言語インタラクション | Claude Desktop、Cursor、Roo Codeをネイティブサポート<br>体系的なAI支援コード解析手法<br>AIがあらゆるサイズのコードファイルを理解<br>自然言語で複雑な解析タスクを完了 |
| **🔍 強力な検索機能** | • インテリジェントなファイル検出<br>• 正確なコンテンツ検索<br>• 2段階検索<br>• プロジェクト境界保護 | fdベースの高性能ファイル検索<br>ripgrepベースの正規表現検索<br>ファイル検出→コンテンツ検索の組み合わせ<br>プロジェクト境界の自動検出と保護 |
| **📊 インテリジェントなコード解析** | • 高速構造解析<br>• 正確なコード抽出<br>• 複雑度解析<br>• 統一要素システム | ファイル全体を読まずにアーキテクチャを理解<br>行範囲による正確なコードスニペット抽出<br>循環的複雑度計算と品質メトリクス<br>革新的な統一コード要素管理 |

### 🌍 エンタープライズグレードの多言語サポート

| プログラミング言語 | サポートレベル | 主要機能 |
|------------------|---------------|---------|
| **Java** | 完全サポート | Springフレームワーク、JPA、エンタープライズ機能 |
| **Python** | 完全サポート | 型アノテーション、デコレータ、モダンPython機能 |
| **JavaScript** | 完全サポート | ES6+、React/Vue/Angular、JSX |
| **TypeScript** | 完全サポート | インターフェース、型、デコレータ、TSX/JSX、フレームワーク検出 |
| **HTML** | 🆕 完全サポート | DOM構造解析、要素分類、属性抽出、階層関係 |
| **CSS** | 🆕 完全サポート | セレクタ解析、プロパティ分類、スタイルルール抽出、インテリジェント分類 |
| **Markdown** | 完全サポート | 見出し、コードブロック、リンク、画像、表、タスクリスト、引用 |
| **C/C++** | 基本サポート | 基本構文解析 |
| **Rust** | 基本サポート | 基本構文解析 |
| **Go** | 基本サポート | 基本構文解析 |

### 🏆 本番環境対応
- **3,370のテスト** - 100%合格率、エンタープライズグレードの品質保証
- **高カバレッジ** - 包括的なテストスイート
- **クロスプラットフォームサポート** - Windows、macOS、Linuxとの完全な互換性
- **継続的なメンテナンス** - アクティブな開発とコミュニティサポート

---

## 2. 📋 前提条件（全ユーザー必読）

AIユーザー、CLIユーザー、開発者のいずれであっても、まず以下のツールをインストールする必要があります：

### 1️⃣ uvのインストール（必須 - ツールの実行に使用）

**uv**は、tree-sitter-analyzerを実行するために使用される高速なPythonパッケージマネージャーです。

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**インストールの確認：**
```bash
uv --version
```

### 2️⃣ fdとripgrepのインストール（検索機能に必須）

**fd**と**ripgrep**は、高度なMCP機能に使用される高性能なファイルおよびコンテンツ検索ツールです。

| オペレーティングシステム | パッケージマネージャー | インストールコマンド | 備考 |
|------------------------|---------------------|-------------------|------|
| **macOS** | Homebrew | `brew install fd@10.3.0 ripgrep@14.1.1` | 推奨方法 |
| **Windows** | winget | `winget install sharkdp.fd --version 10.3.0` <br> `winget install BurntSushi.ripgrep.MSVC --version 14.1.1` | 推奨方法 |
| | Chocolatey | `choco install fd --version 10.3.0` <br> `choco install ripgrep --version 14.1.1` | 代替方法 |
| | Scoop | `scoop install fd@10.3.0 ripgrep@14.1.1` | 代替方法 |
| **Ubuntu/Debian** | apt | `sudo apt install fd-find=10.3.0* ripgrep=14.1.1*` | 公式リポジトリ |
| **CentOS/RHEL/Fedora** | dnf | `sudo dnf install fd-find-10.3.0 ripgrep-14.1.1` | 公式リポジトリ |
| **Arch Linux** | pacman | `sudo pacman -S fd=10.3.0 ripgrep=14.1.1` | 公式リポジトリ |

**インストールの確認：**
```bash
fd --version
rg --version
```

> **⚠️ 重要な注意事項：** 
> - **uv**はすべての機能を実行するために必要です
> - **fd**と**ripgrep**は高度なファイル検索とコンテンツ解析機能を使用するために必要です
> - fdとripgrepをインストールしない場合、基本的なコード解析機能は引き続き使用できますが、ファイル検索機能は使用できません

---

## 3. 🚀 クイックスタート

### 3.1 🤖 AIユーザー（Claude Desktop、Cursorなど）

**対象：** AIアシスタント（Claude Desktop、Cursorなど）を使用してコード解析を行うユーザー

#### ⚙️ 設定手順

**Claude Desktopの設定：**

1. 設定ファイルの場所を見つける：
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Linux**: `~/.config/claude/claude_desktop_config.json`

2. 以下の設定を追加：

**基本設定（推奨 - プロジェクトパスの自動検出）：**
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

**高度な設定（プロジェクトパスを手動で指定）：**
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
        "TREE_SITTER_PROJECT_ROOT": "/absolute/path/to/your/project",
        "TREE_SITTER_OUTPUT_PATH": "/absolute/path/to/output/directory"
      }
    }
  }
}
```

3. AIクライアントを再起動

4. 使用開始！AIに伝える：
   ```
   プロジェクトのルートディレクトリを設定してください：/path/to/your/project
   ```

**その他のAIクライアント：**
- **Cursor**: 組み込みのMCPサポート、Cursorのドキュメントを参照して設定
- **Roo Code**: MCPプロトコルをサポート、同じ設定形式を使用
- **その他のMCP互換クライアント**: 同じサーバー設定を使用

---

### 3.2 💻 CLIユーザー（コマンドラインツール）

**対象：** コマンドラインツールの使用を好む開発者

#### 📦 インストール

```bash
# 基本インストール
uv add tree-sitter-analyzer

# 人気の言語パック（推奨）
uv add "tree-sitter-analyzer[popular]"

# 完全インストール（MCPサポートを含む）
uv add "tree-sitter-analyzer[all,mcp]"
```

#### ⚡ クイック体験

```bash
# ヘルプを表示
uv run python -m tree_sitter_analyzer --help

# ファイルサイズを解析（1419行が瞬時に完了）
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text

# 詳細な構造テーブルを生成
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full

# 🆕 新しいアーキテクチャでHTML/CSS解析
uv run python -m tree_sitter_analyzer examples/comprehensive_sample.html --table=html --output-format=text
uv run python -m tree_sitter_analyzer examples/comprehensive_sample.css --advanced --output-format=text
uv run python -m tree_sitter_analyzer examples/comprehensive_sample.html --structure --language html

# 正確なコード抽出
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 93 --end-line 106
```

---

### 3.3 👨‍💻 開発者（ソース開発）

**対象：** ソースコードを変更したり、コードを貢献したりする必要がある開発者

#### 🛠️ 開発環境のセットアップ

```bash
# リポジトリをクローン
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer

# 依存関係をインストール
uv sync --extra all --extra mcp

# テストを実行
uv run pytest tests/ -v

# カバレッジレポートを生成
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html
```

#### 🔍 コード品質チェック

```bash
# AI生成コードチェック
uv run python llm_code_checker.py --check-all

# 品質チェック
uv run python check_quality.py --new-code-only
```

---

## 4. 📖 使用ワークフローと例

### 4.1 🔄 AIアシスタントSMARTワークフロー

SMARTワークフローは、AIアシスタントを使用してコードを解析するための推奨プロセスです。以下は`examples/BigService.java`（1419行の大規模サービスクラス）を使用した完全なワークフローのデモンストレーションです：

- **S** (Set): プロジェクトルートディレクトリを設定
- **M** (Map): ターゲットファイルを正確にマッピング
- **A** (Analyze): コア構造を解析
- **R** (Retrieve): キーコードを取得
- **T** (Trace): 依存関係を追跡

---

#### **S - プロジェクトの設定（最初のステップ）**

**AIに伝える：**
```
プロジェクトのルートディレクトリを設定してください：C:\git-public\tree-sitter-analyzer
```

**AIは自動的に**`set_project_path`ツールを呼び出します。

> 💡 **ヒント**: MCP設定の環境変数`TREE_SITTER_PROJECT_ROOT`を通じて事前に設定することもできます。

---

#### **M - ターゲットファイルのマッピング（解析するファイルを見つける）**

**シナリオ1：ファイルの場所がわからない場合、まず検索**

```
プロジェクト内で"BigService"を含むすべてのJavaファイルを検索
```

**AIは**`find_and_grep`ツールを呼び出し、BigService.javaで8つの一致を示す結果を返します。

**シナリオ2：ファイルパスがわかっている場合、直接使用**
```
examples/BigService.javaファイルを解析したい
```

---

#### **A - コア構造の解析（ファイルサイズと構成を理解）**

**AIに伝える：**
```
examples/BigService.javaの構造を解析してください。このファイルのサイズと主要なコンポーネントを知りたい
```

**AIは**`analyze_code_structure`ツールを呼び出し、以下を返します：
```json
{
  "file_path": "examples/BigService.java",
  "language": "java",
  "metrics": {
    "lines_total": 1419,
    "lines_code": 906,
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

**重要な情報：**

- ファイルは合計**1419行**
- **1つのクラス**、**66のメソッド**、**9つのフィールド**、**1つのパッケージ**、**合計85の要素**を含む

---

#### **R - キーコードの取得（具体的な実装を深く理解）**

**シナリオ1：完全な構造テーブルを表示**
```
examples/BigService.javaの詳細な構造テーブルを生成してください。すべてのメソッドのリストを見たい
```

**AIは以下を含むMarkdownテーブルを生成します：**

- クラス情報：パッケージ名、型、可視性、行範囲
- フィールドリスト：9つのフィールド（DEFAULT_ENCODING、MAX_RETRY_COUNTなど）
- コンストラクタ：BigService()
- パブリックメソッド：19個（authenticateUser、createSession、generateReportなど）
- プライベートメソッド：47個（initializeService、checkMemoryUsageなど）

**シナリオ2：特定のコードスニペットを抽出**
```
examples/BigService.javaの93-106行目を抽出してください。メモリチェックの具体的な実装を見たい
```

**AIは**`extract_code_section`ツールを呼び出し、checkMemoryUsageメソッドのコードを返します。

---

#### **T - 依存関係の追跡（コードの関連性を理解）**

**シナリオ1：認証関連のすべてのメソッドを検索**
```
examples/BigService.javaで認証（auth）に関連するすべてのメソッドを検索
```

**AIはクエリフィルタリングを呼び出し**、authenticateUserメソッド（141-172行目）を返します。

**シナリオ2：エントリーポイントを検索**
```
このファイルのmainメソッドはどこにありますか？何をしますか？
```

**AIは特定します：**

- **場所**: 1385-1418行目
- **機能**: BigServiceのさまざまな機能を実演（認証、セッション、顧客管理、レポート生成、パフォーマンス監視、セキュリティチェック）

**シナリオ3：メソッド呼び出し関係を理解**
```
authenticateUserメソッドはどのメソッドから呼び出されますか？
```

**AIはコードを検索し**、`main`メソッド内の呼び出しを見つけます：
```java
service.authenticateUser("testuser", "password123");
```

---

### 💡 SMARTワークフローのベストプラクティス

1. **自然言語優先**: 自然言語でニーズを説明すると、AIが自動的に適切なツールを選択します
2. **段階的アプローチ**: まず全体構造を理解（A）してから、具体的なコードに深く入る（R）
3. **必要に応じて追跡**: 複雑な関係を理解する必要がある場合にのみ追跡（T）を使用
4. **組み合わせ使用**: 1つの会話で複数のステップを組み合わせることができます

**完全な例の会話：**
```
大きなファイルexamples/BigService.javaを理解したい：
1. どのくらいの大きさですか？どのような主要機能が含まれていますか？
2. 認証機能はどのように実装されていますか？
3. どのようなパブリックAPIメソッドがありますか？
```

AIは自動的に：
1. ファイル構造を解析（1419行、66メソッド）
2. `authenticateUser`メソッドを特定して抽出（141-172行目）
3. パブリックメソッドのリストを生成（19のパブリックメソッド）

**HTML/CSS解析例：**
```
index.htmlのHTML構造を解析したい：
1. どのようなHTML要素が存在し、どのように構成されていますか？
2. どのようなCSSルールが定義され、どのようなプロパティが設定されていますか？
3. 要素はどのように分類されていますか（構造、メディア、フォーム）？
```

AIは自動的に：
1. タグ名、属性、分類を含むHTML要素を抽出
2. インテリジェントな分類でCSSセレクタとプロパティを解析
3. DOM階層とスタイルルールを示す構造化テーブルを生成

---

## 5. 🤖 MCP完全ツールリスト

Tree-sitter AnalyzerはAIアシスタント向けに設計された豊富なMCPツールセットを提供します：

| ツールカテゴリ | ツール名 | 主要機能 | コア特性 |
|-------------|---------|---------|---------|
| **📊 コード解析** | `check_code_scale` | コードファイル規模の高速解析 | ファイルサイズ統計、行数統計、複雑度解析、パフォーマンス指標 |
| | `analyze_code_structure` | コード構造解析とテーブル生成 | 🆕 suppress_outputパラメータ、複数フォーマット(full/compact/csv/json)、自動言語検出 |
| | `extract_code_section` | 正確なコードセクション抽出 | 指定行範囲抽出、大ファイル効率処理、元フォーマット保持 |
| **🔍 インテリジェント検索** | `list_files` | 高性能ファイル発見 | fdベース、globパターン、ファイルタイプフィルタ、時間範囲制御 |
| | `search_content` | 正規表現コンテンツ検索 | ripgrepベース、複数出力フォーマット、コンテキスト制御、エンコーディング処理、🆕 並行処理エンジン、統一`set_project_path`サポート |
| | `find_and_grep` | 2段階検索 | ファイル発見→コンテンツ検索、fd+ripgrep組み合わせ、インテリジェントキャッシュ最適化、🆕 統一`set_project_path`サポート |
| **🔧 高度なクエリ** | `query_code` | tree-sitterクエリ | 事前定義クエリキー、カスタムクエリ文字列、フィルタ式サポート |
| **⚙️ システム管理** | `set_project_path` | プロジェクトルートパス設定 | セキュリティ境界制御、自動パス検証、🆕 全MCPツールで統一 |
| **📁 リソースアクセス** | コードファイルリソース | URIコードファイルアクセス | URI識別によるファイルコンテンツアクセス |
| | プロジェクト統計リソース | プロジェクト統計データアクセス | プロジェクト解析データと統計情報 |

### 🆕 v1.9.0新機能：並行処理エンジン

革命的な並行処理機能による検索パフォーマンスの向上：

- **🔄 並行処理エンジン**: search_content MCPツールで複数ディレクトリの並行検索対応
- **⚡ パフォーマンス向上**: 大規模コードベースで最大4倍の検索速度向上
- **🛡️ 型安全性改善**: mypyエラー7%削減（341個→318個）
- **✨ コードスタイル統一**: ruff違反の大幅削減
- **🏗️ 技術的負債解消**: 包括的なコード品質改善
- **🚀 テスト実行時間**: 83%短縮の維持（215秒→37秒）

#### 🔄 並行処理機能の詳細
- **自動並行処理**: 複数のrootsディレクトリを自動的に並行実行
- **設定可能**: `enable_parallel`オプションで制御可能（デフォルト: True）
- **スケーラブル**: ディレクトリ数に応じた性能向上
- **メモリ効率**: セマフォによる同時実行数制御

### 🆕 v1.8.4新機能：設定可能ファイルログ

環境変数による柔軟なファイルログ制御システム：

- **🔧 環境変数制御**：`TREE_SITTER_ANALYZER_ENABLE_FILE_LOG`でファイルログの有効/無効を制御
- **📁 カスタムログディレクトリ**：`TREE_SITTER_ANALYZER_LOG_DIR`でログファイルの保存場所を指定
- **📊 ログレベル設定**：`TREE_SITTER_ANALYZER_FILE_LOG_LEVEL`でログの詳細度を制御（DEBUG、INFO、WARNING、ERROR）
- **🚫 プロジェクト汚染防止**：デフォルトでファイルログを無効化し、プロジェクトディレクトリの清潔性を保持
- **🔄 動的制御**：実行時に環境変数を変更してログ動作を調整可能

### 🆕 v1.8.3新機能：MCPツール設計一貫性の強化

包括的なMCPツール統一と設計一貫性の改善：

- **🔧 統一`set_project_path`実装**：SearchContentToolとFindAndGrepToolに一貫した`set_project_path`メソッド実装を追加
- **🏗️ 全MCPツールでの設計一貫性**：全4つのMCPツール（QueryTool、TableFormatTool、SearchContentTool、FindAndGrepTool）で統一されたインターフェース設計を実現
- **📁 FileOutputManager統合**：統一されたファイル出力管理のためのFileOutputManagerファクトリパターン
- **🔄 動的プロジェクトパス変更**：統一されたインターフェースを通じて全MCPツールで動的プロジェクトパス変更をサポート
- **🛡️ セキュリティ境界の強化**：全MCPツールで一貫したセキュリティ境界保護
- **📋 開発者エクスペリエンスの改善**：統一されたインターフェースによりMCPツールの開発と使用がより一貫性のあるものに

### 🆕 v1.8.2新機能：CLIセキュリティと引数検証の強化

包括的なCLIセキュリティ改善と引数検証の最適化：

- **🔒 CLIセキュリティ境界の修正**：CLIモードでのセキュリティ境界エラーを修正し、ファイルアクセスの安全性を確保
- **✅ 正しいCLI引数検証**：完全なCLI引数検証システムを実装し、無効な引数の組み合わせを防止
- **🚫 排他引数制御**：[`--table`](README_ja.md:521)と[`--query-key`](README_ja.md:543)引数が正しく排他制御を実装
- **🔍 強化されたフィルタサポート**：[`--query-key`](README_ja.md:543)と[`--filter`](README_ja.md:560)の組み合わせ使用が完全にサポート
- **⚠️ 明確なエラーメッセージ**：詳細なエラー情報を提供し、ユーザーが正しくコマンドを使用できるよう支援
- **🛡️ セキュリティ機能の強化**：テスト環境での一時ディレクトリアクセス許可とプロジェクト境界保護
- **📋 改善されたユーザーエクスペリエンス**：より直感的なコマンドラインインターフェースとエラー処理

### 🆕 v1.8.0新機能：HTML/CSS言語サポート

専用データモデルとフォーマッティングによる革新的なHTMLとCSS解析機能：

- **🏗️ HTML DOM解析**：タグ名、属性、階層構造を含む完全なHTML要素抽出
- **🎨 CSSルール解析**：インテリジェントな分類によるCSSセレクタとプロパティの包括的解析
- **📊 要素分類システム**：HTML要素（構造、見出し、テキスト、リスト、メディア、フォーム、テーブル、メタデータ）とCSSプロパティ（レイアウト、ボックスモデル、タイポグラフィ、背景、トランジション、インタラクティビティ）のスマート分類
- **🔧 専用データモデル**：正確なWeb技術解析のための新しい`MarkupElement`と`StyleElement`クラス
- **📋 強化されたフォーマッター**：Web開発ワークフロー用の構造化テーブル出力を持つ新しいHTMLフォーマッター
- **🔄 拡張可能なアーキテクチャ**：動的フォーマット管理のための`FormatterRegistry`を持つプラグインベースシステム
- **🆕 依存関係**：ネイティブ解析サポートのための`tree-sitter-html>=0.23.0,<0.25.0`と`tree-sitter-css>=0.23.0,<0.25.0`を追加

### 🆕 v1.7.3機能：Markdown完全サポート

全く新しいMarkdown言語サポートにより、ドキュメント解析とAIアシスタントに強力な機能を提供：

- **📝 完全なMarkdown解析**：ATX見出し、Setext見出し、コードブロック、リンク、画像、表など、すべての主要要素をサポート
- **🔍 インテリジェントな要素抽出**：見出しレベル、コード言語、リンクURL、画像情報などを自動認識・抽出
- **📊 構造化解析**：Markdownドキュメントを構造化データに変換し、AIの理解と処理を容易に
- **🎯 タスクリストサポート**：GitHubスタイルのタスクリスト（チェックボックス）を完全サポート
- **🔧 クエリシステム統合**：既存のすべてのクエリとフィルタリング機能をサポート
- **📁 複数拡張子サポート**：.md、.markdown、.mdown、.mkd、.mkdn、.mdxなどの形式をサポート

### 🆕 v1.7.2機能：ファイル出力最適化機能

MCP検索ツールに新しく追加されたファイル出力最適化機能は、革命的なトークン節約ソリューションです：

- **🎯 ファイル出力最適化**：`find_and_grep`、`list_files`、`search_content`ツールに`suppress_output`と`output_file`パラメータを新追加
- **🔄 自動フォーマット検出**：コンテンツタイプに基づいてファイル形式（JSON/Markdown）を自動選択
- **💾 大幅なトークン節約**：大型検索結果をファイルに保存する際、レスポンスサイズを最大99%削減
- **📚 ROO規則ドキュメント**：tree-sitter-analyzer MCP最適化使用ガイドを新追加
- **🔧 後方互換性**：オプション機能で、既存機能の使用に影響なし

### 🆕 v1.7.0機能：suppress_output機能

`analyze_code_structure`ツールの`suppress_output`パラメータ：

- **問題解決**：解析結果が大きすぎる場合、従来の方式では完全なテーブルデータを返し、大量のトークンを消費
- **インテリジェント最適化**：`suppress_output=true`かつ`output_file`指定時、基本メタデータのみを返却
- **顕著な効果**：レスポンスサイズを最大99%削減、AIダイアログのトークン消費を大幅節約
- **使用シーン**：大型コードファイルの構造解析やバッチ処理シーンに特に適している

---

## 6. ⚡ 完全なCLIコマンド

#### 📊 コード構造解析コマンド

```bash
# クイック解析（サマリー情報を表示）
uv run python -m tree_sitter_analyzer examples/BigService.java --summary

# 詳細解析（完全な構造を表示）
uv run python -m tree_sitter_analyzer examples/BigService.java --structure

# 高度な解析（複雑度メトリクスを含む）
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced

# 完全な構造テーブルを生成
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full

# 🆕 新しいアーキテクチャでHTML/CSS解析
uv run python -m tree_sitter_analyzer examples/comprehensive_sample.html --table=full --output-format=text
uv run python -m tree_sitter_analyzer examples/comprehensive_sample.css --table=full --output-format=text
uv run python -m tree_sitter_analyzer examples/comprehensive_sample.html --advanced --output-format=text
uv run python -m tree_sitter_analyzer examples/comprehensive_sample.css --advanced --output-format=text

# 出力形式を指定
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=json
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text

# 正確なコード抽出
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 93 --end-line 106

# プログラミング言語を指定
uv run python -m tree_sitter_analyzer script.py --language python --table=full
```

#### 🔍 クエリとフィルタコマンド

```bash
# 特定の要素をクエリ
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key classes

# 🆕 v1.8.2 正しい使用方法
# 正しい：--query-keyと--filterの組み合わせ
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=main"

# 正しい：完全な構造テーブルの生成
uv run python -m tree_sitter_analyzer examples/BigService.java --table full

# 🚫 v1.8.2 間違った使用方法（エラーが表示される）
# 間違った：--tableと--query-keyの同時使用（排他引数）
# uv run python -m tree_sitter_analyzer examples/BigService.java --table full --query-key methods
# エラーメッセージ: "--table and --query-key cannot be used together. Use --query-key with --filter instead."

# クエリ結果をフィルタ
# 特定のメソッドを検索
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=main"

# 認証関連メソッドを検索（パターンマッチング）
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=~auth*"

# パラメータなしのパブリックメソッドを検索（複合条件）
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "params=0,public=true"

# 静的メソッドを検索
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "static=true"

# フィルタ構文のヘルプを表示
uv run python -m tree_sitter_analyzer --filter-help
```

#### 🔒 セキュリティ機能の説明

v1.8.2版本でセキュリティ機能が強化され、ファイルアクセスの安全性が確保されています：

```bash
# ✅ 安全なプロジェクト境界保護
# ツールは自動的にプロジェクト境界を検出し、尊重することで、プロジェクト外の機密ファイルへのアクセスを防止

# ✅ テスト環境での一時ディレクトリアクセス
# テスト環境では、テストケースをサポートするために一時ディレクトリへのアクセスが許可

# ✅ 正しいCLI引数検証
# システムは引数の組み合わせの有効性を検証し、無効なコマンドの実行を防止

# 例：安全なファイル解析
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced
# ✅ 許可：ファイルがプロジェクトディレクトリ内にある

# uv run python -m tree_sitter_analyzer /etc/passwd --advanced
# ❌ 拒否：ファイルがプロジェクト境界外にある（セキュリティ保護）
```

#### 📁 ファイルシステム操作コマンド

```bash
# ファイルをリスト
uv run list-files . --extensions java
uv run list-files . --pattern "test_*" --extensions java --types f
uv run list-files . --types f --size "+1k" --changed-within "1week"

# コンテンツを検索
uv run search-content --roots . --query "class.*extends" --include-globs "*.java"
uv run search-content --roots tests --query "TODO|FIXME" --context-before 2 --context-after 2
uv run search-content --files examples/BigService.java examples/Sample.java --query "public.*method" --case insensitive

# 2段階検索（最初にファイルを検索し、次にコンテンツを検索）
uv run find-and-grep --roots . --query "@SpringBootApplication" --extensions java
uv run find-and-grep --roots examples --query "import.*SQLException" --extensions java --file-limit 10 --max-count 5
uv run find-and-grep --roots . --query "public.*static.*void" --extensions java --types f --size "+1k" --output-format json
```

#### ℹ️ 情報クエリコマンド

```bash
# ヘルプを表示
uv run python -m tree_sitter_analyzer --help

# サポートされているクエリキーをリスト
uv run python -m tree_sitter_analyzer --list-queries

# サポートされている言語を表示
uv run python -m tree_sitter_analyzer --show-supported-languages

# サポートされている拡張子を表示
uv run python -m tree_sitter_analyzer --show-supported-extensions

# 一般的なクエリを表示
uv run python -m tree_sitter_analyzer --show-common-queries

# クエリ言語サポートを表示
uv run python -m tree_sitter_analyzer --show-query-languages
```

---

## 7. 🛠️ コア機能

| 機能カテゴリ | 機能名 | コア特性 | 技術的優位性 |
|-------------|--------|---------|-------------|
| **📊 コード構造解析** | インテリジェント解析エンジン | クラス、メソッド、フィールドの統計<br>パッケージ情報とインポート依存関係<br>複雑度メトリクス（循環的複雑度）<br>正確な行番号の位置特定 | tree-sitterベースの高精度解析<br>大規模エンタープライズコードベース対応<br>リアルタイムパフォーマンス最適化 |
| **✂️ インテリジェントなコード抽出** | 精密抽出ツール | 行範囲による正確な抽出<br>元のフォーマットとインデントを保持<br>位置メタデータを含む<br>大きなファイルの効率的な処理 | ゼロロスフォーマット保持<br>メモリ最適化アルゴリズム<br>ストリーミング処理サポート |
| **🔍 高度なクエリフィルタリング** | 多次元フィルター | **完全一致**: `--filter "name=main"`<br>**パターンマッチ**: `--filter "name=~auth*"`<br>**パラメータフィルタ**: `--filter "params=2"`<br>**修飾子フィルタ**: `--filter "static=true,public=true"`<br>**複合条件**: 正確なクエリのために複数の条件を組み合わせる | 柔軟なクエリ構文<br>高性能インデックス<br>インテリジェントキャッシュ機構 |
| **🔗 AIアシスタント統合** | MCPプロトコルサポート | **Claude Desktop** - 完全なMCPサポート<br>**Cursor IDE** - 組み込みのMCP統合<br>**Roo Code** - MCPプロトコルサポート<br>**その他のMCP互換ツール** - ユニバーサルMCPサーバー | 標準MCPプロトコル<br>プラグアンドプレイ設計<br>クロスプラットフォーム互換性 |
| **🌍 多言語サポート** | エンタープライズ言語エンジン | **Java** - 完全サポート、Spring、JPAフレームワークを含む<br>**Python** - 完全サポート、型アノテーション、デコレータを含む<br>**JavaScript** - 企業級サポート、ES6+、React/Vue/Angular、JSXを含む<br>**TypeScript** - **完全サポート**、インターフェース、型、デコレータ、TSX/JSX、フレームワーク検出を含む<br>**HTML** - **🆕 完全サポート**、DOM構造、要素分類、属性抽出を含む<br>**CSS** - **🆕 完全サポート**、セレクタ解析、プロパティ分類、スタイルルールを含む<br>**Markdown** - **完全サポート**、見出し、コードブロック、リンク、画像、表、タスクリスト、引用を含む<br>**C/C++、Rust、Go** - 基本サポート | フレームワーク認識解析<br>構文拡張サポート<br>継続的言語アップデート |
| **📁 高度なファイル検索** | fd+ripgrep統合 | **ListFilesTool** - 複数のフィルタリング条件を持つインテリジェントなファイル検出<br>**SearchContentTool** - 正規表現を使用したインテリジェントなコンテンツ検索<br>**FindAndGrepTool** - 検出と検索の組み合わせ、2段階ワークフロー | Rustベースの高性能ツール<br>並列処理能力<br>インテリジェントキャッシュ最適化 |
| **🏗️ 統一要素システム** | 革新的アーキテクチャ設計 | **単一要素リスト** - すべてのコード要素（クラス、メソッド、フィールド、インポート、パッケージ）の統一管理<br>**一貫した要素タイプ** - 各要素には`element_type`属性があります<br>**簡素化されたAPI** - より明確なインターフェースと複雑さの軽減<br>**より良い保守性** - すべてのコード要素の単一の真実の情報源 | 統一データモデル<br>型安全保証<br>拡張性設計 |

---

## 8. 🏆 品質保証

### 📊 品質メトリクス
- **3,370のテスト** - 100%合格率 ✅
- **高コードカバレッジ** - 包括的なテストスイート
- **ゼロテスト失敗** - 本番環境対応
- **クロスプラットフォームサポート** - Windows、macOS、Linux

### ⚡ 最新の品質成果（v1.8.3）
- ✅ **🔒 CLIセキュリティの強化** - CLIモードでのセキュリティ境界エラーを修正し、ファイルアクセスの安全性を確保
- ✅ **✅ 引数検証の完善** - 完全なCLI引数検証システムを実装し、無効な引数の組み合わせを防止
- ✅ **🚫 排他引数制御** - [`--table`](README_ja.md:521)と[`--query-key`](README_ja.md:543)引数が正しく排他制御を実装
- ✅ **🔍 フィルタ機能の強化** - [`--query-key`](README_ja.md:543)と[`--filter`](README_ja.md:560)の組み合わせ使用が完全にサポート
- ✅ **⚠️ エラーメッセージの最適化** - 明確で詳細なエラー情報を提供し、ユーザーエクスペリエンスを改善
- ✅ **🛡️ プロジェクト境界保護** - 自動的にプロジェクト境界を検出し、尊重することで機密ファイルへのアクセスを防止
- ✅ **🧪 テスト環境サポート** - テスト環境での一時ディレクトリアクセス許可
- ✅ **📋 ユーザーエクスペリエンスの改善** - より直感的なコマンドラインインターフェースとエラー処理メカニズム

### ⚙️ テストの実行
```bash
# すべてのテストを実行
uv run pytest tests/ -v

# カバレッジレポートを生成
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html --cov-report=term-missing

# 特定のテストを実行
uv run pytest tests/test_mcp_server_initialization.py -v
```

### 📈 テストカバレッジの詳細

プロジェクトは高品質なテストカバレッジを維持しています。詳細なモジュールカバレッジ情報については、以下をご覧ください：

[![カバレッジ詳細](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer)

**上記のバッジをクリックして確認できる内容：**
- 📊 **モジュール別カバレッジ** - 各モジュールの詳細なカバレッジ統計
- 📈 **カバレッジトレンド** - 履歴カバレッジ変化トレンド
- 🔍 **未カバーコード行** - テストされていないコードの具体的な場所
- 📋 **詳細レポート** - 完全なカバレッジ分析レポート

### ✅ ドキュメント検証ステータス

**このREADMEのすべてのコンテンツは検証済みです：**
- ✅ **すべてのコマンドがテスト済み** - すべてのCLIコマンドは実際の環境で実行および検証されています
- ✅ **すべてのデータが本物** - カバレッジ率、テスト数などのデータはテストレポートから直接取得されています
- ✅ **SMARTフローが本物** - 実際のBigService.java（1419行）に基づいて実演
- ✅ **クロスプラットフォーム検証** - Windows、macOS、Linux環境でテスト済み

**検証環境：**
- オペレーティングシステム：Windows 10、macOS、Linux
- Pythonバージョン：3.10+
- プロジェクトバージョン：tree-sitter-analyzer v1.8.2
- テストファイル：BigService.java（1419行）、sample.py（256行）、MultiClass.java（54行）
- 新規検証：CLI引数検証、セキュリティ境界保護、排他引数制御

---

## 9. 📚 ドキュメントとサポート

### 📖 完全なドキュメント
本プロジェクトは完全なドキュメントサポートを提供しています：

- **クイックスタートガイド** - 本READMEの[クイックスタート](#3--クイックスタート)部分を参照
- **MCP設定ガイド** - [AIユーザー設定](#31--aiユーザーclaude-desktopcursorなど)部分を参照
- **CLI使用ガイド** - [完全なCLIコマンド](#6--完全なcliコマンド)部分を参照
- **コア機能説明** - [コア機能](#7-️-コア機能)部分を参照

### 🤖 AIコラボレーションサポート
本プロジェクトは、専門的な品質管理を備えたAI支援開発をサポートしています：

```bash
# AIシステムコード生成前チェック
uv run python check_quality.py --new-code-only
uv run python llm_code_checker.py --check-all
```

### 💝 スポンサーと謝辞

**[@o93](https://github.com/o93)** - *主要スポンサー＆サポーター*
- 🚀 **MCPツール強化**: 包括的なMCP fd/ripgrepツール開発をスポンサー
- 🧪 **テストインフラストラクチャ**: エンタープライズグレードのテストカバレッジを実装（50以上の包括的なテストケース）
- 🔧 **品質保証**: バグ修正とパフォーマンス改善をサポート
- 💡 **イノベーションサポート**: 高度なファイル検索とコンテンツ解析機能の早期リリースを可能にしました

**[💖 このプロジェクトをスポンサー](https://github.com/sponsors/aimasteracc)** して、開発者コミュニティのための優れたツールの構築を続けるのを手伝ってください！

---

## 10. 🤝 貢献とライセンス

### 🤝 貢献ガイド

あらゆる種類の貢献を歓迎します！詳細については[貢献ガイド](CONTRIBUTING.md)をご確認ください。

### ⭐ スターをください！

このプロジェクトがお役に立ちましたら、GitHubで⭐をください - それが私たちにとって最大のサポートです！

### 📄 ライセンス

MITライセンス - 詳細については[LICENSE](LICENSE)ファイルをご覧ください。

---

**🎯 大規模なコードベースとAIアシスタントを扱う開発者のために構築**

*すべてのコード行をAIが理解できるようにし、すべてのプロジェクトがトークン制限を突破できるようにする*