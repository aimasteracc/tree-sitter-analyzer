# TOON フォーマットガイド

TOON (Token-Oriented Object Notation) は、LLM との通信に最適化されたデータフォーマットで、JSON と比較して 50-70% のトークン削減を実現しながら、人間にとっての可読性を維持します。

## 概要

### TOON とは？

TOON は、GPT-4 や Claude などの大規模言語モデル（LLM）とのコミュニケーションにおけるトークン消費を削減するために設計された YAML 風のデータフォーマットです。以下の方法でこれを実現します：

- 冗長な構文の排除（引用符、括弧、カンマ）
- 同種データ用のコンパクトな配列テーブル形式
- 人間が読みやすい構造の維持

### トークン削減結果

| データタイプ | 削減率 |
|-------------|--------|
| シンプルな辞書 | ~41% |
| コード分析結果 | ~52% |
| MCP ツールレスポンス | ~59% |
| **平均** | **~51%** |

## フォーマット仕様

### プリミティブ値

```
# Null
null

# Boolean
true
false

# 数値
42
3.14
-100

# 文字列（安全な場合は引用符なし）
hello
simple_string
```

### 特殊文字を含む文字列

特殊文字を含む文字列は引用符で囲まれ、エスケープされます：

```
# 改行を含む文字列
"line1\nline2"

# タブを含む文字列
"col1\tcol2"

# コロンを含む文字列
"key:value"

# 引用符を含む文字列
"said \"hello\""
```

### 辞書

TOON は YAML 風のキー・バリュー構文を使用します：

```
name: example
count: 42
active: true
```

ネストされた辞書はインデントを使用します：

```
file: sample.py
metadata:
  language: python
  version: 3.11
statistics:
  lines: 100
  methods: 5
```

### シンプルな配列

シンプルな配列は括弧表記を使用します：

```
items: [1,2,3,4,5]
tags: [python,typescript,rust]
```

### 配列テーブル（コンパクト形式）

オブジェクトの同種配列はコンパクトなテーブル形式を使用します：

```
[count]{field1,field2,field3}:
  value1,value2,value3
  value4,value5,value6
```

例：

```
methods:
  [4]{name,visibility,lines}:
    init,public,1-10
    process,public,12-45
    validate,private,47-60
    cleanup,public,62-70
```

これは以下の JSON と同等です：

```json
{
  "methods": [
    {"name": "init", "visibility": "public", "lines": "1-10"},
    {"name": "process", "visibility": "public", "lines": "12-45"},
    {"name": "validate", "visibility": "private", "lines": "47-60"},
    {"name": "cleanup", "visibility": "public", "lines": "62-70"}
  ]
}
```

**トークン削減: この例で約53%**

## CLI 使用方法

### 基本コマンド

```bash
# TOON 出力で構造分析
uv run python -m tree_sitter_analyzer.cli file.py --structure --format toon

# または --output-format を使用
uv run python -m tree_sitter_analyzer.cli file.py --structure --output-format toon

# TOON でサマリー
uv run python -m tree_sitter_analyzer.cli file.py --summary --format toon

# 高度な分析
uv run python -m tree_sitter_analyzer.cli file.py --advanced --format toon

# 部分読み取り
uv run python -m tree_sitter_analyzer.cli file.py --partial-read --start-line 1 --end-line 50 --format toon
```

### タブ区切りモード

さらなる圧縮のために、タブ区切りを使用します：

```bash
uv run python -m tree_sitter_analyzer.cli file.py --structure --format toon --toon-use-tabs
```

### 出力例

```bash
$ uv run python -m tree_sitter_analyzer.cli examples/sample.py --structure --format toon

--- Structure Analysis Results ---
file_path: examples/sample.py
language: python
package: null
classes:
  [3]{name}:
    Animal
    Dog
    Cat
methods:
  [18]{name}:
    __init__
    describe
    ...
fields: []
imports: []
statistics:
  class_count: 3
  method_count: 18
  field_count: 1
  import_count: 4
  total_lines: 256
```

## MCP ツール使用方法

すべての MCP ツールは `output_format` パラメータをサポートしています：

### analyze_code_structure

```json
{
  "file_path": "sample.py",
  "output_format": "toon"
}
```

### list_files

```json
{
  "directory": "src",
  "output_format": "toon"
}
```

### search_content

```json
{
  "pattern": "def.*test",
  "output_format": "toon"
}
```

### query_code

```json
{
  "file_path": "sample.py",
  "query_key": "function",
  "output_format": "toon"
}
```

## Python API

### ToonEncoder の使用（低レベル）

```python
from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

encoder = ToonEncoder()

# シンプルなデータをエンコード
data = {"name": "test", "count": 42}
print(encoder.encode(data))
# 出力:
# name: test
# count: 42

# 配列テーブルをエンコード
methods = [
    {"name": "init", "line": 10},
    {"name": "process", "line": 20},
]
print(encoder.encode_array_table(methods))
# 出力:
# [2]{name,line}:
#   init,10
#   process,20
```

### ToonFormatter の使用（高レベル）

```python
from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter

formatter = ToonFormatter()

# 任意のデータをフォーマット
data = {
    "success": True,
    "results": [
        {"file": "a.py", "lines": 100},
        {"file": "b.py", "lines": 200},
    ]
}
print(formatter.format(data))
```

### タブ区切りモード

```python
encoder = ToonEncoder(use_tabs=True)
formatter = ToonFormatter(use_tabs=True)
```

## エラー処理

### 循環参照検出

TOON エンコーダーは循環参照を自動的に検出して処理します：

```python
from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder, ToonEncodeError

encoder = ToonEncoder(fallback_to_json=False)

# これは ToonEncodeError を発生させます
circular = {"key": "value"}
circular["self"] = circular

try:
    encoder.encode(circular)
except ToonEncodeError as e:
    print(f"エラー: {e.message}")
```

### JSON フォールバック

デフォルトでは、エンコードエラーは JSON にフォールバックします：

```python
encoder = ToonEncoder(fallback_to_json=True)  # デフォルト

# エラー時は例外を発生させずに JSON を返します
result = encoder.encode(problematic_data)
```

### 安全なエンコード

`encode_safe()` を使用すると、常に文字列が返されます：

```python
encoder = ToonEncoder()

# 例外を発生させず、常に文字列を返します
result = encoder.encode_safe(any_data)
```

### 最大深度制限

深度制限でスタックオーバーフローを防止：

```python
encoder = ToonEncoder(max_depth=50)  # デフォルト: 100
```

## ベストプラクティス

### TOON を使用すべき場合

✅ **TOON を使用:**
- LLM API 呼び出し（トークンコスト削減）
- コード分析結果
- MCP ツールレスポンス
- 類似オブジェクトの配列を含む構造化データ

❌ **TOON を避ける:**
- 外部システムとのデータ交換
- JSON を必要とする API
- JSON スキーマ検証が必要な場合

### トークン削減の最大化

1. **同種データには配列テーブルを使用**:
   ```
   # 良い: 配列テーブル形式
   [100]{name,line}:
     func1,10
     func2,20
     ...
   
   # 避ける: 個別オブジェクト
   - name: func1
     line: 10
   - name: func2
     line: 20
   ```

2. **キーは短く、でも説明的に**:
   ```
   # 良い
   ln: 100
   
   # OK
   line_count: 100
   
   # 避ける
   total_number_of_lines_in_file: 100
   ```

3. **最大圧縮にはタブ区切りを使用**:
   ```bash
   --format toon --toon-use-tabs
   ```

## 他のフォーマットとの比較

| 機能 | JSON | YAML | TOON |
|------|------|------|------|
| トークン効率 | 低 | 中 | 高 |
| 人間が読みやすい | 中 | 高 | 高 |
| LLM 最適化 | いいえ | いいえ | **はい** |
| 配列テーブル | いいえ | いいえ | **はい** |
| スキーマサポート | はい | はい | 部分的 |
| 標準 | RFC 8259 | YAML 1.2 | カスタム |

## ベンチマークの実行

```bash
# トークン削減ベンチマークを実行
uv run python examples/toon_token_benchmark.py

# デモを実行
uv run python examples/toon_demo.py
```

## トラブルシューティング

### "Circular reference detected"

データに循環参照が含まれています。以下のいずれかを行ってください：
1. 循環参照を削除
2. `fallback_to_json=True` を使用（デフォルト）
3. `encode_safe()` メソッドを使用

### "Maximum nesting depth exceeded"

データのネストが深すぎます。以下のいずれかを行ってください：
1. データ構造をフラット化
2. `max_depth` パラメータを増加

### 出力が JSON のように見える

エンコードエラーにより TOON が JSON にフォールバックしました。詳細はログを確認：

```python
import logging
logging.basicConfig(level=logging.WARNING)
```

## バージョン履歴

- **v1.6.2**: 初期 TOON サポート
  - ToonEncoder と ToonFormatter
  - CLI `--format toon` オプション
  - MCP ツール `output_format` パラメータ
  - JSON フォールバック付きエラー処理
  - イテレーティブ実装（再帰なし）

## 関連ドキュメント

- [CLI リファレンス](cli-reference.md)
- [API ドキュメント](../api/)
- [サンプル](../../examples/)

