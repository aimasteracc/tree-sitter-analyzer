# 🌳 Tree-sitter Analyzer

**[English](README.md)** | **日本語** | **[简体中文](README_zh.md)**

AI エージェントのためのコード インテリジェンス: 事前インデックス済みのトークン効率の良い MCP サーバー — **8 MCP ツール** + CLI、100% ローカル動作。

* **即時の構造的回答。** 誰がこれを呼ぶ？何が壊れる？UML 図を生成。1 回の呼び出しで全ての答えが返る — grep ループ不要。
* **トークン バジェット意識。** TOON 出力は bulk/tabular ペイロードを生 JSON 比 ~50-70% 削減（[実測済み不変量](tests/unit/mcp/test_output_cost_invariants.py); RFC-0012 で代表的な決定ツールにて 0.52× を計測）。
* **安全な編集。** `safe_to_edit` + `change_impact` + 制約 DSL が全ての変更を事前にゲート; コール グラフの[異言語誤結線 ≈0](benchmarks/codegraph_compare/MISWIRE-AUDIT-EXAMPLES.md)。

> **100% ローカル** とは、インデックスがリポジトリ内の `.ast-cache/` に保存され、テレメトリや外部呼び出しが一切ないことを意味します。全 MCP レスポンスおよび CLI 出力は SQLite+FTS5 キャッシュからローカルで生成されます。

> v1.x からの移行は [docs/MIGRATION.md](docs/MIGRATION.md) を参照。

[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-18493%20passed-brightgreen.svg)](#-品質とテスト)
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

エージェントを再起動し、こう伝える: 「`index` ツールを action=status で呼んでください。」

> **PyPI / uvx ユーザーへ — スキルのインストール:** 13 個の `tsa-*` スキルはホイールに同梱されています。一度だけ次のコマンドでインストールしてください:
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

**自分のリポジトリで correctness の差を 1 コマンドで確認**(インストール不要・CodeGraph 不要、最初に再インデックスします):

```bash
uvx --from tree-sitter-analyzer miswire-audit .
```

name-only な code index(多くのツールが採る設計)なら、何件の呼び出しを言語をまたいで誤結線するか(例: Python の `sorted()` → Swift の func)vs TSA が何件かを表示します。実証: [HuggingFace `tokenizers`](benchmarks/codegraph_compare/MISWIRE-AUDIT-EXAMPLES.md) で name-only は **1,259 件**(JS `tokenize()` → Rust 等)、TSA は **0**。ruff **7557×**、polars **9016×**。単一言語リポ(gin/Go)は両方 **0** で誤検知なし。

---

## なぜ Tree-sitter Analyzer か

* **デフォルトでトークン効率**。全 MCP ツール応答は **TOON** — 表形式 JSON バリアントで、生 JSON 比 ~50-70% のペイロード削減（[実測済み不変量](tests/unit/mcp/test_output_cost_invariants.py); RFC-0012 で 0.52× を計測）。
* **Verdict エンベロープ**。すべての応答に `verdict: SAFE | CAUTION | UNSAFE | INFO | WARN | ERROR | NOT_FOUND` が付き、オーケストレーターは再プロンプトなしで結果ごとに分岐可能。
* **プロジェクト健全性 A-F グレーディング**。他のオープンソース ツールには無い — サイズ / 複雑度 / カバレッジ / 重複 / 依存 / 構造 / git-ホットスポットの 7 次元でプロジェクト全体を採点。
* **13 のキュレーション済みワークフロー (Skills)**。「シンボル検索」「コール チェーン追跡」「健全性評価」「リファクター前の安全チェック」「PR レビュー」などの典型シナリオに対応するツール サブセットを事前パッケージ化。
* **5 層の安全保護**。`safe_to_edit` + `modification_guard` + 制約 DSL + `change_impact` + verdict エンベロープ — エージェントが手を入れる前にリスクを *知る* よう設計。
* **CodeGraph の厳密な CLI 上位互換・高速インデックス・一発クエリ DSL** ── 正直なコスト比較は[下記](#codegraph-との比較)。

---

## 主要機能

### 事前インデックス コード インテリジェンス (CodeGraph 相当 + 上位互換)

| 能力 | TSA ツール | ステータス |
|---|---|---|
| シンボル検索 (FTS5 + **BM25 ランク付け**) | `search` action=symbol | **優位** — 関連スコア順にソート |
| go-to-def / find-refs / コール階層を 1 回の呼び出しで | `nav` action=navigate | PRIMARY エントリポイント |
| 関連シンボル N 個のソース + 関係マップを一括取得 | `structure` action=explore | 同等 |
| 関数レベル blast radius + リスク スコア | `nav` action=impact | 同等 + リスク スコア |
| X を呼ぶのは誰 / X は何を呼ぶ | `nav` action=callers / action=callees | 同等 |
| インデックス健全性 (+ エッジ数) | `index` action=status | **優位** — `total_edges` でグラフ密度を把握 |
| 事前構築コール グラフ キャッシュ | `index` action=auto / action=full / action=sync | 同等 |
| 変更の影響を受けるテスト (CLI) | `--affected FILE...` | 同等 |

### Tree-sitter Analyzer 独占機能

| 能力 | TSA ツール | 説明 |
|---|---|---|
| **BM25 ランク付き検索** | 全検索ツール | min-max 正規化 relevance_score (最適=1.0 / 最弱=0.0); DSL で sort(by='confidence') |
| **セマンティック検索 (BM25 事前フィルタ)** | `search` action=chain (`semantic()` DSL) | BM25 で 40k シンボル→約 400 に絞り込んでコサイン再ランク |
| **プロジェクト A-F 健全性グレーディング** | `health` action=project | 7 次元 (サイズ/複雑度/依存/カバレッジ/重複/構造/git)、競合に対応無し |
| **TOON 出力** | 全ツール、デフォルト `output_format: "toon"` | 50-70% トークン節約 |
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
| **1 回のファイル把握** | `project` action=smart | 健全性 + エクスポート + 依存 + 編集リスクを 1 コールで (3-4 コールを代替) |
| **アーキテクチャ意思決定ジャーナル** | `project` action=journal | セッション間で推論を永続化 — 他に提供しているツールは無い |

### Skills (13 のキュレーション済みワークフロー)

CodeGraph には skill システムが存在しない。本ツールは `.claude/skills/tsa-*/` 下に 13 個を提供:

`tsa-landing`、`tsa-find`、`tsa-graph`、`tsa-structure`、`tsa-deps`、`tsa-index`、`tsa-health-watch`、`tsa-edit-safety`、`tsa-edit-then-verify`、`tsa-constraints`、`tsa-pr-review`、`tsa-refactor-queue`、`tsa-temporal`。

各 skill は `allowed-tools` ツール サブセット + 手順レシピ + 決定面スキーマを同梱し、エージェントは 8 個のツールから毎回選別する必要が無い。

### 287 の CLI フラグ

CodeGraph の CLI の厳密な上位互換。主なもの:

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

## CodeGraph との比較

### コールグラフの正確さ — CodeGraph が誤配線する箇所を TSA は正しく解決

トークンコストは一つの軸にすぎません。コードインテリジェンスツールの*第一の*仕事は**正しいグラフ**です。

**このリポジトリでの両ツール ライブ インデックスの対決**（呼び出し元言語と callee 言語が異なる全コール エッジをカウント — 構造的に言語またがり誤結線; [再現可能](benchmarks/codegraph_compare/REPORT-v1.21.0.md)):

| ツール | 異言語誤結線 | 総コール エッジ | 割合 |
|---|---|---|---|
| CodeGraph | **745** | 38,103 | 1.96 % |
| **Tree-sitter Analyzer** | **6** | 114,160 | **0.005 %** |

**異言語正確性で約 390× クリーン、かつ 3× 多くのコール エッジを解決。** CodeGraph の誤結線は 19+ 言語ペアにわたる(python→swift **408**、python→typescript 195、python→ruby 81、…); TSA の 6 件は全て単語 1 つの Java メソッド名による `java→python/php`。

> **この表を信じないで — 自分のリポジトリで実行してください (CodeGraph インストール不要):**
> ```bash
> uvx --from tree-sitter-analyzer miswire-audit .
> ```
> コードをインデックスし、name-only リゾルバ(多くのインデックスが採用する設計)なら何件のコール エッジを言語をまたいで誤結線するか vs TSA が何件かを表示します — 問題のあるエッジ一覧付き(`Python sorted() → Swift func at file:line`)。`--card` でシェア可能なスコアカードを出力。
>
> **実際の実行例:** [HuggingFace `tokenizers`](benchmarks/codegraph_compare/MISWIRE-AUDIT-EXAMPLES.md) (Rust+Python+JS+TS) で name-only リゾルバなら **1,259** 件のコール エッジを誤結線(JS `tokenize()` → Rust def を含む) — TSA: **0**。単一言語リポ(`gin`、Go)では両方 **0** — 誤検知なし。[さらなる例 →](benchmarks/codegraph_compare/MISWIRE-AUDIT-EXAMPLES.md)

具体的に:

| 呼び出し(Python `_resolve_entry_points` / `build_response`) | CodeGraph | TSA |
|---|---|---|
| `sorted()`(Python 組み込み) | ❌ callee = **`tests/golden/corpus_swift.swift` の Swift `func sorted`**(リポジトリ全体で **299** Python 関数の callee として配線) | ✅ `builtin` — 言語をまたぐ edge を作らない |
| `fts_search()` / `fts_search_ranked()` | ❌ 実メソッドではなく**テストモック**(`FallbackCache`)に束縛 | ✅ source メソッド(`_ast_cache_query.py` / `ast_cache.py`)に解決 |

TSA の per-language リゾルバは **13 言語** (Python · Java · Go · JS · TS · C · C++ · Rust · C# · Kotlin · Ruby · PHP · Swift) にわたって全ての束縛を**言語ファミリ**でゲートし、全解決パスで非テスト呼び出し元に対して**テスト専用定義を降格**します。Python 関数が *Swift メソッドを呼ぶ*、あるいは本番コードの呼び出しがテストモックを指す、というのは誤った構造データです。

#### 正確かつ完全 — コール エッジの 96.3% を分類

未知エッジが多い正確なグラフは半分のグラフにすぎません。TSA の解決カスケードは現在**コール エッジの 96.3%** を分類(83.9% から向上)し、**ゼロ**の異言語またはテスト シャドウ誤結線 — 全ての向上はプロジェクトが互換言語のそのシンボルを所有しないことでゲートされ、シャドウは常に保護されます:

| リゾルバ ティア | 解決対象 | ソース |
|---|---|---|
| binding cascade | local / self / import / unique-method / single-global | RFC-0002 |
| stdlib **メソッド** 名 (`write_text`、`strip`、`items`) | `str` / `Path` / `dict` / `re` / `argparse` メソッド → `stdlib` | [RFC-0004](rfcs/0004-stdlib-method-resolution.md) |
| external **ライブラリ** メソッド (`raises`、`given`、`MagicMock`) | pytest / hypothesis / mock → `external` | [RFC-0005](rfcs/0005-external-method-resolution.md) |

残りの ~4% `unknown` は genuinely 解決不能なダイナミック ディスパッチ(`BaseTool.execute()`)、コンストラクタ、曖昧な同名プロジェクト メソッドが支配 — 静的解析の偽陽性の床であり、推測するのではなく正直に残されています。

> **マルチ言語対応。** 異言語安全な解決はもはや Python 専用ではありません。per-language **リゾルバ レジストリ** ([RFC-0010](rfcs/0010-resolver-language-registry.md)) が各言語に独自の分類カスケードを与え、言語ファミリでゲートして束縛が非互換言語にまたがらないようにします。言語の追加は新しいリゾルバ ファイル 1 つ (RFC-0010) とわずかなコール エクストラクション配線で完了します。

### TSA が優る点

- **インデックス構築速度。** commit 後の冗長な edge-refresh パスを除去し、django のコールド index(約 2,950 ファイル)を **181 秒 → 97 秒(−46%)**に短縮。大規模リポジトリほど効果大。変更なしファイルの再 index は content-hash ルックアップ。
- **厳密な CLI 上位互換。** すべての MCP ツールに CLI 等価物がある(CodeGraph の CLI はより薄い)。*振る舞い*のデフォルト(ランキング・上限・切り詰め)は両サーフェスで同期。出力フォーマットだけは意図的に分岐 ── MCP は TOON(エージェント向けトークン効率)、CLI は JSON(人間/`jq` 向け)。
- **一発クエリの表現力。** jQuery 風 chain DSL ── `search('X').callees(depth=2).explore(include_code=true).answer(compact=true)` ── がフロー全体のサブグラフ + source を 1 コールで返す。JS 風の `true`/`false` でエージェントが自然に書ける。
- **構造化 + トークン意識の出力。** MCP は TOON デフォルト(JSON より 50–70% 小)、per-call 切り詰めヒント、全ランキングで一貫した test ファイル降格。
- **広さ。** ヘルス採点、safe-to-edit / change-impact ゲート、13 の curated Skills、広い言語対応。

### トークン コストについて — 修正したベンチマーク

> **訂正 (2026-06)。** 以前のこの節は「コスト中央値 −11% で CodeGraph に勝つ」と主張していました。そのベンチマークにはハーネスのバグがあり、TSA アームの MCP サーバが明示的なプロジェクトルート無しで起動され、対象リポジトリではなく **tree-sitter-analyzer 自身のソース**を解析していたため、数値は無意味でした。バグは修正済み(ハーネスは `--project-root` を渡す)。誇張した主張は撤回し、正直な比較を以下に示します。

トークン コストは CodeGraph が優位だった唯一の軸でした。[RFC-0006](rfcs/0006-context-progressive-disclosure.md) プログレッシブ ディスクロージャにより、このギャップの大半が解消されました: `nav context` が **リーン デフォルト**を返すようになり、フラットなノード/エッジ グラフはオプトイン `include_graph=true` の後ろへ移動。このリポジトリでの計測 (4 代表的クエリ、TOON):

| コンテキスト ペイロード | 文字数 |
|---|---|
| TSA デフォルト、RFC-0006 前 | ~13,900 |
| **TSA デフォルト、後（リーン）** | **~6,600 (−53%)** |
| TSA `include_graph=true` (フル、オプトイン) | ~13,900 |
| CodeGraph ベースライン | ~4,400 |

支配的なコンテキスト呼び出しが **CodeGraph の ~2.9× から ~1.5× に縮小**。

修正後のハーネス(Claude Sonnet、gin + django、MCP アーム、エラーなし)でのタスクあたり**中央値コスト**:

| アーム | 中央値コスト（RFC-0006 前） | tool calls | file reads |
|---|---|---|---|
| CodeGraph MCP | **約 $0.27** | 7 | 2 |
| Tree-sitter Analyzer MCP | 約 $0.44 | 7 | 1 |
| MCP なし (grep/read) | 約 $0.34 | 14 | 7 |

### Reactive push + edge-kind 内訳 — CodeGraph にできない 2 つのこと

- **Reactive push / サブスクリプション ([RFC-0001](rfcs/0001-reactive-push.md)、実装済み)。** `search action=subscribe` が Hyphae セレクターを登録して `tsa://hyphae/{selector}` MCP リソース URI を返します。対象コードが変更されるとサーバが resource-updated 通知を発行 — エージェントはポーリングではなくリソースを再読します。CodeGraph にプッシュやサブスクリプション チャネルはありません。
- **`index action=status` の `edges_by_kind`。** ステータスが per-edge-kind カウント(calls / extends / implements / imports …)を返し、単純な `total_edges` ではありません。CodeGraph は平坦な合計のみを提供します。

両ツールがインデックス済みの任意リポジトリで修正を再現:

```bash
# CodeGraph: 言語またぎ / test-shadow の callee を返す
#   (例: `sorted` → corpus_swift.swift, `fts_search` → テストモック)
# リゾルバ修正後の TSA: 言語的に正しく、source を優先
tree-sitter-analyzer --callees _resolve_entry_points --format json
```

> コスト数値の再現: `uv run python benchmarks/codegraph_compare/run.py phase full-warm --repos gin,django`。原始エンベロープとハーネス修正は同ディレクトリ。

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

検証: `claude mcp list`。13 の `tsa-*` skills は `.claude/skills/` から自動検出される。

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

21 言語プラグイン; 13 はインデクサーへ完全統合 (シンボル + コール グラフ) + 2 はシンボル インデックス済み (コール グラフ配線待ち) + 5 個 (data/markup) は CLI 単一ファイル パス + 1 個スキャフォールド (プラグインあり、インデクサー配線待ち)。bash と scala は v1.22.0 で昇格; 2026-05-24 のパッチで数か月間サイレントにスキップされていた Swift / Kotlin / Ruby / PHP / C# がアンブロック。

| ティア | 言語 |
|---|---|
| **完全インデックス + シンボル + コール グラフ** | Python · Java · JavaScript · TypeScript · Go · Rust · C · C++ · C# · Swift · Kotlin · Ruby · PHP |
| **完全インデックス + シンボル (コール グラフ配線待ち)** | Bash · Scala |
| **単一ファイル解析 (CLI)** | HTML · CSS · Markdown · SQL · YAML |
| **スキャフォールド (プラグイン有 / インデクサー結線待ち)** | json |

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
| テスト通過 | 18,493 ✅ |
| カバレッジ | [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) |
| 型安全性 | 100% mypy |
| プラットフォーム | macOS · Linux · Windows |
| Pre-commit ゲート | ruff · bandit · mypy · pyupgrade · detect-secrets · tsa-codemap-sync |

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
