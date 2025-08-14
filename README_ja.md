# Tree-sitter Analyzer

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-1358%20passed-brightgreen.svg)](#testing)
[![Coverage](https://img.shields.io/badge/coverage-74.82%25-green.svg)](#testing)
[![Quality](https://img.shields.io/badge/quality-enterprise%20grade-blue.svg)](#quality)

**大型コードファイルの LLM トークン制限を解決します。**

AI アシスタントがファイル全体を読まずにコード構造を理解できる拡張可能な多言語コード解析ツール。コード概要、行範囲抽出、複雑度解析など、LLM ワークフローに最適化。

## ✨ なぜ Tree-sitter Analyzer なのか？

**問題:** 大型コードは LLM トークン制限を超え、解析が困難。

**解決:** スマート解析により以下を提供：
- 📊 **コード概要** 全文読まずに把握
- 🎯 **ターゲット抽出** 行範囲で精密抽出
- 📍 **正確な位置情報** 後続操作を容易に
- 🤖 **AI アシスタント統合** MCP プロトコル対応

## 🚀 5 分でクイックスタート

### AI アシスタント利用（Claude Desktop）

1. **インストール:**
```bash
# uv（高速 Python パッケージマネージャ）
curl -LsSf https://astral.sh/uv/install.sh | sh  # macOS/Linux
# または: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# 本パッケージの個別インストールは不要（uv が処理）
```

2. **Claude Desktop 設定:**

設定ファイルに追加：

**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Linux:** `~/.config/claude/claude_desktop_config.json`

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

3. **Claude Desktop を再起動** して開始

### CLI 利用

```bash
# 推奨: uv でインストール
uv add "tree-sitter-analyzer[popular]"

# ステップ 1: 規模チェック
uv run python -m tree_sitter_analyzer examples/Sample.java --advanced --output-format=text

# ステップ 2: 構造解析（大規模ファイル向け）
uv run python -m tree_sitter_analyzer examples/Sample.java --table=full

# ステップ 3: 行範囲抽出
uv run python -m tree_sitter_analyzer examples/Sample.java --partial-read --start-line 84 --end-line 86
```

## 🛠️ コア機能

### 1. コード構造解析
全文を読まずに取得：
- クラス/メソッド/フィールド数
- パッケージ情報
- インポート依存
- 複雑度メトリクス

### 2. ターゲット抽出
指定行範囲を効率抽出：
- 行レンジ抽出
- 正確な位置データ
- コンテンツ長

### 3. AI アシスタント統合（MCP）
三段階ワークフロー：
- `check_code_scale` - 第1段階：規模と複雑度
- `analyze_code_structure` - 第2段階：行位置つき構造表
- `extract_code_section` - 第3段階：行範囲抽出

### 4. 多言語サポート
- **Java** 完全サポート（高度解析）
- **Python** 完全サポート
- **JavaScript/TypeScript** 完全サポート
- **C/C++、Rust、Go** 基本サポート

## 📖 使用例

### AI アシスタント（Claude Desktop）

**ステップ 1：規模チェック**
```
ツール: check_code_scale
引数: {"file_path": "examples/Sample.java"}
```

**ステップ 2：構造解析（>100 行推奨）**
```
ツール: analyze_code_structure
引数: {"file_path": "examples/Sample.java", "format_type": "full"}
```

**ステップ 3：行範囲抽出（ステップ2の行情報を利用）**
```
ツール: extract_code_section
引数: {"file_path": "examples/Sample.java", "start_line": 84, "end_line": 86}
```

> 注意：パラメータ名はすべて snake_case（`file_path`, `start_line`, `end_line`, `format_type`）

### CLI 使用

**ステップ 1：基本解析（規模チェック）**
```bash
uv run python -m tree_sitter_analyzer examples/Sample.java --advanced --output-format=text
```

**ステップ 2：構造解析（大規模ファイル）**
```bash
uv run python -m tree_sitter_analyzer examples/Sample.java --table=full
```

**ステップ 3：ターゲット抽出（特定セクションを読み取り）**
```bash
uv run python -m tree_sitter_analyzer examples/Sample.java --partial-read --start-line 84 --end-line 86
```

**追加オプション：**
```bash
# Quiet モード（INFO 抑制、エラーのみ）
uv run python -m tree_sitter_analyzer examples/Sample.java --advanced --output-format=text --quiet

# Quiet + テーブル出力
uv run python -m tree_sitter_analyzer examples/Sample.java --table=full --quiet
```

## 🔧 インストール

### エンドユーザー
```bash
uv add tree-sitter-analyzer
uv add "tree-sitter-analyzer[popular]"
uv add "tree-sitter-analyzer[mcp]"
uv add "tree-sitter-analyzer[all,mcp]"
```

### 開発者
```bash
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer
uv sync --extra all --extra mcp
```

## 📚 ドキュメント

- **[ユーザー向け MCP セットアップ](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/MCP_SETUP_USERS.md)**
- **[開発者向け MCP セットアップ](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/MCP_SETUP_DEVELOPERS.md)**
- **[プロジェクトルート設定](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/PROJECT_ROOT_CONFIG.md)**
- **[API ドキュメント](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/docs/api.md)**
- **[貢献ガイド](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/CONTRIBUTING.md)**

### 🔒 プロジェクトルート設定

自動検出と境界保護：
- 自動検出: `.git`、`pyproject.toml`、`package.json`
- CLI: `--project-root /path/to/project`
- MCP: `TREE_SITTER_PROJECT_ROOT=${workspaceFolder}`
- セキュリティ: プロジェクト境界内のみ解析

**推奨 MCP 設定：**
```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": ["run", "--with", "tree-sitter-analyzer[mcp]", "python", "-m", "tree_sitter_analyzer.mcp.server"],
      "env": {"TREE_SITTER_PROJECT_ROOT": "${workspaceFolder}"}
    }
  }
}
```

## 🧪 テストと品質

エンタープライズ品質を維持：

### 📊 指標
- **1358 テスト** すべて成功 ✅
- **74.82% カバレッジ**
- **クロスプラットフォーム** Windows / macOS / Linux

### 🏆 最近の成果（v0.8.2）
- ✅ テスト安定化（31 失敗修正）
- ✅ フォーマッタのカバレッジ 0% → 42.30%
- ✅ エラーハンドリング 61.64% → 82.76%
- ✅ 重要モジュールへ 104 テスト追加

### 🔧 テスト実行
```bash
pytest tests/ -v
pytest tests/ --cov=tree_sitter_analyzer --cov-report=html
pytest tests/test_formatters_comprehensive.py -v
pytest tests/test_core_engine_extended.py -v
pytest tests/test_mcp_server_initialization.py -v
```

### 📈 カバレッジハイライト
- フォーマッタ：42.30%
- エラーハンドリング：82.76%
- 言語判定：98.41%
- CLI メイン：97.78%
- セキュリティ基盤：78%+

## 📄 ライセンス

MIT ライセンス（[LICENSE](LICENSE)）

## 🤝 コントリビューション

歓迎します。詳細は [CONTRIBUTING.md](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/CONTRIBUTING.md) を参照。

### 🤖 AI/LLM コラボレーション

AI 支援開発向けの品質コントロール：
```bash
python check_quality.py --new-code-only
python llm_code_checker.py --check-all
python llm_code_checker.py path/to/new_file.py
```

📖 [AI コラボレーションガイド](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/AI_COLLABORATION_GUIDE.md) と [LLM コーディングガイドライン](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/LLM_CODING_GUIDELINES.md) を参照。

---

**大型コードベースと AI アシスタントに取り組む開発者のために。**
