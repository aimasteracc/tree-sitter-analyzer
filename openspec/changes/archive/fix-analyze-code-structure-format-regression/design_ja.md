# 設計: analyze_code_structure フォーマット回帰の修正

## アーキテクチャ概要

この変更は、将来の拡張性のために v1.9.4 で導入された FormatterRegistry アーキテクチャを維持しながら、元の v1.6.1.4 フォーマット仕様を復元します。

## 現在のアーキテクチャ分析

### v1.6.1.4 (レガシー TableFormatter)
```
TableFormatTool -> TableFormatter -> format_structure()
                                  -> _format_full_table()    # Markdown テーブル
                                  -> _format_compact_table() # 複雑度付き Markdown
                                  -> _format_csv()           # シンプル CSV
```

### v1.9.4 (FormatterRegistry)
```
TableFormatTool -> FormatterRegistry -> FullFormatter      # プレーンテキスト (間違い)
                                     -> CompactFormatter    # プレーンテキストリスト (間違い)
                                     -> CsvFormatter        # 複雑な CSV (間違い)
                                     -> HtmlFormatter       # 無許可の追加
```

## 提案されたソリューションアーキテクチャ

### ハイブリッドアプローチ: レガシー互換性 + レジストリ拡張性

```
TableFormatTool -> フォーマット決定ロジック
                -> レガシーフォーマット (full, compact, csv)
                   -> LegacyTableFormatter (v1.6.1.4 ロジックの復元)
                -> 拡張フォーマット (html_*, json)
                   -> FormatterRegistry -> 新しいフォーマッター
```

## 実装戦略

### 1. レガシーフォーマットの復元

v1.6.1.4 の動作を正確に複製する `LegacyTableFormatter` クラスを作成：

```python
class LegacyTableFormatter:
    """復元された v1.6.1.4 TableFormatter 実装"""
    
    def format_structure(self, structure_data: dict[str, Any]) -> str:
        if self.format_type == "full":
            return self._format_full_table(structure_data)  # Markdown テーブル
        elif self.format_type == "compact":
            return self._format_compact_table(structure_data)  # Markdown + 複雑度
        elif self.format_type == "csv":
            return self._format_csv(structure_data)  # シンプル CSV
```

### 2. フォーマット決定ロジック

適切なフォーマッターを使用するように `TableFormatTool.execute()` を更新：

```python
async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
    format_type = args.get("format_type", "full")
    
    # レガシーフォーマット: 復元された v1.6.1.4 実装を使用
    if format_type in ["full", "compact", "csv"]:
        legacy_formatter = LegacyTableFormatter(format_type)
        table_output = legacy_formatter.format_structure(structure_dict)
    
    # 拡張フォーマット: FormatterRegistry を使用 (将来の拡張性)
    elif FormatterRegistry.is_format_supported(format_type):
        registry_formatter = FormatterRegistry.get_formatter(format_type)
        table_output = registry_formatter.format(structure_result.elements)
    
    else:
        raise ValueError(f"Unsupported format: {format_type}")
```

### 3. スキーマ更新

正しいサポート形式を反映するようにツールスキーマを更新：

```python
def get_tool_schema(self) -> dict[str, Any]:
    return {
        "properties": {
            "format_type": {
                "enum": ["full", "compact", "csv"],  # HTML フォーマットを削除
                "default": "full",
            }
        }
    }
```

## フォーマット仕様

### Full フォーマット (Markdown テーブル)
```markdown
# ClassName

## Package
`com.example.package`

## Class Info
| Property | Value |
|----------|-------|
| Package | com.example.package |
| Type | class |
| Visibility | public |
| Lines | 1-50 |
| Total Methods | 5 |
| Total Fields | 3 |

## ClassName (1-50)

### Fields
| Name | Type | Vis | Modifiers | Line | Doc |
|------|------|-----|-----------|------|-----|
| field1 | String | private | final | 10 | Field documentation |

### Methods
| Name | Return | Vis | Modifiers | Params | Line | Complexity | Doc |
|------|--------|-----|-----------|--------|------|------------|-----|
| method1 | void | public | | String param | 20 | 2 | Method documentation |
```

### Compact フォーマット (複雑度付き Markdown テーブル)
```markdown
# Code Structure Summary

## Methods
| Name | Type | Visibility | Lines | Complexity | Parameters |
|------|------|------------|-------|------------|------------|
| method1 | void | public | 20-25 | 2 | String param |

## Fields
| Name | Type | Visibility | Lines |
|------|------|------------|-------|
| field1 | String | private | 10 |
```

### CSV フォーマット (シンプル構造)
```csv
Type,Name,Visibility,Lines,Complexity,Parameters
method,method1,public,20-25,2,"String param"
field,field1,private,10,,
```

## 移行戦略

### フェーズ 1: 後方互換性
1. `full`, `compact`, `csv` の v1.6.1.4 フォーマットを復元
2. `analyze_code_structure` から HTML フォーマットを削除
3. 正しいフォーマットを期待するようにテストを更新

### フェーズ 2: 将来の拡張性
1. 新しいフォーマットタイプのために FormatterRegistry を保持
2. HTML 分析用の別ツールを検討
3. コアフォーマットと拡張フォーマットの明確な分離を維持

## リスク軽減

### 破壊的変更
- **リスク**: v1.9.4 のプレーンテキストフォーマットを期待するユーザー
- **軽減策**: 移行ガイドと非推奨警告の提供

### フォーマットの一貫性
- **リスク**: レガシーフォーマッターとレジストリフォーマッター間の不一致
- **軽減策**: 参照出力を含む包括的なテストスイート

### パフォーマンスへの影響
- **リスク**: デュアルフォーマッターシステムのオーバーヘッド
- **軽減策**: 実行時のフォーマット決定による最小限の影響

## テスト戦略

### 参照出力検証
1. v1.6.1.4 から参照出力ファイルを作成
2. 現在の出力と参照を比較
3. 正確なフォーマット一致を確保

### 回帰テスト
1. サポートされているすべてのプログラミング言語をテスト
2. エッジケース（空ファイル、複雑な構造）をテスト
3. メタデータ抽出の一貫性を検証

### 統合テスト
1. MCP サーバー統合をテスト
2. CLI 互換性をテスト
3. ファイル出力機能をテスト

## 将来の考慮事項

### HTML フォーマットサポート
- 別の `analyze_html_structure` ツールに移動
- FormatterRegistry で HTML フォーマッターを維持
- 関心の明確な分離

### フォーマット拡張性
- 将来のフォーマット追加のために FormatterRegistry を保持
- 新しいフォーマッター用の明確なインターフェースを定義
- 後方互換性の保証を維持

### ドキュメント
- 正しいフォーマット例でツールドキュメントを更新
- v1.9.4 ユーザー向けの移行ガイドを提供
- フォーマット仕様を明確にドキュメント化
