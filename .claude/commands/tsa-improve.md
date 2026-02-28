# /tsa-improve

tree-sitter-analyzerをTDD + Spec駆動で自立的に改善するコマンド。

## 使用方法

```
/tsa-improve [options]
```

## オプション

- `--analyze`: 分析フェーズのみ
- `--spec`: Spec定義のみ
- `--red`: テスト作成のみ
- `--green`: 実装のみ
- `--refactor`: リファクタリングのみ
- `--target <module>`: 特定モジュール対象
- `--coverage <N>`: 目標カバレッジ (デフォルト: 80)

## 実行フロー

```
1. ANALYZE  カバレッジ分析
   uv run pytest --cov --cov-report=json

2. SPEC     仕様定義
   openspec/specs/{module}/spec.md

3. RED      テスト作成
   tests/unit/{module}/test_{target}.py
   → 失敗確認

4. GREEN    最小実装
   tree_sitter_analyzer/{module}/{target}.py
   → 成功確認

5. REFACTOR 品質向上
   mypy, ruff, check_quality.py
```

## 例

```
User: /tsa-improve --target mcp.tools

Claude: カバレッジ分析を実行します...
[uv run pytest --cov=tree_sitter_analyzer.mcp.tools]

低カバレッジモジュール:
- analyze_code_structure_tool: 45%
- query_tool: 62%

Specを作成します...
[openspec/specs/mcp.tools/spec.md]

RED: テストを作成します...
[tests/unit/mcp/test_tools/test_analyze_code_structure_tool.py]

テスト実行: FAILED ✅ (期待通り)

GREEN: 実装します...
...

REFACTOR: 品質チェック...
全テスト: PASS ✅
カバレッジ: 85% (+40%)
```

## 関連コマンド

- `/tsa-spec <target>`: Spec作成
- `/tsa-verify [target]`: 整合性検証
