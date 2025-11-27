# 新しい言語サポート追加チェックリスト

このドキュメントは、Tree-sitter Analyzerに新しいプログラミング言語のサポートを追加する際に必要な手順をまとめたものです。

## 📋 必須チェックリスト

### 1. 言語プラグインの実装

- [ ] `tree_sitter_analyzer/languages/{language}_plugin.py` を作成
  - [ ] `LanguagePlugin` クラスを継承
  - [ ] `get_language_name()` を実装
  - [ ] `get_file_extensions()` を実装
  - [ ] `create_extractor()` を実装
  - [ ] `get_supported_element_types()` を実装
  - [ ] `get_queries()` を実装
  - [ ] `analyze_file()` を実装

### 2. 要素抽出器の実装

- [ ] `{Language}ElementExtractor` クラスを作成
  - [ ] `ElementExtractor` を継承
  - [ ] 言語固有の要素抽出メソッドを実装

### 3. クエリ定義

- [ ] `tree_sitter_analyzer/queries/{language}.py` を作成
  - [ ] 言語固有のTree-sitterクエリを定義

### 4. フォーマッターの実装

- [ ] `tree_sitter_analyzer/formatters/{language}_formatter.py` を作成
  - [ ] `BaseFormatter` を継承
  - [ ] `format_summary()` を実装
  - [ ] `format_structure()` を実装
  - [ ] `format_advanced()` を実装
  - [ ] `format_table()` を実装

### 5. フォーマッターの登録

- [ ] `tree_sitter_analyzer/formatters/formatter_registry.py` にフォーマッターを登録

### 6. サンプルファイルの作成

- [ ] `examples/sample.{ext}` または `examples/Sample.{Ext}` を作成
  - [ ] 言語の主要な機能を網羅したサンプルコード

### 7. 単体テストの作成

- [ ] `tests/test_{language}/test_{language}_plugin.py` を作成
  - [ ] プラグインの基本機能テスト
  - [ ] 要素抽出テスト
  - [ ] エッジケーステスト

### 8. ⭐ ゴールデンマスターテストの追加（重要！）

- [ ] `tests/golden_masters/full/{language}_sample_{name}_full.md` を作成
- [ ] `tests/golden_masters/compact/{language}_sample_{name}_compact.md` を作成（オプション）
- [ ] `tests/golden_masters/csv/{language}_sample_{name}_csv.csv` を作成（オプション）
- [ ] `tests/test_golden_master_regression.py` にテストケースを追加
  ```python
  # {Language} tests
  ("examples/sample.{ext}", "{language}_sample", "full"),
  ("examples/sample.{ext}", "{language}_sample", "compact"),
  ("examples/sample.{ext}", "{language}_sample", "csv"),
  ```

> **⚠️ 教訓**: ゴールデンマスターテストは、将来の変更によるリグレッションを防ぐために非常に重要です。
> 新しい言語を追加する際は、必ずゴールデンマスターテストを作成してください。

### 9. プロパティベーステストの作成（推奨）

- [ ] `tests/test_{language}/test_{language}_properties.py` を作成
  - [ ] 言語固有のプロパティテスト

### 10. 依存関係の追加

- [ ] `pyproject.toml` に tree-sitter-{language} を追加
  ```toml
  [project.optional-dependencies]
  {language} = ["tree-sitter-{language}>=x.x.x"]
  ```

### 11. ドキュメントの更新

- [ ] `README.md` の言語サポート表を更新
- [ ] `README_zh.md` の言語サポート表を更新
- [ ] `README_ja.md` の言語サポート表を更新
- [ ] `CHANGELOG.md` に新機能として記載

### 12. Entry Pointsの登録（必要に応じて）

- [ ] `pyproject.toml` の `[project.entry-points]` セクションを更新

## 📁 ファイル構造の例

```
tree_sitter_analyzer/
├── languages/
│   └── {language}_plugin.py      # 言語プラグイン
├── formatters/
│   └── {language}_formatter.py   # フォーマッター
└── queries/
    └── {language}.py             # クエリ定義

examples/
└── sample.{ext}                  # サンプルファイル

tests/
├── test_{language}/
│   ├── test_{language}_plugin.py
│   ├── test_{language}_properties.py
│   └── test_{language}_golden_master.py  # 言語固有のゴールデンマスターテスト
└── golden_masters/
    ├── full/
    │   └── {language}_sample_full.md
    ├── compact/
    │   └── {language}_sample_compact.md
    └── csv/
        └── {language}_sample_csv.csv
```

## 🔍 テスト実行コマンド

```bash
# 言語固有のテストを実行
uv run pytest tests/test_{language}/ -v

# ゴールデンマスターテストを実行
uv run pytest tests/test_golden_master_regression.py -v -k "{language}"

# 全テストを実行
uv run pytest tests/ -v
```

## 📝 参考実装

以下の言語実装を参考にしてください：

- **Java**: `tree_sitter_analyzer/languages/java_plugin.py` - 最も完全な実装
- **Python**: `tree_sitter_analyzer/languages/python_plugin.py` - シンプルな実装
- **SQL**: `tree_sitter_analyzer/languages/sql_plugin.py` - 専用フォーマッター付き
- **YAML**: `tree_sitter_analyzer/languages/yaml_plugin.py` - 非同期解析の例
- **HTML/CSS**: `tree_sitter_analyzer/languages/html_plugin.py` - マークアップ言語の例

## ⚠️ よくある問題と解決策

### 1. CLIでフォーマッターが使用されない

**問題**: `--table` コマンドで言語固有のフォーマッターが呼び出されない

**解決策**: 
- `formatter_registry.py` にフォーマッターを登録
- `table_command.py` の `LANGUAGE_FORMATTER_CONFIG` に言語を追加

### 2. ゴールデンマスターテストが失敗する

**問題**: 環境によって出力が異なる

**解決策**:
- `normalize_output()` 関数で環境依存の部分を正規化
- 行末の空白や改行コードを統一

### 3. tree-sitter パーサーが見つからない

**問題**: `ImportError: tree-sitter-{language} not installed`

**解決策**:
- `pyproject.toml` に依存関係を追加
- `uv sync --extra {language}` を実行

---

**最終更新**: 2025-11-27
**作成理由**: YAML言語サポート追加時にゴールデンマスターテストが漏れていたため、今後の教訓として作成
