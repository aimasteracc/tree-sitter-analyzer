# アーキテクチャ互換性分析

## 目的

v1.6.1.xからv1.9.3への**仕様変更のみ**を適用し、**アーキテクチャの後退を避ける**。

## v1.9.3の現在のアーキテクチャ

### 主要な構造変更

#### 1. utils.py → utils/ ディレクトリ化
**変更内容**:
- `tree_sitter_analyzer/utils.py` (単一ファイル)
- → `tree_sitter_analyzer/utils/` (モジュール化)
  - `logging.py` - ロギング機能
  - `tree_sitter_compat.py` - Tree-sitter互換性
  - `__init__.py` - モジュールエクスポート

**影響**: v1.6.1.1のロギング機能は**既に完全に統合済み**

#### 2. 新しいプラグインシステム
**v1.9.3の追加機能**:
- `tree_sitter_analyzer/plugins/` - プラグイン基盤
- `tree_sitter_analyzer/formatters/` - 大幅拡張
  - `formatter_registry.py` - フォーマッタ登録システム
  - `language_formatter_factory.py` - ファクトリパターン
  - HTML, TypeScript, Markdown フォーマッタ追加

#### 3. 新しい言語サポート
**v1.9.3の追加**:
- CSS プラグイン (449行)
- HTML プラグイン (496行)
- Markdown プラグイン (1929行)
- TypeScript プラグイン (大幅拡張: 1892行)

#### 4. セキュリティとバリデーション強化
**v1.9.3の追加**:
- `tree_sitter_analyzer/security/validator.py` (415行追加)
- `tree_sitter_analyzer/cli/argument_validator.py` (新規)

#### 5. MCP ツールの大幅拡張
**v1.9.3の改善**:
- `fd_rg_utils.py` (+312行)
- `search_content_tool.py` (+395行) ← **既にLLMガイダンス機能を含む**
- `file_output_factory.py` (217行、新規)

## v1.6.1.x機能の互換性評価

### ✅ v1.6.1.1: ロギング制御
**状態**: **完全に統合済み**

**確認事項**:
```python
# v1.9.3の tree_sitter_analyzer/utils/logging.py に以下が全て存在:
- setup_logger() with string level support
- TREE_SITTER_ANALYZER_ENABLE_FILE_LOG
- TREE_SITTER_ANALYZER_LOG_DIR
- TREE_SITTER_ANALYZER_FILE_LOG_LEVEL
- SafeStreamHandler
- File logging with custom directory support
```

**結論**: v1.6.1.1の機能は既にv1.9.3に統合されている。**追加作業不要**。

---

### ⚠️ v1.6.1.3: OutputFormatValidator + LLMガイダンス
**状態**: **部分的に統合済み**

**既に存在する機能** (v1.9.3):
1. ✅ **LLMガイダンス**: `search_content_tool.py`に既に統合
   - トークン効率ガイド
   - 推奨ワークフロー
   - パラメータ説明の詳細化
2. ✅ **ベストプラクティス**: `.roo/rules/search-best-practices.md`

**欠けている機能**:
1. ❌ **OutputFormatValidator.py** - 相互排他的パラメータ検証クラス
2. ❌ **多言語エラーメッセージ** - 日本語/英語の切り替え
3. ❌ **test_llm_guidance_compliance.py** (170行)
4. ❌ **test_search_content_description.py** (217行)
5. ❌ **設計ドキュメント** (519行)

**適用方法**: 
- `OutputFormatValidator`は**新規クラスとして追加可能**
- v1.9.3の`search_content_tool.py`の`validate_arguments()`に統合
- v1.9.3のパターンに従う:
  ```python
  # v1.9.3パターン: mcp/tools/ 内のツールクラス
  from tree_sitter_analyzer.mcp.tools.output_format_validator import OutputFormatValidator
  ```

**後退リスク**: **低** - 新規クラスの追加のみ、既存コードに影響なし

---

### ⚠️ v1.6.1.4: ストリーミングファイル読み取り
**状態**: **未統合**

**v1.9.3の現在の実装**:
```python
# tree_sitter_analyzer/file_handler.py (v1.9.3)
def read_file_partial(...):
    # 全ファイルをメモリに読み込む
    content, detected_encoding = read_file_safe(file_path)
    lines = content.splitlines(keepends=True)
    # ... 行範囲を選択
```

**v1.6.1.4の実装**:
```python
# 提案: encoding_utils.py に追加
def read_file_safe_streaming(file_path):
    # ストリーミング読み取り
    with open(file_path, "r", encoding=detected_encoding) as f:
        yield f
```

**適用方法**:
1. **新規関数を追加**: `tree_sitter_analyzer/encoding_utils.py`
   - `read_file_safe_streaming()` - v1.9.3のパターンに従う
   - 既存の`read_file_safe()`は維持
2. **既存関数を改善**: `tree_sitter_analyzer/file_handler.py`
   - `read_file_partial()`の内部実装のみ変更
   - 関数シグネチャは変更なし（後方互換性100%）

**後退リスク**: **極めて低**
- 新規関数追加のみ
- 既存APIは完全に互換
- 内部実装の最適化のみ

---

### ❌ v1.6.1.4: OpenSpecドキュメント
**状態**: **未統合**

**欠けているドキュメント**:
- `openspec/changes/refactor-streaming-read-performance/` (179行)
  - design.md, proposal.md, specs/, tasks.md

**適用方法**:
- そのまま移植可能（ドキュメントのみ）
- コードに影響なし

**後退リスク**: **なし** - ドキュメントのみ

---

## 仕様変更の適用戦略

### Phase 1: 安全な追加のみ (推奨)

#### 1.1: OutputFormatValidator 追加
**アクション**:
- ✅ **新規ファイル作成**: `mcp/tools/output_format_validator.py`
- ✅ **統合**: `search_content_tool.py`の`validate_arguments()`に追加
- ✅ **v1.9.3パターンに従う**: 既存のツールクラスと同じ構造

**検証**:
```bash
# 既存テストが全てパスすることを確認
pytest tests/mcp/test_tools/test_search_content_tool.py -v
```

#### 1.2: ストリーミング読み取り追加
**アクション**:
- ✅ **新規関数**: `encoding_utils.py`に`read_file_safe_streaming()`追加
- ✅ **内部最適化**: `file_handler.py`の`read_file_partial()`を改善
- ✅ **API維持**: 外部インターフェースは変更なし

**検証**:
```bash
# 既存の全てのファイル読み取りテストがパス
pytest tests/test_file_handler.py -v
pytest tests/test_encoding_utils.py -v
```

#### 1.3: テストとドキュメント追加
**アクション**:
- ✅ テストファイルを移植（新規追加のみ）
- ✅ OpenSpecドキュメントを移植（履歴として）

### Phase 2: 検証と最適化

#### 2.1: パフォーマンステスト
```bash
pytest tests/test_streaming_read_performance*.py -v
```

#### 2.2: 統合テスト
```bash
pytest tests/ -v --cov=tree_sitter_analyzer
```

---

## 後退防止チェックリスト

### ✅ アーキテクチャ後退を防ぐ
- [ ] `utils/` ディレクトリ構造を維持
- [ ] 新しいプラグインシステムを維持
- [ ] フォーマッタレジストリシステムを維持
- [ ] セキュリティバリデーション機能を維持

### ✅ 既存機能を維持
- [ ] 全ての既存テストがパス（3,370+テスト）
- [ ] カバレッジが低下しない（80%以上）
- [ ] 既存APIが変更されない（後方互換性100%）

### ✅ 新規追加のみ
- [ ] 古いコードの直接コピーはしない
- [ ] v1.9.3のパターンに従う
- [ ] 既存コードの削除はしない

---

## 実装優先度（修正版）

### 🔴 CRITICAL: ストリーミング読み取り
- **理由**: パフォーマンス改善（150倍高速化）
- **リスク**: 極めて低（新規関数 + 内部最適化のみ）
- **工数**: 5時間

### 🟠 HIGH: OutputFormatValidator
- **理由**: UX改善、エラー防止
- **リスク**: 低（新規クラス追加のみ）
- **工数**: 5時間

### 🟡 MEDIUM: テストとドキュメント
- **理由**: 品質保証、将来の保守性
- **リスク**: なし（追加のみ）
- **工数**: 4時間

### ⚪ LOW: v1.6.1.1ロギング
- **理由**: 既に統合済み
- **リスク**: なし
- **工数**: 0時間（不要）

---

## 結論

### ✅ 適用すべき変更
1. **OutputFormatValidator**: 新規クラスとして追加
2. **ストリーミング読み取り**: 新規関数 + 内部最適化
3. **テスト**: 新規追加
4. **ドキュメント**: 履歴として追加

### ❌ 適用すべきでない変更
1. **v1.6.1.1ロギング**: 既に統合済み
2. **古いutils.py**: v1.9.3はutils/モジュール化済み
3. **古いフォーマッタ**: v1.9.3は新しいレジストリシステム

### 📊 更新された工数見積もり
| フェーズ | 工数 | リスク |
|---------|------|--------|
| OutputFormatValidator | 5h | 低 |
| ストリーミング読み取り | 5h | 極めて低 |
| テスト + ドキュメント | 4h | なし |
| **合計** | **14h** | **安全** |

*前回: 24時間 → 更新後: 14時間 (-10時間)*

**理由**: v1.6.1.1は既に統合済み、アーキテクチャに合わせた最小限の変更のみ

---

**ドキュメントバージョン**: 1.0  
**作成日**: 2025-11-04  
**ステータス**: アーキテクチャ分析完了  
**推奨**: 仕様変更のみを適用、アーキテクチャは維持
