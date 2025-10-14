# CLI引数処理アーキテクチャ再設計仕様書

## 概要

--query-keyと--tableの組み合わせ機能の設計を根本的に見直し、正しいCLIアーキテクチャを実装する。

## 問題のある現在の設計

### 1. 間違った機能組み合わせ
- **問題**: --query-keyと--tableの組み合わせを実装してしまった
- **影響**: TableCommandに--query-key処理ロジックが混入
- **結果**: 責任分離の原則に違反

### 2. 不適切なコンポーネント
- **QueryResultParser**: --table用に作成されたが、本来不要
- **TableCommand._execute_query_based_table()**: 削除対象メソッド
- **TableCommand._convert_query_results_to_analysis()**: 削除対象メソッド

### 3. テストケースの問題
- **tests/test_table_query_integration.py**: 全体が削除対象
- 16個のテストケースが間違った機能をテストしている

## 正しい設計要件

### 1. コマンドライン引数の排他制御

```python
# 正しい組み合わせ
✅ --query-key methods
✅ --query-key methods --filter "name=main"
✅ --table full
✅ --table compact

# 禁止される組み合わせ
❌ --table full --query-key methods  # エラーになるべき
```

### 2. 正しい機能の組み合わせ

| 機能 | 目的 | 組み合わせ可能 |
|------|------|----------------|
| --query-key | クエリ実行 | --filter |
| --table | 構造解析のテーブル表示 | 単体のみ |
| --filter | クエリ結果フィルタリング | --query-key |

## 新しいCLIアーキテクチャ設計

### 1. 引数検証レイヤー

```python
class CLIArgumentValidator:
    """CLI引数の検証とエラーハンドリング"""
    
    @staticmethod
    def validate_argument_combinations(args: argparse.Namespace) -> tuple[bool, str]:
        """引数の組み合わせを検証"""
        
        # --tableと--query-keyの排他制御
        if hasattr(args, 'table') and args.table and \
           hasattr(args, 'query_key') and args.query_key:
            return False, "--table and --query-key cannot be used together. Use --query-key with --filter instead."
        
        # --filterは--query-keyと組み合わせてのみ使用可能
        if hasattr(args, 'filter') and args.filter and \
           not (hasattr(args, 'query_key') and args.query_key):
            return False, "--filter can only be used with --query-key"
        
        return True, ""
```

### 2. CommandFactory優先順位の修正

```python
class CLICommandFactory:
    """修正されたコマンドファクトリ"""
    
    @staticmethod
    def create_command(args: argparse.Namespace) -> Any:
        """引数検証後にコマンドを作成"""
        
        # 1. 引数組み合わせ検証
        is_valid, error_msg = CLIArgumentValidator.validate_argument_combinations(args)
        if not is_valid:
            output_error(error_msg)
            return None
        
        # 2. 情報コマンド（ファイル解析不要）
        if args.list_queries:
            return ListQueriesCommand(args)
        # ... 他の情報コマンド
        
        # 3. ファイル解析コマンド（ファイルパス必須）
        if not args.file_path:
            return None
        
        # 4. 優先順位に基づくコマンド選択
        if hasattr(args, "partial_read") and args.partial_read:
            return PartialReadCommand(args)
        
        # TableCommandは--query-key処理を完全に削除
        if hasattr(args, "table") and args.table:
            return TableCommand(args)  # 単体機能のみ
        
        # QueryCommandは--query-keyと--filterの組み合わせを処理
        if hasattr(args, "query_key") and args.query_key:
            return QueryCommand(args)
        
        if hasattr(args, "query_string") and args.query_string:
            return QueryCommand(args)
        
        # ... 他のコマンド
        
        return DefaultCommand(args)
```

### 3. コマンド責任分離

#### TableCommand（修正後）
```python
class TableCommand(BaseCommand):
    """テーブル形式出力専用コマンド（--query-key処理を完全削除）"""
    
    async def execute_async(self, language: str) -> int:
        """標準的な構造解析のテーブル表示のみ"""
        
        # --query-key関連のロジックを完全削除
        # _execute_query_based_table()メソッド削除
        # _convert_query_results_to_analysis()メソッド削除
        
        # 標準解析のみ実行
        analysis_result = await self.analyze_file(language)
        if not analysis_result:
            return 1
        
        # テーブル形式で出力
        structure_result = self._convert_to_structure_format(analysis_result, language)
        formatter = create_table_formatter(self.args.table, language, include_javadoc)
        table_output = formatter.format_structure(structure_result)
        self._output_table(table_output)
        
        return 0
```

#### QueryCommand（変更なし）
```python
class QueryCommand(BaseCommand):
    """クエリ実行専用コマンド（--filterとの組み合わせ対応）"""
    
    async def execute_async(self, language: str) -> int:
        """クエリ実行とフィルタリング"""
        
        # 既存の実装を維持
        # --filterとの組み合わせは既に対応済み
        # 出力形式は--output-format（json/text）で制御
        
        return 0
```

### 4. エラーメッセージ仕様

```python
ERROR_MESSAGES = {
    "table_query_conflict": "--table and --query-key cannot be used together. Use --query-key with --filter instead.",
    "filter_without_query": "--filter can only be used with --query-key",
    "invalid_combination": "Invalid argument combination. Use --help for usage information.",
}

USAGE_EXAMPLES = {
    "query_with_filter": "uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter \"name=main\"",
    "table_only": "uv run python -m tree_sitter_analyzer examples/BigService.java --table full",
    "query_only": "uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods",
}
```

## 実装修正計画

### 削除対象

#### 1. ファイル削除
- `tests/test_table_query_integration.py` - 完全削除
- `tree_sitter_analyzer/core/query_result_parser.py` - 完全削除

#### 2. メソッド削除（TableCommand）
- `_execute_query_based_table()` - 完全削除
- `_convert_query_results_to_analysis()` - 完全削除
- `_output_query_table_with_metadata()` - 完全削除

#### 3. インポート削除
```python
# TableCommandから削除
from ...core.query_result_parser import QueryResultParser  # 削除
```

### 修正対象

#### 1. cli_main.py
- `CLIArgumentValidator`クラス追加
- `CLICommandFactory.create_command()`に引数検証追加
- エラーメッセージ改善

#### 2. TableCommand
- `__init__()`からQueryService削除不要（既存機能で使用）
- `execute_async()`から--query-key処理ロジック完全削除
- 単純化されたテーブル生成ロジックのみ残す

#### 3. 新規テストケース
- 引数検証のテストケース追加
- エラーメッセージのテストケース追加
- 既存の単体機能テストは維持

### 保持対象

#### 1. 既存機能（変更なし）
- `--table`単体での使用
- `--query-key`単体での使用
- `--query-key`と`--filter`の組み合わせ
- QueryCommand全体
- SecurityValidator改善

#### 2. 既存テストケース（維持）
- QueryCommandのテストケース
- TableCommandの単体テストケース
- フィルタリング機能のテストケース

## テストケース更新方針

### 削除するテストケース
```python
# 完全削除対象
tests/test_table_query_integration.py  # 全16テストケース
```

### 新規追加するテストケース
```python
# tests/test_cli_argument_validation.py
class TestCLIArgumentValidation:
    def test_table_query_key_conflict_error(self):
        """--tableと--query-keyの同時指定でエラー"""
        
    def test_filter_without_query_key_error(self):
        """--filterを--query-keyなしで使用してエラー"""
        
    def test_error_message_quality(self):
        """エラーメッセージの品質確認"""
        
    def test_valid_combinations_success(self):
        """正しい組み合わせの成功確認"""
```

### 既存テストケースの影響
- QueryCommandテスト: 影響なし（維持）
- TableCommandテスト: 一部修正（--query-key関連削除）
- 統合テスト: 新しい引数検証ロジックの追加

## 実装スケジュール

### Phase 1: 削除作業
1. `tests/test_table_query_integration.py`削除
2. `tree_sitter_analyzer/core/query_result_parser.py`削除
3. TableCommandから--query-key処理メソッド削除

### Phase 2: 引数検証追加
1. `CLIArgumentValidator`クラス実装
2. `CLICommandFactory`に検証ロジック追加
3. エラーメッセージ改善

### Phase 3: テスト追加
1. 引数検証テストケース追加
2. エラーハンドリングテストケース追加
3. 既存テストケースの修正

### Phase 4: 検証
1. 全テストケース実行
2. 手動テスト実行
3. ドキュメント更新

## 期待される効果

### 1. アーキテクチャの改善
- 責任分離の原則に準拠
- コマンドの役割が明確化
- 保守性の向上

### 2. ユーザビリティの改善
- 明確なエラーメッセージ
- 正しい使用方法の案内
- 混乱を招く機能の排除

### 3. 開発効率の向上
- テストケースの簡素化
- デバッグの容易性
- 新機能追加の安全性

## 結論

この設計により、--query-keyと--tableの組み合わせ問題を根本的に解決し、正しいCLIアーキテクチャを実現する。ユーザーフィードバックに基づく完全削除アプローチにより、混乱を招く機能を排除し、明確で保守しやすいコードベースを構築する。