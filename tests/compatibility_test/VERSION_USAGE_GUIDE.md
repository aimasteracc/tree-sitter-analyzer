# バージョン対応機能使用ガイド

## 概要

tree-sitter-analyzer互換性テストシステムに、異なるバージョンのtree-sitter-analyzerを呼び出す機能が追加されました。これにより、複数のバージョン間での互換性テストが可能になります。

## 🚀 簡単セットアップ（推奨）

### 相対パス方式

`tests/compatibility_test/versions/`ディレクトリ内にバージョンを配置するだけで自動検出されます：

```bash
# バージョン1.6.1のセットアップ
mkdir -p tests/compatibility_test/versions/v1.6.1
cd tests/compatibility_test/versions/v1.6.1
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install tree-sitter-analyzer[mcp]==1.6.1

# バージョン1.9.2のセットアップ
cd ../v1.9.2
python -m venv venv
source venv/bin/activate
pip install tree-sitter-analyzer[mcp]==1.9.2

# すぐにテスト実行可能
cd ../../..
python mcp_test_direct.py --version 1.6.1
python mcp_test_direct.py --version 1.9.2
```

### サポートされるディレクトリ構造

```
tests/compatibility_test/
├── versions/                    # バージョン配置ディレクトリ
│   ├── v1.6.1/                 # バージョン1.6.1
│   │   └── venv/               # 仮想環境
│   │       ├── bin/python      # Python実行可能ファイル
│   │       └── ...
│   ├── v1.9.2/                 # バージョン1.9.2
│   ├── 1.7.0/                  # 別の命名パターン
│   └── tree-sitter-analyzer-1.5.0/  # さらに別のパターン
├── mcp_test_direct.py
└── config.json
```

## 設定方法

### 1. 設定ファイル (`config.json`)

```json
{
  "version_settings": {
    "default_version": "current",
    "relative_version_detection": {
      "enabled": true,
      "base_directory": "versions",
      "patterns": [
        "v{version}",
        "version-{version}",
        "{version}",
        "tree-sitter-analyzer-{version}"
      ],
      "python_paths": [
        "venv/bin/python",
        "venv/Scripts/python.exe",
        ".venv/bin/python",
        ".venv/Scripts/python.exe"
      ]
    },
    "versions": {
      "current": {
        "python_executable": null,
        "virtual_env": null,
        "module_path": "tree_sitter_analyzer",
        "description": "Current development version"
      },
      "1.6.1": {
        "python_executable": "/path/to/venv_1.6.1/bin/python",
        "virtual_env": "/path/to/venv_1.6.1",
        "module_path": "tree_sitter_analyzer",
        "description": "Stable version 1.6.1"
      }
    },
    "auto_detect_versions": true,
    "fallback_to_current": true
  }
}
```

### 2. 環境変数

```bash
# デフォルトバージョンを設定
export TSA_DEFAULT_VERSION="1.6.1"

# 特定バージョンのPython実行可能ファイルを指定
export TSA_VERSION_1_6_1_PYTHON="/path/to/venv_1.6.1/bin/python"

# 特定バージョンの仮想環境を指定
export TSA_VERSION_1_6_1_VENV="/path/to/venv_1.6.1"

# 別のバージョン例
export TSA_VERSION_1_6_0_PYTHON="/path/to/venv_1.9.2/bin/python"
export TSA_VERSION_1_6_0_VENV="/path/to/venv_1.9.2"
```

## 使用方法

### MCPクライアント

```python
from mcp_client import SimpleMCPClient

# 現在のバージョンを使用
client_current = SimpleMCPClient(version="current")

# 特定のバージョンを使用
client_161 = SimpleMCPClient(version="1.6.1")

# 接続してテスト実行
await client_161.connect()
result = await client_161.call_tool("check_code_scale", {
    "file_path": "examples/BigService.java"
})
await client_161.disconnect()
```

### MCP直接テスト

```bash
# 現在のバージョンでテスト
uv run python mcp_test_direct.py --version current

# 特定のバージョンでテスト
uv run python mcp_test_direct.py --version 1.6.1

# 複数バージョンの比較テスト
uv run python mcp_test_direct.py --version 1.6.1 --categories analysis
uv run python mcp_test_direct.py --version current --categories analysis
```

### プログラムからの使用

```python
from version_manager import create_version_manager

# バージョン管理機能を初期化
version_manager = create_version_manager()

# 利用可能なバージョンを確認
versions = version_manager.list_available_versions()
print(f"利用可能なバージョン: {versions}")

# 特定バージョンの情報を取得
version_info = version_manager.get_version_info("1.6.1")
python_exe = version_manager.get_python_executable("1.6.1")
```

## バージョン設定のベストプラクティス

### 1. 相対パス方式（推奨）

```bash
# compatibility_testディレクトリ内でのセットアップ
cd tests/compatibility_test

# バージョン1.6.1
mkdir -p versions/v1.6.1
cd versions/v1.6.1
uv run python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
uv pip install tree-sitter-analyzer[mcp]==1.6.1
cd ../..

# バージョン1.9.2
mkdir -p versions/v1.9.2
cd versions/v1.9.2
uv run python -m venv venv
source venv/bin/activate
uv pip install tree-sitter-analyzer[mcp]==1.9.2
cd ../..

# すぐに使用可能
uv run python mcp_test_direct.py --version 1.6.1
```

### 2. 従来の仮想環境方式

```bash
# プロジェクトルートでの仮想環境作成
uv run python -m venv venv_1.6.1
source venv_1.6.1/bin/activate  # Windows: venv_1.6.1\Scripts\activate
uv pip install tree-sitter-analyzer[mcp]==1.6.1

uv run python -m venv venv_1.9.2
source venv_1.9.2/bin/activate
uv pip install tree-sitter-analyzer[mcp]==1.9.2
```

### 3. 自動検出の活用

#### 相対パス検出（新機能）
`versions/`ディレクトリ内で以下の命名規則を自動検出：

- `v{version}` (例: `v1.6.1`, `v1.9.2`)
- `version-{version}` (例: `version-1.6.1`)
- `{version}` (例: `1.6.1`, `1.9.2`)
- `tree-sitter-analyzer-{version}` (例: `tree-sitter-analyzer-1.6.1`)

#### 従来の検出
プロジェクトルートで以下の命名規則を自動検出：

- `venv_{version}` (例: `venv_1.6.1`)
- `.venv_{version}` (例: `.venv_1.6.1`)
- `env_{version}` (例: `env_1.6.1`)
- `tree-sitter-analyzer-{version}` (例: `tree-sitter-analyzer-1.6.1`)

### 3. 環境変数の活用

CI/CDパイプラインや異なる環境での実行時は、環境変数を使用して設定を動的に変更できます：

```bash
# GitHub Actions例
- name: Set version for testing
  run: |
    echo "TSA_VERSION_1_6_1_PYTHON=${{ github.workspace }}/venv_1.6.1/bin/python" >> $GITHUB_ENV
    echo "TSA_VERSION_1_6_1_VENV=${{ github.workspace }}/venv_1.6.1" >> $GITHUB_ENV
```

## エラーハンドリング

### フォールバック機能

- 指定されたバージョンが見つからない場合、自動的に`current`バージョンにフォールバック
- `fallback_to_current: false`で無効化可能

### エラーログ

```python
import logging
logging.basicConfig(level=logging.INFO)

# バージョン管理のログが出力される
version_manager = create_version_manager()
```

### 検証機能

```python
# バージョンが利用可能かチェック
if version_manager.validate_version("1.6.1"):
    print("バージョン1.6.1が利用可能です")
else:
    print("バージョン1.6.1は利用できません")
```

## トラブルシューティング

### よくある問題

1. **仮想環境が見つからない**
   ```
   WARNING: 指定された仮想環境が存在しません: /path/to/venv_1.6.1
   ```
   → パスを確認し、仮想環境を作成してください

2. **Python実行可能ファイルが見つからない**
   ```
   WARNING: 仮想環境にPython実行可能ファイルが見つかりません
   ```
   → 仮想環境が正しく作成されているか確認してください

3. **バージョン検証に失敗**
   ```
   WARNING: バージョン 1.6.1 の自動検出に失敗
   ```
   → 仮想環境にtree-sitter-analyzerがインストールされているか確認してください

### デバッグ方法

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# 詳細なログが出力される
version_manager = create_version_manager()
```

## 実装の詳細

### アーキテクチャ

1. **VersionManager**: バージョン情報の管理と検証
2. **SubprocessToolWrapper**: 異なるバージョンのツールをサブプロセスで実行
3. **環境変数サポート**: 動的な設定変更
4. **自動検出**: 仮想環境の自動発見
5. **フォールバック**: エラー時の安全な動作

### パフォーマンス考慮事項

- 現在のバージョンは直接インポートで高速実行
- 異なるバージョンはサブプロセス実行（若干のオーバーヘッド）
- バージョン情報のキャッシュで検出処理を最適化

## 🎯 クイックスタートガイド

### ステップ1: バージョンディレクトリを作成

```bash
cd tests/compatibility_test
mkdir -p versions/v1.6.1 versions/1.9.2
```

### ステップ2: 各バージョンをセットアップ

```bash
# バージョン1.6.1
cd versions/v1.6.1
python -m venv venv
source venv/bin/activate
pip install tree-sitter-analyzer[mcp]==1.6.1
cd ../..

# バージョン1.9.2
cd versions/1.9.2
python -m venv venv
source venv/bin/activate
pip install tree-sitter-analyzer[mcp]==1.9.2
cd ../..
```

### ステップ3: テスト実行

```bash
# 利用可能なバージョンを確認
python test_version_manager.py

# 特定バージョンでテスト
python mcp_test_direct.py --version 1.6.1
python mcp_test_direct.py --version 1.9.2

# 比較テスト
python mcp_test_direct.py --version 1.6.1 --categories analysis
python mcp_test_direct.py --version 1.9.2 --categories analysis
```

## 📁 ディレクトリ構造の詳細

詳細なディレクトリ構造とセットアップ方法については、[`versions/README.md`](versions/README.md)を参照してください。

## 今後の拡張

- Docker環境でのバージョン管理
- リモートバージョンの実行
- バージョン間の自動比較レポート
- パフォーマンス比較機能
- GitHubからの自動バージョンダウンロード