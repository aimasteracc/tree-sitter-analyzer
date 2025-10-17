# バージョンディレクトリ構造

このディレクトリは、異なるバージョンのtree-sitter-analyzerを配置するためのものです。

## ディレクトリ構造

```
versions/
├── README.md                    # このファイル
├── v1.6.1/                     # バージョン1.6.1
│   ├── venv/                   # 仮想環境（推奨）
│   │   ├── bin/python          # Python実行可能ファイル（Linux/macOS）
│   │   └── Scripts/python.exe  # Python実行可能ファイル（Windows）
│   └── tree_sitter_analyzer/   # ソースコード（オプション）
├── v1.6.0/                     # バージョン1.6.0
│   └── venv/
└── 1.7.0/                      # バージョン1.7.0（別の命名パターン）
    └── .venv/
```

## サポートされる命名パターン

以下の命名パターンが自動検出されます：

- `v{version}` (例: `v1.6.1`, `v1.6.0`)
- `version-{version}` (例: `version-1.6.1`)
- `{version}` (例: `1.6.1`, `1.6.0`)
- `tree-sitter-analyzer-{version}` (例: `tree-sitter-analyzer-1.6.1`)

## Python実行可能ファイルの検索パス

各バージョンディレクトリ内で、以下のパスが検索されます：

1. `venv/bin/python` (Linux/macOS)
2. `venv/Scripts/python.exe` (Windows)
3. `.venv/bin/python` (Linux/macOS)
4. `.venv/Scripts/python.exe` (Windows)
5. `python` (直接配置)
6. `python.exe` (Windows直接配置)

## セットアップ例

### 方法1: 仮想環境を使用（推奨）

```bash
# バージョン1.6.1のセットアップ
mkdir -p versions/v1.6.1
cd versions/v1.6.1
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install tree-sitter-analyzer[mcp]==1.6.1

# バージョン1.6.0のセットアップ
cd ../..
mkdir -p versions/v1.6.0
cd versions/v1.6.0
python -m venv venv
source venv/bin/activate
pip install tree-sitter-analyzer[mcp]==1.6.0
```

### 方法2: ソースコードを直接配置

```bash
# GitHubからソースコードをクローン
cd versions
git clone --branch v1.6.1 https://github.com/your-repo/tree-sitter-analyzer.git v1.6.1
git clone --branch v1.6.0 https://github.com/your-repo/tree-sitter-analyzer.git v1.6.0
```

## 使用方法

セットアップ後、以下のようにバージョンを指定してテストを実行できます：

```bash
# バージョン1.6.1でテスト
python mcp_test_direct.py --version 1.6.1

# バージョン1.6.0でテスト  
python mcp_test_direct.py --version 1.6.0

# MCPクライアントでのテスト
python -c "
import asyncio
from mcp_client import SimpleMCPClient

async def test():
    client = SimpleMCPClient(version='1.6.1')
    await client.connect()
    result = await client.call_tool('check_code_scale', {'file_path': 'examples/BigService.java'})
    print(result)
    await client.disconnect()

asyncio.run(test())
"
```

## 自動検出の確認

バージョンが正しく検出されているかを確認するには：

```bash
python test_version_manager.py
```

または、プログラムから：

```python
from version_manager import create_version_manager

vm = create_version_manager()
versions = vm.list_available_versions()
print(f"検出されたバージョン: {versions}")

for version in versions:
    info = vm.get_version_info(version)
    print(f"{version}: {info}")
```

## トラブルシューティング

### バージョンが検出されない場合

1. ディレクトリ名が命名パターンに一致しているか確認
2. Python実行可能ファイルが正しいパスに存在するか確認
3. tree-sitter-analyzerが正しくインストールされているか確認

```bash
# 手動でバージョンを確認
versions/v1.6.1/venv/bin/python -c "import tree_sitter_analyzer; print(tree_sitter_analyzer.__version__)"
```

### 権限エラーが発生する場合

```bash
# 実行権限を付与
chmod +x versions/v1.6.1/venv/bin/python
```

## 設定のカスタマイズ

`config.json`で検出設定をカスタマイズできます：

```json
{
  "version_settings": {
    "relative_version_detection": {
      "enabled": true,
      "base_directory": "versions",
      "patterns": ["v{version}", "custom-{version}"],
      "python_paths": ["custom/python", "venv/bin/python"]
    }
  }
}