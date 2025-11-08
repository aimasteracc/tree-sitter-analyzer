# SQL Format Guide

このガイドでは、tree-sitter-analyzerのSQL専用出力フォーマットについて詳しく説明します。

## 概要

tree-sitter-analyzerは、SQLファイル専用の出力フォーマットを提供します。これにより、データベーススキーマの文書化に適した、プロフェッショナルな出力を生成できます。

## 🆕 v1.9.7 SQL出力フォーマット再設計完了

### 主要な改善点

- **完全なSQL専用フォーマッター実装**: SQLFullFormatter、SQLCompactFormatter、SQLCSVFormatterを新規実装
- **データベース専用用語の完全適用**: 全ての出力で適切なデータベース用語を使用
- **包括的なSQL要素サポート**: 全てのSQL要素タイプの完全な識別と表示
- **専門的な出力品質**: データベース文書化標準に準拠した出力形式

## SQL専用フォーマットの特徴

### データベース専用用語

従来の汎用的なクラスベース用語から、適切なデータベース用語に変更されました：

| 従来の用語 | SQL専用用語 |
|------------|-------------|
| Classes Overview | Database Schema Overview |
| Class | Table/View/Procedure/Function/Trigger/Index |
| Method | Procedure/Function |
| Field | Column |
| Public/Private | N/A (データベース要素に適用されない) |

### サポートされるSQL要素

1. **SQLTable** - テーブル構造（カラム、制約、インデックス情報）
2. **SQLView** - ビュー定義（ベーステーブル、カラム構造）
3. **SQLProcedure** - ストアドプロシージャ（パラメータ、戻り値）
4. **SQLFunction** - 関数（引数、戻り値型、機能説明）
5. **SQLTrigger** - トリガー（イベント、タイミング、対象テーブル）
6. **SQLIndex** - インデックス（対象テーブル、カラム、タイプ）

## 出力フォーマット

### Full Format（詳細フォーマット）

データベーススキーマの完全な詳細を表示します。

```markdown
# Database Schema Overview

## Schema Statistics
| Metric | Count |
|--------|-------|
| Tables | 3 |
| Views | 1 |
| Procedures | 2 |
| Functions | 1 |
| Triggers | 1 |
| Indexes | 2 |

## Tables

### users (Lines: 1-8)
**Type:** Table

#### Columns
| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PRIMARY KEY |
| name | VARCHAR(100) | NOT NULL |
| email | VARCHAR(255) | UNIQUE |

#### Constraints
- PRIMARY KEY: id
- UNIQUE: email

### Functions

### get_user_count (Lines: 25-30)
**Type:** Function  
**Return Type:** INTEGER

Returns the total number of users in the system.
```

### Compact Format（概要フォーマット）

重要な情報を1つのテーブルにまとめて表示します。

```markdown
# Database Schema Overview

| Element | Type | Line | Details |
|---------|------|------|---------|
| users | Table | 1-8 | 3 columns, PRIMARY KEY: id |
| orders | Table | 10-18 | 4 columns, FOREIGN KEY: user_id |
| user_view | View | 20-23 | Based on users table |
| get_user_count | Function | 25-30 | Returns INTEGER |
| update_user_stats | Procedure | 32-40 | 2 parameters |
| user_audit_trigger | Trigger | 42-48 | AFTER INSERT ON users |
| idx_user_email | Index | 50-51 | ON users(email) |
```

### CSV Format（データ処理用）

機械処理に適したCSV形式で出力します。

```csv
element_name,element_type,start_line,end_line,details,metadata
users,Table,1,8,"3 columns, PRIMARY KEY: id","{""columns"": 3, ""primary_key"": ""id""}"
orders,Table,10,18,"4 columns, FOREIGN KEY: user_id","{""columns"": 4, ""foreign_keys"": [""user_id""]}"
user_view,View,20,23,"Based on users table","{""base_tables"": [""users""]}"
get_user_count,Function,25,30,"Returns INTEGER","{""return_type"": ""INTEGER""}"
update_user_stats,Procedure,32,40,"2 parameters","{""parameters"": 2}"
user_audit_trigger,Trigger,42,48,"AFTER INSERT ON users","{""event"": ""INSERT"", ""timing"": ""AFTER""}"
idx_user_email,Index,50,51,"ON users(email)","{""table"": ""users"", ""columns"": [""email""]}"
```

## 使用方法

### CLI使用例

```bash
# Full format（詳細）- 専用SQLフォーマッターを使用
uv run tree-sitter-analyzer examples/sample_database.sql --table full

# Compact format（概要）- 専用SQLフォーマッターを使用
uv run tree-sitter-analyzer examples/sample_database.sql --table compact

# CSV format（データ処理用）- 専用SQLフォーマッターを使用
uv run tree-sitter-analyzer examples/sample_database.sql --table csv

# 高度な分析（構造とメトリクス）
uv run tree-sitter-analyzer examples/sample_database.sql --advanced --output-format text
```

### MCP Tool使用例

```json
{
  "tool": "analyze_code_structure",
  "arguments": {
    "file_path": "examples/sample_database.sql",
    "format_type": "full"
  }
}
```

### AI Assistant使用例

```
I want to analyze the database schema in sample_database.sql:
1. What tables, views, and stored procedures are defined?
2. What are the relationships between different database objects?
3. Show me the database structure in a professional format.
```

AI will automatically:
1. Extract all SQL elements (tables, views, procedures, functions, triggers, indexes)
2. Display database-specific terminology ("Database Schema Overview" instead of "Classes Overview")
3. Generate professional database documentation with specialized SQL formatting

## SQL要素の詳細

### SQLTable

テーブル構造の詳細情報を提供します：

- **カラム情報**: 名前、データ型、制約
- **制約情報**: PRIMARY KEY、FOREIGN KEY、UNIQUE、CHECK制約
- **インデックス情報**: 関連するインデックス

### SQLView

ビューの定義情報を提供します：

- **ベーステーブル**: ビューが参照するテーブル
- **カラム情報**: ビューのカラム構造
- **依存関係**: 他のビューやテーブルとの関係

### SQLProcedure

ストアドプロシージャの詳細を提供します：

- **パラメータ**: 入力・出力パラメータの詳細
- **戻り値**: プロシージャの戻り値型
- **説明**: プロシージャの機能説明

### SQLFunction

関数の詳細情報を提供します：

- **パラメータ**: 関数の引数
- **戻り値型**: 関数の戻り値の型
- **説明**: 関数の機能説明

### SQLTrigger

トリガーの詳細情報を提供します：

- **イベント**: INSERT、UPDATE、DELETE
- **タイミング**: BEFORE、AFTER
- **対象テーブル**: トリガーが設定されているテーブル

### SQLIndex

インデックスの詳細情報を提供します：

- **対象テーブル**: インデックスが設定されているテーブル
- **カラム**: インデックスに含まれるカラム
- **タイプ**: UNIQUE、CLUSTERED等のインデックスタイプ

## メタデータ抽出

SQL専用フォーマットでは、以下のメタデータが自動的に抽出されます：

### テーブルメタデータ
- カラム数
- 制約情報
- インデックス情報
- 外部キー関係

### プロシージャ/関数メタデータ
- パラメータ数と型
- 戻り値型
- 複雑度指標

### トリガーメタデータ
- イベントタイプ
- 実行タイミング
- 対象テーブル

## ベストプラクティス

### 1. 適切なフォーマットの選択

- **Full Format**: 詳細なドキュメント作成時
- **Compact Format**: 概要把握や軽量な文書化
- **CSV Format**: データ分析や自動処理

### 2. 大きなスキーマの処理

大きなデータベーススキーマの場合：

```bash
# ファイル出力を使用（リダイレクトで出力）
tree-sitter-analyzer examples/sample_database.sql --table full > schema_doc.md
```

### 3. 継続的文書化

CI/CDパイプラインに組み込んで、スキーマ変更を自動文書化：

```yaml
- name: Generate SQL Documentation
  run: |
    tree-sitter-analyzer examples/sample_database.sql --table full > docs/schema.md
```

## トラブルシューティング

### よくある問題

1. **SQL構文エラー**
   - tree-sitter-sqlがサポートしていない構文
   - 解決策: 標準的なSQL構文を使用

2. **メタデータ抽出の不完全性**
   - 複雑なSQL構造での制限
   - 解決策: シンプルな構造に分割

3. **パフォーマンス問題**
   - 非常に大きなSQLファイル
   - 解決策: ファイルを分割して処理

### サポートされるSQL方言

現在サポートされているSQL方言：

- **標準SQL** (ANSI SQL) - 完全サポート
- **PostgreSQL** - 基本的なサポート
- **MySQL** - 基本的なサポート
- **SQLite** - 基本的なサポート

## 🔧 技術実装詳細

### 専用フォーマッタークラス

1. **SQLFullFormatter** - 詳細なデータベーススキーマ文書化
2. **SQLCompactFormatter** - 概要表示とクイックリファレンス
3. **SQLCSVFormatter** - データ処理と自動化に適したCSV出力

### SQL要素タイプシステム

```python
class SQLElementType(Enum):
    TABLE = "Table"
    VIEW = "View"
    PROCEDURE = "Procedure"
    FUNCTION = "Function"
    TRIGGER = "Trigger"
    INDEX = "Index"
```

### Tree-sitterクエリシステム

包括的なSQL Tree-sitterクエリライブラリを実装：
- 全てのSQL要素（テーブル、ビュー、プロシージャ、関数、トリガー、インデックス）をサポート
- 高度なSQL機能（CTE、ウィンドウ関数、サブクエリ）の解析対応
- tree-sitter-sql ERRORノードのエラーハンドリング実装

## 品質保証

### テストカバレッジ

- **25個の包括的テスト**: 全てのSQLフォーマッターとプラグイン機能をテスト
- **コード品質**: MyPy型チェック100%準拠、Ruffリンティング全チェック合格
- **パフォーマンス**: 大きなSQLファイルでも適切な応答時間とメモリ使用量を確認
- **エンドツーエンドテスト**: CLI、API、MCPインターフェース全てでSQL分析機能が正常動作

### 実際の出力例

実際の`examples/sample_database.sql`ファイルを使用したテスト結果：
- **要素数**: 6個のSQL要素を正確に抽出
- **処理時間**: 0.1秒未満で高速処理
- **出力品質**: データベース文書化標準に準拠した専門的な出力

## 今後の拡張予定

- より多くのSQL方言サポート（Oracle、SQL Server等）
- 高度なメタデータ抽出（詳細な制約情報、パフォーマンス指標）
- ER図生成機能
- スキーマ比較機能
- データベース依存関係の可視化

## 関連ドキュメント

- [README.md](../README.md) - 基本的な使用方法
- [format-specifications.md](./format-specifications.md) - 全フォーマット仕様
- [testing-guide.md](./testing-guide.md) - テスト方法
