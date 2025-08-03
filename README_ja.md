# Tree-sitter Analyzer

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-1126%20passed-brightgreen.svg)](#testing)

**大型コードファイルのLLMトークン制限問題を解決。**

AI アシスタントがファイル全体を読み取ることなくコード構造を理解できる拡張可能な多言語コード解析器。コード概要の取得、特定セクションの抽出、複雑度解析 - すべてLLMワークフロー向けに最適化。

## ✨ なぜTree-sitter Analyzerなのか？

**問題：** 大型コードファイルがLLMトークン制限を超え、コード解析が非効率または不可能になる。

**解決策：** スマートなコード解析により以下を提供：
- 📊 **コード概要** ファイル全体を読み取らずに
- 🎯 **ターゲット抽出** 特定の行範囲
- 📍 **精密な位置特定** 正確なコード操作のため
- 🤖 **AIアシスタント統合** MCPプロトコル経由

## 🚀 クイックスタート（5分）

### AIアシスタントユーザー向け（Claude Desktop）

1. **パッケージのインストール：**
```bash
# uv（高速Pythonパッケージマネージャー）をインストール
curl -LsSf https://astral.sh/uv/install.sh | sh  # macOS/Linux
# または：powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# パッケージを個別にインストールする必要はありません - uvが処理します
```

2. **Claude Desktopの設定：**

Claude Desktop設定ファイルに追加：

**Windows：** `%APPDATA%\Claude\claude_desktop_config.json`
**macOS：** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Linux：** `~/.config/claude/claude_desktop_config.json`

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

3. **Claude Desktopを再起動** してコード解析を開始！

### CLIユーザー向け

```bash
# uvでインストール（推奨）
uv add "tree-sitter-analyzer[popular]"

# ステップ1：ファイル規模をチェック
uv run python -m tree_sitter_analyzer examples/Sample.java --advanced --output-format=text

# ステップ2：構造解析（大型ファイル向け）
uv run python -m tree_sitter_analyzer examples/Sample.java --table=full

# ステップ3：特定行の抽出
uv run python -m tree_sitter_analyzer examples/Sample.java --partial-read --start-line 84 --end-line 86
```

## 🛠️ コア機能

### 1. コード構造解析
ファイル全体を読み取らずに包括的な概要を取得：
- クラス、メソッド、フィールド数
- パッケージ情報
- インポート依存関係
- 複雑度メトリクス

### 2. ターゲットコード抽出
特定のコードセクションを効率的に抽出：
- 行範囲抽出
- 精密な位置データ
- コンテンツ長情報

### 3. AIアシスタント統合
AIアシスタント向けの4つの強力なMCPツール：
- `analyze_code_scale` - コードメトリクスと複雑度を取得
- `analyze_code_structure` - 詳細な構造テーブルを生成
- `read_code_partial` - 特定の行範囲を抽出
- `analyze_code_universal` - 自動検出による汎用解析

### 4. 多言語サポート
- **Java** - 高度解析による完全サポート
- **Python** - 完全サポート
- **JavaScript/TypeScript** - 完全サポート
- **C/C++、Rust、Go** - 基本サポート

## 📖 使用例

### AIアシスタント使用（Claude Desktop経由）

**ステップ1：コード概要の取得：**
> "このJavaファイルexamples/Sample.javaの全体的な複雑度とサイズはどうですか？"

**ステップ2：コード構造の解析（大型ファイル向け）：**
> "examples/Sample.javaの構造を解析して詳細なテーブルを表示してください"

**ステップ3：特定コードの抽出：**
> "examples/Sample.javaの84-86行目を表示してください"

### CLI使用

**ステップ1：基本解析（ファイル規模チェック）：**
```bash
uv run python -m tree_sitter_analyzer examples/Sample.java --advanced --output-format=text
```

**ステップ2：構造解析（LLM制限を超える大型ファイル向け）：**
```bash
uv run python -m tree_sitter_analyzer examples/Sample.java --table=full
```

**ステップ3：ターゲット抽出（特定コードセクションの読み取り）：**
```bash
uv run python -m tree_sitter_analyzer examples/Sample.java --partial-read --start-line 84 --end-line 86
```

**追加オプション：**
```bash
# クワイエットモード（INFOメッセージを抑制、エラーのみ表示）
uv run python -m tree_sitter_analyzer examples/Sample.java --advanced --output-format=text --quiet

# クワイエットモードでのテーブル出力
uv run python -m tree_sitter_analyzer examples/Sample.java --table=full --quiet
```

## 🔧 インストールオプション

### エンドユーザー向け
```bash
# 基本インストール
uv add tree-sitter-analyzer

# 人気言語付き（Java、Python、JS、TS）
uv add "tree-sitter-analyzer[popular]"

# MCPサーバーサポート付き
uv add "tree-sitter-analyzer[mcp]"

# フルインストール
uv add "tree-sitter-analyzer[all,mcp]"
```

### 開発者向け
```bash
# 開発用にクローンしてインストール
git clone https://github.com/aisheng-yu/tree-sitter-analyzer.git
cd tree-sitter-analyzer
uv sync --extra all --extra mcp
```

## 📚 ドキュメント

- **[ユーザー向けMCPセットアップガイド](https://github.com/aisheng-yu/tree-sitter-analyzer/blob/main/MCP_SETUP_USERS.md)** - AIアシスタントユーザー向けの簡単セットアップ
- **[開発者向けMCPセットアップガイド](https://github.com/aisheng-yu/tree-sitter-analyzer/blob/main/MCP_SETUP_DEVELOPERS.md)** - ローカル開発設定
- **[APIドキュメント](https://github.com/aisheng-yu/tree-sitter-analyzer/blob/main/docs/api.md)** - 詳細なAPIリファレンス
- **[コントリビューションガイド](https://github.com/aisheng-yu/tree-sitter-analyzer/blob/main/CONTRIBUTING.md)** - 貢献方法

## 🧪 テスト

このプロジェクトは**1126個のテスト**により高いコード品質を維持しています。

```bash
# テスト実行
pytest tests/ -v

# カバレッジ付きで実行
pytest tests/ --cov=tree_sitter_analyzer
```

## 📄 ライセンス

MITライセンス - 詳細は[LICENSE](LICENSE)ファイルをご覧ください。

## 🤝 コントリビューション

コントリビューションを歓迎します！詳細は[コントリビューションガイド](https://github.com/aisheng-yu/tree-sitter-analyzer/blob/main/CONTRIBUTING.md)をご覧ください。

### 🤖 AI/LLMコラボレーション

このプロジェクトは専門的な品質管理によりAI支援開発をサポートします：

```bash
# AIシステム向け - コード生成前に実行
python check_quality.py --new-code-only
python llm_code_checker.py --check-all

# AI生成コードレビュー向け
python llm_code_checker.py path/to/new_file.py
```

📖 **AIシステムとの作業に関する詳細な手順については、[AIコラボレーションガイド](https://github.com/aisheng-yu/tree-sitter-analyzer/blob/main/AI_COLLABORATION_GUIDE.md)と[LLMコーディングガイドライン](https://github.com/aisheng-yu/tree-sitter-analyzer/blob/main/LLM_CODING_GUIDELINES.md)をご覧ください。**

---

**大型コードベースとAIアシスタントを扱う開発者のために❤️で作られました。**
