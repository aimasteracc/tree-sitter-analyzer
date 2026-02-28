# /tsa-improve

tree-sitter-analyzerをTDD + Spec駆動で自立的に改善するコマンド。

## 使用方法

```
/tsa-improve [options]
```

## オプション

| オプション | 説明 |
|-----------|------|
| `--analyze` | 分析フェーズのみ実行 |
| `--spec` | Spec定義フェーズのみ |
| `--red` | RED (テスト作成) フェーズのみ |
| `--green` | GREEN (実装) フェーズのみ |
| `--refactor` | REFACTOR フェーズのみ |
| `--target <module>` | 特定モジュールのみ対象 |
| `--coverage <N>` | 目標カバレッジ (デフォルト: 80) |
| `--dry-run` | タスク生成のみ、実行しない |
| `--continue` | 前回の続きから再開 |

## 実行例

```
/tsa-improve                          # フルサイクル実行
/tsa-improve --analyze                # 分析のみ
/tsa-improve --target mcp.tools       # MCPツールのみ
/tsa-improve --coverage 90            # 90%目標
/tsa-improve --red --target cli       # CLIのテスト作成のみ
```

## ワークフロー

```
1. ANALYZE  カバレッジ分析 → 改善候補特定
2. SPEC     機能仕様定義
3. RED      失敗するテスト作成
4. GREEN    最小実装でテスト成功
5. REFACTOR 品質向上
```

## 出力

- Spec: `openspec/specs/{module}/spec.md`
- Test: `tests/unit/{module}/test_{target}.py`
- Impl: `tree_sitter_analyzer/{module}/{target}.py`

## 終了条件

- 全テストパス
- カバレッジ >= 目標値
- 品質チェックパス
