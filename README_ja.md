# Tree-sitter Analyzer

**[English](README.md)** | **日本語** | **[简体中文](README_zh.md)**

[![Pythonバージョン](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![ライセンス](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![テスト](https://img.shields.io/badge/tests-2046%20passed-brightgreen.svg)](#品質保証)
[![カバレッジ](https://img.shields.io/badge/coverage-69.67%25-green.svg)](#品質保証)
[![品質](https://img.shields.io/badge/quality-enterprise%20grade-blue.svg)](#品質保証)
[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![バージョン](https://img.shields.io/badge/version-1.6.2-blue.svg)](https://github.com/aimasteracc/tree-sitter-analyzer/releases)
[![GitHub Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer)

## 🚀 AI時代のエンタープライズグレードコード解析ツール

> **深いAI統合 · 強力なファイル検索 · 多言語サポート · インテリジェントなコード解析**

## 📋 目次

- [💡 主な特徴](#-主な特徴)
- [📋 前提条件（全ユーザー必読）](#-前提条件全ユーザー必読)
- [🚀 クイックスタート](#-クイックスタート)
  - [🤖 AIユーザー（Claude Desktop、Cursorなど）](#-aiユーザーclaude-desktopcursorなど)
  - [💻 CLIユーザー（コマンドラインツール）](#-cliユーザーコマンドラインツール)
  - [👨‍💻 開発者（ソース開発）](#-開発者ソース開発)
- [📖 使用ワークフローと例](#-使用ワークフローと例)
  - [🔄 AIアシスタントSMARTワークフロー](#-aiアシスタントsmartワークフロー)
  - [⚡ 完全なCLIコマンド](#-完全なcliコマンド)
- [🛠️ コア機能](#️-コア機能)
- [🏆 品質保証](#-品質保証)
- [📚 ドキュメントとサポート](#-ドキュメントとサポート)
- [🤝 貢献とライセンス](#-貢献とライセンス)

---

## 💡 主な特徴

Tree-sitter Analyzerは、AI時代のために設計されたエンタープライズグレードのコード解析ツールで、以下を提供します：

### 🤖 深いAI統合
- **MCPプロトコルサポート** - Claude Desktop、Cursor、Roo CodeなどのAIツールをネイティブサポート
- **SMARTワークフロー** - 体系的なAI支援コード解析手法
- **トークン制限の突破** - AIがあらゆるサイズのコードファイルを理解できるようにする
- **自然言語インタラクション** - 自然言語を使用して複雑なコード解析タスクを完了

### 🔍 強力な検索機能
- **インテリジェントなファイル検出** - fdベースの高性能ファイル検索、複数のフィルタリング条件をサポート
- **正確なコンテンツ検索** - ripgrepベースの正規表現コンテンツ検索
- **2段階検索** - ファイルを見つけてからコンテンツを検索する組み合わせワークフロー
- **プロジェクト境界保護** - プロジェクト境界の自動検出と尊重によりセキュリティを確保

### 📊 インテリジェントなコード解析
- **高速構造解析** - ファイル全体を読まずにコードアーキテクチャを理解
- **正確なコード抽出** - 行範囲による正確なコードスニペットの抽出をサポート
- **複雑度解析** - 循環的複雑度の計算とコード品質メトリクス
- **統一要素システム** - 革新的な統一コード要素管理アーキテクチャ

### 🌍 エンタープライズグレードの多言語サポート
- **Java** - 完全サポート（1103行のプラグインコード、73%カバレッジ）、Spring、JPAフレームワークを含む
- **Python** - 完全サポート（584行のプラグインコード、63%カバレッジ）、型アノテーション、デコレータを含む
- **JavaScript** - エンタープライズグレードサポート（1445行のプラグインコード、68%カバレッジ）、ES6+、React/Vue/Angular、JSXを含む
- **TypeScript** - **完全サポート**（1553行のプラグインコード、29%カバレッジ）、インターフェース、型、デコレータ、TSX/JSX、フレームワーク検出を含む
- **その他の言語** - C/C++、Rust、Goの基本サポート

### 🏆 本番環境対応
- **2,046のテスト** - 100%合格率、エンタープライズグレードの品質保証
- **69.67%カバレッジ** - 包括的なテストスイート
- **クロスプラットフォームサポート** - Windows、macOS、Linuxとの完全な互換性
- **継続的なメンテナンス** - アクティブな開発とコミュニティサポート

---

## 📋 前提条件（全ユーザー必読）

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

```bash
# macOS
brew install fd ripgrep

# Windows（wingetの使用を推奨）
winget install sharkdp.fd BurntSushi.ripgrep.MSVC

# Windows（その他の方法）
# choco install fd ripgrep
# scoop install fd ripgrep

# Ubuntu/Debian
sudo apt install fd-find ripgrep

# CentOS/RHEL/Fedora
sudo dnf install fd-find ripgrep

# Arch Linux
sudo pacman -S fd ripgrep
```

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

## 🚀 クイックスタート

### 🤖 AIユーザー（Claude Desktop、Cursorなど）

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

### 💻 CLIユーザー（コマンドラインツール）

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

# 正確なコード抽出
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 93 --end-line 106
```

---

### 👨‍💻 開発者（ソース開発）

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

## 📖 使用ワークフローと例

### 🔄 AIアシスタントSMARTワークフロー

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

---

### ⚡ 完全なCLIコマンド

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

## 🛠️ コア機能

### 📊 コード構造解析
- クラス、メソッド、フィールドの統計
- パッケージ情報とインポート依存関係
- 複雑度メトリクス（循環的複雑度）
- 正確な行番号の位置特定

### ✂️ インテリジェントなコード抽出
- 行範囲による正確な抽出
- 元のフォーマットとインデントを保持
- 位置メタデータを含む
- 大きなファイルの効率的な処理

### 🔍 高度なクエリフィルタリング
- **完全一致**: `--filter "name=main"`
- **パターンマッチ**: `--filter "name=~auth*"`
- **パラメータフィルタ**: `--filter "params=2"`
- **修飾子フィルタ**: `--filter "static=true,public=true"`
- **複合条件**: 正確なクエリのために複数の条件を組み合わせる

### 🔗 AIアシスタント統合
- **Claude Desktop** - 完全なMCPサポート
- **Cursor IDE** - 組み込みのMCP統合
- **Roo Code** - MCPプロトコルサポート
- **その他のMCP互換ツール** - ユニバーサルMCPサーバー

### 🌍 多言語サポート
- **Java** - 完全サポート（1103行のプラグイン）、Spring、JPAフレームワークを含む
- **Python** - 完全サポート（584行のプラグイン）、型アノテーション、デコレータを含む
- **JavaScript** - エンタープライズグレードサポート（1445行のプラグイン）、ES6+、React/Vue/Angular、JSXを含む
- **TypeScript** - **完全サポート**（1553行のプラグイン）、インターフェース、型、デコレータ、TSX/JSX、フレームワーク検出を含む
- **C/C++、Rust、Go** - 基本サポート

### 📁 高度なファイル検索
fdとripgrepに基づく強力なファイル検出とコンテンツ検索：
- **ListFilesTool** - 複数のフィルタリング条件を持つインテリジェントなファイル検出
- **SearchContentTool** - 正規表現を使用したインテリジェントなコンテンツ検索
- **FindAndGrepTool** - 検出と検索の組み合わせ、2段階ワークフロー

### 🏗️ 統一要素システム
- **単一要素リスト** - すべてのコード要素（クラス、メソッド、フィールド、インポート、パッケージ）の統一管理
- **一貫した要素タイプ** - 各要素には`element_type`属性があります
- **簡素化されたAPI** - より明確なインターフェースと複雑さの軽減
- **より良い保守性** - すべてのコード要素の単一の真実の情報源

---

## 🏆 品質保証

### 📊 品質メトリクス
- **1,893のテスト** - 100%合格率 ✅
- **71.48%コードカバレッジ** - 包括的なテストスイート
- **ゼロテスト失敗** - 本番環境対応
- **クロスプラットフォームサポート** - Windows、macOS、Linux

### ⚡ 最新の品質成果（v1.6.2）
- ✅ **クロスプラットフォームパス互換性** - Windowsの短いパス名とmacOSのシンボリックリンクの違いを修正
- ✅ **エンタープライズグレードの信頼性** - 50以上の包括的なテストケースで安定性を確保
- ✅ **GitFlow実装** - プロフェッショナルな開発/リリースブランチ戦略
- ✅ **AIコラボレーション最適化** - AI支援開発のための専門的な品質管理

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

**コアモジュール：**
- **言語検出器**: 98.41%（優秀） - 自動プログラミング言語認識
- **CLIメインエントリ**: 94.36%（優秀） - コマンドラインインターフェース
- **クエリフィルタシステム**: 96.06%（優秀） - コードクエリとフィルタリング
- **クエリサービス**: 86.25%（良好） - クエリ実行エンジン
- **MCPエラー処理**: 82.76%（良好） - AIアシスタント統合エラー処理

**言語プラグイン：**
- **Javaプラグイン**: 73.00%（良好） - 1103行のコード、完全なエンタープライズグレードサポート
- **JavaScriptプラグイン**: 68.31%（良好） - 1445行のコード、モダンなES6+機能サポート
- **Pythonプラグイン**: 63.26%（良好） - 584行のコード、完全な型アノテーションサポート

**MCPツール：**
- **ファイル検索ツール**: 88.77%（優秀） - fd/ripgrep統合
- **コンテンツ検索ツール**: 92.70%（優秀） - 正規表現検索
- **組み合わせ検索ツール**: 91.57%（優秀） - 2段階検索

### ✅ ドキュメント検証ステータス

**このREADMEのすべてのコンテンツは検証済みです：**
- ✅ **すべてのコマンドがテスト済み** - すべてのCLIコマンドは実際の環境で実行および検証されています
- ✅ **すべてのデータが本物** - カバレッジ率、テスト数などのデータはテストレポートから直接取得されています
- ✅ **SMARTフローが本物** - 実際のBigService.java（1419行）に基づいて実演
- ✅ **クロスプラットフォーム検証** - Windows、macOS、Linux環境でテスト済み

**検証環境：**
- オペレーティングシステム：Windows 10、macOS、Linux
- Pythonバージョン：3.10+
- プロジェクトバージョン：tree-sitter-analyzer v1.6.2
- テストファイル：BigService.java（1419行）、sample.py（256行）、MultiClass.java（54行）

---

## 📚 ドキュメントとサポート

### 📖 完全なドキュメント
- **[ユーザーMCPセットアップガイド](MCP_SETUP_USERS.md)** - シンプルな設定ガイド
- **[開発者MCPセットアップガイド](MCP_SETUP_DEVELOPERS.md)** - ローカル開発設定
- **[プロジェクトルート設定](PROJECT_ROOT_CONFIG.md)** - 完全な設定リファレンス
- **[APIドキュメント](docs/api.md)** - 詳細なAPIリファレンス
- **[貢献ガイド](CONTRIBUTING.md)** - コードの貢献方法
- **[オンボーディング＆トレーニングガイド](training/README.md)** - 新しいメンバー/メンテナー向けのシステムオンボーディング資料

### 🤖 AIコラボレーションサポート
このプロジェクトは、専門的な品質管理を備えたAI支援開発をサポートしています：

```bash
# AIシステムの事前生成チェック
uv run python check_quality.py --new-code-only
uv run python llm_code_checker.py --check-all
```

📖 **詳細ガイド**:
- [AIコラボレーションガイド](AI_COLLABORATION_GUIDE.md)
- [LLMコーディングガイドライン](LLM_CODING_GUIDELINES.md)

### 💝 スポンサーと謝辞

**[@o93](https://github.com/o93)** - *主要スポンサー＆サポーター*
- 🚀 **MCPツール強化**: 包括的なMCP fd/ripgrepツール開発をスポンサー
- 🧪 **テストインフラストラクチャ**: エンタープライズグレードのテストカバレッジを実装（50以上の包括的なテストケース）
- 🔧 **品質保証**: バグ修正とパフォーマンス改善をサポート
- 💡 **イノベーションサポート**: 高度なファイル検索とコンテンツ解析機能の早期リリースを可能にしました

**[💖 このプロジェクトをスポンサー](https://github.com/sponsors/aimasteracc)** して、開発者コミュニティのための優れたツールの構築を続けるのを手伝ってください！

---

## 🤝 貢献とライセンス

### 🤝 貢献ガイド

あらゆる種類の貢献を歓迎します！詳細については[貢献ガイド](CONTRIBUTING.md)をご確認ください。

### ⭐ スターをください！

このプロジェクトがお役に立ちましたら、GitHubで⭐をください - それが私たちにとって最大のサポートです！

### 📄 ライセンス

MITライセンス - 詳細については[LICENSE](LICENSE)ファイルをご覧ください。

---

**🎯 大規模なコードベースとAIアシスタントを扱う開発者のために構築**

*すべてのコード行をAIが理解できるようにし、すべてのプロジェクトがトークン制限を突破できるようにする*