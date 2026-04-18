# v1.6.1.x から v1.9.3 への仕様変更適用 - 実行サマリー

## ⚠️ アーキテクチャ互換性重視

**重要な更新**: v1.9.3の改善されたアーキテクチャを尊重し、後退を避けます。

**主要な発見**:
- ✅ **v1.6.1.1ロギング機能**: 既にv1.9.3に完全統合済み (`utils/logging.py`)
- ✅ **v1.9.3アーキテクチャ**: 大幅に改善 (プラグイン、フォーマッタ、セキュリティ)
- 📋 **アプローチ**: **仕様変更のみ**を適用、古いコードを直接コピーしない
- 🎯 **目標**: v1.9.3のアーキテクチャを劣化させずに欠けている機能を追加

詳細は `ARCHITECTURE_COMPATIBILITY.md` を参照。

## 🎯 分析結果の概要

v1.6.1.1 から v1.6.1.4 のリリースブランチを詳細に分析した結果、**現在の v1.9.3 に欠けている2つの重要な機能仕様**を特定しました。

### ❌ 欠けている機能

1. **ストリーミングファイル読み取り** (v1.6.1.4)
   - パフォーマンス: 30秒 → 200ms未満 (**150倍高速化**)
   - メモリ効率: ファイル全体を読み込まずに必要な行のみ処理
   - 影響範囲: `extract_code_section` MCPツール

2. **OutputFormatValidator** (v1.6.1.3)
   - 相互排他的パラメータの検証 (total_only, count_only_matches等)
   - 多言語エラーメッセージ (英語・日本語)
   - LLM向けトークン効率ガイダンス
   - **ツール説明の大幅改善**: 推奨ワークフロー、トークン効率比較、パラメータ別ガイダンス
   - 影響範囲: `search_content` MCPツール

### ✅ すでに実装済み

- **v1.6.1.1**: ロギング制御の改善 → ✅ **v1.9.3の`utils/logging.py`に完全統合済み**
  - 全ての環境変数サポート (`TREE_SITTER_ANALYZER_ENABLE_FILE_LOG`等)
  - ファイルログ、カスタムディレクトリ、レベル制御
  - **追加作業不要**
- **v1.6.1.2**: バージョン同期のみ → 該当なし

## 📊 技術的な詳細

### 問題1: 現在のfile_handler.pyの性能問題

**現在のコード** (v1.9.3 の line 130):
```python
def read_file_partial(...):
    # ファイル全体を安全に読み込む
    content, detected_encoding = read_file_safe(file_path)
    
    # 行に分割
    lines = content.splitlines(keepends=True)
```

**問題点**:
- 100MBのファイルで30秒以上かかる
- ファイル全体をメモリに読み込むため、メモリ使用量が大きい
- ユーザー体験が悪い

**v1.6.1.4の解決策**:
```python
import itertools
from .encoding_utils import read_file_safe_streaming

def read_file_partial(...):
    # ストリーミングアプローチを使用
    with read_file_safe_streaming(file_path) as f:
        # itertools.islice で効率的に行を選択
        selected_lines_iter = itertools.islice(f, start_idx, end_idx + 1)
        selected_lines = list(selected_lines_iter)
```

**改善**:
- **150倍高速**: 30秒 → 200ms未満
- **メモリ効率**: O(ファイルサイズ) → O(要求行数)
- **後方互換性**: 100% (同じ関数シグネチャ)

### 問題2: 出力フォーマットパラメータの検証とガイダンスがない

**現在のsearch_content_tool.py**:
- 5つの相互排他的パラメータ (`total_only`, `count_only_matches`, `summary_only`, `group_by_file`, `suppress_output`)
- **検証なし** → LLMが競合するパラメータを指定できる → 混乱する結果
- **簡素なツール説明** → LLMがどのフォーマットを選ぶべきか分からない

**v1.6.1.3の解決策**: OutputFormatValidator + 改善されたツール説明

**主な機能**:
```python
class OutputFormatValidator:
    OUTPUT_FORMAT_PARAMS = {
        "total_only",        # ~10トークン (最も効率的)
        "count_only_matches", # ~50-200トークン
        "summary_only",       # ~100-500トークン
        "group_by_file",      # ~200-1000トークン
        "suppress_output"     # 0トークン (キャッシュのみ)
    }
    
    def _detect_language(self) -> str:
        """環境から優先言語を検出 (LANG環境変数とlocale)"""
        lang = os.environ.get('LANG', '')
        if lang.startswith('ja'):
            return 'ja'
        return 'en'
    
    def _get_error_message(self, conflicting: list[str]) -> str:
        """ローカライズされたエラーメッセージ"""
        if self._detect_language() == 'ja':
            return f"""出力フォーマットエラー: 相互排他的なパラメータが同時に指定されています: {', '.join(conflicting)}
            
以下のパラメータは同時に使用できません:
- total_only: マッチ総数のみ表示 (~10トークン、最も効率的)
- count_only_matches: ファイル別マッチ数 (~50-200トークン)
- summary_only: マッチの簡潔なサマリー (~100-500トークン)
- group_by_file: ファイルごとにグループ化 (~200-1000トークン)
- suppress_output: 出力を抑制しキャッシュのみ (0トークン)

1つのパラメータのみを選択してください。"""
        else:
            return "Output format error: Mutually exclusive parameters..."
```

#### 改善されたツール説明

v1.6.1.3では、ツールの説明も大幅に改善されました:

**1. メイン説明にトークン効率ガイドを追加**:
```
⚡ IMPORTANT: Token Efficiency Guide

📋 RECOMMENDED WORKFLOW (Most Efficient Approach):
1. START with total_only=true (~10 tokens)
2. IF more detail needed, use count_only_matches=true (~50-200 tokens)
3. IF context needed, use summary_only=true (~500-2000 tokens)
4. ONLY use full results when specific review required (~2000-50000+ tokens)

⚡ TOKEN EFFICIENCY COMPARISON:
- total_only: ~10 tokens (最も効率的)
- count_only_matches: ~50-200 tokens
- summary_only: ~500-2000 tokens
- group_by_file: ~2000-10000 tokens
- Full results: ~2000-50000+ tokens

⚠️ MUTUALLY EXCLUSIVE: 一度に1つのパラメータのみ使用可能
```

**2. パラメータレベルのガイダンス**:
各出力フォーマットパラメータに ⚡ EXCLUSIVE マーカーと RECOMMENDED ユースケースを追加
```json
"total_only": {
    "description": "⚡ EXCLUSIVE: Return only total match count (~10 tokens - MOST EFFICIENT). RECOMMENDED for: Count validation, filtering decisions, existence checks. Cannot be combined with other output formats."
}
```

**3. ベストプラクティスドキュメント**:
- 新規ファイル: `.roo/rules/search-best-practices.md` (250行)
- ワークフロー例とJSON
- トークン効率比較表
- 実用的な使用シナリオ

**効果**:
- LLMが最適な出力フォーマットを選択できる
- 不必要なトークン使用を削減
- パラメータ競合を事前に防止
- 予測可能な動作で改善されたUX

## 📋 作成したドキュメント

完全なOpenSpec提案書を作成しました:

### 1. `analysis.md` - 詳細分析
- v1.6.1.1 〜 v1.6.1.4の各バージョン分析
- 現在のv1.9.3とのギャップ分析
- コード比較 (現在 vs v1.6.1.x)
- 影響評価とリスク分析
- 依存関係の確認

### 2. `proposal.md` - 実装提案
- ユーザー価値の明確化
- 技術的アプローチの詳細
- フェーズ別実装計画
- 受け入れ基準
- 実装タイムライン (3日間)
- リスクと軽減策
- 代替アプローチの検討

### 3. `tasks.md` - 実装タスク
- **全10タスク**に分解
- 各タスクの詳細な受け入れ基準
- コード例とテストコマンド
- 依存関係の明確化
- 優先度レベル (HIGH/MEDIUM/LOW)
- 推定時間: 合計19時間 (~2.5日)

## 🚀 次のステップ

### フェーズ1: ストリーミングファイル読み取り (優先度: HIGH)
```bash
# Task 1.1: encoding_utils.py に read_file_safe_streaming() を追加 (2時間)
# - コンテキストマネージャーの実装
# - 最初の8KBからエンコーディング検出
# - エンコーディングキャッシュの活用

# Task 1.2: file_handler.py の read_file_partial() をリファクタリング (3時間)
# - itertools.islice() を使用した効率的な行選択
# - ストリーミングアプローチに置き換え
# - 後方互換性の維持

# Task 1.3: パフォーマンステストの移植 (2時間)
git show 8e1500e:tests/test_streaming_read_performance.py > tests/test_streaming_read_performance.py
git show 8e1500e:tests/test_streaming_read_performance_extended.py > tests/test_streaming_read_performance_extended.py
pytest tests/test_streaming_read_performance*.py -v
```

### フェーズ2: OutputFormatValidator (優先度: MEDIUM)
```bash
# Task 2.1: output_format_validator.py を作成 (3時間)
git show 3f44ac6:tree_sitter_analyzer/mcp/tools/output_format_validator.py > \
    tree_sitter_analyzer/mcp/tools/output_format_validator.py

# Task 2.2: search_content_tool.py と統合 (2時間)
# - validate_arguments() に検証ロジックを追加
# - エラーメッセージの表示

# Task 2.3: LLMガイダンステストの移植 (2時間)
git show 3f44ac6:tests/test_llm_guidance_compliance.py > tests/test_llm_guidance_compliance.py
git show 3f44ac6:tests/test_search_content_description.py > tests/test_search_content_description.py
pytest tests/test_llm_guidance*.py tests/test_search_content_description.py -v
```

### フェーズ3: 統合と品質保証 (優先度: HIGH)
```bash
# Task 3.1: 全テストスイートの実行 (1時間)
pytest tests/ -v --cov=tree_sitter_analyzer --cov-report=term-missing

# Task 3.2: パフォーマンスベンチマーク (2時間)
# - 大規模ファイルの読み取り時間測定
# - メモリ使用量のプロファイリング
# - 結果の文書化

# Task 3.3: ドキュメント更新 (1時間)
# - CHANGELOG.md にエントリー追加
# - パフォーマンス指標の更新

# Task 3.4: コードレビューとクリーンアップ (1時間)
black tree_sitter_analyzer/
isort tree_sitter_analyzer/
mypy tree_sitter_analyzer/
pylint tree_sitter_analyzer/
```

## 📈 期待される効果

### パフォーマンス
- ✅ 大規模ファイル読み取り: **30秒 → 200ms未満** (150倍改善)
- ✅ メモリ使用量: **O(ファイルサイズ) → O(要求行数)**
- ✅ 小規模ファイルオーバーヘッド: **<10ms**

### ユーザー体験
- ✅ 明確なエラーメッセージ (英語・日本語)
- ✅ トークン効率ガイダンス (LLM向け)
- ✅ 競合パラメータの自動検出
- ✅ 最適なフォーマット選択の支援

### 品質
- ✅ テストカバレッジ: **>80%** 維持
- ✅ テスト合格率: **100%** (3,370+テスト)
- ✅ 後方互換性: **100%** (破壊的変更なし)

## ⚠️ リスクと軽減策

### リスク1: ストリーミングがエッジケースで失敗
- **可能性**: 低
- **影響**: 中
- **軽減策**: v1.6.1.4の包括的なテストカバレッジ、フィーチャーフラグで旧実装へのフォールバック

### リスク2: ロケール検出が一部環境で失敗
- **可能性**: 中
- **影響**: 低
- **軽減策**: LANG環境変数がない場合は英語にフォールバック、locale モジュールの try/except

### リスク3: 小規模ファイルでのパフォーマンス低下
- **可能性**: 低
- **影響**: 低
- **軽減策**: 小規模ファイル(<1MB)のベンチマーク、エンコーディング検出キャッシュ、必要に応じて適応戦略

## 📝 実装状況

### 完了 ✅
- [x] v1.6.1.1 〜 v1.6.1.4 の git 履歴分析
- [x] 現在の v1.9.3 コードとの比較
- [x] **アーキテクチャ互換性分析** (`ARCHITECTURE_COMPATIBILITY.md`)
- [x] v1.6.1.1がv1.9.3に既に統合されていることを確認
- [x] 欠けている機能の特定（仕様レベル）
- [x] 詳細分析ドキュメント作成 (`analysis.md`) - アーキテクチャ考慮版
- [x] 実装提案書作成 (`proposal.md`) - 仕様変更のみ
- [x] タスク分解ドキュメント作成 (`tasks.md`) - 14時間版
- [x] ツール説明の更新 (search_content_tool.py) - 既存
- [x] ベストプラクティスドキュメント追加 (.roo/rules/search-best-practices.md) - 既存

### 未完了 ⏳
- [ ] ストリーミングファイル読み取りの実装 (5時間)
- [ ] OutputFormatValidator の実装 (5時間)
- [ ] 統合テストと品質保証 (4時間)

## 🆕 追加発見事項

### v1.6.1.3からの追加発見 (コミット `3f44ac6`)

v1.6.1.3のコミットを詳細にレビューした結果、**6つの欠落コンポーネント**を発見しました:

#### 欠けているテストファイル
1. **`tests/test_llm_guidance_compliance.py`** (170行) ❌
   - 相互排他的パラメータ検証テスト
   - トークン効率ガイダンス検証
   - 多言語エラーメッセージテスト

2. **`tests/test_search_content_description.py`** (217行) ❌
   - MCPツール説明の検証
   - パラメータ説明の完全性チェック
   - LLMガイダンスフォーマット検証

#### 欠けているドキュメント
3. **`docs/mcp_fd_rg_design.md`** (132行) ❌
   - fdとrgツールの詳細設計
   - アーキテクチャ決定
   - パフォーマンス最適化戦略

4. **`openspec/specs/llm-guidance/spec.md`** (201行) ❌
   - LLMガイダンス機能の正式仕様
   - トークン効率の要件とシナリオ
   - MCPツールとの統合パターン

5. **`openspec/specs/mcp-tools/spec.md`** (186行) ❌
   - MCPツール仕様
   - ツールインターフェース要件
   - パラメータ検証標準

#### コード品質改善
6. **`tree_sitter_analyzer/mcp/utils/file_output_manager.py`** - スレッド安全性 ⚠️
   - **現在**: 警告メッセージのスレッド同期なし
   - **v1.6.1.3**: `_warning_lock = threading.Lock()` によるスレッド安全な操作
   - **問題**: 複数スレッドが警告状態にアクセスする際の競合状態
   - **修正**: `with FileOutputManager._warning_lock:` でクリティカルセクションをラップ
   - **利点**: 並行シナリオでの重複警告メッセージを防止

### v1.6.1.4からの追加発見 (コミット `8e1500e`) - **NEW**

v1.6.1.4のコミットを詳細にレビューした結果、**さらに6つの欠落コンポーネント**を発見しました:

#### 欠けているテストファイル
7. **`tests/test_streaming_read_performance.py`** (163行) ❌
   - ストリーミング読み取り基本機能テスト
   - メモリ効率検証
   - エンコーディング検出テスト
   - 空ファイルとEOF処理テスト

8. **`tests/test_streaming_read_performance_extended.py`** (232行) ❌
   - 大規模ファイルパフォーマンステスト (100万行+)
   - カラム範囲とストリーミングの組み合わせ
   - 異なるエンコーディングタイプテスト
   - 後方互換性検証
   - パフォーマンス劣化検出

#### 欠けているOpenSpecドキュメント
9. **`openspec/changes/refactor-streaming-read-performance/design.md`** (84行) ❌
   - 問題の背景とコンテキスト (30秒のファイル読み取り問題)
   - 技術的設計決定の詳細
   - 代替アプローチの検討 (itertools.islice vs mmap vs 手動カウント)
   - 実装スケッチとコード例
   - パフォーマンス目標 (30秒 → <200ms)

10. **`openspec/changes/refactor-streaming-read-performance/proposal.md`** (18行) ❌
    - 変更が必要な理由
    - 変更内容
    - 影響を受けるコンポーネント

11. **`openspec/changes/refactor-streaming-read-performance/specs/mcp-tools/spec.md`** (23行) ❌
    - パフォーマンス要件
    - API互換性要件

12. **`openspec/changes/refactor-streaming-read-performance/tasks.md`** (54行) ❌
    - v1.6.1.4での元のタスク分解
    - 検証ステップ

**発見の重要性**:
- **テストカバレッジ**: 395行の包括的なテストが欠落
- **設計根拠**: 84行の設計ドキュメントにより技術的決定の理由が明確
- **OpenSpec完全性**: 完全なOpenSpec変更提案構造 (design, proposal, specs, tasks)
- **保守性**: 将来の開発者が設計の意図を理解可能

### 総計
- **v1.6.1.3から**: 6コンポーネント (387行のテスト + 519行のドキュメント + スレッド安全性)
- **v1.6.1.4から**: 6コンポーネント (395行のテスト + 179行のOpenSpecドキュメント)
- **合計**: **12ファイル、約1,480行のコード/ドキュメント/テスト**

## 📊 更新された実装計画

### フェーズ1: ストリーミングファイル読み取り (8時間) - **UPDATED**
#### タスク1.1: encoding_utils.pyにread_file_safe_streaming()を追加 (2時間)
#### タスク1.2: file_handler.pyのread_file_partial()をリファクタリング (3時間)
#### タスク1.3: ストリーミングパフォーマンステストの移植 (2時間)
#### タスク1.4: v1.6.1.4からOpenSpecドキュメントを移植 (1時間) - **NEW**

### フェーズ2: OutputFormatValidator (7時間)

### フェーズ3: QA & ドキュメント (5時間)

### フェーズ4: v1.6.1.3からの追加改善 (4時間)

#### タスク4.1: file_output_manager.pyのスレッド安全性追加 (1時間)
```python
import threading

class FileOutputManager:
    _warning_lock = threading.Lock()  # スレッド安全なロック追加
    
    @staticmethod
    def _should_show_warning(warning_key: str, max_age_seconds: int = 3600) -> bool:
        with FileOutputManager._warning_lock:  # スレッド安全なアクセス
            # ... クリティカルセクション ...
```

#### タスク4.2: LLMガイダンステストの移植 (2時間)
- `test_llm_guidance_compliance.py` - 相互排他検証、多言語、トークン効率
- `test_search_content_description.py` - ツール説明検証、ガイダンス形式

#### タスク4.3: 設計・仕様ドキュメントの追加 (1時間)
- `docs/mcp_fd_rg_design.md` - fd/rgツールアーキテクチャ
- `openspec/specs/llm-guidance/spec.md` - LLMガイダンス要件
- `openspec/specs/mcp-tools/spec.md` - MCPツール仕様

## 📈 更新された期待効果

### 元の期待効果 (変更なし)
- ✅ 大規模ファイル読み取り: **30秒 → 200ms未満** (150倍改善)
- ✅ メモリ使用量: **O(ファイルサイズ) → O(要求行数)**
- ✅ 明確なエラーメッセージ (英語・日本語)
- ✅ トークン効率ガイダンス

### 追加の期待効果 (新規)
- ✅ **スレッド安全性**: 並行実行時の競合状態を防止
- ✅ **包括的テスト**: 170+217行の新規テストでカバレッジ向上
- ✅ **完全なドキュメント**: 設計決定と仕様の明確化
- ✅ **保守性向上**: 将来の変更がより安全に

## 📝 実装状況

## 🎯 推奨される実行順序

1. **まず実装提案をレビュー**: `openspec/changes/apply-v1-6-1-x-fixes/proposal.md`
2. **タスク詳細を確認**: `openspec/changes/apply-v1-6-1-x-fixes/tasks.md` (全13タスク)
3. **フェーズ1から開始**: ストリーミングファイル読み取り (パフォーマンスクリティカル)
4. **フェーズ2を実装**: OutputFormatValidator (UX改善)
5. **フェーズ4を実装**: スレッド安全性とテスト追加 (品質向上)
6. **フェーズ3で検証**: 全テスト実行とベンチマーク

## 📊 更新された工数見積もり（アーキテクチャ互換性版）

| フェーズ | タスク数 | 推定時間 | 優先度 |
|---------|---------|---------|--------|
| フェーズ1: ストリーミング | 3タスク | 5時間 | 🔴 CRITICAL |
| フェーズ2: バリデータ | 2タスク | 5時間 | 🟠 HIGH |
| フェーズ3: QA & ドキュメント | 3タスク | 4時間 | 🟡 MEDIUM |
| **合計** | **8タスク** | **14時間** | **(~2日)** |

*工数削減の理由*:
- v1.6.1.1は既に統合済み (-6時間)
- OpenSpec履歴ドキュメントは後回し (-2時間)
- スレッド安全性も既に実装済み (-2時間)
- **前回: 24時間 → 更新後: 14時間 (-10時間、42%削減)**

## 📚 参考資料

### Gitコミット
- v1.6.1.3 LLM guidance: `3f44ac6`
- v1.6.1.4 Streaming read: `8e1500e`

### ドキュメント
- 分析ドキュメント: `openspec/changes/apply-v1-6-1-x-fixes/analysis.md`
- 提案書: `openspec/changes/apply-v1-6-1-x-fixes/proposal.md`
- タスク: `openspec/changes/apply-v1-6-1-x-fixes/tasks.md`

### テストファイル取得コマンド
```bash
# v1.6.1.4 ストリーミングパフォーマンステスト
git show 8e1500e:tests/test_streaming_read_performance.py > tests/test_streaming_read_performance.py
git show 8e1500e:tests/test_streaming_read_performance_extended.py > tests/test_streaming_read_performance_extended.py

# v1.6.1.4 OpenSpecドキュメント
mkdir -p openspec/changes/refactor-streaming-read-performance/specs/mcp-tools
git show 8e1500e:openspec/changes/refactor-streaming-read-performance/design.md > openspec/changes/refactor-streaming-read-performance/design.md
git show 8e1500e:openspec/changes/refactor-streaming-read-performance/proposal.md > openspec/changes/refactor-streaming-read-performance/proposal.md
git show 8e1500e:openspec/changes/refactor-streaming-read-performance/specs/mcp-tools/spec.md > openspec/changes/refactor-streaming-read-performance/specs/mcp-tools/spec.md
git show 8e1500e:openspec/changes/refactor-streaming-read-performance/tasks.md > openspec/changes/refactor-streaming-read-performance/tasks.md

# v1.6.1.3 LLMガイダンステスト
git show 3f44ac6:tests/test_llm_guidance_compliance.py > tests/test_llm_guidance_compliance.py
git show 3f44ac6:tests/test_search_content_description.py > tests/test_search_content_description.py

# v1.6.1.3 設計・仕様ドキュメント
git show 3f44ac6:docs/mcp_fd_rg_design.md > docs/mcp_fd_rg_design.md
git show 3f44ac6:openspec/specs/llm-guidance/spec.md > openspec/specs/llm-guidance/spec.md
git show 3f44ac6:openspec/specs/mcp-tools/spec.md > openspec/specs/mcp-tools/spec.md

# 実装ファイル (参照用)
git show 8e1500e:tree_sitter_analyzer/file_handler.py  # ストリーミング版
git show 3f44ac6:tree_sitter_analyzer/mcp/tools/output_format_validator.py > \
    tree_sitter_analyzer/mcp/tools/output_format_validator.py
```

---

**ドキュメントバージョン**: 1.2  
**作成日**: 2025-01-04  
**最終更新**: 2025-01-04  
**ステータス**: 分析完了、実装準備完了  
**推定実装時間**: 24時間 (~3日)  
**変更履歴**: 
- v1.0: 初版 (v1.6.1.3とv1.6.1.4の主要機能分析)
- v1.1: フェーズ4追加 (v1.6.1.3の6つの追加コンポーネント) - 21時間
- v1.2: Task 1.4追加 (v1.6.1.4の6つのOpenSpecドキュメントとテスト) - 24時間
