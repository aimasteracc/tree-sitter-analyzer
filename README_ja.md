# 🌳 Tree-sitter Analyzer

**[English](README.md)** | **日本語** | **[简体中文](README_zh.md)**

[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/) [![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org) [![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE) [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) [![Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer) [![対応: Claude Code · Cursor · MCP](https://img.shields.io/badge/対応-Claude%20Code%20%C2%B7%20Cursor%20%C2%B7%20MCP-6f42c1.svg)](#supported-agents)

**AI エージェントが信頼できるコード インテリジェンス** — クロスランゲージ構造解析、エージェントネイティブ設計（MCP + CLI）。

TSA は tree-sitter でコードベースをインデックスし、コール グラフ・シンボル検索・構造クエリを AI コーディング エージェントへ提供します — **8 MCP ツール** + CLI、完全ローカル、テレメトリなし。

**なぜ違うのか：**
* **クロスランゲージ正確性がモート（堀）。** 言語ファミリ ゲートが、名前のみを根拠にしたクロスランゲージ束縛を防ぎます。
* **エージェントネイティブ。** **8 MCP ツール**が TOON 出力と verdict エンベロープを提供し、CLI とキュレーション済みワークフローからも利用できます。
* **広くかつ正確に分類。** 13 言語は `pipeline_registered`（パイプライン登録済み、非 E2E: Python · Go · Rust · Java · JS · TS · C · C++ · C# · Swift · Kotlin · Ruby · PHP）です。これは登録・配線の証拠であり、クロスファイル呼び出し解決の検証を意味しません。

> v1.x からの移行は [docs/MIGRATION.md](docs/MIGRATION.md) を参照。

---

## はじめに

> **Python 3.10 以上が必要です**（確認: `python3 --version`）。必要に応じて [python.org](https://www.python.org/downloads/) からインストールしてください。

### 自動インストール（推奨）

```bash
curl -fsSL https://raw.githubusercontent.com/aimasteracc/tree-sitter-analyzer/main/install.sh | bash
```

`install.sh` は `uv` の有無を確認して未インストールなら自動導入し、Claude Desktop / Claude Code / Cursor / VS Code の設定ファイルを検出して MCP エントリを自動書き込みします。セットアップ後は `tree-sitter-analyzer --doctor` で設定を確認できます。

**Claude Code** へワンライナーでインストール:

```bash
claude mcp add tree-sitter-analyzer \
  --env TREE_SITTER_PROJECT_ROOT="$PWD" \
  -- uvx --from "tree-sitter-analyzer[mcp]" tree-sitter-analyzer-mcp
```

エージェントを再起動し、こう伝える: 「`index` ツールを action=status で呼んでください。」

> **PyPI / uvx ユーザーへ — スキルのインストール:** `tsa-*` スキルはホイールに同梱されています。一度だけ次のコマンドでインストールしてください:
> ```bash
> tree-sitter-analyzer --install-skills
> ```
> git clone ユーザーはすでに `.claude/skills/` に含まれているため、操作不要です。

[その他のエージェント (Cursor / Copilot / Cline / Continue / Claude Desktop / Roo Code) →](#-対応エージェント)

### クイック インストール

#### 1. 依存関係をインストール

```bash
# uv (必須)
curl -LsSf https://astral.sh/uv/install.sh | sh        # macOS / Linux
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# fd + ripgrep (検索機能で必須)
brew install fd ripgrep                                # macOS
winget install sharkdp.fd BurntSushi.ripgrep.MSVC      # Windows
```

#### 2. Tree-sitter Analyzer をインストール

```bash
# スタンドアロンインストール(永続 CLI コマンド):
uv tool install "tree-sitter-analyzer[all,mcp]"
# — インストール不要でも可:下の MCP エントリは uvx でオンデマンド実行されます。
# uv 管理の Python プロジェクト内では: uv add "tree-sitter-analyzer[all,mcp]"
```

#### 3. エージェントへ接続

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

再起動後: 「`index` ツールを action=status で呼んでください。」

**自分のリポジトリでリゾルバの動作を確認**（インストール不要、最初に再インデックスします）:

```bash
uvx --from tree-sitter-analyzer miswire-audit .
```

クロスランゲージの名前衝突候補を報告し、自分のリポジトリでリゾルバの動作を調査できます。結果は診断情報であり、競合ベンチマークの主張ではありません。

---

## なぜ Tree-sitter Analyzer か

* **トークンを意識した出力。** MCP 応答はデフォルトで **TOON** を使用します。ペイロードの挙動は [output-cost invariants](tests/unit/mcp/test_output_cost_invariants.py) で保護され、既知の decision-tool 制約は [RFC-0018](rfcs/0018-response-envelope-normalization-and-adaptive-toon.md) で追跡されています。
* **Verdict エンベロープ。** すべての応答に `verdict: SAFE | CAUTION | UNSAFE | INFO | REVIEW | WARN | ERROR | NOT_FOUND` が付き、オーケストレーターは結果に応じて分岐できます。
* **プロジェクト健全性 A-F グレーディング。** サイズ、複雑度、カバレッジ、重複、依存、構造、git ホットスポットを組み合わせて評価します。
* **キュレーション済みワークフロー（Skills）。** 「シンボル検索」「コール チェーン追跡」「健全性評価」「リファクター前の安全チェック」「PR レビュー」などのツール サブセットを提供します。
* **多層的な安全保護。** `edit action=safe` + `edit action=guard` + 制約 DSL + `edit action=impact` + verdict エンベロープで、編集前のリスク判断を支援します。
* **CLI/MCP パリティと統合クエリ DSL。** 同じ解析プリミティブをエージェントとシェル ユーザーが利用できます。

---

## 主要機能

### 事前インデックス コード インテリジェンス (CodeGraph 相当 + 上位互換)

| 能力 | TSA ツール | ステータス |
|---|---|---|
| シンボル検索 (FTS5 + **BM25 ランク付け**) | `search` action=symbol | **優位** — 関連スコア順にソート |
| go-to-def / find-refs / コール階層をまとめて要求 | `nav` action=navigate | PRIMARY エントリポイント |
| 関連シンボル N 個のソース + 関係マップを一括取得 | `structure` action=explore | 同等 |
| 関数レベル blast radius + リスク スコア | `nav` action=impact | 同等 + リスク スコア |
| X を呼ぶのは誰 / X は何を呼ぶ | `nav` action=callers / action=callees | 同等 |
| インデックス健全性 (+ エッジ数) | `index` action=status | **優位** — `total_edges` でグラフ密度を把握 |
| 事前構築コール グラフ キャッシュ | `index` action=auto / action=full / action=sync | 同等 |
| 変更の影響を受けるテスト (CLI) | `--affected FILE...` | 同等 |

### Tree-sitter Analyzer 独占機能

| 能力 | TSA ツール | 説明 |
|---|---|---|
| **BM25 ランク付き検索** | 全検索ツール | 全結果に min-max 正規化した relevance_score; DSL で sort(by='confidence') |
| **セマンティック検索 (BM25 事前フィルタ)** | `search` action=chain (`semantic()` DSL) | コサイン再ランク前に字句フィルタリング |
| **プロジェクト A-F 健全性グレーディング** | `health` action=project | サイズ、複雑度、依存、カバレッジ、重複、構造、git ホットスポットを統合 |
| **TOON 出力** | 全ツール、デフォルト `output_format: "toon"` | コンパクトな表形式エンコーディング; decision tool は RFC-0018 で追跡 |
| **Verdict エンベロープ** | 全ツール | `SAFE/CAUTION/UNSAFE/INFO/WARN/ERROR/NOT_FOUND` |
| **Safe-to-edit ゲート** | `edit` action=safe / action=guard | 高リスク編集前に拒否 |
| **アーキテクチャ制約 DSL** | `edit` action=constraints | 「モジュール A は B に依存禁止」→ 強制 |
| **ファイル レベル健全性** | `health` action=file | ブロック / 長メソッド / コード スメル検出 |
| **クラス階層** | `structure` action=class_tree | 型継承ツリー |
| **依存マトリクス** | `health` action=matrix | モジュール結合マトリクス |
| **デッド コード** | `health` action=dead | 推移的到達不能解析 |
| **複雑度ヒート マップ** | `health` action=heatmap | 関数別循環的複雑度 + プロジェクト ビュー |
| **AST 構造的クローン検出** | `viz` action=similarity | テキスト類似度を超える |
| **Mermaid コール グラフ エクスポート** | `viz` action=graph | ドキュメントへ直接貼付 |
| **UML Mermaid エクスポート** | `viz` action=uml | class / package / component / sequence 図 |
| **PR レビュー** | `edit` action=pr | AST diff + セマンティック分類 + blast radius |
| **agent_summary** | 全応答 | エンベロープに次ステップ ヒントを内蔵 |
| **Synapse クロスファイル リゾルバ** | 内部 | import-aware、正規表現推測より強力 |
| **時間的アクティベーション** | `nav` action=lineage | シンボル別 git 修正頻度 |
| **ファイル把握** | `project` action=smart | 健全性 + エクスポート + 依存 + 編集リスクをまとめた応答で返す |
| **アーキテクチャ意思決定ジャーナル** | `project` action=journal | セッション間で推論を永続化 — 他に提供しているツールは無い |

### Skills

TSA は `.claude/skills/tsa-*/` 下にキュレーション済みワークフローを提供します:

`tsa-landing`、`tsa-find`、`tsa-graph`、`tsa-structure`、`tsa-deps`、`tsa-index`、`tsa-health-watch`、`tsa-edit-safety`、`tsa-edit-then-verify`、`tsa-constraints`、`tsa-pr-review`、`tsa-refactor-queue`、`tsa-temporal`。

各 skill は `allowed-tools` ツール サブセット + 手順レシピ + 決定面スキーマを同梱し、エージェントは 8 個のツールから毎回選別する必要がありません。

### 323 の CLI フラグ

CodeGraph の CLI の厳密な上位互換。主なもの:

```bash
tree-sitter-analyzer --table full <file>          # メソッド/シグネチャ/複雑度テーブル
tree-sitter-analyzer --partial-read --start-line N --end-line M <file>
tree-sitter-analyzer --project-health             # プロジェクト A-F グレーディング
# 注意: --callers / --callees はコールグラフインデックスが必要 — 先に --full-index を実行
tree-sitter-analyzer --full-index                 # コールグラフインデックスを構築（一度だけ）
tree-sitter-analyzer --callers <symbol>           # 呼び出し元
tree-sitter-analyzer --codegraph-impact <fn>      # blast radius + リスク
tree-sitter-analyzer --affected <file...>         # 影響を受けるテスト
tree-sitter-analyzer --dead-code                  # 推移的到達不能
tree-sitter-analyzer --check-constraints          # アーキテクチャ規則
tree-sitter-analyzer --safe-to-edit <file>        # リスク時に拒否
```

完全なインターフェースは [`docs/CODEMAPS/cli.md`](docs/CODEMAPS/cli.md) を参照。

---

## 定量的主張のガバナンス

公開するベンチマーク、性能、競合比較の数値は、[`benchmarks/codegraph_compare/claim_registry.json`](benchmarks/codegraph_compare/claim_registry.json) の provenance-bound registry からのみ生成します。E4 証拠は、ツール名とバージョン、測定値、コーパス、ベンチマーク日付/バージョン、artifact digest を厳密に結び付ける必要があります。E4 未満の証拠は内部情報に留まり、公開文言を生成できません。[ベンチマーク runbook](benchmarks/codegraph_compare/README.md) を参照してください。

<!-- BEGIN GENERATED QUANTITATIVE CLAIMS -->
<!-- END GENERATED QUANTITATIVE CLAIMS -->

生成項目がない場合、公開が承認された定量的主張は現在ありません。上記の定性的説明は境界を明示した製品能力であり、測定済みの優位性を主張するものではありません。

---

## 仕組み

```
ソース コード → tree-sitter 解析 → SQLite + FTS5 インデックス (.ast-cache/index.db)
                                          ↓
       nav (navigate) / structure (explore) / nav (callers) / ...
                                          ↓
                            TOON 圧縮エンベロープ
                            (verdict + agent_summary + データ)
                                          ↓
                               MCP クライアント / CLI 消費者
```

インデックスは最初のクエリで遅延構築され、ファイル変更時はコンテンツ ハッシュ差分で増分更新 (`index` action=sync)。8 個のファサード全てが同じ `.ast-cache/` を共有し、クエリとフォローアップは作業を共有する。

---

## 対応エージェント

<details>
<summary><b>📘 Claude Code</b> (推奨)</summary>

```bash
claude mcp add tree-sitter-analyzer \
  --env TREE_SITTER_PROJECT_ROOT="$PWD" \
  -- uvx --from "tree-sitter-analyzer[mcp]" tree-sitter-analyzer-mcp
```

検証: `claude mcp list`。同梱の `tsa-*` skills は `.claude/skills/` から自動検出されます。

**PyPI / uvx ユーザー** — 同梱スキルを一度インストール:
```bash
tree-sitter-analyzer --install-skills
```
git clone ユーザーはすでに含まれているため不要です。
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

> ⚠️ `TREE_SITTER_PROJECT_ROOT` は **絶対パス** が必須。サーバーは `SecurityValidator` でエスケープを防ぐセキュリティ境界を強制する。

---

## サポート言語

<!-- BEGIN GENERATED LANGUAGE SUPPORT INVENTORY -->
ランタイムレジストリから生成。**22 言語プラグイン**; 13 は `pipeline_registered`（非 E2E）、3 は `index_admitted`、5 個は data/markup、1 個はスキャフォールド。登録は正のクロスファイル束縛を保証しない。
| ティア | 言語 |
|---|---|
| **`pipeline_registered`（パイプライン登録済み、非 E2E）** | C · C++ · C# · Go · Java · JavaScript · Kotlin · PHP · Python · Ruby · Rust · Swift · TypeScript |
| **`index_admitted`（インデックス受け入れ済み）** | Bash · Lua · Scala |
| **単一ファイル解析 (CLI)** | CSS · HTML · Markdown · SQL · YAML |
| **スキャフォールド (プラグイン有 / インデクサー結線待ち)** | JSON |

Lua はインデックス受け入れ済みで call dispatch と resolver slot も持つが、import dispatch とクロスファイル E2E 証拠は未確認。
<!-- END GENERATED LANGUAGE SUPPORT INVENTORY -->

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
| テスト通過 | 包括的テストスイート ✅ |
| カバレッジ | [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) |
| 型安全性 | mypy |
| プラットフォーム | macOS · Linux · Windows |
| Pre-commit ゲート | ruff · bandit · mypy · pyupgrade · detect-secrets · tsa-codemap-sync |

```bash
uv run pytest -q                                # フル スイート
uv run pytest -q --maxfail=1 -m "not slow and not full_language and not integration"  # 開発時の高速ループ
PYTEST_XDIST_AUTO_NUM_WORKERS=1 uv run pytest -q --maxfail=1 -m "not slow and not full_language and not integration"  # CPUを抑えたいとき
PYTEST_XDIST_AUTO_NUM_WORKERS=2 uv run pytest -q --maxfail=1 -m "not slow and not full_language and not integration"  # ほどほどな並列
uv run pytest --lf --maxfail=1                  # 前回失敗したテストだけ再実行
uv run python check_quality.py --new-code-only  # 品質ゲート
```

---

## トラブルシューティング

| 症状 | 修正 |
|---|---|
| `.swift / .kt / .rb / .php / .cs` で `unsupported language` | ≥ 1.12.x へ更新 — 5 言語 gap は commit `50e99a8f` で修正済み。extras 区分の文法モジュールはベースインストールに同梱されません。`pip install "tree-sitter-analyzer[swift]"`(または `kotlin`、`ruby`、`php`、`csharp`)で追加してください |
| MCP サーバーがクライアントに表示されない | `TREE_SITTER_PROJECT_ROOT` は**絶対パス**必須; 設定編集後にクライアント再起動。[TREE\_SITTER\_PROJECT\_ROOT に相対パスを指定した場合](#tree_sitter_project_root-に相対パスを指定した場合)も参照 |
| `database is locked` | `.ast-cache/index.db` を保持する他プロセスを停止; 継続する場合は `rm -rf .ast-cache && tree-sitter-analyzer --autoindex` |
| 初回呼び出しが遅い | 初回はインデックスを構築。後続はサブ秒。事前に `--full-index` を実行すれば償却可能 |
| エージェントが誤ったツールを選ぶ | `tsa-*` skill (`/tsa-graph`、`/tsa-find` 等) を使用 — 各 skill は可視ツールを 1 ワークフローに制限 |

### TREE\_SITTER\_PROJECT\_ROOT に相対パスを指定した場合

**症状:** MCP サーバーはエラーなく起動するが、TSA が誤った解析結果を返すか `project root not found` のようなエラーが発生する。

**原因:** `TREE_SITTER_PROJECT_ROOT` に相対パス（例: `./myproject`）が設定されている。`uvx` がサーバーを起動するとき、プロセスの作業ディレクトリがインストール実行時と異なる場合があり、相対パスが誤った場所に解決される。

**修正:** 常に絶対パスを使用する:

```bash
# 正しい
"TREE_SITTER_PROJECT_ROOT": "/home/user/myproject"

# これも正しい（install.sh が実行時に解決する）
"TREE_SITTER_PROJECT_ROOT": "$(pwd)"        # または $(realpath .)

# 誤り
"TREE_SITTER_PROJECT_ROOT": "./myproject"
"TREE_SITTER_PROJECT_ROOT": "myproject"
```

`tree-sitter-analyzer --doctor` で設定を確認できます。

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
