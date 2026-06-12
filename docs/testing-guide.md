# テストとゴールデンマスター管理ガイド

## 概要

このプロジェクトでは、**Golden Master Testing**（ゴールデンマスターテスト）を使用して、コード変更による意図しない出力の変更を検出します。

## ディレクトリ構造

```
tree-sitter-analyzer/
├── tests/
│   ├── golden_masters/          # ゴールデンマスター（期待される出力）
│   │   ├── full/               # full フォーマット
│   │   ├── compact/            # compact フォーマット
│   │   └── csv/                # csv フォーマット
│   ├── test_data/              # テスト用の入力ファイル
│   │   ├── test_enum.ts        # TypeScript enum テスト
│   │   ├── test_class.js       # JavaScript class テスト
│   │   └── test_class.py       # Python class テスト
├── regression/
│   └── test_plugin_golden_masters.py  # プラグインゴールデンマスターリグレッションテスト
└── examples/                    # サンプルファイル（テスト入力としても使用）
    ├── Sample.java
    └── BigService.java
```

## ワークフロー

### 1. 新機能開発・バグ修正

#### ステップ1: 変更を実装
コードを変更します。

#### ステップ2: リグレッションテストを実行
```bash
# 全てのゴールデンマスターテストを実行
uv run pytest tests/regression/test_plugin_golden_masters.py -v

# 特定のプラグインだけ実行（パラメタライズド test_plugin_golden_master を -k で絞る）
uv run pytest "tests/regression/test_plugin_golden_masters.py::test_plugin_golden_master" -v -k "java"
```

#### ステップ3: 結果を確認
- ✅ **すべてパス**: 変更は出力に影響していません
- ❌ **失敗あり**: 出力が変更されています
  - 意図した変更の場合 → ゴールデンマスターを更新（ステップ4へ）
  - 意図しない変更の場合 → コードを修正

#### ステップ4: ゴールデンマスターの更新（必要な場合）
```bash
# プラグイン・ゴールデンマスターを更新（意図した出力変更を受け入れる）
TSA_UPDATE_GOLDEN=1 uv run pytest tests/regression/test_plugin_golden_masters.py -q

# （参考）フォーマッタ・ベースライン（tests/golden_masters/{full,compact,csv}）は別系統:
# uv run python tests/integration/formatters/update_baselines.py

# 更新後、環境変数なしで再度テストを実行して確認
uv run pytest tests/regression/test_plugin_golden_masters.py -v
```

### 2. 新しいテストケースの追加

#### ステップ1: テスト用ファイルを作成
```bash
# tests/test_data/ に新しいテストファイルを作成
# 例: tests/test_data/new_feature.java
```

#### ステップ2: ゴールデンマスターを生成
```bash
uv run pytest tests/ -v --update-goldens
```

#### ステップ3: テストケースを追加
該当するリグレッションテストファイル（`tests/` 以下）に新しいテストケースを追加：
```python
@pytest.mark.parametrize("input_file,golden_name,table_format", [
    # ... 既存のケース ...
    ("tests/test_data/new_feature.java", "java_new_feature", "full"),
])
def test_golden_master_comparison(self, input_file, golden_name, table_format):
    # ...
```

## ベストプラクティス

### ✅ DO（推奨）

1. **コミット前に必ずテストを実行**
   ```bash
   uv run pytest tests/test_golden_master_regression.py -v
   ```

2. **意図的な出力変更は必ずゴールデンマスターを更新**
   - 変更の理由をコミットメッセージに記載
   - PRのdescriptionに「ゴールデンマスター更新」と明記

3. **テストファイルは`tests/test_data/`に配置**
   - ルートディレクトリには一時ファイルを残さない
   - `.gitignore`で一時ファイルパターンを除外

4. **複数フォーマットをテスト**
   - full, compact, csv すべてで動作確認

### ❌ DON'T（非推奨）

1. **テストが失敗したまま放置しない**
   - 必ず原因を調査して修正

2. **ゴールデンマスターを手動編集しない**
   - pytest の golden 更新オプションを使用

3. **一時ファイルをコミットしない**
   - `test*.md`, `debug*.py` などはGit管理外

## トラブルシューティング

### Q: テストが失敗するが、出力は正しい
A: ゴールデンマスターを更新してください：
```bash
uv run pytest tests/ -v --update-goldens
```

### Q: 新しい言語サポートを追加した
A: 以下の手順で対応：
1. `tests/test_data/`にサンプルファイルを追加
2. ゴールデンマスターを生成（pytest golden 更新オプション使用）
3. テストケースを追加

### Q: 一時ファイルがたくさん残っている
A: 以下のコマンドでクリーンアップ：
```bash
# Windowsの場合
Remove-Item -Path test*.md,test*.js,test*.ts,test_class.py,debug*.py,sample_json.json -ErrorAction SilentlyContinue

# Linux/Macの場合
rm -f test*.md test*.js test*.ts test_class.py debug*.py sample_json.json
```

## 参考資料

- [Golden Master Testing とは](https://www.martinfowler.com/bliki/GoldenMaster.html)
- [Pytest パラメータ化テスト](https://docs.pytest.org/en/stable/parametrize.html)
- [リグレッションテストのベストプラクティス](https://testing.googleblog.com/)

## 変更履歴

- 2025-11-06: Javaの interface/enum type と visibility の修正に伴いゴールデンマスター更新
  - `enum_body_declarations` サポート追加
  - package-private visibility の正しい認識
  - interface/enum type の正しい分類
