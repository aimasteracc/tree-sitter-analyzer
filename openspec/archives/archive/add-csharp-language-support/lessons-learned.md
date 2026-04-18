# Lessons Learned: C# Language Support Implementation

## 📋 概要

C#言語サポート実装から学んだ教訓と、今後の言語追加時に活用できるベストプラクティスをまとめます。

## 🎯 発見された設計漏れ

### 1. クエリシステムの実装忘れ ⚠️

**問題**: 
- 初期実装では `get_queries()`, `execute_query_strategy()`, `get_element_categories()` メソッドが欠けていた
- HTML, CSSプラグインには実装されていたが、見落とした

**影響**:
- 高度なコード検索機能が使えない
- 他の言語との機能パリティがない

**解決策**:
```python
# tree_sitter_analyzer/queries/csharp.py を作成
CSHARP_QUERIES: dict[str, str] = {
    "class": """(class_declaration name: (identifier) @class_name) @class""",
    # ... 30+ queries
}

# Plugin に3つのメソッドを追加
def get_queries(self) -> dict[str, str]:
    from ..queries.csharp import CSHARP_QUERIES
    return CSHARP_QUERIES

def execute_query_strategy(self, query_key: str | None, language: str) -> str | None:
    if language != "csharp":
        return None
    queries = self.get_queries()
    return queries.get(query_key) if query_key else None

def get_element_categories(self) -> dict[str, list[str]]:
    return {
        "classes": ["class", "interface", "record", "enum", "struct"],
        "methods": ["method", "constructor"],
        # ...
    }
```

**教訓**: 
- ✅ 既存の**すべての**言語プラグインを確認し、共通パターンを抽出する
- ✅ クエリシステムは高度な機能なので、初期実装で見落としやすい

### 2. フォーマッターの実装忘れ ⚠️⚠️

**問題**:
- `tree_sitter_analyzer/formatters/` ディレクトリにC#フォーマッターがなかった
- 他の言語（Java, Python, TypeScript, SQL, HTML, CSS, Markdown）にはすべて専用フォーマッターがある

**影響**:
- C#コードの出力が汎用フォーマットになり、言語固有の最適化がない
- 他の言語との一貫性がない

**解決策**:
```python
# 1. tree_sitter_analyzer/formatters/csharp_formatter.py を作成
class CSharpTableFormatter(BaseTableFormatter):
    def _format_full_table(self, data: dict[str, Any]) -> str:
        # C# specific formatting
        pass
    
    def _format_compact_table(self, data: dict[str, Any]) -> str:
        # Compact format
        pass
    
    def _format_csv(self, data: dict[str, Any]) -> str:
        # CSV format
        pass

# 2. formatter_config.py に追加
"csharp": {
    "table": "legacy",
    "compact": "legacy",
    "full": "legacy",
    "csv": "legacy",
    "json": "legacy",
},

# 3. language_formatter_factory.py に登録
from .csharp_formatter import CSharpTableFormatter

_formatters: dict[str, type[BaseFormatter]] = {
    # ...
    "csharp": CSharpTableFormatter,
    "cs": CSharpTableFormatter,  # Alias
}
```

**教訓**:
- ✅ フォーマッターは**3箇所**に登録が必要
  1. フォーマッターファイル作成
  2. `formatter_config.py` に設定追加
  3. `language_formatter_factory.py` に登録
- ✅ エイリアス（`cs` for C#）も忘れずに

### 3. tasks.md のチェックボックス未更新 ⚠️

**問題**:
- 実装は完了していたが、OpenSpec の `tasks.md` のチェックボックスが `[ ]` のまま
- 進捗状況が正確に反映されていない

**解決策**:
```python
# 自動更新スクリプトを作成
import re

with open("tasks.md", "r") as f:
    content = f.read()

# 完了したセクションのチェックボックスを更新
content = re.sub(r"- \[ \]", "- [x]", content)

with open("tasks.md", "w") as f:
    f.write(content)
```

**教訓**:
- ✅ 実装完了後、すぐにタスクチェックボックスを更新する
- ✅ 自動化スクリプトを活用する

## 🎓 ベストプラクティス

### 1. 3つの主要コンポーネント

新言語サポートには、以下の3つのコンポーネントすべてが必要：

```
1. Language Plugin (必須)
   ├── {Language}Plugin
   └── {Language}ElementExtractor

2. Query System (必須)
   ├── queries/{language}.py
   └── Plugin methods (get_queries, execute_query_strategy, get_element_categories)

3. Table Formatter (必須)
   ├── formatters/{language}_formatter.py
   ├── formatter_config.py (設定)
   └── language_formatter_factory.py (登録)
```

### 2. 実装順序

推奨される実装順序：

```
Phase 1: 基盤セットアップ
  ├── 依存関係追加 (pyproject.toml)
  └── 言語検出設定 (language_detector.py)

Phase 2: Plugin実装
  ├── Plugin クラス
  ├── ElementExtractor クラス
  └── エントリーポイント登録

Phase 3: Query実装 ⭐ 見落としやすい
  ├── queries/{language}.py
  └── Plugin にメソッド追加

Phase 4: Formatter実装 ⭐ 見落としやすい
  ├── formatters/{language}_formatter.py
  ├── formatter_config.py
  └── language_formatter_factory.py

Phase 5: サンプルとテスト
  ├── サンプルファイル
  ├── 単体テスト
  └── 統合テスト

Phase 6: ドキュメント
  ├── README
  ├── CHANGELOG
  └── OpenSpec
```

### 3. チェックリスト駆動開発

**実装前**:
```markdown
## 実装チェックリスト

### Plugin
- [ ] Plugin クラス作成
- [ ] ElementExtractor クラス作成
- [ ] エントリーポイント登録

### Query
- [ ] queries/{language}.py 作成
- [ ] get_queries() 実装
- [ ] execute_query_strategy() 実装
- [ ] get_element_categories() 実装

### Formatter
- [ ] formatters/{language}_formatter.py 作成
- [ ] formatter_config.py に追加
- [ ] language_formatter_factory.py に登録

### Test
- [ ] サンプルファイル作成
- [ ] 単体テスト作成
- [ ] CLI動作確認

### Documentation
- [ ] README 更新
- [ ] CHANGELOG 更新
```

### 4. 参照実装の選択

新言語を追加する際は、類似した既存言語を参照：

| 新言語タイプ | 参照実装 | 理由 |
|-------------|---------|------|
| OOP言語 (C#, Kotlin, Swift) | Java | クラス、メソッド、フィールド構造が類似 |
| スクリプト言語 (Ruby, PHP) | Python | 動的型付け、柔軟な構文 |
| 関数型言語 (Haskell, F#) | TypeScript | 型システム、高度な機能 |
| マークアップ言語 (XML, YAML) | HTML | 階層構造、要素ベース |
| データ言語 (JSON, TOML) | SQL | データ構造、クエリ |

### 5. 早期テスト

各フェーズ完了後、すぐに動作確認：

```bash
# Phase 2完了後
uv run tree-sitter-analyzer examples/Sample.{ext} --table full

# Phase 3完了後
# クエリが動作するか確認（MCP経由など）

# Phase 4完了後
uv run tree-sitter-analyzer examples/Sample.{ext} --table compact
uv run tree-sitter-analyzer examples/Sample.{ext} --table csv
```

## 🔍 設計漏れ検出方法

### 自動チェックスクリプト

```bash
#!/bin/bash
# check_language_completeness.sh

LANG=$1
EXT=$2

echo "Checking completeness for language: $LANG"

# 1. Plugin exists
if [ -f "tree_sitter_analyzer/languages/${LANG}_plugin.py" ]; then
    echo "✓ Plugin file exists"
else
    echo "✗ Plugin file missing"
fi

# 2. Query file exists
if [ -f "tree_sitter_analyzer/queries/${LANG}.py" ]; then
    echo "✓ Query file exists"
else
    echo "✗ Query file missing"
fi

# 3. Formatter exists
if [ -f "tree_sitter_analyzer/formatters/${LANG}_formatter.py" ]; then
    echo "✓ Formatter file exists"
else
    echo "✗ Formatter file missing"
fi

# 4. Entry point registered
if grep -q "${LANG} = " pyproject.toml; then
    echo "✓ Entry point registered"
else
    echo "✗ Entry point not registered"
fi

# 5. Formatter config
if grep -q "\"${LANG}\":" tree_sitter_analyzer/formatters/formatter_config.py; then
    echo "✓ Formatter config exists"
else
    echo "✗ Formatter config missing"
fi

# 6. Formatter factory
if grep -q "${LANG}" tree_sitter_analyzer/formatters/language_formatter_factory.py; then
    echo "✓ Formatter factory registered"
else
    echo "✗ Formatter factory not registered"
fi

# 7. Sample file exists
if [ -f "examples/Sample.${EXT}" ]; then
    echo "✓ Sample file exists"
else
    echo "✗ Sample file missing"
fi

# 8. README updated
if grep -q "${LANG}" README.md; then
    echo "✓ README updated"
else
    echo "✗ README not updated"
fi
```

使用例:
```bash
./check_language_completeness.sh csharp cs
```

### 手動チェックリスト

実装完了後、以下を確認：

```markdown
## 完成度チェック

### ファイル存在確認
- [ ] tree_sitter_analyzer/languages/{language}_plugin.py
- [ ] tree_sitter_analyzer/queries/{language}.py
- [ ] tree_sitter_analyzer/formatters/{language}_formatter.py
- [ ] examples/Sample.{ext}

### 設定登録確認
- [ ] pyproject.toml: dependencies
- [ ] pyproject.toml: optional-dependencies
- [ ] pyproject.toml: entry-points
- [ ] formatter_config.py: language config
- [ ] language_formatter_factory.py: formatter registration

### 機能確認
- [ ] CLI: --table full
- [ ] CLI: --table compact
- [ ] CLI: --table csv
- [ ] Query: get_queries() works
- [ ] Formatter: all formats work

### ドキュメント確認
- [ ] README.md: language list updated
- [ ] CHANGELOG.md: entry added
- [ ] Language count updated (8→9)
```

## 📊 C#実装の統計

| カテゴリ | 初期実装 | 最終実装 | 追加 |
|---------|---------|---------|------|
| Plugin | ✓ | ✓ | - |
| Query | ✗ | ✓ | +1 file, +3 methods |
| Formatter | ✗ | ✓ | +1 file, +2 configs |
| サンプル | ✓ | ✓ | - |
| テスト | △ | ✓ | 動作確認 |
| ドキュメント | △ | ✓ | 完全更新 |

**初期完成度**: 50% (3/6)  
**最終完成度**: 100% (6/6)

## 🚀 改善提案

### 1. テンプレートジェネレーター

```bash
# 新言語追加用のスクリプト
./scripts/generate_language_template.sh kotlin kt

# 自動生成されるファイル:
# - tree_sitter_analyzer/languages/kotlin_plugin.py
# - tree_sitter_analyzer/queries/kotlin.py
# - tree_sitter_analyzer/formatters/kotlin_formatter.py
# - examples/Sample.kt
# - tests/test_languages/test_kotlin_plugin.py
```

### 2. 完成度チェックCI

```yaml
# .github/workflows/language-completeness.yml
name: Language Completeness Check

on: [pull_request]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Check language completeness
        run: |
          ./scripts/check_all_languages.sh
```

### 3. ドキュメント自動生成

```python
# scripts/update_language_docs.py
# README.md の言語リストを自動更新
# CHANGELOG.md のテンプレート生成
```

## 💡 重要な気づき

1. **設計は3層構造**: Plugin + Query + Formatter
2. **登録箇所は複数**: 1つのコンポーネントに対して2-3箇所の登録が必要
3. **既存言語を参照**: 車輪の再発明をしない
4. **早期テスト**: 各フェーズで動作確認
5. **チェックリスト駆動**: 見落としを防ぐ

## 📚 参考資料

- [新言語追加チェックリスト](../development/new-language-checklist.md)
- [C# OpenSpec Proposal](./proposal.md)
- [C# Design Document](./design.md)
- [C# Tasks](./tasks.md)

## 🎯 次回への提言

新しい言語を追加する際は：

1. ✅ このドキュメントを読む
2. ✅ チェックリストを印刷/コピーする
3. ✅ 類似言語の実装を3つ確認する
4. ✅ 各フェーズ完了後に動作確認
5. ✅ 完成度チェックスクリプトを実行
6. ✅ すべてのチェックボックスが ✓ になるまで完了しない

**完璧な実装 = Plugin + Query + Formatter + Tests + Docs**

