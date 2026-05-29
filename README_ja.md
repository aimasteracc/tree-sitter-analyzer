# 🌳 Tree-sitter Analyzer

**[English](README.md)** | **日本語** | **[简体中文](README_zh.md)**

> **AI エージェントのための MCP コード インテリジェンス サーバー — トークン削減、ツール呼び出し削減、100% ローカル動作。**
> 事前インデックス AST キャッシュ + 60 MCP ツール + 13 のキュレーション済みエージェント スキル + TOON 圧縮出力。
> 6 リポジトリの実測比較で **CodeGraph を上回る**（コスト中央値 **−11% vs CodeGraph の −4%**）、CLI は厳密な上位互換。

[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-18423%20passed-brightgreen.svg)](#-品質とテスト)
[![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer)
[![GitHub Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer)

---

## はじめに

**Claude Code** へワンライナーでインストール:

```bash
claude mcp add tree-sitter-analyzer \
  --env TREE_SITTER_PROJECT_ROOT="$PWD" \
  -- uvx --from "tree-sitter-analyzer[mcp]" tree-sitter-analyzer-mcp
```

エージェントを再起動し、こう伝える: 「プロジェクト ルートを私のリポジトリに設定して、codegraph_status を呼んでください。」

[その他のエージェント (Cursor / Copilot / Cline / Continue / Claude Desktop / Roo Code) →](#-対応エージェント)

---

## なぜ Tree-sitter Analyzer か

* **デフォルトでトークン効率**。全 MCP ツール応答は **TOON** — 表形式 JSON バリアントで、生 JSON 比 50-70% のペイロード削減。
* **Verdict エンベロープ**。すべての応答に `verdict: SAFE | CAUTION | UNSAFE | INFO | WARN | ERROR | NOT_FOUND` が付き、オーケストレーターは再プロンプトなしで結果ごとに分岐可能。
* **プロジェクト健全性 A-F グレーディング**。他のオープンソース ツールには無い — サイズ / 複雑度 / カバレッジ / 重複 / 依存 / git-ホットスポットの 6 次元でプロジェクト全体を採点。
* **13 のキュレーション済みワークフロー (Skills)**。「シンボル検索」「コール チェーン追跡」「健全性評価」「リファクター前の安全チェック」「PR レビュー」などの典型シナリオに対応するツール サブセットを事前パッケージ化。
* **5 層の安全保護**。`safe_to_edit` + `modification_guard` + 制約 DSL + `change_impact` + verdict エンベロープ — エージェントが手を入れる前にリスクを *知る* よう設計。
* **主要競合 CodeGraph に複数の head-to-head ベンチマークで勝利**。下記参照。

---

## ベンチマーク結果

ヘッドレス Claude Code (Haiku 4.5) にリポジトリごとに 1 つのアーキテクチャ質問を実施。3 アーム: MCP なし / CodeGraph MCP / Tree-sitter Analyzer MCP。各アーム 1 回実行 — 示唆的な数値であり統計的に厳密ではない。

| リポジトリ | 言語/ファイル数 | MCP なし基線 | CodeGraph | **TSA** | 勝者 |
|---|---|---|---|---|---|
| **Gin** | Go / 99 | $0.164 | $0.094 (−43 %) | **$0.080 (−51 %)** | **TSA** ⭐ |
| **Alamofire** | Swift / 98 | $0.201 | $0.219 (+9 %) | **$0.147 (−27 %)** | **TSA** ⭐ |
| **Excalidraw** | TS / 603 | $0.204 | **$0.179 (−12 %)** | $0.212 (+4 %) | CodeGraph |
| **Django** | Py / 2 910 | $0.162 | **$0.106 (−35 %)** | $0.205 (+27 %) | CodeGraph |
| **Tokio** | Rust / 778 | **$0.214** | $0.285 (+33 %) | $0.303 (+42 %) | 両者敗北 |
| **OkHttp** | Java / 596 | **$0.169** | $0.200 (+18 %) | $0.178 (+5 %) | 両者敗北 |
| **基線に対する中央値 Δ** | | | **−4 %** | **−11 %** | **TSA** |

TSA は **6 リポジトリ中 2 つで完勝**、**コスト中央値節約 (−11%) は CodeGraph の −4% を超え**、indexer-class ツールが機能するべきリポジトリで CodeGraph と同じ方向性を示した。

> 中央値が CodeGraph 公表の −35% と異なる理由: コスト制御のため Haiku を使用 (彼らは Opus + 4 回中央値)。完全な原始エンベロープと再現スクリプトは `docs/internal/CODEGRAPH_BENCHMARK_FINAL_2026-05-24.md` を参照。

---

## 主要機能

### 事前インデックス コード インテリジェンス (CodeGraph 相当 + 上位互換)

| 能力 | TSA ツール | ステータス |
|---|---|---|
| シンボル検索 (FTS5 + **BM25 ランク付け**) | `codegraph_symbol_search` | **優位** — 関連スコア順にソート |
| go-to-def / find-refs / コール階層を 1 回の呼び出しで | `codegraph_navigate` | PRIMARY エントリポイント |
| 関連シンボル N 個のソース + 関係マップを一括取得 | `codegraph_explore` | 同等 |
| 関数レベル blast radius + リスク スコア | `codegraph_impact` | 同等 + リスク スコア |
| X を呼ぶのは誰 / X は何を呼ぶ | `codegraph_callers` / `codegraph_callees` | 同等 |
| インデックス健全性 (+ エッジ数) | `codegraph_status` | **優位** — `total_edges` でグラフ密度を把握 |
| 事前構築コール グラフ キャッシュ | `codegraph_autoindex` / `codegraph_full_index` / `codegraph_incremental_sync` | 同等 |
| 変更の影響を受けるテスト (CLI) | `--affected FILE...` | 同等 |

### Tree-sitter Analyzer 独占機能

| 能力 | TSA ツール | 説明 |
|---|---|---|
| **BM25 ランク付き検索** | 全検索ツール | 各結果に relevance_score; DSL で sort(by='confidence') |
| **セマンティック検索 (133× 高速化)** | `codegraph_query semantic()` | BM25 で 40k シンボル→約 400 に絞り込んでコサイン再ランク |
| **プロジェクト A-F 健全性グレーディング** | `check_project_health` | 6 次元、競合に対応無し |
| **TOON 出力** | 全ツール、デフォルト `output_format: "toon"` | 50-70% トークン節約 |
| **Verdict エンベロープ** | 全ツール | `SAFE/CAUTION/UNSAFE/INFO/WARN/ERROR/NOT_FOUND` |
| **Safe-to-edit ゲート** | `safe_to_edit` + `modification_guard` | 高リスク編集前に拒否 |
| **アーキテクチャ制約 DSL** | `check_constraints` | 「モジュール A は B に依存禁止」→ 強制 |
| **ファイル レベル健全性** | `check_file_health` | ブロック / 長メソッド / コード スメル検出 |
| **クラス階層** | `codegraph_class_hierarchy` | 型継承ツリー |
| **依存マトリクス** | `codegraph_dependency_matrix` | モジュール結合マトリクス |
| **デッド コード** | `codegraph_dead_code` | 推移的到達不能解析 |
| **複雑度ヒート マップ** | `codegraph_complexity_heatmap` | 関数別循環的複雑度 + プロジェクト ビュー |
| **AST 構造的クローン検出** | `codegraph_similarity` | テキスト類似度を超える |
| **Mermaid コール グラフ エクスポート** | `codegraph_visualize` | ドキュメントへ直接貼付 |
| **UML Mermaid エクスポート** | `codegraph_uml` | class / package / component / sequence 図 |
| **PR レビュー** | `codegraph_pr_review` | AST diff + セマンティック分類 + blast radius |
| **agent_summary** | 全応答 | エンベロープに次ステップ ヒントを内蔵 |
| **Synapse クロスファイル リゾルバ** | 内部 | import-aware、正規表現推測より強力 |
| **時間的アクティベーション** | `symbol_lineage` | シンボル別 git 修正頻度 |

### Skills (13 のキュレーション済みワークフロー)

CodeGraph には skill システムが存在しない。本ツールは `.claude/skills/tsa-*/` 下に 13 個を提供:

`tsa-landing`、`tsa-find`、`tsa-graph`、`tsa-structure`、`tsa-deps`、`tsa-index`、`tsa-health-watch`、`tsa-edit-safety`、`tsa-edit-then-verify`、`tsa-constraints`、`tsa-pr-review`、`tsa-refactor-queue`、`tsa-temporal`。

各 skill は `allowed-tools` ツール サブセット + 手順レシピ + 決定面スキーマを同梱し、エージェントは 60 個のツールから毎回選別する必要が無い。

### 252 の CLI フラグ

CodeGraph の 15 コマンド CLI の厳密な上位互換。主なもの:

```bash
tree-sitter-analyzer --table full <file>          # メソッド/シグネチャ/複雑度テーブル
tree-sitter-analyzer --partial-read --start-line N --end-line M <file>
tree-sitter-analyzer --project-health             # プロジェクト A-F グレーディング
tree-sitter-analyzer --callers <symbol>           # 呼び出し元
tree-sitter-analyzer --codegraph-impact <fn>      # blast radius + リスク
tree-sitter-analyzer --affected <file...>         # 影響を受けるテスト
tree-sitter-analyzer --dead-code                  # 推移的到達不能
tree-sitter-analyzer --check-constraints          # アーキテクチャ規則
tree-sitter-analyzer --safe-to-edit <file>        # リスク時に拒否
```

完全なインターフェースは [`docs/CODEMAPS/cli.md`](docs/CODEMAPS/cli.md) を参照。

---

## クイック スタート

### 1. 依存関係をインストール

```bash
# uv (必須)
curl -LsSf https://astral.sh/uv/install.sh | sh        # macOS / Linux
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# fd + ripgrep (検索機能で必須)
brew install fd ripgrep                                # macOS
winget install sharkdp.fd BurntSushi.ripgrep.MSVC      # Windows
```

### 2. Tree-sitter Analyzer をインストール

```bash
uv add "tree-sitter-analyzer[all,mcp]"
```

### 3. エージェントへ接続

[**対応エージェント**](#-対応エージェント)を参照。多くのクライアントで以下の MCP 設定を使用:

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uvx",
      "args": ["--from", "tree-sitter-analyzer[mcp]", "tree-sitter-analyzer-mcp"],
      "env": { "TREE_SITTER_PROJECT_ROOT": "/絶対パス/プロジェクト" }
    }
  }
}
```

再起動後: 「プロジェクト ルートを私のリポジトリに設定して、codegraph_status を呼んでください。」

---

## 仕組み

```
ソース コード → tree-sitter 解析 → SQLite + FTS5 インデックス (.ast-cache/index.db)
                                          ↓
       codegraph_navigate / codegraph_explore / codegraph_callers / ...
                                          ↓
                            TOON 圧縮エンベロープ
                            (verdict + agent_summary + データ)
                                          ↓
                               MCP クライアント / CLI 消費者
```

インデックスは最初のクエリで遅延構築され、ファイル変更時はコンテンツ ハッシュ差分で増分更新 (`codegraph_incremental_sync`)。60 ツール全てが同じ `.ast-cache/` を共有し、クエリとフォローアップは作業を共有する。

---

## 対応エージェント

<details>
<summary><b>📘 Claude Code</b> (推奨)</summary>

```bash
claude mcp add tree-sitter-analyzer \
  --env TREE_SITTER_PROJECT_ROOT="$PWD" \
  -- uvx --from "tree-sitter-analyzer[mcp]" tree-sitter-analyzer-mcp
```

検証: `claude mcp list`。13 の `tsa-*` skills は `.claude/skills/` から自動検出される。
</details>

<details>
<summary><b>📗 Claude Desktop</b></summary>

`claude_desktop_config.json` を編集 (macOS: `~/Library/Application Support/Claude/`, Windows: `%APPDATA%\Claude\`, Linux: `~/.config/Claude/`):

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uvx",
      "args": ["--from", "tree-sitter-analyzer[mcp]", "tree-sitter-analyzer-mcp"],
      "env": { "TREE_SITTER_PROJECT_ROOT": "/絶対パス/プロジェクト" }
    }
  }
}
```
</details>

<details>
<summary><b>📙 GitHub Copilot (VS Code)</b></summary>

`.vscode/mcp.json` を作成 (注: キーは `servers`、`mcpServers` では無い):

```json
{
  "servers": {
    "tree-sitter-analyzer": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "tree-sitter-analyzer[mcp]", "tree-sitter-analyzer-mcp"],
      "env": { "TREE_SITTER_PROJECT_ROOT": "${workspaceFolder}" }
    }
  }
}
```
</details>

<details>
<summary><b>🖱 Cursor / Cline / Continue / Roo Code</b></summary>

すべて Claude Desktop と同じ `mcpServers` スキーマを使用。Cursor: **設定 → MCP**。Cline: MCP パネル → 設定編集。Continue: `~/.continue/config.json` の `experimental.modelContextProtocolServers`。Roo Code: MCP パネル → MCP 設定編集。
</details>

> ⚠️ `TREE_SITTER_PROJECT_ROOT` は **絶対パス** が必須。サーバーは `SecurityBoundaryManager` でエスケープを防ぐセキュリティ境界を強制する。

---

## サポート言語

21 言語プラグイン; 16 はインデクサーへ完全統合 + 5 個 (data/markup) は CLI 単一ファイル パスで到達可能。2026-05-24 のパッチで数か月間サイレントにスキップされていた Swift / Kotlin / Ruby / PHP / C# がアンブロック。

| ティア | 言語 |
|---|---|
| **完全インデックス + シンボル + コール グラフ** | Python · Java · JavaScript · TypeScript · Go · Rust · C · C++ · C# · Swift · Kotlin · Ruby · PHP |
| **単一ファイル解析 (CLI)** | HTML · CSS · Markdown · SQL · YAML |
| **スキャフォールド (プラグイン有 / インデクサー結線待ち)** | bash · scala · json |

CodeGraph も類似の集合をサポート; 両ツール共に未実装の主流コード言語は **Dart, Vue, Svelte, Lua** のみ (次スプリント バックログ)。

---

## 設定

基本的に設定不要。デフォルトでエージェントに接続して忘れて構わない:

* **出力形式**: TOON。`output_format: "json"` で呼び出し毎にオーバーライド可。
* **プロジェクト ルート**: `TREE_SITTER_PROJECT_ROOT` (env, MCP) または `--project-root` (CLI)。
* **キャッシュ場所**: `<project>/.ast-cache/`。安全に削除可 — 自動再構築される。
* **任意**: `TREE_SITTER_OUTPUT_PATH` 大出力の書き込み先。

---

## 品質とテスト

| 指標 | 値 |
|---|---|
| テスト通過 | 18,423 ✅ |
| カバレッジ | [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) |
| 型安全性 | 100% mypy |
| プラットフォーム | macOS · Linux · Windows |
| Pre-commit ゲート | bandit · mypy · pyupgrade · detect-secrets · codemap-sync · smell-ratchet |

```bash
uv run pytest -q                                # フル スイート
uv run python check_quality.py --new-code-only  # 品質ゲート
```

---

## トラブルシューティング

| 症状 | 修正 |
|---|---|
| `.swift / .kt / .rb / .php / .cs` で `unsupported language` | ≥ 1.12.x へ更新 — 5 言語 gap は commit `50e99a8f` で修正済み |
| MCP サーバーがクライアントに表示されない | `TREE_SITTER_PROJECT_ROOT` は**絶対パス**必須; 設定編集後にクライアント再起動 |
| `database is locked` | `.ast-cache/index.db` を保持する他プロセスを停止; 継続する場合は `rm -rf .ast-cache && tree-sitter-analyzer --autoindex` |
| 初回呼び出しが遅い | 初回はインデックスを構築。後続はサブ秒。事前に `--full-index` を実行すれば償却可能 |
| エージェントが誤ったツールを選ぶ | `tsa-*` skill (`/tsa-graph`、`/tsa-find` 等) を使用 — 各 skill は可視ツールを 1 ワークフローに制限 |

---

## 開発

```bash
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer
uv sync --extra all --extra mcp
uv run pytest -q
```

開発ガイドは **[`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md)** を参照。

---

## 貢献とライセンス

* ⭐ GitHub star は他の AI エージェント ユーザーに本ツールを届ける助けに。
* 💖 [スポンサー](https://github.com/sponsors/aimasteracc) — 継続的な MCP / Skills 開発を支援。
* リード スポンサー: **[@o93](https://github.com/o93)**。
* MIT ライセンス — [LICENSE](LICENSE) を参照。
