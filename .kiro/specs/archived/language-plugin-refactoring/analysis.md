# 言語プラグインのコード重複分析

## 概要

`tree_sitter_analyzer/languages/` ディレクトリ内の主要な言語プラグイン（Python, Java, JavaScript, TypeScript, SQL）を分析し、コードの重複と共通パターンを特定しました。本ドキュメントでは、その詳細とリファクタリングの機会について報告します。

## 分析対象ファイル

- `python_plugin.py`
- `java_plugin.py`
- `javascript_plugin.py`
- `typescript_plugin.py`
- `sql_plugin.py`
- `../plugins/programming_language_extractor.py` (基底クラス)

## 主要な重複パターン

### 1. エントリポイントメソッドのボイラープレート

ほとんどのプラグインで、`extract_functions`, `extract_classes` などのエントリポイントメソッドが、ほぼ同じ構造を持っています。

**共通パターン:**
```python
def extract_X(self, tree, source_code):
    self._initialize_source(source_code)
    # (オプション) 言語固有の初期化
    
    elements = []
    extractors = {
        "node_type_1": self._handler_1,
        "node_type_2": self._handler_2,
    }
    
    if tree and tree.root_node:
        try:
            self._traverse_and_extract_iterative(
                tree.root_node, extractors, elements, "element_type"
            )
            log_debug(...)
        except ...:
            log_debug(...)
            
    return elements
```

**影響:**
新しい要素タイプを追加するたびに、このボイラープレートをコピー＆ペーストする必要があります。

### 2. 要素抽出ハンドラの構造 (`_extract_X_optimized`)

個々のノードを処理するハンドルメソッドも、非常に似通った構造をしています。

**共通パターン:**
1. `try-except` ブロックによる全体のエラーハンドリング
2. `start_line`, `end_line` の取得 (`node.start_point[0] + 1` など)
3. シグネチャ解析ヘルパーの呼び出し (`_parse_X_signature`)
4. ドキュメントコメントの抽出 (`_extract_docstring_for_line`)
5. 複雑度計算 (`_calculate_complexity_optimized`)
6. 生テキストの抽出 (`raw_text`)
7. モデルオブジェクト (`Function`, `Class` 等) の生成と返却

**リファクタリングの機会:**
共通のメタデータ（行番号、生テキスト、ドキュメント、複雑度）を抽出するロジックを一元化できます。

### 3. 複雑度計算 (`_calculate_complexity_optimized`)

基底クラス `ProgrammingLanguageExtractor` にデフォルト実装がありますが、多くのプラグインでオーバーライドされています。しかし、その内容は「決定ポイントとなるキーワードのリスト」が異なるだけで、走査ロジック自体は同じです。

**Python:**
```python
keywords = ["if", "elif", "while", "for", "except", "and", "or", ...]
```

**Java:**
```python
decision_nodes = ["if_statement", "while_statement", "for_statement", "switch_statement", ...]
```

**Javascript/TypeScript:**
決定キーワードやノードタイプが異なるのみ。

**リファクタリングの機会:**
キーワードやノードタイプのリストを設定として持たせ、ロジック自体は基底クラスに集約できます。

### 4. ドキュメントコメント抽出

Pythonの `_extract_docstring_for_line` と JS/TS の `_extract_jsdoc_for_line` / `_extract_tsdoc_for_line` は、実装詳細（クォートの種類やコメント記号）は異なりますが、「特定の行に関連するコメントブロックを探す」という目的とアプローチは共通しています。

### 5. ASTノードからのテキスト抽出

`self._get_node_text_optimized(node)` の呼び出しや、バイト範囲を使用したテキスト抽出処理が各所に散在しています。

## 言語固有の差異（考慮事項）

リファクタリング時に注意すべき固有の差異も特定されました。

1.  **インポート処理:**
    *   **Python:** `import X`, `from X import Y` (モジュールパスとシンボルの分離)
    *   **Java:** `import package.Class`, `import static ...` (完全修飾名が主)
    *   **JS/TS:** `import { X } from 'path'`, `require('path')`, default/named/namespace imports (構造が複雑)
    *   **SQL:** クロススキーマ参照としてのインポート概念

2.  **変数/フィールド宣言:**
    *   **Python:** クラス属性としての代入文解析
    *   **Java:** 型宣言を含むフィールド宣言、修飾子 (`private`, `static` 等)
    *   **JS/TS:** `var`, `let`, `const`, 分割代入 (`const {a, b} = obj`)
    *   **SQL:** インデックスを変数として扱う特殊なマッピング

3.  **型システム:**
    *   動的型付け (Python, JS) vs 静的型付け (Java, TS)
    *   ジェネリクスの扱い (Java, TS)

## 結論

コードベースには大幅な重複があり、共通基底クラスの強化によって保守性と拡張性を大きく向上させることができます。特に、AST走査のボイラープレートと、標準的なメタデータ抽出処理の共通化が最も効果的です。

一方で、`extract_imports` やシグネチャ解析の詳細部分 (`_parse_function_signature` 等) は言語ごとの構文差が大きいため、無理に共通化せず、抽象メソッドまたはフックメソッドとして各言語に実装を委ねるのが適切です。
