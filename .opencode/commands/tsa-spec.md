# /tsa-spec

tree-sitter-analyzerの機能仕様 (Spec) を作成・管理するコマンド。

## 使用方法

```
/tsa-spec <target> [options]
```

## 引数

| 引数 | 説明 |
|------|------|
| `<target>` | Spec対象 (モジュール名、ファイルパス、機能名) |

## オプション

| オプション | 説明 |
|-----------|------|
| `--from-tests` | 既存テストからSpec逆生成 |
| `--from-code` | 既存コードからSpec生成 |
| `--template` | 空のSpecテンプレート作成 |
| `--verify` | Specと実装の整合性検証 |
| `--list` | 既存Spec一覧表示 |

## 実行例

```
/tsa-spec mcp.tools.analyze_code_structure    # 機能のSpec作成
/tsa-spec cli --from-tests                    # テストからSpec生成
/tsa-spec --list                              # Spec一覧
/tsa-spec query --verify                      # 整合性検証
```

## Specファイル構成

```markdown
# {機能名} Specification

## 概要
## インターフェース
## 振る舞い
## 事前条件
## 事後条件
## 受け入れ基準
## テストケース一覧
```

## 出力先

`openspec/specs/{module}/spec.md`

## ワークフロー

1. 対象コード/テストを分析
2. インターフェース抽出
3. 振る舞いパターン特定
4. Specファイル生成
5. テストケース定義
