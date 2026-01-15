# Plugin Base Class Extraction - Task Plan

## 目標

全18言語プラグインの3層アーキテクチャへの移行を完了し、BaseElementExtractorの削除とドキュメント整備を行う。

## 現在の状況

### ✅ 完了済みフェーズ

**Phase LR-1: 3層基底クラス作成** ✅
- `CachedElementExtractor`: キャッシュインフラ
- `ProgrammingLanguageExtractor`: プログラミング言語用
- `MarkupLanguageExtractor`: マークアップ言語用

**Phase LR-2: 主要プログラミング言語移行** ✅
- 7言語: Python, Java, JavaScript, TypeScript, C, C++, C#
- テスト成功率: 98%+

**Phase LR-3: 追加プログラミング言語移行** ✅
- 5言語: Go, Rust, Kotlin, PHP, Ruby
- テスト成功率: 98%+

**Phase LR-4: マークアップ言語移行** ✅
- 4言語: Markdown, YAML, CSS, HTML
- テスト成功率: 98.5% (707/718)

**Phase LR-5: SQL Plugin移行** ✅ (2026-01-15完了)
- SQLプラグインをProgrammingLanguageExtractorに移行
- テスト成功率: 98.3% (353/359)
- コード削減: ~83行
- **全18言語プラグイン移行完了** 🎉

### 📊 累積成果

- **総コード削減**: ~1,600+ 行
- **全体テスト成功率**: 98%+
- **型安全性**: MyPy 100%準拠維持
- **3層アーキテクチャ**: 確立完了

```
Layer 1: CachedElementExtractor (キャッシュインフラ)
         ↓
Layer 2: ProgrammingLanguageExtractor (13言語 + SQL)
         MarkupLanguageExtractor (4言語)
         ↓
Layer 3: 個別言語プラグイン (18言語)
```

## 残りのフェーズ

### Phase LR-6: BaseElementExtractor削除とクリーンアップ
**Status:** in_progress
**Priority:** P0
**Estimated:** 2-3時間

### Phase LR-7: ドキュメント整備
**Status:** pending
**Priority:** P1
**Estimated:** 3-4時間

### Phase LR-8: 最終検証とリリース
**Status:** pending
**Priority:** P0
**Estimated:** 2-3時間

---

## フェーズ詳細

### Phase LR-6: BaseElementExtractor削除とクリーンアップ

#### T6.1: BaseElementExtractor使用状況確認
**Status:** ✅ completed
**Objective:** 旧BaseElementExtractorが使用されていないことを確認

**Tasks:**
- [x] 全プラグインの継承確認
- [x] インポート文の検索
- [x] テストファイルの確認

**Result:**
- 使用箇所ゼロ（コメントのみ）
- `tests/unit/plugins/test_base_element_extractor.py` も削除対象として特定

---

#### T6.2: BaseElementExtractorファイル削除
**Status:** in_progress
**Objective:** 旧基底クラスファイルを削除

**Tasks:**
- [ ] ファイル削除: `tree_sitter_analyzer/plugins/base_element_extractor.py`
- [ ] テストファイル削除: `tests/unit/plugins/test_base_element_extractor.py`
- [ ] `__init__.py`からインポート削除
  ```python
  # Remove this line from tree_sitter_analyzer/plugins/__init__.py
  from .base_element_extractor import BaseElementExtractor
  ```
- [ ] 全テスト実行で確認
  ```bash
  uv run pytest tests/ -v
  ```

**Files to Delete:**
- `tree_sitter_analyzer/plugins/base_element_extractor.py`
- `tests/unit/plugins/test_base_element_extractor.py`

**Files to Modify:**
- `tree_sitter_analyzer/plugins/__init__.py`

---

#### T6.3: 削除後の検証
**Status:** pending
**Objective:** 削除による影響がないことを確認

**Tasks:**
- [ ] 全ユニットテスト実行
- [ ] 全統合テスト実行
- [ ] MyPy型チェック
- [ ] インポートエラーチェック

**Acceptance Criteria:**
- 全テスト通過
- インポートエラーなし
- MyPy 100%準拠

---

### Phase LR-7: ドキュメント整備

#### T7.1: プラグイン開発ガイド作成
**Status:** pending
**Objective:** 新しいプラグイン追加のためのガイド作成

**Tasks:**
- [ ] ファイル作成: `docs/plugin-development-guide.md`
- [ ] 内容:
  - 3層アーキテクチャの概要
  - ProgrammingLanguageExtractor vs MarkupLanguageExtractor
  - 最小限のプラグイン実装例
  - フックメソッドのカスタマイズ方法
  - テストの書き方
  - よくある問題と解決策

**Files to Create:**
- `docs/plugin-development-guide.md`

---

#### T7.2: マイグレーションガイド作成
**Status:** pending
**Objective:** 既存プラグインのメンテナンス者向けガイド

**Tasks:**
- [ ] ファイル作成: `docs/migration-guide.md`
- [ ] 内容:
  - なぜ3層アーキテクチャに移行したか
  - Before/Afterのコード例
  - よくある移行パターン
  - トラブルシューティング

**Files to Create:**
- `docs/migration-guide.md`

---

#### T7.3: CLAUDE.md更新
**Status:** pending
**Objective:** プロジェクトのメイン指示ファイルを更新

**Tasks:**
- [ ] アーキテクチャセクションの更新
  - 3層アーキテクチャの追加
  - 継承図の更新
- [ ] プラグイン開発セクションの追加
- [ ] 新しいプラグイン追加の手順更新

**Files to Modify:**
- `CLAUDE.md`

---

#### T7.4: アーキテクチャ図作成
**Status:** pending
**Objective:** 視覚的なアーキテクチャドキュメント

**Tasks:**
- [ ] Mermaid図の作成（継承階層）
- [ ] データフロー図の作成
- [ ] `docs/architecture.md`への追加

**Files to Modify:**
- `docs/architecture.md`

---

### Phase LR-8: 最終検証とリリース

#### T8.1: 最終的な全テスト実行
**Status:** pending
**Objective:** プロジェクト全体の動作を検証

**Tasks:**
- [ ] 全ユニットテスト実行
  ```bash
  uv run pytest tests/unit/ -v
  ```
- [ ] 全統合テスト実行
  ```bash
  uv run pytest tests/integration/ -v
  ```
- [ ] 全リグレッションテスト実行
  ```bash
  uv run pytest tests/regression/ -m regression
  ```
- [ ] 全ベンチマークテスト実行
  ```bash
  uv run pytest tests/benchmarks/ -v
  ```
- [ ] Golden Masterテスト検証
- [ ] MyPy型チェック
  ```bash
  uv run mypy tree_sitter_analyzer/
  ```
- [ ] リンティング実行
  ```bash
  uv run python check_quality.py --new-code-only
  ```

**Acceptance Criteria:**
- 8,405テスト全て通過
- MyPy 100%準拠
- リンティングエラーなし
- パフォーマンスベンチマーク±5%以内
- Golden Master一致

---

#### T8.2: 最終コミットとマージ
**Status:** pending
**Objective:** リファクタリングの完了をマーク

**Tasks:**
- [ ] Phase LR-5のコミット
- [ ] Phase LR-6のコミット（BaseElementExtractor削除）
- [ ] Phase LR-7のコミット（ドキュメント整備）
- [ ] 最終コミット
- [ ] CHANGELOGの更新
- [ ] feature branchをmainにマージ

**Acceptance Criteria:**
- プロジェクトが安定している
- ドキュメントが完備されている
- 全変更がコミットされている

---

## タスク依存関係

```
Phase LR-5 (完了) ✅
    ↓
T6.1: 使用状況確認
    ↓
T6.2: ファイル削除
    ↓
T6.3: 削除後検証
    ↓
T7.1: 開発ガイド作成
T7.2: マイグレーションガイド作成
    ↓
T7.3: CLAUDE.md更新
    ↓
T7.4: アーキテクチャ図作成
    ↓
T8.1: 最終テスト実行
    ↓
T8.2: 最終コミットとマージ
```

---

## 進捗トラッキング

**完了フェーズ:** 5/8 (Phase LR-1 ~ LR-5)
**進捗率:** 62.5%

**残りタスク:**
- Phase LR-6: 1/3 タスク (T6.1完了)
- Phase LR-7: 0/4 タスク
- Phase LR-8: 0/2 タスク

**総タスク:** 9タスク残り

---

## 次のアクション

**即座に実行:** T6.2 (BaseElementExtractorファイル削除)
