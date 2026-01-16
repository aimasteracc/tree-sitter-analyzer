# Layered Refactoring Design - BaseElementExtractor分層設計

## 概要

BaseElementExtractor（497行）を3層のクラス階層に分割し、各言語タイプに適した基底クラスを提供する。

**目標:**
- ✅ 単一責任原則の遵守（各層が明確な責任を持つ）
- ✅ 適切な抽象化レベル（プログラミング言語 vs マークアップ言語）
- ✅ 既存の7つの移行済みプラグインの保護（最小限の変更）
- ✅ 未移行の10プラグインに適切な基底クラスを提供

---

## 現状分析

### 現在のBaseElementExtractor（497行）の問題

1. **過度な統合**: プログラミング言語とマークアップ言語の両方に対応しようとして肥大化
2. **不要な機能の強制**: Markdown/YAML/CSS/HTMLには不要なAST traversalと複雑度計算
3. **単一責任原則違反**: キャッシュ管理 + テキスト抽出 + AST走査 + 複雑度計算

### プラグイン分類

| カテゴリ | プラグイン数 | 必要な機能 | 現状 |
|---------|------------|-----------|------|
| **プログラミング言語** | 13 | AST traversal, 複雑度計算, 高度なキャッシュ | 7移行済み, 6未移行 |
| **マークアップ言語** | 4 | 基本キャッシュ, シンプルな走査 | 0移行済み, 4未移行 |
| **特殊ケース (SQL)** | 1 | 独自実装 | 0移行済み, 1未移行 |

**移行済みプラグイン (7):**
- Python, Java, JavaScript, TypeScript, C++, C#, C

**未移行プラグイン (10):**
- プログラミング言語: Go, Rust, Kotlin, PHP, Ruby, SQL (6)
- マークアップ言語: Markdown, YAML, CSS, HTML (4)

---

## 分層設計

### クラス階層図

```
ElementExtractor (ABC)
│
├── CachedElementExtractor (~80行)
│   │   - 基本キャッシュ管理
│   │   - ノードテキスト抽出
│   │   - ソースコード初期化
│   │
│   ├── ProgrammingLanguageExtractor (~250行)
│   │   │   - AST反復的トラバーサル
│   │   │   - 要素キャッシュ管理
│   │   │   - 複雑度計算
│   │   │
│   │   ├── PythonElementExtractor (移行済み)
│   │   ├── JavaElementExtractor (移行済み)
│   │   ├── JavaScriptElementExtractor (移行済み)
│   │   ├── TypeScriptElementExtractor (移行済み)
│   │   ├── CppElementExtractor (移行済み)
│   │   ├── CSharpElementExtractor (移行済み)
│   │   ├── CElementExtractor (移行済み)
│   │   ├── GoElementExtractor (未移行)
│   │   ├── RustElementExtractor (未移行)
│   │   ├── KotlinElementExtractor (未移行)
│   │   ├── PhpElementExtractor (未移行)
│   │   └── RubyElementExtractor (未移行)
│   │
│   └── MarkupLanguageExtractor (~100行)
│       │   - シンプルなノード走査
│       │   - 位置ベース処理追跡
│       │
│       ├── MarkdownElementExtractor (未移行)
│       ├── YamlElementExtractor (未移行)
│       ├── CssElementExtractor (未移行)
│       └── HtmlElementExtractor (未移行)
│
└── SqlElementExtractor (独立、特殊ケース)
```

---

## Layer 1: CachedElementExtractor

### 責任
- 基本的なキャッシュ管理
- ノードテキスト抽出（バイト/位置ベース）
- ソースコード初期化

### 実装（~80行）

```python
# tree_sitter_analyzer/plugins/cached_element_extractor.py

from typing import TYPE_CHECKING, Any
from abc import ABC

if TYPE_CHECKING:
    import tree_sitter

from ..encoding_utils import extract_text_slice, safe_encode
from ..utils import log_error
from .base import ElementExtractor


class CachedElementExtractor(ElementExtractor, ABC):
    """
    Minimal base class providing basic caching and text extraction.
    
    Suitable for all language types as a foundation.
    Provides only essential functionality without imposing heavy machinery.
    """

    def __init__(self) -> None:
        super().__init__()
        
        # Minimal caching - only node text
        self._node_text_cache: dict[tuple[int, int], str] = {}
        
        # Source code management
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self._file_encoding: str = "utf-8"

    def _reset_caches(self) -> None:
        """Reset performance caches - call before analyzing new file"""
        self._node_text_cache.clear()

    def _initialize_source(
        self, 
        source_code: str, 
        encoding: str = "utf-8"
    ) -> None:
        """Initialize source code for processing"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n") if source_code else []
        self._file_encoding = encoding
        self._reset_caches()

    def _get_node_text_optimized(
        self,
        node: "tree_sitter.Node",
        use_byte_offsets: bool = True,
    ) -> str:
        """
        Extract text from AST node with caching.
        
        Uses position-based cache keys (start_byte, end_byte) for deterministic
        behavior across test runs.
        
        Args:
            node: Tree-sitter AST node
            use_byte_offsets: If True, use byte-based extraction (recommended for UTF-8).
                             If False, fall back to line/column-based extraction.
            
        Returns:
            Extracted text string, or empty string on error
            
        Performance:
            - First call: O(n) where n is text length
            - Subsequent calls with same node position: O(1) cache lookup
        """
        cache_key = (node.start_byte, node.end_byte)
        
        if cache_key in self._node_text_cache:
            return self._node_text_cache[cache_key]
        
        text = ""
        try:
            if use_byte_offsets:
                text = self._extract_text_by_bytes(node)
            else:
                text = self._extract_text_by_position(node)
            
            # If byte extraction returns empty, try position-based fallback
            if not text and use_byte_offsets:
                text = self._extract_text_by_position(node)
        
        except Exception as e:
            log_error(f"Node text extraction failed: {e}")
            # Try fallback on error
            try:
                text = self._extract_text_by_position(node)
            except Exception:
                text = ""
        
        self._node_text_cache[cache_key] = text
        return text

    def _extract_text_by_bytes(self, node: "tree_sitter.Node") -> str:
        """Extract text using byte offsets (UTF-8 optimized)"""
        content_bytes = safe_encode(
            "\n".join(self.content_lines), 
            self._file_encoding
        )
        return extract_text_slice(
            content_bytes,
            node.start_byte,
            node.end_byte,
            self._file_encoding
        )

    def _extract_text_by_position(self, node: "tree_sitter.Node") -> str:
        """Extract text using line/column positions (fallback)"""
        start_point = node.start_point
        end_point = node.end_point
        
        # Boundary validation
        if not self.content_lines:
            return ""
        
        if start_point[0] < 0 or start_point[0] >= len(self.content_lines):
            return ""
        
        if end_point[0] < 0 or end_point[0] >= len(self.content_lines):
            return ""
        
        # Single line extraction
        if start_point[0] == end_point[0]:
            line = self.content_lines[start_point[0]]
            start_col = max(0, min(start_point[1], len(line)))
            end_col = max(start_col, min(end_point[1], len(line)))
            return line[start_col:end_col]
        
        # Multi-line extraction
        lines = []
        for i in range(start_point[0], end_point[0] + 1):
            if i >= len(self.content_lines):
                break
            
            line = self.content_lines[i]
            if i == start_point[0]:
                # First line: from start column to end
                start_col = max(0, min(start_point[1], len(line)))
                lines.append(line[start_col:])
            elif i == end_point[0]:
                # Last line: from beginning to end column
                end_col = max(0, min(end_point[1], len(line)))
                lines.append(line[:end_col])
            else:
                # Middle lines: entire line
                lines.append(line)
        
        return "\n".join(lines)
```

**行数:** ~95行（フォールバックロジック追加により15行増加）
**複雑度:** 低
**依存関係:** ElementExtractor, encoding_utils

**重要な設計決定:**
- **二段階フォールバック戦略**: バイト抽出失敗時に位置ベース抽出を試行し、それも失敗した場合は空文字列を返す
- **キャッシュキー**: 位置ベース `(start_byte, end_byte)` を使用（決定論的、テスト可能）
- **エラーハンドリング**: 例外発生時も位置ベースフォールバックを試行してから空文字列を返す

---

## Layer 2a: ProgrammingLanguageExtractor

### 責任
- 反復的ASTトラバーサル
- 要素キャッシュ管理
- 複雑度計算
- プログラミング言語固有の最適化

### 実装（~250行）

```python
# tree_sitter_analyzer/plugins/programming_language_extractor.py

from typing import TYPE_CHECKING, Any, Callable
from abc import ABC

if TYPE_CHECKING:
    import tree_sitter

from ..utils import log_debug, log_error, log_warning
from .cached_element_extractor import CachedElementExtractor


class ProgrammingLanguageExtractor(CachedElementExtractor, ABC):
    """
    Base class for programming language plugins.
    
    Provides advanced features needed for programming languages:
    - Iterative AST traversal with depth limits
    - Element caching for performance
    - Cyclomatic complexity calculation
    - Container node type customization
    """

    def __init__(self) -> None:
        super().__init__()
        
        # Programming language specific caches
        # Note: Uses object ID-based tracking (set[int]) for processed nodes
        # This differs from markup languages which use position-based tracking
        self._processed_nodes: set[int] = set()
        self._element_cache: dict[tuple[int, str], Any] = {}

    def _reset_caches(self) -> None:
        """Reset all caches including programming-specific ones"""
        super()._reset_caches()
        self._processed_nodes.clear()
        self._element_cache.clear()

    # --- AST Traversal ---

    def _get_container_node_types(self) -> set[str]:
        """
        Get node types that may contain target elements.
        Override in subclasses for language-specific containers.
        """
        return {
            "program",
            "module",
            "block",
            "body",
        }

    def _traverse_and_extract_iterative(
        self,
        root_node: "tree_sitter.Node | None",
        extractors: dict[str, Callable],
        results: list[Any],
        element_type: str,
        max_depth: int = 50,
    ) -> None:
        """
        Generic iterative AST traversal with element extraction.
        
        Args:
            root_node: Root node to start traversal
            extractors: Mapping of node types to extractor functions
            results: List to accumulate extracted elements
            element_type: Type of element being extracted (for caching)
            max_depth: Maximum traversal depth
        """
        if not root_node:
            return
        
        target_node_types = set(extractors.keys())
        container_node_types = self._get_container_node_types()
        
        node_stack = [(root_node, 0)]
        processed_nodes = 0
        
        while node_stack:
            current_node, depth = node_stack.pop()
            
            # Depth limit check
            if depth > max_depth:
                log_warning(f"Maximum traversal depth ({max_depth}) exceeded")
                continue
            
            processed_nodes += 1
            node_type = current_node.type
            
            # Early exit: skip irrelevant nodes
            if (
                depth > 0
                and node_type not in target_node_types
                and node_type not in container_node_types
            ):
                continue
            
            # Process target nodes
            if node_type in target_node_types:
                node_id = id(current_node)
                
                # Skip if already processed
                if node_id in self._processed_nodes:
                    continue
                
                # Cache check
                cache_key = (node_id, element_type)
                if cache_key in self._element_cache:
                    element = self._element_cache[cache_key]
                    self._append_element_to_results(element, results)
                    self._processed_nodes.add(node_id)
                    continue
                
                # Extract and cache
                extractor = extractors.get(node_type)
                if extractor:
                    try:
                        element = extractor(current_node)
                        self._element_cache[cache_key] = element
                        self._append_element_to_results(element, results)
                        self._processed_nodes.add(node_id)
                    except Exception as e:
                        log_error(f"Element extraction failed: {e}")
                        self._processed_nodes.add(node_id)
            
            # Push children to stack
            if current_node.children:
                self._push_children_to_stack(current_node, depth, node_stack)
        
        log_debug(f"Iterative traversal processed {processed_nodes} nodes")

    def _append_element_to_results(
        self, 
        element: Any, 
        results: list[Any]
    ) -> None:
        """Helper to append element(s) to results list"""
        if element:
            if isinstance(element, list):
                results.extend(element)
            else:
                results.append(element)

    def _push_children_to_stack(
        self,
        node: "tree_sitter.Node",
        depth: int,
        stack: list[tuple["tree_sitter.Node", int]],
    ) -> None:
        """Helper to push children to traversal stack"""
        try:
            children_list = list(node.children)
            # Reverse order for DFS
            for child in reversed(children_list):
                stack.append((child, depth + 1))
        except (TypeError, AttributeError):
            # Fallback for Mock objects
            try:
                children_list = list(node.children)
                for child in children_list:
                    stack.append((child, depth + 1))
            except (TypeError, AttributeError):
                pass  # No children

    # --- Complexity Calculation ---

    def _get_decision_keywords(self) -> set[str]:
        """
        Get language-specific decision keywords.
        Override in subclasses.
        """
        return {
            "if_statement",
            "for_statement",
            "while_statement",
            "case",
            "catch",
            "and",
            "or",
        }

    def _calculate_complexity_optimized(
        self, 
        node: "tree_sitter.Node"
    ) -> int:
        """
        Calculate cyclomatic complexity (can be overridden).
        Default implementation counts decision points.
        """
        complexity = 1  # Base complexity
        
        decision_keywords = self._get_decision_keywords()
        
        def count_decisions(n: "tree_sitter.Node") -> int:
            count = 0
            if n.type in decision_keywords:
                count += 1
            for child in n.children:
                count += count_decisions(child)
            return count
        
        complexity += count_decisions(node)
        return complexity
```

**行数:** ~270行（実装の詳細により20行増加の見込み）
**複雑度:** 中
**依存関係:** CachedElementExtractor

**重要な設計決定:**
- **キャッシュキー型の違い**:
  - `_processed_nodes: set[int]` - オブジェクトIDベースの追跡（プログラミング言語用）
  - これはMarkupLanguageExtractorの位置ベース追跡 `set[tuple[int, int]]` とは異なる
  - 理由: プログラミング言語では同じ位置に複数の要素が存在する可能性があるため、オブジェクトIDが必要
- **要素キャッシュ**: `_element_cache: dict[tuple[int, str], Any]` - 抽出済み要素のキャッシュ
- **反復的トラバーサル**: スタックオーバーフロー回避のため、再帰ではなく反復的実装を使用

---

## Layer 2b: MarkupLanguageExtractor

### 責任
- シンプルなノード走査（再帰的）
- 位置ベースの処理追跡
- マークアップ言語固有の軽量機能

### 実装（~100行）

```python
# tree_sitter_analyzer/plugins/markup_language_extractor.py

from typing import TYPE_CHECKING, Iterator
from abc import ABC

if TYPE_CHECKING:
    import tree_sitter

from .cached_element_extractor import CachedElementExtractor


class MarkupLanguageExtractor(CachedElementExtractor, ABC):
    """
    Base class for markup language plugins.
    
    Provides lightweight features suitable for markup languages:
    - Simple recursive node traversal
    - Position-based processing tracking
    - No heavy AST machinery or complexity calculation
    """

    def __init__(self) -> None:
        super().__init__()
        
        # Lightweight tracking using position-based keys
        self._processed_nodes: set[tuple[int, int]] = set()

    def _reset_caches(self) -> None:
        """Reset caches including markup-specific tracking"""
        super()._reset_caches()
        self._processed_nodes.clear()

    def _traverse_nodes(
        self, 
        root_node: "tree_sitter.Node"
    ) -> Iterator["tree_sitter.Node"]:
        """
        Simple recursive node traversal.
        
        Yields all nodes in the tree in depth-first order.
        Suitable for markup languages where complex traversal is not needed.
        
        Args:
            root_node: Root node to start traversal
            
        Yields:
            Tree-sitter nodes in DFS order
        """
        yield root_node
        
        if hasattr(root_node, 'children'):
            for child in root_node.children:
                yield from self._traverse_nodes(child)

    def _is_node_processed(self, node: "tree_sitter.Node") -> bool:
        """Check if node has been processed (position-based)"""
        node_key = (node.start_byte, node.end_byte)
        return node_key in self._processed_nodes

    def _mark_node_processed(self, node: "tree_sitter.Node") -> None:
        """Mark node as processed (position-based)"""
        node_key = (node.start_byte, node.end_byte)
        self._processed_nodes.add(node_key)
```

**行数:** ~100行
**複雑度:** 低
**依存関係:** CachedElementExtractor

**重要な設計決定:**
- **キャッシュキー型の違い**:
  - `_processed_nodes: set[tuple[int, int]]` - 位置ベースの追跡（マークアップ言語用）
  - これはProgrammingLanguageExtractorのオブジェクトIDベース追跡 `set[int]` とは異なる
  - 理由: マークアップ言語では位置情報のみで要素を一意に識別できるため、よりシンプルな実装が可能
- **再帰的トラバーサル**: マークアップ言語は通常ネストが浅いため、シンプルな再帰実装で十分
- **軽量設計**: 複雑度計算や要素キャッシュなどの重い機能は不要

---

## マイグレーション戦略

### Phase 1: 新しい層の作成（1日）

**タスク:**
1. `CachedElementExtractor`の実装
2. `ProgrammingLanguageExtractor`の実装
3. `MarkupLanguageExtractor`の実装
4. ユニットテストの作成

**検証:**
- 各層が独立してテスト可能
- mypy型チェック通過
- 既存コードに影響なし

### Phase 2: 移行済みプラグインの調整（1日）

**対象:** Python, Java, JavaScript, TypeScript, C++, C#, C (7プラグイン)

**変更内容:**
```python
# Before
from ..plugins.base_element_extractor import BaseElementExtractor

class PythonElementExtractor(BaseElementExtractor):
    pass

# After
from ..plugins.programming_language_extractor import ProgrammingLanguageExtractor

class PythonElementExtractor(ProgrammingLanguageExtractor):
    pass
```

**検証:**
- 各プラグインのテストが通過
- パフォーマンスベンチマーク維持
- Golden Master一致

### Phase 3: 未移行プログラミング言語の移行（1日）

**対象:** Go, Rust, Kotlin, PHP, Ruby (5プラグイン)

**プロセス:**
1. `ProgrammingLanguageExtractor`を継承
2. 重複コード削除
3. 言語固有のカスタマイズ
4. テスト実行

### Phase 4: マークアップ言語の移行（1日）

**対象:** Markdown, YAML, CSS, HTML (4プラグイン)

**プロセス:**
1. `MarkupLanguageExtractor`を継承
2. 既存の軽量実装を保持
3. `_traverse_nodes()`ヘルパーを活用
4. テスト実行

### Phase 5: 旧BaseElementExtractorの削除（0.5日）

**タスク:**
1. `base_element_extractor.py`の削除
2. インポート参照の更新
3. 最終テスト実行

---

## コード削減効果

### 現状（BaseElementExtractor使用）
- BaseElementExtractor: 497行
- 移行済みプラグイン7個: 各150行削減 = 1,050行削減
- **合計削減:** 1,050行

### 分層後
- CachedElementExtractor: 80行
- ProgrammingLanguageExtractor: 250行
- MarkupLanguageExtractor: 100行
- **基底クラス合計:** 430行（497行から67行削減）

### 追加削減効果
- 未移行プログラミング言語5個: 各150行削減 = 750行
- 未移行マークアップ言語4個: 各50行削減 = 200行
- **追加削減:** 950行

### 最終削減効果
- **合計削減:** 1,050 + 67 + 950 = **2,067行**
- **目標達成:** ✅ 2,000行以上削減

---

## リスク緩和

### リスク1: 移行済みプラグインの破壊

**緩和策:**
- 継承元を変更するだけ（実装は変更しない）
- 各プラグインを個別にテスト
- 問題があれば即座にロールバック

### リスク2: パフォーマンス劣化

**緩和策:**
- 各層でベンチマーク実行
- プロファイリングで分析
- 必要に応じて最適化

### リスク3: テスト失敗

**緩和策:**
- 段階的な移行（1プラグインずつ）
- Golden Masterテストで回帰検出
- CI/CDで自動検証

---

## 成功メトリクス

### 定量的
- ✅ 2,000行以上削減
- ✅ 全8,405テスト通過
- ✅ パフォーマンス±5%以内
- ✅ mypy 100%準拠

### 定性的
- ✅ 各層が単一責任を持つ
- ✅ 適切な抽象化レベル
- ✅ 新プラグイン追加が容易
- ✅ コードレビューが容易

---

## 次のステップ

1. ✅ この設計ドキュメントのレビュー
2. ⏳ Phase 1の実装開始（新しい層の作成）
3. ⏳ Phase 2の実装（移行済みプラグインの調整）
4. ⏳ Phase 3-5の実装（残りプラグインの移行）

---

## 参照

- [ARCHITECTURAL_SKEPTICISM_REPORT.md](.kiro/specs/plugin-base-class-extraction/ARCHITECTURAL_SKEPTICISM_REPORT.md)
- [design.md](.kiro/specs/plugin-base-class-extraction/design.md)
- [tasks.md](.kiro/specs/plugin-base-class-extraction/tasks.md)
- [progress.md](.kiro/specs/plugin-base-class-extraction/progress.md)
