# Pre-commit Setup Guide

## 🎯 概要

tree-sitter-analyzerプロジェクトでは、**パフォーマンス最適化された**包括的なpre-commit hooksを使用しています。修正したファイルのみをチェックすることで、高速な開発体験と高品質なコードベースの両立を実現しています。

## ⚡ パフォーマンス最適化

### **2段階チェック戦略**

1. **コミット時（高速）**: 修正したファイルのみをチェック
2. **プッシュ時（包括的）**: より詳細なチェックを実行

## 🚀 セットアップ

### 1. Pre-commitのインストール

```bash
# 開発依存関係をインストール
uv sync --extra dev

# Pre-commit hooksをインストール
uv run pre-commit install
```

### 2. 初回実行（推奨）

```bash
# 全ファイルに対してpre-commit hooksを実行
uv run pre-commit run --all-files
```

## 🔍 実行される品質チェック

## 📊 ツール別実行モード詳細

| ツール | コミット時 | プッシュ時 | 手動実行 | 対象ファイル |
|--------|------------|------------|----------|--------------|
| **black** | ✅ | - | ✅ | 修正ファイルのみ |
| **ruff** | ✅ | - | ✅ | 修正ファイルのみ |
| **ruff-format** | ✅ | - | ✅ | 修正ファイルのみ |
| **isort** | ✅ | - | ✅ | 修正ファイルのみ |
| **pyupgrade** | ✅ | - | ✅ | 修正ファイルのみ |
| **mypy** | ✅ | - | - | **修正ファイルのみ** |
| **mypy-all** | - | - | ✅ | **全ファイル** |
| **bandit** | ✅ | - | - | **修正ファイルのみ** |
| **bandit (all)** | - | - | ✅ | **全ファイル** |
| **pydocstyle** | - | ✅ | ✅ | 修正ファイルのみ |
| **flake8** | - | ✅ | ✅ | 修正ファイルのみ |
| **safety** | - | ✅ | ✅ | 全依存関係 |
| **quality-check** | - | ✅ | ✅ | 全ファイル |

### **コミット時（高速 - 修正ファイルのみ）**

1. **コードフォーマット**
   - `black`: Pythonコードの自動フォーマット
   - `ruff-format`: 高速なコードフォーマット

2. **基本リンティング**
   - `ruff`: 高速なPythonリンター（pyflakes, pycodestyle等を統合）

3. **型チェック（最重要）**
   - `mypy`: 静的型チェック（**修正したファイルのみ**）

4. **インポート整理**
   - `isort`: インポート文の自動整理

5. **セキュリティチェック**
   - `bandit`: セキュリティ脆弱性の検出（**修正したファイルのみ**）

6. **Python現代化**
   - `pyupgrade`: Python 3.10+の新機能への自動アップグレード

7. **ファイル形式チェック**
   - YAML, JSON, TOML形式の検証
   - 末尾空白、改行の統一
   - 大きなファイルの検出

### **プッシュ時（包括的 - より詳細）**

1. **ドキュメント品質**
   - `pydocstyle`: Docstring品質チェック（Google形式）

2. **高度なリンティング**
   - `flake8`: 追加的なコード品質チェック

3. **依存関係脆弱性チェック**
   - `safety`: 既知の脆弱性を持つパッケージの検出

4. **カスタム品質チェック**
   - `check_quality.py`: プロジェクト固有の品質チェック

### **手動実行（全ファイル - 必要時）**

1. **完全型チェック**
   - `mypy-all`: 全ファイルの型チェック

2. **完全セキュリティチェック**
   - `bandit (all)`: 全ファイルのセキュリティチェック

## 🛠️ 使用方法

### **通常の開発フロー**

```bash
# コードを編集
vim tree_sitter_analyzer/some_file.py

# 通常通りコミット（自動的にpre-commit hooksが実行される）
git add .
git commit -m "feat: 新機能を追加"

# プッシュ時にも追加チェックが実行される
git push origin develop
```

### **手動実行**

#### **修正ファイルのみ（高速）**
```bash
# 特定のhookのみ実行
uv run pre-commit run mypy
uv run pre-commit run black

# 全hookを実行（修正ファイルのみ）
uv run pre-commit run

# 特定のファイルに対して実行
uv run pre-commit run --files tree_sitter_analyzer/core.py
```

#### **全ファイルチェック（包括的）**
```bash
# 全ファイルのmypyチェック
uv run pre-commit run mypy-all

# 全ファイルのbanditチェック
uv run pre-commit run bandit --hook-stage manual

# 全ての手動チェックを実行
uv run pre-commit run --hook-stage manual

# 全hookを全ファイルに対して実行
uv run pre-commit run --all-files
```

#### **段階別実行**
```bash
# コミット時のチェックのみ
uv run pre-commit run --hook-stage pre-commit

# プッシュ時のチェックのみ
uv run pre-commit run --hook-stage pre-push

# 手動チェックのみ
uv run pre-commit run --hook-stage manual
```

### **緊急時のスキップ**

```bash
# 緊急時のみ使用（推奨しません）
git commit -m "hotfix: 緊急修正" --no-verify
```

## 🔧 設定のカスタマイズ

### **個別ツールの設定**

- **mypy**: `pyproject.toml` の `[tool.mypy]` セクション
- **black**: `pyproject.toml` の `[tool.black]` セクション
- **ruff**: `pyproject.toml` の `[tool.ruff]` セクション
- **isort**: `pyproject.toml` の `[tool.isort]` セクション

### **Pre-commit設定**

`.pre-commit-config.yaml` で以下をカスタマイズ可能：

```yaml
# 特定のファイルを除外
exclude: ^(tests/|examples/|archived_files/)

# 特定のhookを無効化
# - id: mypy
#   stages: [manual]  # 手動実行のみ

# 失敗時に即座に停止
fail_fast: true
```

## 🚨 トラブルシューティング

### **よくある問題**

1. **mypyエラー**
   ```bash
   # 型エラーを修正するか、一時的に無視
   # type: ignore コメントを追加
   ```

2. **フォーマットエラー**
   ```bash
   # 自動修正される場合が多い
   # 再度コミットを試行
   git add .
   git commit -m "同じメッセージ"
   ```

3. **依存関係の問題**
   ```bash
   # Pre-commitの再インストール
   uv run pre-commit clean
   uv run pre-commit install
   ```

### **パフォーマンス最適化**

```bash
# キャッシュをクリア
uv run pre-commit clean

# 特定のhookのみ実行
uv run pre-commit run --hook-stage manual mypy
```

## ⚡ パフォーマンス特徴

### **高速コミット**
- **修正ファイルのみ**をチェック（`pass_filenames: true`）
- **mypyは変更されたファイルのみ**を型チェック
- **平均コミット時間**: 5-15秒（従来の1/3以下）

### **包括的プッシュ**
- **重いチェック**はプッシュ時に実行
- **CI/CD前**に品質を保証
- **チーム全体**で統一された品質基準

## 📊 品質メトリクス

Pre-commit hooksにより以下が保証されます：

- ✅ **型安全性**: mypy 100%パス（修正ファイル）
- ✅ **コード品質**: ruff, flake8 100%パス
- ✅ **セキュリティ**: bandit, safety 100%パス
- ✅ **フォーマット**: black, isort 100%統一
- ✅ **ドキュメント**: pydocstyle Google形式準拠

## 🎯 利点

1. **高速開発**: 修正ファイルのみチェックで待機時間最小化
2. **早期エラー検出**: コミット前に型エラーを発見
3. **一貫した品質**: チーム全体で同じ基準
4. **自動修正**: 多くの問題が自動で修正
5. **CI/CD効率化**: 事前チェックによりCI時間短縮
6. **学習効果**: 品質の高いコードの書き方を学習

---

**注意**: 初回セットアップ時は全ファイルのチェックに時間がかかる場合がありますが、その後は変更されたファイルのみがチェックされるため高速です。
