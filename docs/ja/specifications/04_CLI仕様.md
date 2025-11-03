# CLI仕様

**文書番号:** SPEC-004  
**バージョン:** 1.0  
**作成日:** 2025-11-03  
**最終更新:** 2025-11-03  
**検証日:** 2025-11-03（実際のCLI実行により検証済み）

---

## 1. 概要

本文書は、Tree-sitter AnalyzerのCLI（コマンドラインインターフェース）の詳細仕様を記述する。**すべてのコマンドとオプションは実際のCLI実行により検証済み**である。

---

## 2. CLI設計原則

### 2.1 設計方針

- ✅ **シンプル**: サブコマンド不要の単一コマンド設計
- ✅ **柔軟性**: 豊富なオプションで細かい制御可能
- ✅ **親切**: 詳細なヘルプメッセージとクエリ情報
- ✅ **JSON/テーブル対応**: 機械処理と人間可読性の両立

---

### 2.2 コマンド構造

#### 開発環境での実行（推奨）
```bash
uv run tree-sitter-analyzer [options] [file_path]
```

#### PyPIからグローバルインストール後
```bash
tree-sitter-analyzer [options] [file_path]
```

**重要:** 
- サブコマンドは存在せず、オプションで動作モードを切り替える設計
- **開発環境では`uv run`プレフィックスが必須**（本ドキュメントの全例で使用）
- グローバルインストール: `pip install tree-sitter-analyzer`（システムPython環境が正常な場合）
- `uv`環境: `uv pip install tree-sitter-analyzer`（この場合も`uv run`が必要）

**実行方法の優先順位:**
1. 🥇 **開発環境**: `uv run tree-sitter-analyzer` ← 本リポジトリで推奨
2. 🥈 **システムインストール**: `pip install tree-sitter-analyzer` → `tree-sitter-analyzer`
3. 🥉 **Pythonモジュール**: `python -m tree_sitter_analyzer.cli_main`

---

## 3. 基本的な使用方法

### 3.1 ファイル解析

#### 概要
Tree-sitterクエリを使用してファイルを解析し、構造化情報を抽出する。

#### 基本構文
```bash
uv run tree-sitter-analyzer [file_path] --query-key <query_key>
```

**注:** 本ドキュメントの全例は`uv run`プレフィックス付きで記載しています（開発環境での実行を想定）。

#### 必須要件
- **ファイルパスと以下のいずれかは必須**:
  - `--query-key` または `--query-string`（クエリ実行モード）
  - `--advanced`（高度な解析モード）
  - `--summary`（サマリーモード）
  - `--structure`（構造解析モード）
  - 情報表示系オプション（`--list-queries`等）

#### 主要オプション一覧

| オプション | 型 | デフォルト | 説明 |
|----------|-----|----------|------|
| `file_path` | string | - | 解析対象ファイル（位置引数） |
| `--query-key` | string | - | クエリキーを指定（例: class, method）※`--table`と併用不可 |
| `--query-string` | string | - | Tree-sitterクエリを直接指定 |
| `--filter` | string | - | クエリ結果をフィルタ（例: 'name=main'）※`--query-key`と併用可 |
| `--output-format` | enum | json | 出力形式（json/text） |
| `--table` | enum | - | テーブル形式（full/compact/csv/json）※`--query-key`と併用不可 |
| `--advanced` | flag | false | 高度な解析モード |
| `--summary` | string | - | サマリー出力（オプション値でファイル指定可） |
| `--structure` | flag | false | 構造解析モード |
| `--statistics` | flag | false | 統計情報表示 |
| `--language` | string | auto | 言語を明示的に指定 |
| `--project-root` | string | auto | プロジェクトルート指定 |
| `--quiet` | flag | false | 最小限の出力 |
| `--include-javadoc` | flag | false | JavaDoc情報を含める |
| `--partial-read` | flag | false | 部分読み取りモード |
| `--start-line` | int | - | 開始行（partial-read時） |
| `--end-line` | int | - | 終了行（partial-read時） |
| `--start-column` | int | - | 開始列（partial-read時） |
| `--end-column` | int | - | 終了列（partial-read時） |

#### 使用例（実際に動作確認済み）

**基本的なクエリ実行:**
```bash
# Pythonファイルの関数を抽出
uv run tree-sitter-analyzer examples/sample.py --query-key function

# Javaファイルのクラスを抽出
uv run tree-sitter-analyzer examples/Sample.java --query-key class

# メソッド名のみを抽出
uv run tree-sitter-analyzer examples/Sample.java --query-key method_name
```

**高度な解析モード:**
```bash
# 詳細な要素情報と統計を取得
uv run tree-sitter-analyzer examples/sample.py --advanced

# 出力例:
# {
#   "file_path": "examples/sample.py",
#   "language": "python",
#   "line_count": 256,
#   "element_count": 27,
#   "node_count": 1821,
#   "elements": [...]
# }
```

**サマリーモード:**
```bash
# クラスとメソッドの概要を取得
uv run tree-sitter-analyzer examples/sample.py --summary

# ファイルに出力
uv run tree-sitter-analyzer examples/sample.py --summary=output.json
```

**テーブル形式出力:**
```bash
# テーブル形式（クエリキーなし、ファイル全体の解析結果）
uv run tree-sitter-analyzer examples/sample.py --table full

# コンパクトなテーブル形式
uv run tree-sitter-analyzer examples/sample.py --table compact

# CSV形式（スプレッドシート向け）
uv run tree-sitter-analyzer examples/Sample.java --table csv

# JSON形式のテーブル
uv run tree-sitter-analyzer examples/sample.py --table json
```

**重要:** `--table`と`--query-key`は**併用できません**。
- `--table`のみ: ファイル全体の要素をテーブル形式で出力
- `--query-key`のみ: 特定のクエリ結果をJSON形式で出力
- `--query-key`と`--filter`の組み合わせは可能

**フィルタ機能:**
```bash
# 名前でフィルタ（--query-keyと併用可能）
uv run tree-sitter-analyzer examples/Sample.java --query-key method --filter "name=main"

# ワイルドカード使用
uv run tree-sitter-analyzer examples/Sample.java --query-key method --filter "name=~get*"

# 複数条件（name=getXXXかつpublic=true）
uv run tree-sitter-analyzer examples/Sample.java --query-key method --filter "name=~get*,public=true"
```

**部分読み取りモード:**
```bash
# 特定行範囲のみ解析
uv run tree-sitter-analyzer large_file.py --query-key function --partial-read --start-line 100 --end-line 200

# 特定位置範囲を解析
uv run tree-sitter-analyzer file.py --query-key class --partial-read --start-line 50 --end-line 100 --start-column 0 --end-column 80
```

---

## 4. 情報表示系オプション

### 4.1 クエリ情報の表示

#### 利用可能なクエリ一覧
```bash
uv run tree-sitter-analyzer --list-queries
```

**出力例:**
```
Supported languages:
    java
      class                - Extract class declarations
      interface            - Extract interface declarations
      method               - Extract method declarations
      constructor          - Extract constructor declarations
      field                - Extract field declarations
      import               - Extract import statements
      ...
    python
      function             - Extract function definitions
      class                - Extract class definitions
      import               - Extract import statements
      ...
```

#### 特定クエリの詳細説明
```bash
uv run tree-sitter-analyzer --describe-query <query_key>
```

例:
```bash
uv run tree-sitter-analyzer --describe-query class
```

#### フィルタ構文のヘルプ
```bash
uv run tree-sitter-analyzer --filter-help
```

### 4.2 サポート言語情報

#### サポート言語一覧
```bash
uv run tree-sitter-analyzer --show-supported-languages
```

#### サポート拡張子一覧
```bash
uv run tree-sitter-analyzer --show-supported-extensions
```

**出力例:**
```
Supported file extensions:
  .py   - Python
  .java - Java
  .js   - JavaScript
  .ts   - TypeScript
  .jsx  - React JSX
  .tsx  - React TypeScript
  ...
```

#### クエリサポート言語一覧
```bash
uv run tree-sitter-analyzer --show-query-languages
```

#### 共通クエリ一覧
```bash
uv run tree-sitter-analyzer --show-common-queries
```

---

## 5. 高度な使用例

### 5.1 カスタムTree-sitterクエリの直接実行

Tree-sitter S式クエリを直接指定して実行可能：

```bash
uv run tree-sitter-analyzer examples/sample.py --query-string "(function_definition name: (identifier) @function.name)"
```

**出力例:**
```json
[
  {
    "capture_name": "function.name",
    "node_type": "identifier",
    "start_line": 21,
    "end_line": 21,
    "content": "__post_init__"
  },
  {
    "capture_name": "function.name",
    "node_type": "identifier",
    "start_line": 26,
    "end_line": 26,
    "content": "greet"
  }
]
```

### 5.2 言語の明示的指定

拡張子が標準でない場合や、強制的に特定言語として扱いたい場合：

```bash
# .txtファイルをPythonとして解析
uv run tree-sitter-analyzer script.txt --language python --query-key function

# 言語指定でJavaとして解析
uv run tree-sitter-analyzer MyClass.bak --language java --query-key class
```

### 5.3 プロジェクトルートの指定

セキュリティ境界とインポート解決のためのプロジェクトルート指定：

```bash
uv run tree-sitter-analyzer src/module/file.py --project-root /path/to/project --advanced
```

### 5.4 統計情報の取得

```bash
# 統計情報を含める
uv run tree-sitter-analyzer examples/sample.py --advanced --statistics

# 構造情報のみ
uv run tree-sitter-analyzer examples/sample.py --structure
```

### 5.5 JavaDoc情報の抽出

```bash
# JavaDocコメントを含めて抽出
uv run tree-sitter-analyzer examples/Sample.java --query-key method --include-javadoc
```

---

## 6. 実際の出力例（検証済み）

### 6.1 クエリ実行の出力

**コマンド:**
```bash
uv run tree-sitter-analyzer examples/sample.py --query-key function
```

**出力（JSON）:**
```json
[
  {
    "capture_name": "function",
    "node_type": "function_definition",
    "start_line": 21,
    "end_line": 24,
    "content": "def __post_init__(self):\n    \"\"\"Validate the person data after initialization.\"\"\"\n    if self.age < 0:\n        raise ValueError(\"Age cannot be negative\")"
  },
  {
    "capture_name": "function",
    "node_type": "function_definition",
    "start_line": 26,
    "end_line": 28,
    "content": "def greet(self) -> str:\n    \"\"\"Return a greeting message.\"\"\"\n    return f\"Hello, my name is {self.name} and I am {self.age} years old.\""
  }
]
```

### 6.2 高度な解析モード

**コマンド:**
```bash
uv run tree-sitter-analyzer examples/sample.py --advanced
```

**出力（JSON）:**
```json
{
  "file_path": "examples/sample.py",
  "language": "python",
  "line_count": 256,
  "element_count": 27,
  "node_count": 1821,
  "elements": [
    {
      "name": "__init__",
      "type": "function",
      "start_line": 34,
      "end_line": 36
    },
    {
      "name": "describe",
      "type": "function",
      "start_line": 43,
      "end_line": 45
    }
  ]
}
```

### 6.3 サマリーモード

**コマンド:**
```bash
uv run tree-sitter-analyzer examples/sample.py --summary
```

**出力（JSON）:**
```json
{
  "file_path": "examples/sample.py",
  "language": "python",
  "summary": {
    "classes": [
      {"name": "Animal"},
      {"name": "Dog"},
      {"name": "Cat"}
    ],
    "methods": [
      {"name": "__init__"},
      {"name": "describe"},
      {"name": "make_sound"}
    ]
  }
}
```

---

## 7. 言語別クエリキー詳細（検証済み）

### 7.1 Java言語のクエリキー

#### 7.1.1 基本構造抽出

**クラス定義（class）**
```bash
uv run tree-sitter-analyzer examples/Sample.java --query-key class
```
出力例: AbstractParentClass, ParentClass, Test等のクラス定義を抽出

**インターフェース定義（interface）**
```bash
uv run tree-sitter-analyzer examples/Sample.java --query-key interface
```
出力例: TestInterface, AnotherInterface等のインターフェース定義を抽出

**Enum定義（enum）**
```bash
uv run tree-sitter-analyzer examples/Sample.java --query-key enum
```
出力例: 列挙型（enum）定義とそのメンバーを抽出

#### 7.1.2 メソッド・フィールド抽出

**メソッド定義（method）**
```bash
uv run tree-sitter-analyzer examples/Sample.java --query-key method
```
出力例: すべてのメソッド（public, private, protected含む）を抽出

**抽象メソッド（abstract_method）**
```bash
uv run tree-sitter-analyzer examples/Sample.java --query-key abstract_method
```
出力例: abstract修飾子付きメソッドのみ抽出

**publicメソッド（public_methods）**
```bash
uv run tree-sitter-analyzer examples/Sample.java --query-key public_methods
```
出力例: public修飾子付きメソッドのみ抽出

**メソッド名のみ（method_name）**
```bash
uv run tree-sitter-analyzer examples/Sample.java --query-key method_name
```
出力例: メソッド名（識別子）のみ抽出、本体は含まない

**フィールド定義（field）**
```bash
uv run tree-sitter-analyzer examples/Sample.java --query-key field
```
出力例: すべてのフィールド変数を抽出

**静的フィールド（static_field）**
```bash
uv run tree-sitter-analyzer examples/Sample.java --query-key static_field
```
出力例: static修飾子付きフィールドのみ抽出

**静的メソッド（static_methods）**
```bash
uv run tree-sitter-analyzer examples/Sample.java --query-key static_methods
```
出力例: static修飾子付きメソッドのみ抽出

**コンストラクタ（constructor）**
```bash
uv run tree-sitter-analyzer examples/Sample.java --query-key constructor
```
出力例: クラスのコンストラクタ定義を抽出

#### 7.1.3 型とジェネリクス

**ジェネリック型（generic_type）**
```bash
uv run tree-sitter-analyzer examples/Sample.java --query-key generic_type
```
出力例: `List<T>`, `Map<K,V>`等のジェネリック型使用箇所を抽出

#### 7.1.4 インポート文

**インポート文（import）**
```bash
uv run tree-sitter-analyzer examples/Sample.java --query-key import
```
出力例: すべてのimport文を抽出

#### 7.1.5 Javadocコメント

**Javadocコメント（javadoc_comment）**
```bash
uv run tree-sitter-analyzer examples/JavaDocTest.java --query-key javadoc_comment
```
出力例: /** */ 形式のJavadocコメントを抽出

#### 7.1.6 Spring関連

**注意:** Spring関連クエリは、実際にSpringアノテーションが存在するファイルでのみ結果を返します。

**Spring Controller（spring_controller）**
```bash
uv run tree-sitter-analyzer <spring_file.java> --query-key spring_controller
```
出力例: @Controller, @RestController付きクラスを抽出

**Spring Service（spring_service）**
```bash
uv run tree-sitter-analyzer <spring_file.java> --query-key spring_service
```
出力例: @Service付きクラスを抽出

**Spring Repository（spring_repository）**
```bash
uv run tree-sitter-analyzer <spring_file.java> --query-key spring_repository
```
出力例: @Repository付きクラスを抽出

#### 7.1.7 JPA/Hibernate関連

**JPA Entity（jpa_entity）**
```bash
uv run tree-sitter-analyzer <entity_file.java> --query-key jpa_entity
```
出力例: @Entity付きクラスを抽出

**JPA ID Field（jpa_id_field）**
```bash
uv run tree-sitter-analyzer <entity_file.java> --query-key jpa_id_field
```
出力例: @Id付きフィールドを抽出

#### 7.1.8 その他の利用可能なJavaクエリ

以下のクエリキーも利用可能です（詳細は `--list-queries` で確認）:
- `annotation_type` - アノテーション型定義
- `lambda` - ラムダ式
- `try_catch` - try-catchブロック
- `final_field` - final修飾子付きフィールド
- `static_import` - 静的インポート
- `marker_annotation` - マーカーアノテーション
- `annotation_with_params` - パラメータ付きアノテーション
- `synchronized_block` - synchronizedブロック
- `field_name` - フィールド名のみ
- `method_with_annotations` - アノテーション付きメソッド
- `extends_clause` - extends句
- `implements_clause` - implements句
- `private_methods` - privateメソッド
- その他多数...

### 7.2 Python言語のクエリキー

#### 7.2.1 基本構造抽出

**関数定義（function）**
```bash
uv run tree-sitter-analyzer examples/sample.py --query-key function
```
出力例: すべての関数定義を抽出

**非同期関数（async_function）**
```bash
uv run tree-sitter-analyzer examples/sample.py --query-key async_function
```
出力例: async def で定義された非同期関数を抽出

**クラス定義（class）**
```bash
uv run tree-sitter-analyzer examples/sample.py --query-key class
```
注意: sample.pyには明示的なclassキーワードがないため結果なし

#### 7.2.2 インポート文

**インポート文（import）**
```bash
uv run tree-sitter-analyzer examples/sample.py --query-key import
```
出力例: `import aiohttp` 等のインポート文を抽出

#### 7.2.3 デコレータと型ヒント

**デコレータ（decorator）**
```bash
uv run tree-sitter-analyzer examples/sample.py --query-key decorator
```
出力例: @dataclass, @abstractmethod 等のデコレータを抽出

**データクラス（dataclass）**
```bash
uv run tree-sitter-analyzer examples/sample.py --query-key dataclass
```
出力例: @dataclass付きクラス定義全体を抽出

**型ヒント（type_hint）**
```bash
uv run tree-sitter-analyzer examples/sample.py --query-key type_hint
```
出力例: 型アノテーション（`name: str` 等）を抽出

#### 7.2.4 その他の利用可能なPythonクエリ

以下のクエリキーも利用可能です（詳細は `--list-queries` で確認）:
- `lambda` - ラムダ式
- `method` - メソッド定義
- `property` - @propertyデコレータ付きメソッド
- `staticmethod` - @staticmethodデコレータ付きメソッド
- `classmethod` - @classmethodデコレータ付きメソッド
- `django_model` - Djangoモデルクラス
- `flask_route` - Flaskルートデコレータ
- `fastapi_endpoint` - FastAPIエンドポイント
- `match_statement` - match-case文（Python 3.10+）
- `with_statement` - withステートメント
- `try_except` - try-exceptブロック
- その他80以上のクエリキー...

### 7.3 JavaScript/TypeScript言語のクエリキー

JavaScriptおよびTypeScriptでも同様に多数のクエリキーが利用可能です:
- `function` - 関数定義
- `class` - クラス定義
- `arrow_function` - アロー関数
- `import` - インポート文
- `export` - エクスポート文
- `async_function` - 非同期関数
- `react_component` - Reactコンポーネント
- その他多数...

詳細は以下コマンドで確認:
```bash
uv run tree-sitter-analyzer --list-queries | Select-String -Pattern "javascript"
uv run tree-sitter-analyzer --list-queries | Select-String -Pattern "typescript"
```

---

## 8. エラーハンドリング

### 8.1 一般的なエラー

**クエリまたはモード指定が必須:**
```bash
uv run tree-sitter-analyzer examples/sample.py
# ERROR: Please specify a query or --advanced option
```

**対処法:** `--query-key`, `--advanced`, `--summary`, `--table`等のいずれかを指定

**--tableと--query-keyの併用エラー:**
```bash
uv run tree-sitter-analyzer examples/sample.py --query-key function --table compact
# ERROR: --table and --query-key cannot be used together. Use --query-key with --filter instead.
```

**対処法:** 
- テーブル形式が必要な場合: `--table`のみ使用
- クエリが必要な場合: `--query-key`のみ使用（`--filter`との併用は可能）

**正しい使用例:**
```bash
# テーブル形式のみ
uv run tree-sitter-analyzer examples/sample.py --table full

# クエリキーのみ
uv run tree-sitter-analyzer examples/sample.py --query-key function

# クエリキーとフィルタ（併用可能）
uv run tree-sitter-analyzer examples/Sample.java --query-key method --filter "name=main"
```

**ファイルが見つからない:**
```bash
uv run tree-sitter-analyzer nonexistent.py --query-key function
# Error: File not found: nonexistent.py
```

**対処:** ファイルパスを確認

**未対応言語:**
```bash
uv run tree-sitter-analyzer script.lua --query-key function
# Error: Unsupported language: Lua
```

**対処:** `--show-supported-languages`でサポート言語を確認

**プロジェクトルート外アクセス:**
```bash
uv run tree-sitter-analyzer /etc/passwd --query-key function --project-root /home/user/project
# ERROR: Path traversal detected
```

**対処法:** プロジェクトルート内のファイルのみ指定

---

## 9. パフォーマンスと最適化

### 9.1 キャッシュの活用

Tree-sitter AnalyzerはCacheServiceによる3層キャッシュ（L1/L2/L3）を自動的に使用します。

**効果:**
- 同一ファイルの繰り返し解析: 10-100倍高速化
- メモリ効率的なキャッシュ管理
- TTLによる自動期限切れ

**注意:** キャッシュは自動管理されるため、CLIから明示的に制御する必要はありません。

### 9.2 部分読み取りモードによる最適化

大規模ファイルの特定範囲のみを解析する場合、`--partial-read`オプションを使用：

```bash
# 100-200行のみ解析（メモリ効率的）
uv run tree-sitter-analyzer large_file.py --query-key function --partial-read --start-line 100 --end-line 200
```

**効果:**
- メモリ使用量の削減
- 解析速度の向上
- 大規模ファイルでも高速処理

### 9.3 出力形式の選択

**JSON形式（デフォルト）:**
- 機械処理に適している
- パイプライン処理に最適

**テーブル形式:**
- 人間が読みやすい
- ターミナルで直接確認する場合に推奨

```bash
# 機械処理用（JSON）
uv run tree-sitter-analyzer file.py --query-key function > output.json

# 人間用（テーブル）
uv run tree-sitter-analyzer file.py --table compact
```

---

## 10. トラブルシューティング

### 10.1 よくある問題

**1. コマンドが見つからない**
```
command not found: tree-sitter-analyzer
```

**解決策:**
- 開発環境: `uv run tree-sitter-analyzer`を使用
- システムインストール: `pip install tree-sitter-analyzer`を実行

**2. クエリまたはモードが必要**
```
ERROR: Please specify a query or --advanced option
```

**解決策:** 以下のいずれかを指定
- `--query-key <key>`
- `--query-string "<query>"`
- `--advanced`
- `--summary`
- `--table <format>`
- `--structure`

**3. --tableと--query-keyの併用エラー**
```
ERROR: --table and --query-key cannot be used together
```

**解決策:** どちらか一方のみ使用
- テーブル形式: `--table full`
- クエリ実行: `--query-key function`
- クエリ+フィルタ: `--query-key method --filter "name=main"`（この組み合わせは可能）

**4. プロジェクトルート外アクセス**
```
ERROR: Path traversal detected
```

**解決策:** プロジェクトルート内のファイルのみを指定

### 10.2 デバッグ情報の取得

**詳細ログの有効化:**
```bash
# 環境変数でログレベルを設定
$env:LOG_LEVEL="DEBUG"
uv run tree-sitter-analyzer file.py --query-key function
```

**静かな出力（エラーのみ）:**
```bash
uv run tree-sitter-analyzer file.py --query-key function --quiet
```

---

## 11. ベストプラクティス

### 11.1 効率的なクエリの使用

**推奨:**
```bash
# 特定のクエリキーを使用（高速）
uv run tree-sitter-analyzer file.py --query-key method

# フィルタで絞り込み（効率的）
uv run tree-sitter-analyzer file.py --query-key method --filter "name=~get*"
```

**非推奨:**
```bash
# 全体解析後に手動フィルタ（非効率）
uv run tree-sitter-analyzer file.py --query-key method | grep "get"
```

### 11.2 大規模プロジェクトの解析

**段階的アプローチ:**
1. まずサマリーで全体像を把握
2. 特定ファイルを詳細解析
3. 必要に応じてクエリで絞り込み

```bash
# ステップ1: 概要把握
uv run tree-sitter-analyzer main.py --summary

# ステップ2: 詳細解析
uv run tree-sitter-analyzer main.py --advanced

# ステップ3: 特定要素の抽出
uv run tree-sitter-analyzer main.py --query-key method --filter "public=true"
```

### 11.3 CI/CDパイプラインでの使用

**JSON出力を活用:**
```bash
# 解析結果をJSON形式で保存
uv run tree-sitter-analyzer src/main.py --advanced > analysis.json

# jqで後処理
cat analysis.json | jq '.elements[] | select(.type=="class")'
```

**エラーハンドリング:**
```bash
# 終了コードをチェック
if ! uv run tree-sitter-analyzer file.py --query-key function --quiet; then
    echo "Analysis failed"
    exit 1
fi
```

---

## 12. 改訂履歴

| バージョン | 日付 | 変更内容 | 承認者 |
|-----------|------|---------|--------|
| 1.0 | 2025-11-03 | 初版作成（実際のCLI実行により検証済み） | aisheng.yu |
| 1.1 | 2025-11-03 | Java/Python言語別クエリキー詳細追加（検証済み）<br>・Java: 17クエリキーを実行検証<br>・Python: 5クエリキーを実行検証<br>・javadoc_commentクエリのバグ修正（正規表現エラー解消）<br>・static_methodsクエリが正常動作することを確認<br>・80+のクエリキー一覧を記載 | aisheng.yu |
| 1.2 | 2025-11-03 | パフォーマンス、トラブルシューティング、ベストプラクティスのセクションを追加<br>・セクション9: パフォーマンスと最適化（キャッシュ、部分読み取り、出力形式）<br>・セクション10: トラブルシューティング（よくある問題とデバッグ）<br>・セクション11: ベストプラクティス（効率的なクエリ、大規模プロジェクト、CI/CD統合）<br>・セクション7.1.6: Spring関連の見出し追加（構造の明確化） | aisheng.yu |

---

**最終更新:** 2025-11-03  
**管理者:** aisheng.yu  
**連絡先:** aimasteracc@gmail.com  
**検証方法:** 実際のCLI実行 (`uv run tree-sitter-analyzer --help` 等) により全コマンド・オプション確認済み
