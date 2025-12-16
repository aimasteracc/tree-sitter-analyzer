## Task 分解（Phase 2）：Batch Extract（多ファイル×多範囲） + Batch Metrics（多ファイル）

### ゴール（設計の要点）

- **`extract_code_section`**: `requests[]` により **複数ファイル×複数範囲**を 1 回で抽出できる
- **`check_code_scale`（AnalyzeScaleTool）**: `metrics_only + file_paths[]` により **複数ファイルのメトリクス**を 1 回で取得できる
- **出力形式**: **デフォルトは TOON**、`output_format="toon"` のとき **JSON詳細（results/sections/content等）を返さない**
- **制限**: 上限超過は **デフォルト fail**、`allow_truncate=true` のときのみ truncate を許可
- **互換性**: 既存の単一入力は維持し、`requests[]` と単一指定は **排他**
- **仕様統一（CLI/API）**: CLI でも同等のバッチ入力を受けられるようにし、内部的に MCP ツール実装を呼び出す（入口差による挙動差を最小化）

---

## 1. 実装タスク（extract_code_section：バッチ）

### 1.1 スキーマ/引数パース

- **対象**: `tree_sitter_analyzer/mcp/tools/read_partial_tool.py`（※実ファイル名は repo に合わせて調整）
- **追加引数**:
  - `requests: list[ { file_path: str, sections: list[{start_line:int, end_line?:int, label?:str}] } ]`
  - `output_format: "toon" | "json"`（デフォルト: `"toon"`）
  - `allow_truncate?: bool`（デフォルト: false）
  - `fail_fast?: bool`（デフォルト: false）
- **排他**:
  - `requests` がある場合、既存の `file_path/start_line/end_line/...` が同時指定なら **ValueError**

### 1.2 ループ実装（多ファイル×多範囲）

- **必須**: 各 `file_path` について `BaseMCPTool.resolve_and_validate_file_path` を用いて
  - resolve
  - security validate（SharedCache活用）
- **チェック**:
  - ファイル存在
  - `max_file_size_bytes` 超過は fail（巨大ファイル拒否）
  - section ごとに start/end の整合性（1-based、範囲外、start>end、など）
- **読み出し**:
  - 既存の「部分抽出」ロジックを流用（行範囲指定）
- **集約**:
  - default: partial_success（失敗は `errors[]` に積む）
  - `fail_fast=true`: 最初の失敗で中断

### 1.3 制限の適用（fail / truncate）

- **上限**（設計値）:
  - `max_files=20`
  - `max_sections_per_file=50`
  - `max_sections_total=200`
  - `max_total_bytes=1MiB`
  - `max_total_lines=5000`
  - `max_file_size_bytes=5MiB`
- **デフォルト挙動**:
  - 上限超過 → **fail**
- **allow_truncate=true**:
  - 返却対象を上限内に収める（超過分の section はスキップ）
  - `truncated=true` と理由をメタ情報に付与

### 1.4 出力（TOON/JSON）

- **output_format デフォルト**: `"toon"`
- **TOON時の返却**:
  - `toon_content` + 最小メタ情報のみ（例: `success/count_files/count_sections/limits/truncated/errors_summary`）
  - **禁止**: `results/sections/content` 等の詳細 JSON を同時に返す
- **JSON時の返却**:
  - 詳細構造（results/sections/content 等）を返す
- **対象**: `tree_sitter_analyzer/mcp/utils/format_helper.py` の既存方針と整合を取る

---

## 2. 実装タスク（check_code_scale：メトリクス一括）

### 2.1 スキーマ追加

- **対象**: `tree_sitter_analyzer/mcp/tools/analyze_scale_tool.py`
- **追加引数**:
  - `file_paths: list[str]`
  - `metrics_only: bool`（true の場合は構造解析をスキップ）
  - `output_format: "toon" | "json"`（デフォルト: `"toon"`）
- **排他/整合性**:
  - 既存の入力と競合する場合は明確なエラー（互換性）

### 2.2 メトリクス計算のバッチ化

- **利用**: `tree_sitter_analyzer/mcp/utils/file_metrics.py::compute_file_metrics`
- **キャッシュ**: SharedCache の metrics cache を活用（content hash key）
- **制限**:
  - `max_files=200`（metrics_only の場合）
  - 並列度: 4（Windows/CI 安定性優先）
- **失敗**:
  - partial_success を基本（`errors[]` へ）
  - `fail_fast` は必要になったら追加（現時点は任意）

### 2.3 出力（TOON/JSON）

- **TOONデフォルト** + **TOON時にJSON詳細を返さない** を徹底

---

## 3. テストタスク

### 3.1 extract_code_section バッチ

- **新規テスト**: `tests/test_mcp/test_read_partial_batch.py`（仮）
- **観点**:
  - 正常: 2ファイル×複数範囲が 1 回で取れる
  - 排他: `requests` と単一指定の同時指定がエラー
  - partial_success: 片方の範囲が不正でも他が返る
  - 上限: `max_files/max_sections_total/max_total_bytes/max_total_lines` 超過で fail
  - allow_truncate: truncate され `truncated=true`
  - **TOONデフォルト**: output_format 省略時に TOON になる
  - **TOON時に詳細JSONが返っていない**（results/content 等が無い）
  - JSON指定時のみ詳細が返る

### 3.2 metrics batch

- **新規テスト**: `tests/test_mcp/test_metrics_batch.py`（仮）
- **観点**:
  - 複数ファイルメトリクス取得ができる
  - キャッシュ（同一内容で再計算されない／content変更で失効）
  - TOONデフォルト + TOON時にJSON詳細なし

---

## 4. ドキュメント/互換性タスク

- **tool schema の説明**を README または tool doc（存在する場合）へ追記
- **既存クライアント互換性**:
  - 既存の単一入力の挙動は変更しない
  - 追加引数は後方互換（未指定でも動く）
  - CLI は単発実装を維持しつつ、バッチは MCP ツール引数と揃える（`--partial-read-requests-*` / `--metrics-only --file-paths/--files-from`）

---

## 5. 完了条件（Definition of Done）

- 設計の受け入れ基準を満たす
- 追加テストがすべてパス
- `output_format` 未指定時に TOON となり、TOON時にJSON詳細が混入しない
- 上限超過時のデフォルトfailと allow_truncate の動作が明確に検証されている


