# Code Quality Issues - Tree-sitter Analyzer

**Review Date:** 2026-01-15  
**Reviewer:** Code Skeptic Mode  
**Scope:** `tree_sitter_analyzer/` directory

---

## Executive Summary

徹底的なコードレビューの結果、**重大な品質問題**を多数発見しました。このプロジェクトには以下の深刻な問題があります：

- **極めて高い複雑性**: 複数の関数が複雑度50以上
- **過度な例外処理**: 489箇所の`except Exception`
- **巨大なファイル**: 800行を超えるファイルが複数存在
- **重複コード**: 同じロジックが複数箇所に散在
- **グローバル変数の乱用**: 8箇所でグローバル変数を使用
- **テスト可能性の欠如**: 密結合により単体テストが困難

---

## 🔴 Critical Issues (優先度: 高)

### 1. 極めて高い循環的複雑度

**ファイル:** [`tree_sitter_analyzer/api.py`](tree_sitter_analyzer/api.py:1)

**問題:**
- [`analyze_file()`](tree_sitter_analyzer/api.py:37-192): **複雑度 54** (156行)
- [`analyze_code()`](tree_sitter_analyzer/api.py:195-329): **複雑度 45** (135行)

**詳細:**
これらの関数は**許容できないほど複雑**です。一般的に、循環的複雑度は10以下が推奨され、15を超えると保守が困難になります。54と45は**異常に高い**値です。

**影響:**
- バグの温床となる
- テストが困難
- 変更時のリスクが極めて高い
- 新規開発者の理解が困難

**推奨事項:**
1. 関数を小さな責務に分割
2. 要素変換ロジックを別関数に抽出
3. エラーハンドリングを統一
4. Strategy パターンの適用を検討

**カテゴリ:** 複雑性  
**優先度:** 🔴 高

---

### 2. 巨大なファイル - MCP Server

**ファイル:** [`tree_sitter_analyzer/mcp/server.py`](tree_sitter_analyzer/mcp/server.py:1)

**問題:**
- **831行** の巨大ファイル
- 複数の責務が混在（サーバー管理、ツール実行、リソース管理）
- [`_analyze_code_scale()`](tree_sitter_analyzer/mcp/server.py:185-349): 165行の巨大メソッド

**詳細:**
このファイルは以下の責務を持っています：
1. MCPサーバーの初期化と設定
2. ツールの登録と実行
3. リソースの管理
4. セキュリティ検証
5. ファイル解析ロジック

**影響:**
- 単一責任原則(SRP)違反
- テストが困難
- 変更の影響範囲が不明確
- マージコンフリクトのリスク

**推奨事項:**
1. ツール実行ロジックを別クラスに分離
2. リソース管理を専用クラスに移動
3. サーバー設定を設定クラスに抽出
4. ファイルを300行以下に分割

**カテゴリ:** ファイルサイズ、複雑性  
**優先度:** 🔴 高

---

### 3. 巨大なファイル - CLI Main

**ファイル:** [`tree_sitter_analyzer/cli_main.py`](tree_sitter_analyzer/cli_main.py:1)

**問題:**
- **649行** の巨大ファイル
- [`handle_special_commands()`](tree_sitter_analyzer/cli_main.py:302-580): 279行の巨大関数
- [`create_argument_parser()`](tree_sitter_analyzer/cli_main.py:99-299): 201行の巨大関数

**詳細:**
CLIの引数解析、コマンド実行、特殊処理が全て1ファイルに集中しています。

**影響:**
- 新しいコマンド追加が困難
- テストカバレッジの低下
- コマンド間の依存関係が不明確

**推奨事項:**
1. コマンドごとにファイルを分割
2. 引数解析を専用モジュールに移動
3. 特殊コマンドをプラグイン化
4. Command パターンの適用

**カテゴリ:** ファイルサイズ、複雑性  
**優先度:** 🔴 高

---

### 4. 過度な例外処理 - Bare Exception

**全体的な問題:**

**統計:**
- **489箇所** で `except Exception` を使用
- 特に多いファイル：
  - [`languages/markdown_plugin.py`](tree_sitter_analyzer/languages/markdown_plugin.py:1): 39箇所
  - [`languages/typescript_plugin.py`](tree_sitter_analyzer/languages/typescript_plugin.py:1): 24箇所
  - [`languages/sql_plugin.py`](tree_sitter_analyzer/languages/sql_plugin.py:1): 23箇所
  - [`languages/javascript_plugin.py`](tree_sitter_analyzer/languages/javascript_plugin.py:1): 23箇所
  - [`languages/python_plugin.py`](tree_sitter_analyzer/languages/python_plugin.py:1): 22箇所

**問題:**
```python
try:
    # 何らかの処理
except Exception as e:
    # 全ての例外を捕捉
    log_error(f"Error: {e}")
```

**詳細:**
`except Exception` は以下の問題を引き起こします：
1. **KeyboardInterrupt** や **SystemExit** も捕捉してしまう
2. 予期しないエラーを隠蔽
3. デバッグが困難
4. エラーの根本原因が不明確

**影響:**
- バグの発見が遅れる
- 本番環境での予期しない動作
- デバッグ時間の増加
- ユーザーへの不適切なエラーメッセージ

**推奨事項:**
1. 具体的な例外型を指定（`FileNotFoundError`, `ValueError` など）
2. 予期しない例外は再スロー
3. ログレベルを適切に設定
4. カスタム例外クラスの作成

**カテゴリ:** エラーハンドリング  
**優先度:** 🔴 高

---

### 5. 巨大な関数 - Analysis Engine

**ファイル:** [`tree_sitter_analyzer/core/analysis_engine.py`](tree_sitter_analyzer/core/analysis_engine.py:1)

**問題:**
- [`analyze_file()`](tree_sitter_analyzer/core/analysis_engine.py:174-237): 64行、複雑な条件分岐
- [`analyze_code_sync()`](tree_sitter_analyzer/core/analysis_engine.py:292-342): 51行、ネストした例外処理

**詳細:**
[`analyze_code_sync()`](tree_sitter_analyzer/core/analysis_engine.py:292) は以下の問題があります：
```python
def analyze_code_sync(self, code: str, language: str, ...) -> Any:
    try:
        asyncio.get_running_loop()
        # イベントループが実行中の場合
        import concurrent.futures
        def run_in_new_loop() -> Any:
            new_loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(new_loop)
                return new_loop.run_until_complete(...)
            finally:
                new_loop.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run_in_new_loop)
            return future.result(timeout=60)
    except RuntimeError:
        return asyncio.run(self.analyze_code(code, language, filename, request))
```

**影響:**
- 非同期処理の複雑性が高い
- デッドロックのリスク
- テストが困難
- パフォーマンスの問題

**推奨事項:**
1. 同期/非同期を明確に分離
2. イベントループ管理を専用クラスに移動
3. タイムアウト処理を統一
4. 非同期コンテキストの検出ロジックを改善

**カテゴリ:** 複雑性、非同期処理  
**優先度:** 🔴 高

---

## 🟡 Major Issues (優先度: 中)

### 6. 重複コード - Element Conversion

**ファイル:** [`tree_sitter_analyzer/api.py`](tree_sitter_analyzer/api.py:1)

**問題:**
[`analyze_file()`](tree_sitter_analyzer/api.py:100-162) と [`analyze_code()`](tree_sitter_analyzer/api.py:241-303) で**同じ要素変換ロジック**が重複しています。

**重複コード例:**
```python
# analyze_file() 内
for elem in analysis_result.elements:
    elem_dict = {
        "name": elem.name,
        "type": type(elem).__name__.lower(),
        "start_line": elem.start_line,
        # ... 40行以上の同じコード
    }
    elements_list.append(elem_dict)

# analyze_code() 内
for elem in analysis_result.elements:
    elem_dict = {
        "name": elem.name,
        "type": type(elem).__name__.lower(),
        "start_line": elem.start_line,
        # ... 40行以上の同じコード
    }
    elements_list.append(elem_dict)
```

**影響:**
- DRY原則違反
- バグ修正時に2箇所修正が必要
- 保守コストの増加

**推奨事項:**
1. `_convert_element_to_dict()` ヘルパー関数を作成
2. 共通ロジックを抽出
3. 単体テストを追加

**カテゴリ:** 重複コード  
**優先度:** 🟡 中

---

### 7. グローバル変数の使用

**問題:**
8箇所でグローバル変数を使用：
- [`api.py`](tree_sitter_analyzer/api.py:21): `_engine`
- [`language_loader.py`](tree_sitter_analyzer/language_loader.py:1): グローバルローダー
- [`query_loader.py`](tree_sitter_analyzer/query_loader.py:1): グローバルクエリローダー
- [`output_manager.py`](tree_sitter_analyzer/output_manager.py:1): グローバル出力設定

**詳細:**
```python
# api.py
_engine: UnifiedAnalysisEngine | None = None

def get_engine() -> UnifiedAnalysisEngine:
    global _engine
    if _engine is None:
        _engine = UnifiedAnalysisEngine()
    return _engine
```

**影響:**
- テストの独立性が損なわれる
- 並行処理時の競合リスク
- 状態管理が困難
- モックが困難

**推奨事項:**
1. 依存性注入(DI)パターンの採用
2. シングルトンパターンをクラスベースに変更
3. コンテキストマネージャーの使用
4. テスト用のファクトリー関数を提供

**カテゴリ:** 設計、テスト可能性  
**優先度:** 🟡 中

---

### 8. 深いネスト - Query Service

**ファイル:** [`tree_sitter_analyzer/core/query_service.py`](tree_sitter_analyzer/core/query_service.py:1)

**問題:**
[`_execute_plugin_query()`](tree_sitter_analyzer/core/query_service.py:191-278) メソッドに**5段階のネスト**があります。

**詳細:**
```python
def _execute_plugin_query(self, root_node, query_key, language, source_code):
    captures = []
    plugin = self.plugin_manager.get_plugin(language)
    if not plugin:  # Level 1
        return self._fallback_query_execution(root_node, query_key)
    try:  # Level 2
        elements = plugin.execute_query_strategy(source_code, query_key or "function")
        if elements:  # Level 3
            for element in elements:  # Level 4
                if hasattr(element, "start_line") and hasattr(element, "end_line"):  # Level 5
                    # 処理
```

**影響:**
- 可読性の低下
- テストが困難
- バグの混入リスク

**推奨事項:**
1. Early return パターンの使用
2. ヘルパーメソッドへの分割
3. ネストを3段階以下に制限

**カテゴリ:** 複雑性、可読性  
**優先度:** 🟡 中

---

### 9. 長いパラメータリスト

**ファイル:** [`tree_sitter_analyzer/core/analysis_engine.py`](tree_sitter_analyzer/core/analysis_engine.py:1)

**問題:**
[`analyze_file()`](tree_sitter_analyzer/core/analysis_engine.py:174-237) メソッドが**9個のパラメータ**を持っています。

**詳細:**
```python
async def analyze_file(
    self,
    file_path: str,
    language: str | None = None,
    request: AnalysisRequest | None = None,
    format_type: str | None = None,
    include_details: bool | None = None,
    include_complexity: bool | None = None,
    include_elements: bool | None = None,
    include_queries: bool | None = None,
    queries: list[str] | None = None,
) -> Any:
```

**影響:**
- 関数呼び出しが複雑
- パラメータの順序を間違えやすい
- 後方互換性の維持が困難

**推奨事項:**
1. パラメータオブジェクトパターンの使用
2. `AnalysisRequest` に全てのオプションを集約
3. ビルダーパターンの検討

**カテゴリ:** 設計、可読性  
**優先度:** 🟡 中

---

### 10. 巨大なクラス - Plugin Base

**ファイル:** [`tree_sitter_analyzer/plugins/base.py`](tree_sitter_analyzer/plugins/base.py:1)

**問題:**
- **651行** の巨大ファイル
- [`DefaultExtractor`](tree_sitter_analyzer/plugins/base.py:334-609) クラス: 276行
- 複数の責務が混在

**詳細:**
`DefaultExtractor` は以下を全て実装：
- 関数抽出
- クラス抽出
- 変数抽出
- インポート抽出
- ノード走査
- テキスト抽出

**影響:**
- 単一責任原則違反
- テストが困難
- 拡張が困難

**推奨事項:**
1. 抽出ロジックを言語ごとに分離
2. ノード走査を専用クラスに移動
3. テンプレートメソッドパターンの適用

**カテゴリ:** クラスサイズ、設計  
**優先度:** 🟡 中

---

## 🟢 Minor Issues (優先度: 低)

### 11. 不適切な命名

**ファイル:** [`tree_sitter_analyzer/api.py`](tree_sitter_analyzer/api.py:1)

**問題:**
- [`_group_captures_by_main_node()`](tree_sitter_analyzer/api.py:542-616): 75行の「ヘルパー」関数
- プライベート関数が複雑すぎる

**推奨事項:**
1. 複雑なプライベート関数はクラスに昇格
2. 責務を明確にする命名

**カテゴリ:** 命名、設計  
**優先度:** 🟢 低

---

### 12. マジックナンバー

**ファイル:** [`tree_sitter_analyzer/core/parser.py`](tree_sitter_analyzer/core/parser.py:1)

**問題:**
```python
_cache: LRUCache = LRUCache(maxsize=100)  # なぜ100?
```

**推奨事項:**
1. 定数として定義
2. 設定ファイルから読み込み

**カテゴリ:** 保守性  
**優先度:** 🟢 低

---

### 13. ドキュメント不足

**全体的な問題:**

**統計:**
- 多くの関数にdocstringが存在するが、**実装の詳細**が不足
- 複雑なアルゴリズムの説明がない
- エラーケースの記載がない

**推奨事項:**
1. 複雑な関数には実装の詳細を追加
2. エラーケースを明記
3. 使用例を追加

**カテゴリ:** ドキュメント  
**優先度:** 🟢 低

---

## 📊 統計サマリー

| カテゴリ | 件数 | 優先度 |
|---------|------|--------|
| 極めて高い複雑度 | 2 | 🔴 高 |
| 巨大ファイル | 3 | 🔴 高 |
| 過度な例外処理 | 489 | 🔴 高 |
| 重複コード | 1 | 🟡 中 |
| グローバル変数 | 8 | 🟡 中 |
| 深いネスト | 1 | 🟡 中 |
| 長いパラメータリスト | 1 | 🟡 中 |
| 巨大クラス | 1 | 🟡 中 |
| 不適切な命名 | 1 | 🟢 低 |
| マジックナンバー | 1 | 🟢 低 |
| ドキュメント不足 | 多数 | 🟢 低 |

---

## 🎯 優先的に対処すべき問題

### 即座に対処すべき（1週間以内）

1. **[`api.py`](tree_sitter_analyzer/api.py:1) の複雑度削減**
   - [`analyze_file()`](tree_sitter_analyzer/api.py:37) と [`analyze_code()`](tree_sitter_analyzer/api.py:195) を分割
   - 要素変換ロジックを共通化

2. **例外処理の改善**
   - 最も使用頻度の高いファイルから着手
   - 具体的な例外型を指定

3. **[`mcp/server.py`](tree_sitter_analyzer/mcp/server.py:1) の分割**
   - ツール実行ロジックを分離
   - 400行以下に削減

### 中期的に対処すべき（1ヶ月以内）

4. **グローバル変数の削除**
   - 依存性注入パターンの導入
   - テスト可能性の向上

5. **[`cli_main.py`](tree_sitter_analyzer/cli_main.py:1) のリファクタリング**
   - コマンドパターンの適用
   - 300行以下に削減

6. **重複コードの削除**
   - 共通ロジックの抽出
   - ヘルパー関数の作成

### 長期的に対処すべき（3ヶ月以内）

7. **アーキテクチャの改善**
   - レイヤードアーキテクチャの導入
   - 依存関係の整理

8. **テストカバレッジの向上**
   - 複雑な関数の単体テスト追加
   - 統合テストの強化

9. **ドキュメントの充実**
   - アーキテクチャドキュメント作成
   - API仕様書の整備

---

## 🔍 レビュー方法論

このレビューでは以下の手法を使用しました：

1. **静的解析**
   - Tree-sitter Analyzer自身を使用してコード構造を分析
   - 循環的複雑度の計算
   - ファイルサイズとメトリクスの測定

2. **パターン検索**
   - `except Exception` の検索
   - グローバル変数の検索
   - TODO/FIXME コメントの検索

3. **手動レビュー**
   - 主要ファイルの詳細読解
   - アーキテクチャの評価
   - 設計パターンの確認

---

## 📝 結論

このプロジェクトは**機能的には動作している**ものの、**保守性と拡張性に重大な問題**があります。

**最も深刻な問題:**
1. 複雑度54の関数が存在（業界標準の5倍以上）
2. 489箇所の不適切な例外処理
3. 800行を超える巨大ファイルが複数存在

**推奨アクション:**
1. **即座に**: 複雑度の高い関数を分割
2. **1週間以内**: 例外処理を改善
3. **1ヶ月以内**: 巨大ファイルを分割
4. **3ヶ月以内**: アーキテクチャを再設計

これらの問題に対処することで、コードの品質、保守性、テスト可能性が大幅に向上します。

---

## 🔴 High-Level Architecture & Design Issues (優先度: 高)

### 14. グローバルシングルトンパターンの問題

**ファイル:** [`tree_sitter_analyzer/api.py`](tree_sitter_analyzer/api.py:21)

**問題:**
```python
# Global engine instance (singleton pattern)
_engine: UnifiedAnalysisEngine | None = None

def get_engine() -> UnifiedAnalysisEngine:
    """Get the global analysis engine instance."""
    global _engine
    if _engine is None:
        _engine = UnifiedAnalysisEngine()
    return _engine
```

**詳細:**
グローバル変数を使用したシングルトンパターンは以下の問題を引き起こします：
1. **テスト可能性が低い**: テスト間でエンジンインスタンスが共有される
2. **依存性注入ができない**: コンポーネントがエンジンに密結合
3. **並行処理時の競合リスク**: 複数のスレッドが同時にエンジンにアクセス
4. **状態管理が困難**: エンジンのライフサイクルが不明確

**影響:**
- テストの独立性が損なわれる
- 並行処理時の予期しない動作
- 新しい機能追加の困難さ

**推奨事項:**
1. 依存性注入(DI)パターンの採用
2. エンジンをファクトリー関数経由で提供
3. コンテキストマネージャーの使用
4. テスト用のファクトリー関数を提供

**カテゴリ:** アーキテクチャ、設計  
**優先度:** 🔴 高

---

### 15. 複雑な同期/非同期処理の設計

**ファイル:** [`tree_sitter_analyzer/core/analysis_engine.py`](tree_sitter_analyzer/core/analysis_engine.py:292-342)

**問題:**
```python
def analyze_code_sync(
    self,
    code: str,
    language: str,
    filename: str = "string",
    request: AnalysisRequest | None = None,
) -> Any:
    """
    Sync version of analyze_code.
    
    注意: この同期メソッドは以下のケースを安全に処理します：
    1. イベントループが実行されていない場合: asyncio.run() を使用
    2. イベントループが実行中の場合: 別スレッドで新しいループを作成して実行
    
    警告: 非同期コンテキスト内からこのメソッドを呼び出すことは推奨されません。
    可能な限り analyze_code() を直接 await してください。
    """
    try:
        asyncio.get_running_loop()
        # イベントループが実行中の場合
        # 別スレッドで新しいイベントループを作成して実行
        # これは追加リソースを消費しますが、デッドロックを回避します
        import concurrent.futures

        def run_in_new_loop() -> Any:
            """新しいイベントループでコルーチンを実行"""
            new_loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(new_loop)
                return new_loop.run_until_complete(
                    self.analyze_code(code, language, filename, request)
                )
            finally:
                new_loop.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run_in_new_loop)
            return future.result(timeout=60)

    except RuntimeError:
        # イベントループが実行されていない場合、asyncio.run() を安全に使用
        return asyncio.run(self.analyze_code(code, language, filename, request))
```

**詳細:**
同期/非同期処理の複雑な設計は以下の問題を引き起こします：
1. **イベントループ検出の複雑さ**: `asyncio.get_running_loop()`で検出
2. **スレッドプールの使用**: 新しいスレッドでイベントループを作成
3. **タイムアウト処理**: 60秒のハードコードされたタイムアウト
4. **リソースの追加消費**: 新しいイベントループとスレッドの作成

**影響:**
- デッドロックのリスク
- パフォーマンスの低下
- テストが困難
- 理解しにくいコード

**推奨事項:**
1. 同期/非同期を明確に分離
2. イベントループ管理を専用クラスに移動
3. タイムアウト処理を統一
4. 非同期コンテキストの検出ロジックを改善

**カテゴリ:** アーキテクチャ、非同期処理  
**優先度:** 🔴 高

---

### 16. 責務の分離が不十分なAPI関数

**ファイル:** [`tree_sitter_analyzer/api.py`](tree_sitter_analyzer/api.py:137-252)

**問題:**
[`analyze_file()`](tree_sitter_analyzer/api.py:137)関数が以下の多くの責務を持っています：
1. エンジンの取得
2. リクエストの作成
3. 解析の実行
4. 結果の変換（辞書形式への変換）
5. エラーハンドリング
6. 結果のフィルタリング
7. 成功/失敗の判断

**詳細:**
```python
def analyze_file(
    file_path: str | Path,
    language: str | None = None,
    queries: list[str] | None = None,
    include_elements: bool = True,
    include_details: bool = False,
    include_queries: bool = True,
    include_complexity: bool = False,
) -> dict[str, Any]:
    """Analyze a source code file."""
    try:
        engine = get_engine()
        
        # Create analysis request
        request = AnalysisRequest(...)
        
        # Perform the analysis using sync method
        analysis_result = engine.analyze_sync(request)
        
        # Convert AnalysisResult to expected API format (same as analyze_code)
        result = {
            "success": analysis_result.success,
            "file_info": {...},
            "language_info": {...},
            "ast_info": {...},
        }
        
        # If analysis failed but we have a result, return it
        if not analysis_result.success:
            if analysis_result.error_message:
                result["error"] = analysis_result.error_message
            return result
            
        if include_elements:
            result["elements"] = _convert_elements_to_list(analysis_result)
            
        # Add query results if requested and available
        if include_queries and hasattr(analysis_result, "query_results"):
            result["query_results"] = analysis_result.query_results
            
        # Add error message if analysis failed
        if not analysis_result.success and analysis_result.error_message:
            result["error"] = analysis_result.error_message
            
        # Filter results based on options
        if not include_elements and "elements" in result:
            del result["elements"]
            
        if not include_queries and "query_results" in result:
            del result["query_results"]
            
        return result
        
    except FileNotFoundError:
        raise
    except (OSError, IOError) as e:
        log_error(f"File system error in analyze_file: {e}")
        return {...}
    except (ValueError, TypeError) as e:
        log_error(f"Invalid input in analyze_file: {e}")
        return {...}
    except Exception as e:
        log_error(f"Unexpected error in analyze_file: {e}")
        return {...}
```

**影響:**
- 単一責任原則違反
- テストが困難
- 変更時の影響範囲が不明確
- 新しい機能追加の困難さ

**推奨事項:**
1. 関数を小さな責務に分割
2. 結果ビルダーパターンの使用
3. エラーハンドリングを統一
4. Strategy パターンの適用を検討

**カテゴリ:** 設計、複雑性  
**優先度:** 🔴 高

---

### 17. プラグインシステムの設計上の問題

**ファイル:** [`tree_sitter_analyzer/plugins/manager.py`](tree_sitter_analyzer/plugins/manager.py:101-236)

**問題:**
プラグインマネージャーで複雑なプラグイン発見とロードのロジックが混在しています：
1. `_discover_from_entry_points()`と `_load_from_entry_points()`が重複
2. 遅延ロードと即時ロードのロジックが混在
3. プラグインのエイリアス処理が不十分

**詳細:**
```python
def load_plugins(self) -> list[LanguagePlugin]:
    """
    Discover available plugins without fully loading them for performance.
    They will be lazily loaded in get_plugin().
    """
    if self._discovered:
        return list(self._loaded_plugins.values())
    
    # Discover plugins from entry points (only metadata scan)
    if _should_load_entry_points():
        self._discover_from_entry_points()
    
    # Discover local plugins (only metadata scan)
    self._discover_from_local_directory()
    
    self._discovered = True
    return list(self._loaded_plugins.values())

def _discover_from_entry_points(self) -> None:
    """Discover plugins from setuptools entry points without loading classes."""
    try:
        # We use a special mapping for entry points to load them later
        self._entry_point_map: dict[str, Any] = {}
        entry_points = importlib.metadata.entry_points()
        
        plugin_entries: Any = []
        if hasattr(entry_points, "select"):
            plugin_entries = entry_points.select(group=self._entry_point_group)
        elif hasattr(entry_points, "get"):
            result = entry_points.get(self._entry_point_group)
            plugin_entries = list(result) if result else []
            
        for entry_point in plugin_entries:
            # We can't know language without loading,
            # so we might have to load entry points or use their names as hints
            lang_hint = entry_point.name.lower()
            self._entry_point_map[lang_hint] = entry_point
            log_debug(f"Discovered entry point plugin: {entry_point.name}")
    except Exception as e:
        log_warning(f"Failed to discover plugins from entry points: {e}")

def _load_from_entry_points(self) -> list[LanguagePlugin]:
    """
    Load plugins from setuptools entry points.
    
    Returns:
        List of plugin instances loaded from entry points
    """
    plugins = []
    
    try:
        # Get entry points for our plugin group
        entry_points = importlib.metadata.entry_points()
        
        # Handle both old and new entry_points API
        plugin_entries: Any = []
        if hasattr(entry_points, "select"):
            plugin_entries = entry_points.select(group=self._entry_point_group)
        else:
            # Old API - handle different return types
            try:
                if hasattr(entry_points, "get"):
                    result = entry_points.get(self._entry_point_group)
                    plugin_entries = list(result) if result else []
                else:
                    plugin_entries = []
            except (TypeError, AttributeError):
                plugin_entries = []
        
        for entry_point in plugin_entries:
            try:
                # Load plugin class
                plugin_class = entry_point.load()
                
                # Validate it's a LanguagePlugin
                if not issubclass(plugin_class, LanguagePlugin):
                    log_warning(f"Entry point {entry_point.name} is not a LanguagePlugin")
                    continue
                
                # Create instance
                plugin_instance = plugin_class()
                plugins.append(plugin_instance)
                
                log_debug(f"Loaded plugin from entry point: {entry_point.name}")
                
            except Exception as e:
                log_error(f"Failed to load plugin from entry point {entry_point.name}: {e}")
    except Exception as e:
        log_warning(f"Failed to load plugins from entry points: {e}")
    
    return plugins
```

**影響:**
- プラグインの発見とロードのロジックが重複
- 拡張性が低い
- テストが困難
- 新しいプラグインの追加が困難

**推奨事項:**
1. プラグインの発見とロードを統一
2. エイリアス処理を設定ファイルから読み込み
3. プラグインのライフサイクルを明確に定義
4. プラグインの依存関係を管理

**カテゴリ:** アーキテクチャ、設計  
**優先度:** 🔴 高

---

### 18. フォーマットシステムの設計上の問題

**ファイル:** [`tree_sitter_analyzer/formatters/formatter_registry.py`](tree_sitter_analyzer/formatters/formatter_registry.py:20-285)

**問題:**
2つの異なるインターフェースが混在しています：
1. `IFormatter` - CodeElementリスト用
2. `IStructureFormatter` - 辞書データ用

**詳細:**
```python
class IFormatter(ABC):
    """
    Interface for code element formatters.
    
    All formatters must implement this interface to be compatible
    with FormatterRegistry system.
    """
    
    @staticmethod
    @abstractmethod
    def get_format_name() -> str:
        """Return format name this formatter supports."""
        pass
    
    @abstractmethod
    def format(self, elements: list[CodeElement]) -> str:
        """Format a list of CodeElements into a string representation."""
        pass

class IStructureFormatter(ABC):
    """
    Interface for structure-based formatters (legacy compatibility).
    
    These formatters accept dict-based structure data instead of CodeElement lists.
    Used for backward compatibility with v1.6.1.4 format output.
    """
    
    @abstractmethod
    def format_structure(self, structure_data: dict[str, Any]) -> str:
        """Format structure data dictionary into a string representation."""
        pass
```

**影響:**
- どちらのインターフェースを使用すべきか不明確
- 後方互換性のために複雑さが増加
- 新しいフォーマットの追加が困難

**推奨事項:**
1. 2つのインターフェースを統一
2. 後方互換性レイヤーを分離
3. フォーマットの責務を明確に定義
4. アダプターパターンの適用

**カテゴリ:** 設計、アーキテクチャ  
**優先度:** 🔴 高

---

## 🟡 Major Performance Issues (優先度: 中)

### 19. 非効率的な木構造走査アルゴリズム

**ファイル:** [`tree_sitter_analyzer/core/query_service.py`](tree_sitter_analyzer/core/query_service.py:351-396)

**問題:**
[`_fallback_query_execution()`](tree_sitter_analyzer/core/query_service.py:351)メソッドで再帰的な木構造の走査を使用しています。

**詳細:**
```python
def _fallback_query_execution(
    self, root_node: Any, query_key: str | None
) -> list[tuple[Any, str]]:
    """
    Basic fallback query execution for unsupported languages
    
    Args:
        root_node: Root node of the parsed tree
        query_key: Query key to execute
        
    Returns:
        List of (node, capture_name) tuples
    """
    captures = []
    
    def walk_tree_basic(node: Any) -> None:
        """Basic tree walking for unsupported languages"""
        # Get node type safely
        node_type = getattr(node, "type", "")
        if not isinstance(node_type, str):
            node_type = str(node_type)
        
        # Generic node type matching (support both singular and plural forms)
        if (
            query_key in ("function", "functions")
            and "function" in node_type
            or query_key in ("class", "classes")
            and "class" in node_type
            or query_key in ("method", "methods")
            and "method" in node_type
            or query_key in ("variable", "variables")
            and "variable" in node_type
            or query_key in ("import", "imports")
            and "import" in node_type
            or query_key in ("header", "headers")
            and "heading" in node_type
        ):
            captures.append((node, query_key))
        
        # Recursively process children
        children = getattr(node, "children", [])
        for child in children:
            walk_tree_basic(child)
    
    walk_tree_basic(root_node)
    return captures
```

**影響:**
- 大きなファイルでパフォーマンスが低下
- 再帰の深さ制限がない
- スタックオーバーフローのリスク
- メモリ使用量が増加

**推奨事項:**
1. 反復的な木構造走査に変更
2. 深さ制限を追加
3. ノードタイプの判定をキャッシュ
4. 早期終了条件を追加

**カテゴリ:** パフォーマンス、アルゴリズム  
**優先度:** 🟡 中

---

### 20. 分散したキャッシュ管理システム

**ファイル:** [`tree_sitter_analyzer/languages/python_plugin.py`](tree_sitter_analyzer/languages/python_plugin.py:45-58), [`tree_sitter_analyzer/languages/java_plugin.py`](tree_sitter_analyzer/languages/java_plugin.py:37-48), [`tree_sitter_analyzer/languages/javascript_plugin.py`](tree_sitter_analyzer/languages/javascript_plugin.py:44-57)

**問題:**
各言語プラグインが独自のキャッシュを持っており、統一されたキャッシュ管理システムがありません。

**詳細:**
```python
# Python Plugin
class PythonElementExtractor(ProgrammingLanguageExtractor):
    def __init__(self) -> None:
        super().__init__()
        
        # Python-specific caches
        self._docstring_cache: dict[int, str] = {}
        self._complexity_cache: dict[int, int] = {}

# Java Plugin
class JavaElementExtractor(ProgrammingLanguageExtractor):
    def __init__(self) -> None:
        super().__init__()
        
        # Java-specific caches
        self._annotation_cache: dict[int, list[dict[str, Any]]] = {}
        self._signature_cache: dict[int, str] = {}

# JavaScript Plugin
class JavaScriptElementExtractor(ProgrammingLanguageExtractor):
    def __init__(self) -> None:
        super().__init__()
        
        # JavaScript-specific caches
        self._jsdoc_cache: dict[int, str] = {}
        self._complexity_cache: dict[int, int] = {}
```

**影響:**
- キャッシュ管理が分散
- メモリ使用量が増加
- キャッシュの無効化が困難
- キャッシュの統計が取得できない

**推奨事項:**
1. 統一されたキャッシュ管理システムを作成
2. キャッシュのサイズ制限を追加
3. キャッシュの有効期限を追加
4. キャッシュの統計機能を追加

**カテゴリ:** パフォーマンス、設計  
**優先度:** 🟡 中

---

## 🟡 Major Extensibility Issues (優先度: 中)

### 21. 言語プラグインのコード重複と抽象化不足

**ファイル:** [`tree_sitter_analyzer/languages/python_plugin.py`](tree_sitter_analyzer/languages/python_plugin.py:33-96), [`tree_sitter_analyzer/languages/java_plugin.py`](tree_sitter_analyzer/languages/java_plugin.py:27-100), [`tree_sitter_analyzer/languages/javascript_plugin.py`](tree_sitter_analyzer/languages/javascript_plugin.py:34-98)

**問題:**
各言語プラグインがほぼ同じ構造を持っており、コードの重複が著しいです。

**詳細:**
```python
# Python Plugin
class PythonElementExtractor(ProgrammingLanguageExtractor):
    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract Python function definitions with comprehensive details"""
        self._initialize_source(source_code or "")
        self._detect_file_characteristics()
        
        functions: list[Function] = []
        
        # Use optimized traversal for multiple function types
        extractors = {
            "function_definition": self._extract_function_optimized,
        }
        
        if tree is not None and tree.root_node is not None:
            try:
                self._traverse_and_extract_iterative(
                    tree.root_node, extractors, functions, "function"
                )
                log_debug(f"Extracted {len(functions)} Python functions")
            except (AttributeError, TypeError, ValueError) as e:
                log_debug(f"Error during function extraction: {e}")
                return []
        
        return functions

# Java Plugin
class JavaElementExtractor(ProgrammingLanguageExtractor):
    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract Java method definitions using AdvancedAnalyzer implementation"""
        self._initialize_source(source_code)
        
        functions: list[Function] = []
        
        # Use optimized traversal for multiple function types
        extractors = {
            "method_declaration": self._extract_method_optimized,
            "constructor_declaration": self._extract_constructor_optimized,
        }
        
        if tree is not None and tree.root_node is not None:
            try:
                self._traverse_and_extract_iterative(
                    tree.root_node, extractors, functions, "function"
                )
                log_debug(f"Extracted {len(functions)} Java methods")
            except (AttributeError, TypeError, ValueError) as e:
                log_debug(f"Error during function extraction: {e}")
                return []
        
        return functions

# JavaScript Plugin
class JavaScriptElementExtractor(ProgrammingLanguageExtractor):
    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract JavaScript function definitions with comprehensive details"""
        self._initialize_source(source_code)
        self._detect_file_characteristics()
        
        functions: list[Function] = []
        
        # Use optimized traversal for multiple function types
        extractors = {
            "function_declaration": self._extract_function_optimized,
            "function_expression": self._extract_function_optimized,
            "arrow_function": self._extract_arrow_function_optimized,
            "method_definition": self._extract_method_optimized,
            "generator_function_declaration": self._extract_generator_function_optimized,
        }
        
        if tree is not None and tree.root_node is not None:
            try:
                self._traverse_and_extract_iterative(
                    tree.root_node, extractors, functions, "function"
                )
                log_debug(f"Extracted {len(functions)} JavaScript functions")
            except (AttributeError, TypeError, ValueError) as e:
                log_debug(f"Error during function extraction: {e}")
                return []
        
        return functions
```

**影響:**
- DRY原則違反
- バグ修正時に複数箇所修正が必要
- 保守コストの増加
- 新しい言語の追加が困難

**推奨事項:**
1. 共通ロジックを抽出
2. テンプレートメソッドパターンの適用
3. 戦略パターンの適用
4. 単体テストを追加

**カテゴリ:** 重複コード、設計  
**優先度:** 🟡 中

---

### 22. MCPツールの拡張性が低い

**ファイル:** [`tree_sitter_analyzer/mcp/server.py`](tree_sitter_analyzer/mcp/server.py:432-573)

**問題:**
[`handle_call_tool()`](tree_sitter_analyzer/mcp/server.py:432)メソッドで多数のif-elif分岐を使用しており、新しいツールの追加が困難です。

**詳細:**
```python
@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict[str, Any]
) -> list[TextContent]:
    try:
        # Ensure server is fully initialized
        self._ensure_initialized()
        
        # Log tool call
        logger.info(f"MCP tool call: {name} with args: {list(arguments.keys())}")
        
        # Handle tool calls with simplified parameter handling
        if name == "check_code_scale":
            result = await self.analyze_scale_tool.execute(arguments)
            
        elif name == "analyze_code_structure":
            if "file_path" not in arguments:
                raise ValueError("file_path parameter is required")
            result = await self.table_format_tool.execute(arguments)
            
        elif name == "extract_code_section":
            # ... (複雑な分岐)
            
        elif name == "set_project_path":
            # ...
            
        elif name == "query_code":
            result = await self.query_tool.execute(arguments)
            
        elif name == "list_files":
            result = await self.list_files_tool.execute(arguments)
            
        elif name == "search_content":
            result = await self.search_content_tool.execute(arguments)
            
        elif name == "find_and_grep":
            result = await self.find_and_grep_tool.execute(arguments)
            
        else:
            raise ValueError(f"Unknown tool: {name}")
        
        # Return result
        return [
            TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False),
            )
        ]
```

**影響:**
- 新しいツールの追加が困難
- コードの可読性の低下
- テストが困難
- 拡張性が低い

**推奨事項:**
1. ツールレジストリパターンの使用
2. ツールの共通インターフェースを定義
3. ツールの自動登録
4. ツールの依存関係を管理

**カテゴリ:** 拡張性、設計  
**優先度:** 🟡 中

---

### 23. CLIコマンドの拡張性が低い

**ファイル:** [`tree_sitter_analyzer/cli_main.py`](tree_sitter_analyzer/cli_main.py:33-96)

**問題:**
[`CLICommandFactory.create_command()`](tree_sitter_analyzer/cli_main.py:36)メソッドで多数のif-elif分岐を使用しており、新しいコマンドの追加が困難です。

**詳細:**
```python
class CLICommandFactory:
    """Factory for creating CLI commands based on arguments."""
    
    @staticmethod
    def create_command(args: argparse.Namespace) -> Any:
        """Create appropriate command based on arguments."""
        
        # Validate argument combinations first
        validator = CLIArgumentValidator()
        validation_error = validator.validate_arguments(args)
        if validation_error:
            output_error(validation_error)
            output_info(validator.get_usage_examples())
            return None
        
        # Information commands (no file analysis required)
        if args.list_queries:
            return ListQueriesCommand(args)
            
        if args.describe_query:
            return DescribeQueryCommand(args)
            
        if args.show_supported_languages:
            return ShowLanguagesCommand(args)
            
        if args.show_supported_extensions:
            return ShowExtensionsCommand(args)
            
        if args.filter_help:
            from tree_sitter_analyzer.core.query_filter import QueryFilter
            
            filter_service = QueryFilter()
            output_info(filter_service.get_filter_help())
            return None  # This will exit with code 0
        
        # File analysis commands (require file path)
        if not args.file_path:
            return None
            
        # Partial read command - highest priority for file operations
        if hasattr(args, "partial_read") and args.partial_read:
            return PartialReadCommand(args)
            
        # Handle table command with or without query-key
        if hasattr(args, "table") and args.table:
            return TableCommand(args)
            
        if hasattr(args, "structure") and args.structure:
            return StructureCommand(args)
            
        if hasattr(args, "summary") and args.summary is not None:
            return SummaryCommand(args)
            
        if hasattr(args, "advanced") and args.advanced:
            return AdvancedCommand(args)
            
        if hasattr(args, "query_key") and args.query_key:
            return QueryCommand(args)
            
        if hasattr(args, "query_string") and args.query_string:
            return QueryCommand(args)
            
        # Default command - if file_path is provided but no specific command, use default analysis
        return DefaultCommand(args)
```

**影響:**
- 新しいコマンドの追加が困難
- コードの可読性の低下
- テストが困難
- 拡張性が低い

**推奨事項:**
1. コマンドレジストリパターンの使用
2. コマンドの共通インターフェースを定義
3. コマンドの自動登録
4. コマンドの依存関係を管理

**カテゴリ:** 拡張性、設計  
**優先度:** 🟡 中

---

## 🟡 Major Testability Issues (優先度: 中)

### 24. テスト可能性の低いコードの特定

**ファイル:** [`tree_sitter_analyzer/api.py`](tree_sitter_analyzer/api.py:21-34), [`tree_sitter_analyzer/core/analysis_engine.py`](tree_sitter_analyzer/core/analysis_engine.py:50-88)

**問題:**
グローバル変数とLazy initializationの使用により、テスト可能性が低いです。

**詳細:**
```python
# api.py - Global singleton
_engine: UnifiedAnalysisEngine | None = None

def get_engine() -> UnifiedAnalysisEngine:
    """Get the global analysis engine instance."""
    global _engine
    if _engine is None:
        _engine = UnifiedAnalysisEngine()
    return _engine

# analysis_engine.py - Lazy initialization
def __init__(self, project_root: str | None = None) -> None:
    """Initialize the engine"""
    if getattr(self, "_initialized", False):
        return
    
    # Lazy init attributes
    self._cache_service: Any = None
    self._plugin_manager: Any = None
    self._performance_monitor: Any = None
    self._language_detector: Any = None
    self._security_validator: Any = None
    self._parser: Any = None
    self._query_executor: Any = None
    self._project_root = project_root
    
    # Initial discovery only (no heavy loading)
    self._load_plugins()
    self._initialized = True

def _ensure_initialized(self) -> None:
    """Ensure all components are lazily initialized only when needed"""
    if self._cache_service is not None and self._parser is not None:
        return
    
    # Perform heavy imports only once
    from ..language_detector import LanguageDetector
    from ..plugins.manager import PluginManager
    from ..security import SecurityValidator
    from .cache_service import CacheService
    from .parser import Parser
    from .query import QueryExecutor
    
    self._cache_service = CacheService()
    self._plugin_manager = PluginManager()
    self._performance_monitor = PerformanceMonitor()
    self._language_detector = LanguageDetector()
    self._security_validator = SecurityValidator(self._project_root)
    self._parser = Parser()
    self._query_executor = QueryExecutor()
```

**影響:**
- テストの独立性が損なわれる
- モックが困難
- 並行テストが困難
- テストのセットアップが複雑

**推奨事項:**
1. 依存性注入(DI)パターンの採用
2. エンジンをファクトリー関数経由で提供
3. コンテキストマネージャーの使用
4. テスト用のファクトリー関数を提供

**カテゴリ:** テスト可能性、設計  
**優先度:** 🟡 中

---

## 📊 高レベルな問題の統計サマリー

| カテゴリ | 件数 | 優先度 |
|---------|------|--------|
| グローバルシングルトンパターン | 1 | 🔴 高 |
| 複雑な同期/非同期処理 | 1 | 🔴 高 |
| 責務の分離が不十分 | 1 | 🔴 高 |
| プラグインシステムの設計上の問題 | 1 | 🔴 高 |
| フォーマットシステムの設計上の問題 | 1 | 🔴 高 |
| 非効率的な木構造走査 | 1 | 🟡 中 |
| 分散したキャッシュ管理 | 1 | 🟡 中 |
| 言語プラグインのコード重複 | 1 | 🟡 中 |
| MCPツールの拡張性が低い | 1 | 🟡 中 |
| CLIコマンドの拡張性が低い | 1 | 🟡 中 |
| テスト可能性の低いコード | 1 | 🟡 中 |

---

## 🎯 高レベルな問題の優先対処

### 即座に対処すべき（1週間以内）

1. **グローバルシングルトンパターンの削除**
   - 依存性注入パターンの導入
   - エンジンをファクトリー関数経由で提供
   - テスト可能性の向上

2. **複雑な同期/非同期処理の改善**
   - 同期/非同期を明確に分離
   - イベントループ管理を専用クラスに移動
   - デッドロックのリスク低減

3. **責務の分離が不十分なAPI関数の分割**
   - 関数を小さな責務に分割
   - 結果ビルダーパターンの使用
   - エラーハンドリングを統一

### 中期的に対処すべき（1ヶ月以内）

4. **プラグインシステムの設計改善**
   - プラグインの発見とロードを統一
   - エイリアス処理を設定ファイルから読み込み
   - プラグインのライフサイクルを明確に定義

5. **フォーマットシステムの設計改善**
   - 2つのインターフェースを統一
   - 後方互換性レイヤーを分離
   - フォーマットの責務を明確に定義

6. **非効率的な木構造走査の改善**
   - 反復的な木構造走査に変更
   - 深さ制限を追加
   - ノードタイプの判定をキャッシュ

### 長期的に対処すべき（3ヶ月以内）

7. **言語プラグインのコード重複の削除**
   - 共通ロジックを抽出
   - テンプレートメソッドパターンの適用
   - 戦略パターンの適用
   - 単体テストを追加

8. **MCPツールの拡張性向上**
   - ツールレジストリパターンの使用
   - ツールの共通インターフェースを定義
   - ツールの自動登録
   - ツールの依存関係を管理

9. **CLIコマンドの拡張性向上**
   - コマンドレジストリパターンの使用
   - コマンドの共通インターフェースを定義
   - コマンドの自動登録
   - コマンドの依存関係を管理

10. **統一されたキャッシュ管理システムの導入**
   - 統一されたキャッシュ管理システムを作成
   - キャッシュのサイズ制限を追加
   - キャッシュの有効期限を追加
   - キャッシュの統計機能を追加

---

**レビュー完了日:** 2026-01-15  
**次回レビュー推奨日:** 改善後、1ヶ月以内
