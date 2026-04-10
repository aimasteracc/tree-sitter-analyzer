# 🌳 Tree-sitter Analyzer

**[English](README.md)** | **日本語** | **[简体中文](README_zh.md)**

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-8942%20passed-brightgreen.svg)](#-品質とテスト)
[![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer)
[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![Version](https://img.shields.io/badge/version-1.11.0-blue.svg)](https://github.com/aimasteracc/tree-sitter-analyzer/releases)
[![GitHub Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer)

> 🔎 **大規模リポジトリ向けのAI用エビデンスベースコードナビゲーション** - MCP統合 · 最小コンテキスト取得 · 重い前処理なしの検索

*Claudeはコードベース全体を読む必要がありません。あなたも、もう必要ない。*

---

## ✨ v1.11.0 最新情報

- **Claudeがファイルを1つも読まずにプロジェクトの骨格を把握**: `get_project_summary` がPageRankランク付きアーキテクチャノードを返す。elasticsearch(4万ファイル)・spring-framework(1.1万)・mybatis・spring-petclinicで検証済み
- **重要クラスを変更？Claudeが先に止める**: `modification_guard` がアーキテクチャランキングを読み取り。elasticsearchの`Writeable`をリネーム → verdict UNSAFE、rank #1、4745 callers
- **新言語 = 新ファイル1つ、既存コード変更なし**: プラグイン `edge_extractors/` パッケージ。Java・Python・TypeScript同梱。Kotlin追加は1ファイル+1行
- **未知のプロジェクトで探索効率2倍**: 端到端テスト済み — summaryあり5回 vs なし10回以上。Claudeが盲目的な検索フェーズをスキップ
- **設定不要のfirst-partyフィルタリング**: JavaはpomのgroupIdを読取り。Pythonは`sys.stdlib_module_names`使用。ブラックリスト管理一切不要

📖 完全なバージョン履歴は **[変更履歴](CHANGELOG.md)** をご覧ください。
---

---

## 🎬 デモ

<!-- GIF プレースホルダー - 作成手順は docs/assets/demo-placeholder.md を参照 -->
*デモGIF準備中 - SMARTワークフローとAI統合のデモンストレーション*

---

## 🎯 Tree-sitter Analyzer が解決すること

Tree-sitter Analyzer は、大規模コードベースで AI アシスタントが本当に必要な部分だけを読めるようにする、オープンソースの MCP / CLI ツールキットです。

- **ファイル丸ごと投入ではなく最小コンテキスト**: AI に渡す前に、本当に必要なコード断片だけを絞り込みます
- **エビデンスベースの解析**: tree-sitter の構造解析と `fd` / `ripgrep` を組み合わせて、関連ファイル・シンボル・経路を見つけます
- **重い前処理に依存しない**: フルインデックスが遅い、古くなりやすい、保守しづらいリポジトリでも使いやすい設計です

### よくあるユースケース

- 非常に大きなファイルやモジュールの役割を、全文を AI に渡さずに理解する
- 複雑なリポジトリで、業務ロジックや UI ハンドラ、バグに関係するコード経路を追跡する
- Java など巨大コードベースで、AI に解析や変更依頼を出す前にコンテキストを絞り込む

---

## 🚀 5分クイックスタート

### 前提条件

```bash
# uv のインストール (必須)
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows PowerShell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# fd + ripgrep のインストール (検索機能に必須)
brew install fd ripgrep          # macOS
winget install sharkdp.fd BurntSushi.ripgrep.MSVC  # Windows
```

📖 各プラットフォームの詳細は **[インストールガイド](docs/installation.md)** をご覧ください。

### インストールの確認

```bash
uv run tree-sitter-analyzer --show-supported-languages
```

---

## 🤖 AI統合

MCPプロトコルでAIアシスタントにTree-sitter Analyzerを設定します。

特に、非常に大きなファイル、ノイズの多いリポジトリ全体コンテキスト、あるいは一括投入コストが高いレガシーコードで効果を発揮します。

### Claude Desktop / Cursor / Roo Code

MCP設定に追加:

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uvx",
      "args": [
        "--from", "tree-sitter-analyzer[mcp]",
        "tree-sitter-analyzer-mcp"
      ],
      "env": {
        "TREE_SITTER_PROJECT_ROOT": "/path/to/your/project",
        "TREE_SITTER_OUTPUT_PATH": "/path/to/output/directory"
      }
    }
  }
}
```

**設定ファイルの場所:**
- **Claude Desktop**: `%APPDATA%\Claude\claude_desktop_config.json` (Windows) / `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
- **Cursor**: 内蔵MCP設定
- **Roo Code**: MCP設定

再起動後、AIに伝える: `プロジェクトルートディレクトリを設定してください: /path/to/your/project`

📖 完全なAPIドキュメントは **[MCPツールリファレンス](docs/api/mcp_tools_specification.md)** をご覧ください。

---

## 💻 よく使うCLIコマンド

### インストール

```bash
uv add "tree-sitter-analyzer[all,mcp]"  # フルインストール
```

### トップ5コマンド

```bash
# 1. ファイル構造を分析
uv run tree-sitter-analyzer examples/BigService.java --table full

# 2. クイックサマリー
uv run tree-sitter-analyzer examples/BigService.java --summary

# 3. コードセクションを抽出
uv run tree-sitter-analyzer examples/BigService.java --partial-read --start-line 93 --end-line 106

# 4. ファイルを検索してコンテンツを検索
uv run find-and-grep --roots . --query "class.*Service" --extensions java

# 5. 特定の要素をクエリ
uv run tree-sitter-analyzer examples/BigService.java --query-key methods --filter "public=true"
```

<details>
<summary>📋 出力例を表示</summary>

```
╭─────────────────────────────────────────────────────────────╮
│                   BigService.java 分析                       │
├─────────────────────────────────────────────────────────────┤
│ 総行数: 1419 | コード: 906 | コメント: 246 | 空白: 267      │
│ クラス: 1 | メソッド: 66 | フィールド: 9 | 平均複雑度: 5.27 │
╰─────────────────────────────────────────────────────────────╯
```

</details>

📖 すべてのコマンドとオプションは **[CLIリファレンス](docs/cli-reference.md)** をご覧ください。

---

## 🌍 対応言語

| 言語 | サポートレベル | 主な機能 |
|------|---------------|----------|
| **Java** | ✅ 完全対応 | Spring、JPA、エンタープライズ機能 |
| **Python** | ✅ 完全対応 | 型アノテーション、デコレータ |
| **TypeScript** | ✅ 完全対応 | インターフェース、型、TSX/JSX |
| **JavaScript** | ✅ 完全対応 | ES6+、React/Vue/Angular |
| **C** | ✅ 完全対応 | 関数、構造体、共用体、列挙型、プリプロセッサ |
| **C++** | ✅ 完全対応 | クラス、テンプレート、名前空間、継承 |
| **C#** | ✅ 完全対応 | Records、async/await、属性 |
| **SQL** | ✅ 強化対応 | テーブル、ビュー、ストアドプロシージャ、トリガー |
| **HTML** | ✅ 完全対応 | DOM構造、要素分類 |
| **CSS** | ✅ 完全対応 | セレクタ、プロパティ、分類 |
| **Go** | ✅ 完全対応 | 構造体、インターフェース、goroutine |
| **Rust** | ✅ 完全対応 | Trait、implブロック、マクロ |
| **Kotlin** | ✅ 完全対応 | データクラス、コルーチン |
| **PHP** | ✅ 完全対応 | PHP 8+、属性、Trait |
| **Ruby** | ✅ 完全対応 | Railsパターン、メタプログラミング |
| **YAML** | ✅ 完全対応 | アンカー、エイリアス、マルチドキュメント |
| **Markdown** | ✅ 完全対応 | ヘッダー、コードブロック、テーブル |

📖 言語固有の詳細は **[機能ドキュメント](docs/features.md)** をご覧ください。

---

## 📊 機能概要

| 機能 | 説明 | 詳細 |
|------|------|------|
| **SMARTワークフロー** | Set-Map-Analyze-Retrieve-Trace手法 | [ガイド](docs/smart-workflow.md) |
| **MCPプロトコル** | ネイティブAIアシスタント統合 | [APIドキュメント](docs/api/mcp_tools_specification.md) |
| **トークン最適化** | 最大95%のトークン削減 | [機能](docs/features.md) |
| **ファイル検索** | fdベースの高性能検出 | [CLIリファレンス](docs/cli-reference.md) |
| **コンテンツ検索** | ripgrep正規表現検索 | [CLIリファレンス](docs/cli-reference.md) |
| **セキュリティ** | プロジェクト境界保護 | [アーキテクチャ](docs/architecture.md) |

---

## 🔬 文法カバレッジ（MECEフレームワーク）

Tree-sitter Analyzerは、対応全17言語にわたる文法カバレッジ検証で**誤検知ゼロ**を保証します。

### フェーズ1：MECEアーキテクチャ（2026-03）

**新アーキテクチャ**：
- ノードタイプだけでなく**構文パス** `(node_type, parent_path)` を追跡
- **完全なノード同一性マッチング**（type + バイト範囲 + 親チェーン + ファイルパス）
- ネストしたノードの誤分類を排除（ラッパーノードによる誤検知なし）

---

## 🏆 品質とテスト

| 指標 | 値 |
|------|-----|
| **テスト** | 8,942 合格 ✅ |
| **カバレッジ** | [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) |
| **型安全性** | 100% mypy準拠 |
| **プラットフォーム** | Windows、macOS、Linux |

```bash
# テストを実行
uv run pytest tests/ -v

# カバレッジレポートを生成
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html
```

---

## 🔒 セキュリティとアーキテクチャ

Tree-sitter Analyzerは、AI支援開発ワークフローのための**デフォルトで安全**な設計原則に基づいています。

### セキュリティモデル

**プロジェクト境界の強制**
- すべてのMCPツールは、プロジェクトルート境界に対してファイルパスを検証
- 設定されたプロジェクトディレクトリ外のファイルへのアクセス不可
- シンボリックリンクトラバーサル防止
- パス正規化により `../` エスケープを防止

**入力検証**
- すべてのMCPツールパラメータでJSON Schemaバリデーション
- 厳格なmypy準拠による型安全なPython API
- シェルコマンド実行前のユーザー入力サニタイズ
- glob/regex検索のパターン検証

**リモート実行なし**
- 100%ローカル処理 — クラウド依存なし
- テレメトリやデータ収集なし
- オプションのPyPIバージョンチェック以外のネットワーク呼び出しなし
- ソースコード分析はあなたのマシン上に留まる

**安全なデフォルト**
- デフォルトで読み取り専用ファイル操作
- ファイル変更には明示的なオプトインが必要
- 外部ツール（fd、ripgrep）のサンドボックス化されたサブプロセス実行
- 環境変数の分離

### アーキテクチャ原則

```
┌─────────────────────────────────────────────────────────┐
│  AIアシスタント（Claude Desktop / Cursor / Roo Code）  │
└────────────────────┬────────────────────────────────────┘
                     │ MCPプロトコル（JSON-RPC）
                     ▼
┌─────────────────────────────────────────────────────────┐
│  MCPサーバー層                                          │
│  • 入力検証（JSON Schema）                              │
│  • プロジェクト境界チェック                             │
│  • ツールディスパッチ                                   │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  分析エンジン                                           │
│  • Tree-sitter AST解析（17言語）                        │
│  • 高速ファイル検索（fd）                               │
│  • コンテンツ検索（ripgrep）                            │
│  • 出力フォーマット（JSON / TOON）                      │
└─────────────────────────────────────────────────────────┘
```

**主要なセキュリティ境界**:
1. **MCPプロトコル**: AIは検証済みスキーマを持つ明示的に定義されたツールのみ呼び出し可能
2. **プロジェクトルート**: ファイル操作は設定されたディレクトリに限定
3. **読み取り専用**: 明示的なユーザー同意なしに破壊的操作なし
4. **ローカルファースト**: すべての処理はあなたのマシン上で実行

### セキュリティテスト

- **8,942以上の自動テスト**（セキュリティ重視のエッジケースを含む）
- **100% mypy型安全**により、バグのクラス全体を防止
- **CI/CDセキュリティスキャン**: Bandit（Pythonセキュリティ）、safety（依存関係の脆弱性）
- すべてのMCPツール実装の**手動セキュリティレビュー**

### セキュリティ問題の報告

セキュリティ上の懸念を発見しましたか？aimasteracc@gmail.comまでメールするか、GitHubでプライベートセキュリティアドバイザリを開いてください。

**自動化されたセキュリティバッジサービスは使用していません** — 当プロジェクトのセキュリティ姿勢は、サードパーティのスコアではなく、アーキテクチャ、テスト、コードレビューによって文書化されています。

---

## 🛠️ 開発

### セットアップ

```bash
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer
uv sync --extra all --extra mcp
```

### 品質チェック

```bash
uv run pytest tests/ -v                    # テストを実行
uv run python check_quality.py --new-code-only  # 品質チェック
uv run python llm_code_checker.py --check-all   # AIコードチェック
```

📖 システム設計の詳細は **[アーキテクチャガイド](docs/architecture.md)** をご覧ください。

---

## 🤝 コントリビュートとライセンス

コントリビュートを歓迎します！開発ガイドラインは **[コントリビューションガイド](docs/CONTRIBUTING.md)** をご覧ください。

### ⭐ サポート

このプロジェクトが役に立ったら、GitHubで ⭐ をお願いします！

### 💝 スポンサー

**[@o93](https://github.com/o93)** - MCPツール強化、テストインフラ、品質改善を支援するリードスポンサー。

**[💖 このプロジェクトをスポンサー](https://github.com/sponsors/aimasteracc)**

### 📄 ライセンス

MITライセンス - [LICENSE](LICENSE) ファイルをご覧ください。

---

## 🧪 テスト

### テストカバレッジ

| 指標 | 値 |
|------|-----|
| **総テスト数** | 8,942 テスト ✅ |
| **テスト合格率** | 100% (8,942/8,942) |
| **コードカバレッジ** | [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) |
| **型安全性** | 100% mypy準拠 |

### テストの実行

```bash
# すべてのテストを実行
uv run pytest tests/ -v

# 特定のテストカテゴリを実行
uv run pytest tests/unit/ -v              # 単体テスト
uv run pytest tests/integration/ -v         # 統合テスト
uv run pytest tests/regression/ -m regression  # 回帰テスト
uv run pytest tests/benchmarks/ -v         # ベンチマークテスト

# カバレッジを含めて実行
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html

# プロパティベーステストを実行
uv run pytest tests/property/

# パフォーマンスベンチマークを実行
uv run pytest tests/benchmarks/ --benchmark-only
```

### テストドキュメント

| ドキュメント | 説明 |
|--------------|------|
| [テスト作成ガイド](docs/test-writing-guide.md) | テスト作成の包括的なガイド |
| [回帰テストガイド](docs/regression-testing-guide.md) | Golden Master手法と回帰テスト |
| [テストドキュメント](docs/TESTING.md) | プロジェクトのテスト標準 |

### テストカテゴリ

- **単体テスト** (8,942+ テスト総計): 個別のコンポーネントを分離してテスト

### CI/CD統合

- **テストカバレッジワークフロー**: PRとプッシュでの自動カバレッジチェック
- **回帰テストワークフロー**: Golden Master検証とフォーマット安定性チェック
- **パフォーマンスベンチマーク**: 日次ベンチマーク実行とトレンド分析
- **品質チェック**: 自動リンティング、型チェック、セキュリティスキャン

### テストのコントリビュート

新機能をコントリビュートする際：

1. **テストを書く**: [テスト作成ガイド](docs/test-writing-guide.md)に従う
2. **カバレッジを確保**: 80%以上のコードカバレッジを維持
3. **ローカルで実行**: `uv run pytest tests/ -v`
4. **品質をチェック**: `uv run ruff check . && uv run mypy tree_sitter_analyzer/`
5. **ドキュメントを更新**: 新しいテストと機能を文書化

---

## 📚 ドキュメント

| ドキュメント | 説明 |
|--------------|------|
| [インストールガイド](docs/installation.md) | 各プラットフォームのセットアップ |
| [CLIリファレンス](docs/cli-reference.md) | 完全なコマンドリファレンス |
| [SMARTワークフロー](docs/smart-workflow.md) | AI支援分析ガイド |
| [MCPツールAPI](docs/api/mcp_tools_specification.md) | MCP統合の詳細 |
| [機能](docs/features.md) | 言語サポートの詳細 |
| [アーキテクチャ](docs/architecture.md) | システム設計 |
| [コントリビュート](docs/CONTRIBUTING.md) | 開発ガイドライン |
| [テスト作成ガイド](docs/test-writing-guide.md) | 包括的なテスト作成ガイド |
| [回帰テストガイド](docs/regression-testing-guide.md) | Golden Master手法 |
| [変更履歴](CHANGELOG.md) | バージョン履歴 |

---

**🎯 大規模コードベースとAIアシスタントを扱う開発者のために構築**

*すべてのコード行をAIに理解させ、すべてのプロジェクトがトークン制限を突破できるように*
