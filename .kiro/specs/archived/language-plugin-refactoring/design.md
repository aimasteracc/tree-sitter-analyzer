# 言語プラグインリファクタリング - 設計仕様書

## 1. 設計目標

本設計の主な目標は、各言語プラグイン (`*_plugin.py`) に存在するコード重複を排除し、保守性と拡張性を向上させることです。具体的には、テンプレートメソッドパターンを活用して共通ロジックを基底クラスに集約し、各プラグインは言語固有の構文解析ルール（抽出ロジック）の定義に集中できるようにします。

## 2. アーキテクチャ概要

既存の `ProgrammingLanguageExtractor` クラスを拡張し、より高機能な基底クラスとして再定義します（または `BaseLanguagePlugin` として新設し、段階的に移行します）。

### 現行の構造
`ElementExtractor` (基底) <|-- `CachedElementExtractor` <|-- `ProgrammingLanguageExtractor` <|-- `PythonElementExtractor`, `JavaElementExtractor`, ...

### 提案する構造
継承関係は維持しつつ、`ProgrammingLanguageExtractor` に以下の責任を追加します。

1.  **標準化されたエントリポイント**: `extract_functions`, `extract_classes` などの共通実装。
2.  **ハンドラレジストリ**: ノードタイプと抽出メソッドのマッピング管理。
3.  **共通メタデータ抽出**: 行番号、テキスト、ドキュメント、複雑度などの一括抽出。
4.  **設定駆動**: 複雑度キーワードなどをメソッドオーバーライドではなく設定値として定義。

## 3. クラス設計詳細

### 3.1 `ProgrammingLanguageExtractor` の拡張

```python
class ProgrammingLanguageExtractor(CachedElementExtractor):
    def __init__(self):
        super().__init__()
        self.decision_keywords = self._get_default_decision_keywords()
        
    # --- テンプレートメソッド (共通実装) ---

    def extract_functions(self, tree, source_code) -> list[Function]:
        """
        全プラグイン共通の関数抽出エントリポイント
        """
        self._initialize_source(source_code)
        self._detect_file_characteristics() # フックメソッド
        
        functions = []
        handlers = self._get_function_handlers() # 抽象メソッド/フック
        
        if tree and tree.root_node:
            try:
                self._traverse_and_extract_iterative(
                    tree.root_node, handlers, functions, "function"
                )
                log_debug(f"Extracted {len(functions)} functions")
            except Exception as e:
                log_debug(f"Error: {e}")
                
        return functions

    def extract_classes(self, tree, source_code) -> list[Class]:
        """
        全プラグイン共通のクラス抽出エントリポイント
        """
        self._initialize_source(source_code)
        
        classes = []
        handlers = self._get_class_handlers() # 抽象メソッド/フック
        
        if tree and tree.root_node:
            try:
                self._traverse_and_extract_iterative(
                    tree.root_node, handlers, classes, "class"
                )
                log_debug(f"Extracted {len(classes)} classes")
            except Exception as e:
                log_debug(f"Error: {e}")
                
        return classes

    # --- 抽象メソッド / フックメソッド (サブクラスで実装) ---

    def _get_function_handlers(self) -> dict[str, Callable]:
        """
        ノードタイプとハンドラのマッピングを返す
        例: {"function_definition": self._extract_function_node}
        """
        return {}

    def _get_class_handlers(self) -> dict[str, Callable]:
        """
        ノードタイプとハンドラのマッピングを返す
        """
        return {}
    
    def _detect_file_characteristics(self) -> None:
        """
        ファイル特性（フレームワーク、モジュールタイプ等）の検出
        """
        pass

    # --- 共通ヘルパーメソッド ---

    def _extract_common_metadata(self, node: "tree_sitter.Node") -> dict:
        """
        あらゆるノードで共通のメタデータを抽出する
        """
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        
        return {
            "start_line": start_line,
            "end_line": end_line,
            "raw_text": self._extract_raw_text(start_line, end_line),
            "docstring": self._extract_docstring_for_node(node),
            "complexity": self._calculate_complexity_optimized(node)
        }

    def _extract_docstring_for_node(self, node) -> str | None:
        """
        デフォルトのドキュメント抽出戦略（行ベース）
        言語ごとにオーバーライド可能
        """
        start_line = node.start_point[0] + 1
        return self._extract_docstring_for_line(start_line)

    def _get_default_decision_keywords(self) -> set[str]:
        """
        デフォルトの決定キーワード（複雑度計算用）
        """
        return {"if", "for", "while", "case", "catch"}
```

### 3.2 各言語プラグインの実装イメージ (Pythonの例)

```python
class PythonElementExtractor(ProgrammingLanguageExtractor):
    def __init__(self):
        super().__init__()
        # Python固有の設定
        self.decision_keywords = {"if", "elif", "for", "while", "except", ...}

    def _get_function_handlers(self):
        return {
            "function_definition": self._extract_function_node,
            "async_function_definition": self._extract_function_node
        }

    def _extract_function_node(self, node):
        # 共通メタデータの取得
        meta = self._extract_common_metadata(node)
        
        # 言語固有のシグネチャ解析
        sig = self._parse_function_signature(node)
        if not sig: return None
        
        # モデル生成
        return Function(
            name=sig.name,
            start_line=meta["start_line"],
            end_line=meta["end_line"],
            raw_text=meta["raw_text"],
            docstring=meta["docstring"],
            complexity_score=meta["complexity"],
            parameters=sig.parameters,
            # ...
        )
```

## 4. リファクタリングによるメリット

1.  **コード量削減**: ボイラープレートコードが削除され、各プラグインは本質的なロジックのみになります。
2.  **一貫性の向上**: エラーハンドリング、ログ出力、基本メタデータの抽出が全言語で統一されます。
3.  **拡張性**: 新しい言語を追加する際、`_get_X_handlers` と個別の抽出ロジックを実装するだけで済みます。
4.  **保守性**: バグ修正（例：複雑度計算のロジック修正）を一箇所で行えば全言語に反映されます。

## 5. 考慮事項と制約

*   **後方互換性**: 既存の `extract_X` メソッドのシグネチャと戻り値は変更しません。
*   **段階的移行**: 一度に全プラグインを書き換えるのではなく、基底クラスを拡張した後、1言語ずつ移行します。
*   **特殊ケース**: SQLプラグインの `extract_functions` はプロシージャやトリガーも含むため、テンプレートメソッドの適用には注意が必要です（デフォルト実装をオーバーライドするか、ハンドラで柔軟に対応する）。

## 6. テスト戦略

1.  **リグレッションテスト**: 既存のテストスイート（`tests/`）をそのまま使用し、リファクタリング前後で出力が変わらないことを確認します。
2.  **ゴールデンマスターテスト**: `examples/` ディレクトリ内のサンプルファイルに対し、リファクタリング前の解析結果を保存し、リファクタリング後の結果と完全一致することを検証します。
