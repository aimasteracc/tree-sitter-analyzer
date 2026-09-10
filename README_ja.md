# 🌳 Tree-sitter Analyzer

**[English](README.md)** | **日本語** | **[简体中文](README_zh.md)**

[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/) [![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org) [![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE) [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) [![Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer) [![対応: Claude Code · Cursor · MCP](https://img.shields.io/badge/対応-Claude%20Code%20%C2%B7%20Cursor%20%C2%B7%20MCP-6f42c1.svg)](#supported-agents)

**AI エージェントが信頼できるコード インテリジェンス** — [対応言語一覧](#サポート言語)全体で正確なクロスランゲージ構造解析、エージェントネイティブ設計（MCP + CLI）。

TSA は tree-sitter でコードベースをインデックスし、コール グラフ・シンボル検索・構造クエリを AI コーディング エージェントへ提供します — **8 MCP ツール** + CLI、完全ローカル、テレメトリなし。

**なぜ違うのか：**
* **クロスランゲージ正確性がモート（堀）。** 言語ファミリ ゲートが、名前のみを根拠にしたクロスランゲージ束縛を防ぎます。
* **エージェントネイティブ。** **8 MCP ツール**が構造化 JSON 出力と verdict エンベロープを提供し、CLI とキュレーション済みワークフローからも利用できます。
* **広くかつ正確に分類。** [生成された対応深度インベントリ](#サポート言語)は、パイプラインの証拠と未検証のクロスファイル動作を区別します。

> v1.x からの移行は [docs/MIGRATION.md](docs/MIGRATION.md) を参照。

### 神経系の境界 (Pulse / TQL / セマンティック クエリ)

TQL の時間セレクタは変更タイムスタンプを比較するものであり、変更回数を比較するものではありません。
`tql_schema` アクションは、素の `:hot` と `:recently_modified` が共有するウィンドウとデフォルト値を文書化します。深度クエリは正確な定義同一性を保持し、トラバーサル上限を超えた場合は明示的に失敗します。

Pulse のリクエストはスナップショット境界のコンテキストを返します。識別情報・関係性・逆 import コンテキスト・任意のキャッシュ済み LSP エンリッチメントのための SQL 読み取りは、呼び出し元が保有するトランザクションを終了させることなく savepoint を共有します。これは SQL ラウンドトリップやレイテンシの保証を意味するものではありません。

Pulse の Python 逆 import コンテキストは既存のモジュール リゾルバを使用します。これはクロスランゲージのモジュール解決が完全であるという主張ではありません。コメント コンテキストにはコメント抽出込みで再構築されたインデックスが必要です。古いインデックスやコメント抽出に対応していない言語では、空の成功応答ではなく `COMMENTS_NOT_INDEXED` を返します。不要な場合は、文書化された `max_comments` 設定でコメント コンテキストを明示的に省略してください。欠落しているレガシー コミット メッセージ投影は遅延リフレッシュのため `pending` になります。`disabled` の有効化状態は保持されます。レガシーの NULL 有効化状態も、古いメッセージやカウントをクリアすることなく pending になります。有効化されたキャッシュ済みインデックス作成サイクルは、境界付きの有効化リフレッシュを継続します。Pulse は利用不能な有効化状態を `null` として公開し、時間的クエリは不完全な有効化証拠を拒否します。リフレッシュは境界付きバッチを通じて実際の Git 履歴を読み取ります。メッセージ読み取りに失敗した場合は、完了したと主張せず保留中の作業として保持します。

セマンティック クエリには既知の保存済み埋め込みモデルと一貫した次元数が必要です。混在または未知のモデルはエラーとなり、プロバイダのフォールバックはありません。オフライン テストではモデル ダブルを使用します。これは実運用プロバイダの品質を保証するものではありません。

Pulse のバッチ処理は成功したエントリを保持しますが、対象が 1 つでも失敗すると失敗を報告します。TQL は欠落または読み取り不能なインデックスをエラーとして扱い、これは「マッチなしの準備済みインデックス」とは区別されます。公開リクエストの検証は、インデックスを開いたり埋め込みプロバイダを呼び出したりする前に、無効な型や上限値を拒否します。

---

## はじめに

> **Python 3.10 以上が必要です**（確認: `python3 --version`）。必要に応じて [python.org](https://www.python.org/downloads/) からインストールしてください。

### 自動インストール（推奨）

```bash
curl -fsSL https://raw.githubusercontent.com/aimasteracc/tree-sitter-analyzer/main/install.sh | bash
```

`install.sh` は `uv` の有無を確認して未インストールなら自動導入し、Claude Desktop / Claude Code / Cursor / VS Code の設定ファイルを検出して MCP エントリを自動書き込みします。セットアップ後は `tree-sitter-analyzer --doctor` で設定を確認できます。

> **ブートストラップの信頼性について:** 利便性のため、上記コマンドは `uv` が未インストールまたは古い場合、公式 `uv` インストーラを TLS 経由でダウンロード・実行します。このインストーラは可変であり **content-bound ではありません**。TSA はダウンロード前に警告を表示し、インストール後に厳密なバージョン確認を行います。この未検証のブートストラップを避けたい場合は、事前に `uv >= 0.11.0` を手動でインストールするか、次のセキュアなオプトアウトを使用してください（ブートストラップが必要な場合は手動インストール手順を表示して終了します）:
> ```bash
> curl -fsSL https://raw.githubusercontent.com/aimasteracc/tree-sitter-analyzer/main/install.sh \
>   | TSA_DISABLE_UNVERIFIED_UV_BOOTSTRAP=1 bash
> ```

**Claude Code** へワンライナーでインストール:

```bash
claude mcp add tree-sitter-analyzer \
  --env TREE_SITTER_PROJECT_ROOT="$PWD" \
  -- uvx --from "tree-sitter-analyzer[mcp]" tree-sitter-analyzer-mcp
```

エージェントを再起動し、こう伝える: 「`index` ツールを action=status で呼んでください。」
CLI での同等操作 (エージェント不要): `tree-sitter-analyzer --codegraph-status`

> **PyPI / uvx ユーザーへ — スキルのインストール:** `tsa-*` スキルはホイールに同梱されています。一度だけ次のコマンドでインストールしてください:
> ```bash
> tree-sitter-analyzer --install-skills              # ./.claude/skills/ へ (このプロジェクトのみ)
> tree-sitter-analyzer --install-skills-global       # ~/.claude/skills/ へ (全プロジェクト共通)
> ```
> git clone ユーザーはすでに `.claude/skills/` に含まれているため、操作不要です。

[その他のエージェント (Cursor / Copilot / Cline / Continue / Claude Desktop / Roo Code) →](#-対応エージェント)

### クイック インストール

#### 1. 依存関係をインストール

```bash
# uv (必須)。この公式簡易インストーラは可変で content-bound ではありません。
# 代替の手動インストール方法は https://docs.astral.sh/uv/ を参照。
curl -LsSf https://astral.sh/uv/install.sh | sh        # macOS / Linux
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# fd + ripgrep (`search action=batch` の複数クエリ テキスト検索に必須; シンボル検索は SQLite FTS5 を使用しどちらも不要)
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
CLI での同等操作 (エージェント不要): `tree-sitter-analyzer --codegraph-status`

**自分のリポジトリでリゾルバの動作を確認**（インストール不要、最初に再インデックスします）:

```bash
uvx --from tree-sitter-analyzer miswire-audit .
```

クロスランゲージの名前衝突候補を報告し、自分のリポジトリでリゾルバの動作を調査できます。結果は診断情報であり、競合ベンチマークの主張ではありません。

---

## なぜ Tree-sitter Analyzer か

* **構造化出力。** MCP 応答は標準 JSON エンベロープを使用します。ペイロードの挙動はレスポンス契約テストで保護されています。
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
| **JSON 出力** | 全ツール、デフォルト `output_format: "json"` | 標準の構造化レスポンス エンベロープ |
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

### 356 の CLI フラグ

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
tree-sitter-analyzer --uml class                  # Mermaid UML class 図
```

このパッケージにはスタンドアロンのファイル一覧ヘルパーも同梱されています:

```bash
list-files <dir>          # fd 相当のファイル探索
```

`search-content` と `find-and-grep` は develop で削除されました。詳細は
[migration guide](docs/MIGRATION.md) と [`CLI codemap`](docs/CODEMAPS/cli.md) を参照。

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
                            JSON レスポンス エンベロープ
                            (verdict + agent_summary + データ)
                                          ↓
                               MCP クライアント / CLI 消費者
```

8 個の MCP ツールがインデックス済みクエリと直接的なソース解析を提供します。
索引済みのシンボル/コンテキストクエリの前に、`tree-sitter-analyzer --ast-cache --ast-cache-mode index --format json` で AST インデックスを明示的に構築してください。ソース変更後は `index` action=sync でリフレッシュします。索引済みクエリはキャッシュされた AST データを再利用します。自動ウォームアップは個々のツールに固有です。

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
tree-sitter-analyzer --install-skills              # ./.claude/skills/ へ (このプロジェクトのみ)
tree-sitter-analyzer --install-skills-global       # ~/.claude/skills/ へ (全プロジェクト共通)
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

<details>
<summary><b>🐳 Docker</b> (ローカルに Python / uv が無い場合)</summary>

このリポジトリには、ソースから MCP サーバー (stdio トランスポート) をビルドする [`Dockerfile`](Dockerfile) が同梱されています。そのためイメージは常にコミット済みのコードと一致します。

```bash
# 一度だけビルド
docker build -t tree-sitter-analyzer-mcp .

# 現在のリポジトリに対して実行 (サーバーは stdio で MCP を話す; -i は stdin を開いたままにする)
docker run --rm -i --user "$(id -u):$(id -g)" \
  -v "$PWD:/work" -w /work tree-sitter-analyzer-mcp
```

`--user "$(id -u):$(id -g)"` はホストの UID/GID で実行するため、バインド マウントされたリポジトリ下の `.ast-cache/`、意思決定ジャーナル、`edit` による書き込みはすべて root ではなくあなたの所有になります。

MCP クライアント設定 (コンテナ内のプロジェクト ルートはマウント ポイント `/work`):

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "--user", "1000:1000",
        "-v", "/絶対パス/プロジェクト:/work",
        "-w", "/work",
        "-e", "TREE_SITTER_PROJECT_ROOT=/work",
        "tree-sitter-analyzer-mcp"
      ]
    }
  }
}
```
</details>

> ⚠️ `TREE_SITTER_PROJECT_ROOT` は **絶対パス** が必須。サーバーは `SecurityValidator` でエスケープを防ぐセキュリティ境界を強制する。

---

## サポート言語

<!-- BEGIN GENERATED LANGUAGE SUPPORT INVENTORY -->
ランタイムレジストリから生成。**22 言語プラグイン**; 13 は `pipeline_registered`（非 E2E）、3 は `index_admitted`、0 は `call_dispatch_only`、5 個は data/markup、1 個はスキャフォールド。登録は正のクロスファイル束縛を保証しない。
| ティア | 言語 |
|---|---|
| **`pipeline_registered`（パイプライン登録済み、非 E2E）** | C · C++ · C# · Go · Java · JavaScript · Kotlin · PHP · Python · Ruby · Rust · Swift · TypeScript |
| **`index_admitted`（インデックス受け入れ済み）** | Bash · Lua · Scala |
| **`call_dispatch_only`（call dispatch のみ）** |  |
| **単一ファイル解析 (CLI)** | CSS · HTML · Markdown · SQL · YAML |
| **スキャフォールド (プラグイン有 / インデクサー結線待ち)** | JSON |

Lua はインデックス受け入れ済みで call dispatch と resolver slot も持つが、import dispatch とクロスファイル E2E 証拠は未確認。
<!-- END GENERATED LANGUAGE SUPPORT INVENTORY -->

---

## 設定

基本的に設定不要。デフォルトでエージェントに接続して忘れて構わない:

* **出力形式**: JSON。明示的に `output_format: "json"` を指定できます。
* **プロジェクト ルート**: `TREE_SITTER_PROJECT_ROOT` (env, MCP) または `--project-root` (CLI)。
* **キャッシュ場所**: `<project>/.ast-cache/`。安全に削除可 — 自動再構築される。
* **任意**: `TREE_SITTER_OUTPUT_PATH` 大出力の書き込み先。

### スナップショット証拠のプラットフォーム範囲

通常のファイル解析、インデックスの作成/更新、レガシー インデックス経由のクエリは、
認証済みスナップショット アクセスとは別物です。既存の Windows 上の操作パスは、
新しいプライベート WAL スナップショット カーネルを必要としません。これらの操作は
キャッシュを作成・更新できますが、認証済みの読み取り専用アクセスは別の契約に従います。

このスナップショット実装が追加するのは **POSIX 専用のプライベート データベース/WAL 証拠キャプチャ**であり、
記述子相対操作、`O_NOFOLLOW`、安全な外部一時ディレクトリ、source/manifest/projection
チェックの成功を要求します。これは Windows の読み取り専用スナップショット パリティを提供する
ものでも、明示的な `access_mode="read_existing"` 消費者向けの既存の資格ゲートを拡張するもの
でもありません。

Windows のスナップショット認証は develop ベースラインの時点ですでに利用不可であり
（`SECURE_FD_SNAPSHOT_UNSUPPORTED`）、この実装でも引き続き利用できません
（`WAL_PRIVATE_SNAPSHOT_UNSUPPORTED`、`completeness="unknown"`、スナップショット トークンなし）。
これは物理インデックスが空であることや、通常のクエリが無効化されていることを意味するものでは
ありません。新しいキャプチャ パスに対するネイティブ Windows 資格検証は実施されておらず、
ローカルの能力テストはその代替にはなりません。

ファイル単位の `certified_at` 状態は、完全なスナップショット権限の代替にはなりません。
`partial_at` の永続履歴は **本 PR では未実装であり、含まれていません**。
不完全または検証不能な projection は、認証済み消費者を許可できません。

---

## 品質とテスト

| 指標 | 値 |
|---|---|
| テスト通過 | 包括的テストスイート ✅ |
| カバレッジ | [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) |
| 型安全性 | mypy |
| プラットフォーム | macOS · Linux · Windows（通常操作）。スナップショット証拠は上記のとおりより狭い範囲となる |
| Pre-commit ゲート | ruff · bandit · mypy · pyupgrade · detect-secrets · tsa-codemap-sync |

```bash
uv run pytest -q                                # 境界付きのローカル高速ゲート
uv run pytest tests/ -q --timeout=120 -m "not e2e and not network and not benchmark"  # 包括的なローカル スイート
PYTEST_XDIST_AUTO_NUM_WORKERS=1 uv run pytest -q --maxfail=1                  # 高速ゲート、ワーカー1 (CPU負荷を抑える)
PYTEST_XDIST_AUTO_NUM_WORKERS=2 uv run pytest -q --maxfail=1                  # 高速ゲート、ワーカー2 (バランス型)
uv run pytest --lf --maxfail=1                  # 前回失敗したテストだけ再実行
uv run python check_quality.py --new-code-only  # 品質ゲート
```

---

## トラブルシューティング

| 症状 | 修正 |
|---|---|
| `.swift / .kt / .rb / .php / .cs` で `unsupported language` | 現行のサポート対象リリースへ更新してください — この言語欠落は commit `50e99a8f` で修正済みです。extras 区分の文法モジュールはベースインストールに同梱されません。`pip install "tree-sitter-analyzer[swift]"`(または `kotlin`、`ruby`、`php`、`csharp`)で追加してください。 |
| MCP サーバーがクライアントに表示されない | `TREE_SITTER_PROJECT_ROOT` は**絶対パス**である必要があります（例: `$(pwd)` や `/home/user/project`）。相対パスだとサーバーが誤ったディレクトリに対して解決してしまいます。設定編集後はクライアントを再起動してください。`tree-sitter-analyzer --doctor` で確認できます。 |
| `database is locked` | `.ast-cache/index.db` を保持する他プロセスを停止してください。継続する場合は `rm -rf .ast-cache && tree-sitter-analyzer --full-index` を実行してください。 |
| 初回呼び出しが遅い・インデックスがない | 一部のツールは自動でインデックスをウォームアップします。索引済みクエリの前に `--full-index` を事前に実行してください。 |
| エージェントが誤ったツールを選ぶ | `tsa-*` skill (`/tsa-graph`、`/tsa-find` 等) を使用してください — 各 skill は可視ツールを専用ワークフローに制限します。 |

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
* リリース履歴: [CHANGELOG.md](CHANGELOG.md)。
