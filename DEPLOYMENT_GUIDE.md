# Tree-sitter Analyzer デプロイメントガイド

このガイドでは、tree-sitter-analyzerをPyPIに登録し、スタンドアロン実行ファイルを作成する手順を説明します。

## 目次

1. [PyPIへの登録](#pypiへの登録)
2. [スタンドアロン実行ファイルの作成](#スタンドアロン実行ファイルの作成)
3. [ユーザー向けインストール手順](#ユーザー向けインストール手順)

## PyPIへの登録

### 前提条件

1. PyPIアカウントの作成
   - [PyPI](https://pypi.org/account/register/) でアカウントを作成
   - [TestPyPI](https://test.pypi.org/account/register/) でテスト用アカウントを作成

2. API トークンの設定
   ```bash
   # PyPI用
   uv run python -m pip install --upgrade pip
   uv add --dev build twine
   
   # 認証情報の設定（~/.pypirc）
   [distutils]
   index-servers =
       pypi
       testpypi
   
   [pypi]
   username = __token__
   password = <your-pypi-api-token>
   
   [testpypi]
   repository = https://test.pypi.org/legacy/
   username = __token__
   password = <your-testpypi-api-token>
   ```

### アップロード手順

#### 方法1: 自動スクリプトを使用

```bash
# アップロードスクリプトを実行（uv 統一）
uv run python upload_to_pypi.py
```

このスクリプトは以下を自動実行します：
- 必要なツールのインストール
- パッケージのビルド
- 整合性チェック
- TestPyPI または PyPI へのアップロード

#### 方法2: 手動実行

```bash
# 1. 依存関係のインストール
uv add --dev build twine

# 2. パッケージのビルド
uv run python -m build

# 3. パッケージの検証
uv run python -m twine check dist/*

# 4. TestPyPIにアップロード（テスト用）
uv run python -m twine upload --repository testpypi dist/*

# 5. 本番PyPIにアップロード
uv run python -m twine upload dist/*
```

### アップロード後の確認

```bash
# TestPyPIからのインストールテスト
pip install --index-url https://test.pypi.org/simple/ tree-sitter-analyzer==0.9.4

# 本番PyPIからのインストール
pip install tree-sitter-analyzer==0.9.4
```

## スタンドアロン実行ファイルの作成

Python環境がないユーザーでも使用できるスタンドアロン実行ファイルを作成できます。

### 前提条件

```bash
# PyInstallerのインストール
uv add --dev pyinstaller
```

### ビルド手順

#### 方法1: 自動スクリプトを使用

```bash
# スタンドアロンビルドスクリプトを実行
uv run python build_standalone.py
```

#### 方法2: 手動実行

```bash
# 1. PyInstallerのインストール
pip install pyinstaller

# 2. 実行ファイルの作成
pyinstaller --onefile --name tree-sitter-analyzer tree_sitter_analyzer/cli_main.py

# 3. 必要なデータファイルを含める場合
pyinstaller --onefile --name tree-sitter-analyzer \
    --add-data "tree_sitter_analyzer/queries:tree_sitter_analyzer/queries" \
    tree_sitter_analyzer/cli_main.py
```

### 生成されるファイル

- Windows: `dist/tree-sitter-analyzer.exe`
- Linux/macOS: `dist/tree-sitter-analyzer`

### 使用方法

```bash
# Windows
./dist/tree-sitter-analyzer.exe examples/Sample.java --advanced

# Linux/macOS
./dist/tree-sitter-analyzer examples/Sample.java --advanced
```

## ユーザー向けインストール手順

### Python環境がある場合

#### PyPIからのインストール

```bash
# 基本インストール
pip install tree-sitter-analyzer

# Java サポート付き
pip install "tree-sitter-analyzer[java]"

# 人気言語サポート付き（Java, Python, JavaScript, TypeScript）
pip install "tree-sitter-analyzer[popular]"

# 全言語サポート付き
pip install "tree-sitter-analyzer[all]"

# MCP サーバーサポート付き
pip install "tree-sitter-analyzer[mcp]"
```

#### uvを使用したインストール（推奨）

```bash
# uvのインストール
curl -LsSf https://astral.sh/uv/install.sh | sh

# プロジェクトのインストール
uv add tree-sitter-analyzer

# 特定の機能付きインストール
uv add "tree-sitter-analyzer[popular]"
```

### Python環境がない場合

1. **スタンドアロン実行ファイルをダウンロード**
   - GitHubのReleasesページから最新版をダウンロード
   - または、開発者から提供された実行ファイルを使用

2. **実行権限の付与（Linux/macOS）**
   ```bash
   chmod +x tree-sitter-analyzer
   ```

3. **使用方法**
   ```bash
   # Windows
   tree-sitter-analyzer.exe your-code-file.java --advanced
   
   # Linux/macOS
   ./tree-sitter-analyzer your-code-file.java --advanced
   ```

## 配布戦略

### 1. PyPI配布
- Python開発者向け
- 依存関係の自動管理
- 簡単なインストール

### 2. スタンドアロン実行ファイル配布
- Python環境がないユーザー向け
- 単一ファイルで完結
- 依存関係なし

### 3. GitHub Releases
- 両方の配布形式を提供
- バージョン管理
- ダウンロード統計

## トラブルシューティング

### PyPIアップロード時の問題

1. **認証エラー**
   ```
   解決策: API トークンの確認、~/.pypirc の設定確認
   ```

2. **パッケージ名の重複**
   ```
   解決策: pyproject.toml の name フィールドを変更
   ```

3. **バージョンの重複**
   ```
   解決策: pyproject.toml の version を更新
   ```

### スタンドアロンビルド時の問題

1. **モジュールが見つからない**
   ```
   解決策: --hidden-import オプションでモジュールを明示的に指定
   ```

2. **データファイルが含まれない**
   ```
   解決策: --add-data オプションでデータファイルを指定
   ```

3. **実行ファイルサイズが大きい**
   ```
   解決策: --exclude-module で不要なモジュールを除外
   ```

## 継続的デプロイメント

GitHub Actionsを使用した自動デプロイメントの設定例：

```yaml
# .github/workflows/deploy.yml
name: Deploy to PyPI

on:
  release:
    types: [published]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install build twine
    - name: Build package
      run: python -m build
    - name: Publish to PyPI
      env:
        TWINE_USERNAME: __token__
        TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
      run: twine upload dist/*
```

このガイドに従って、tree-sitter-analyzerを効果的に配布し、幅広いユーザーに提供できます。
