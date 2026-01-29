# SQL Plugin Migration Analysis

**作成日:** 2026-01-15  
**対象:** Phase LR-5 Task T5.1  
**目的:** SQLプラグインの最適な移行方針を決定

---

## 📊 現状分析

### 現在の継承構造
```
ElementExtractor (ABC)
└── SQLElementExtractor
```

### SQLプラグインの特徴

**1. 追跡方式**
```python
self._processed_nodes: set[int]  # オブジェクトID追跡
```
- プログラミング言語と同じ方式
- マークアップ言語の位置ベース追跡とは異なる

**2. キャッシュ管理**
```python
self._node_text_cache: dict[tuple[int, int], str]  # 位置ベースキャッシュ
self._processed_nodes: set[int]  # オブジェクトID追跡
self._file_encoding: str | None
```

**3. テキスト抽出メソッド**
```python
def _get_node_text(self, node) -> str:
    # 2段階フォールバック:
    # 1. バイトベース抽出 (encoding_utils.extract_text_slice)
    # 2. 行/列ベース抽出 (content_lines)
```

**4. AST走査**
```python
def _traverse_nodes(self, node) -> Iterator[Node]:
    # シンプルな再帰的深さ優先探索
    yield node
    for child in node.children:
        yield from self._traverse_nodes(child)
```

**5. SQL固有機能**
- プラットフォーム互換性アダプター
- 複雑な検証・修正ロジック (`_validate_and_fix_elements`)
- SQL要素型の抽出 (`extract_sql_elements`)
- 識別子検証 (`_is_valid_identifier`)

---

## 🔍 移行オプション比較

### Option A: ProgrammingLanguageExtractor継承 ⭐ 推奨

**メリット:**
- ✅ オブジェクトID追跡(`set[int]`)が一致
- ✅ 複雑なAST処理に適した`_traverse_and_extract_iterative()`が利用可能
- ✅ `_element_cache`でパフォーマンス向上
- ✅ 既存の13プログラミング言語と同じパターン

**デメリット:**
- ⚠️ `_get_node_text()` → `_get_node_text_optimized()`への統合が必要
- ⚠️ `_traverse_nodes()`の互換性確認が必要

**実装難易度:** 中（2-3時間）

**リスク:** 低
- テキスト抽出ロジックは既に`CachedElementExtractor`と同等
- SQL固有機能は独立しているため影響なし

---

### Option B: 独自のSQLLanguageExtractor作成

**メリット:**
- ✅ SQL固有の複雑さを完全に分離
- ✅ 将来的な拡張性が高い

**デメリット:**
- ❌ 新しい基底クラスの作成が必要（スコープ拡大）
- ❌ 3層アーキテクチャの設計意図から逸脱
- ❌ メンテナンスコスト増加

**実装難易度:** 高（4-6時間）

**リスク:** 中
- 設計の一貫性が損なわれる
- 追加のテストとドキュメントが必要

---

### Option C: 現状維持（ElementExtractor直接継承）

**メリット:**
- ✅ 変更なし、リスク最小

**デメリット:**
- ❌ リファクタリング目標未達成
- ❌ コード重複が残る（`_get_node_text()`, `_reset_caches()`等）
- ❌ 他の17プラグインと一貫性がない

**実装難易度:** なし

**リスク:** なし（ただし技術的負債が残る）

---

## 🎯 推奨方針: Option A

### 理由

1. **追跡方式の一致**
   - SQLは`set[int]`（オブジェクトID）を使用
   - ProgrammingLanguageExtractorと完全一致

2. **AST処理の複雑さ**
   - SQLは複雑な検証・修正ロジックを持つ
   - プログラミング言語的な深いAST処理が必要

3. **一貫性**
   - 13プログラミング言語が既にProgrammingLanguageExtractorを使用
   - SQLも同じパターンに従うことで保守性向上

4. **実装コスト**
   - 中程度の実装難易度
   - 低リスク（既存ロジックとの互換性が高い）

---

## 📋 移行計画（Option A）

### Phase 1: メソッド統合（1-2時間）

**1. `_get_node_text()` → `_get_node_text_optimized()`**

現在のSQLプラグイン:
```python
def _get_node_text(self, node: "tree_sitter.Node") -> str:
    cache_key = (node.start_byte, node.end_byte)
    if cache_key in self._node_text_cache:
        return self._node_text_cache[cache_key]
    
    # バイトベース抽出
    try:
        encoding = self._file_encoding or "utf-8"
        content_bytes = safe_encode("\n".join(self.content_lines), encoding)
        text = extract_text_slice(content_bytes, start_byte, end_byte, encoding)
        if text:
            self._node_text_cache[cache_key] = text
            return text
    except Exception as e:
        log_debug(f"Error in _get_node_text: {e}")
    
    # 行/列ベースフォールバック
    # ... (複雑なロジック)
```

CachedElementExtractorの`_get_node_text_optimized()`:
```python
def _get_node_text_optimized(self, node, use_byte_offsets=True) -> str:
    cache_key = (node.start_byte, node.end_byte)
    if cache_key in self._node_text_cache:
        return self._node_text_cache[cache_key]
    
    text = ""
    if use_byte_offsets:
        text = self._extract_text_by_bytes(node)
    else:
        text = self._extract_text_by_position(node)
    
    # フォールバック
    if not text and use_byte_offsets:
        text = self._extract_text_by_position(node)
    
    self._node_text_cache[cache_key] = text
    return text
```

**結論:** ロジックはほぼ同等。`_get_node_text()`を削除し、`_get_node_text_optimized()`を使用可能。

---

**2. `_reset_caches()`のオーバーライド**

現在:
```python
def _reset_caches(self) -> None:
    self._node_text_cache.clear()
    self._processed_nodes.clear()
```

移行後:
```python
def _reset_caches(self) -> None:
    super()._reset_caches()  # CachedElementExtractor + ProgrammingLanguageExtractor
    # SQL固有のキャッシュがあれば追加
```

---

**3. `_traverse_nodes()`の互換性確認**

現在のSQLプラグイン:
```python
def _traverse_nodes(self, node) -> Iterator[Node]:
    yield node
    for child in node.children:
        yield from self._traverse_nodes(child)
```

ProgrammingLanguageExtractorには`_traverse_and_extract_iterative()`があるが、
SQLプラグインは独自の`_traverse_nodes()`を使用している。

**対応:** SQLプラグインの`_traverse_nodes()`を維持（オーバーライド）

---

### Phase 2: 継承変更（30分）

```python
# Before
from ..plugins.base import ElementExtractor

class SQLElementExtractor(ElementExtractor):
    def __init__(self, diagnostic_mode: bool = False) -> None:
        super().__init__()
        # ...

# After
from ..plugins.programming_language_extractor import ProgrammingLanguageExtractor

class SQLElementExtractor(ProgrammingLanguageExtractor):
    def __init__(self, diagnostic_mode: bool = False) -> None:
        super().__init__()
        # ...
```

---

### Phase 3: メソッド置換（30分）

**置換対象:**
- `_get_node_text()` → `_get_node_text_optimized()`の呼び出しに変更
- 全てのSQL抽出メソッドで使用箇所を確認

**検索パターン:**
```bash
grep -n "_get_node_text(" tree_sitter_analyzer/languages/sql_plugin.py
```

---

### Phase 4: テスト実行（30分）

```bash
# SQL固有テスト
uv run pytest tests/ -k sql -v

# 全テスト
uv run pytest tests/ -v

# 型チェック
uv run mypy tree_sitter_analyzer/languages/sql_plugin.py
```

---

## ⚠️ 注意事項

### 1. プラットフォーム互換性の維持

SQLプラグインは`CompatibilityAdapter`を使用:
```python
self.adapter: CompatibilityAdapter | None = None

def set_adapter(self, adapter: CompatibilityAdapter) -> None:
    self.adapter = adapter
```

**対応:** この機能は独立しているため、移行の影響なし。

---

### 2. SQL固有の検証ロジック

`_validate_and_fix_elements()`は複雑なプラットフォーム固有の修正を実施:
- Phantom要素の削除
- 名前の修正
- 重複排除
- 欠落したViewの復元

**対応:** この機能は独立しているため、移行の影響なし。

---

### 3. SQL要素型の保持

`extract_sql_elements()`は`SQLElement`型を返す:
```python
def extract_sql_elements(self, tree, source_code) -> list[SQLElement]:
    # SQLTable, SQLView, SQLProcedure, SQLFunction, SQLTrigger, SQLIndex
```

**対応:** この機能は独立しているため、移行の影響なし。

---

## 📊 期待される成果

### コード削減
- `_get_node_text()`: ~75行削除
- `_reset_caches()`: 簡素化
- 合計: 約80-100行削減

### 品質向上
- ✅ 一貫性: 全18プラグインが統一アーキテクチャ
- ✅ 保守性: 共通基底クラスの恩恵
- ✅ パフォーマンス: `_element_cache`の活用可能

### テスト
- 既存のSQLテスト全て通過（目標: 100%）
- プラットフォーム互換性テスト通過
- パフォーマンステスト通過

---

## 🎯 結論

**推奨:** Option A - ProgrammingLanguageExtractor継承

**理由:**
1. 追跡方式の一致（オブジェクトID）
2. 複雑なAST処理に適している
3. 既存の13プログラミング言語と一貫性
4. 実装コストが妥当（2-3時間）
5. リスクが低い

**次のステップ:** T5.2 SQL Plugin移行実装の開始

---

**分析者:** Claude Sonnet 4.5  
**承認待ち:** Phase LR-5 T5.2開始
