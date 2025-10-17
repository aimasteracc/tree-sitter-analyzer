# 簡素化されたバージョン管理システム

## 概要

tree-sitter-analyzerの互換性テストで使用する、シンプルで理解しやすいバージョン管理システムです。高度な自動インストール機能により、インタラクティブなセットアップ、並列インストール、PyPIからの自動バージョン取得、リッチなUI表示を提供します。

## 🆕 新機能

### インタラクティブセットアップ機能
- **対話型インターフェース**: [`questionary`](tests/compatibility_test/setup_versions.py:25)を使用したユーザーフレンドリーなTUI
- **バージョン選択**: 利用可能なバージョンから複数選択可能
- **設定カスタマイズ**: 同時インストール数や強制上書きの設定

### 並列インストール機能
- **高速セットアップ**: 最大4つのバージョンを同時にインストール
- **進捗表示**: [`rich`](tests/compatibility_test/setup_versions.py:27)ライブラリによるリアルタイム進捗バー
- **セマフォ制御**: [`asyncio.Semaphore`](tests/compatibility_test/setup_versions.py:175)による同時実行数制限

### PyPIからの自動バージョン取得
- **最新情報**: [`pip index versions`](tests/compatibility_test/setup_versions.py:242)コマンドによる最新バージョン情報の取得
- **バージョン管理**: [`packaging.version`](tests/compatibility_test/setup_versions.py:32)による適切なバージョンソート
- **フォールバック**: PyPI接続失敗時のデフォルトバージョンリスト

### リッチなUI表示
- **カラフルな出力**: [`rich.console`](tests/compatibility_test/setup_versions.py:45)による見やすい表示
- **テーブル表示**: インストール状況の一覧表示
- **パネル表示**: 重要な情報のハイライト表示
- **進捗バー**: インストール進行状況のリアルタイム表示

## 基本ルール

**単一の規約**: `tests/compatibility_test/versions/v{version}/venv/` 構造

```
tests/compatibility_test/
├── versions/
│   ├── v1.6.1/
│   │   └── venv/
│   │       ├── Scripts/python.exe  (Windows)
│   │       └── bin/python          (Unix/Linux/macOS)
│   ├── v1.9.2/
│   │   └── venv/
│   │       ├── Scripts/python.exe  (Windows)
│   │       └── bin/python          (Unix/Linux/macOS)
│   └── README.md
├── config.json                     (簡素化済み)
├── version_manager.py              (規約ベース)
└── mcp_test_direct.py
```

## 設定ファイル

### config.json (簡素化済み)

```json
{
  "test_settings": {
    "timeout": 30,
    "max_retries": 3,
    "log_level": "INFO"
  },
  "mcp_settings": {
    "project_root_auto_detect": true,
    "normalize_paths": true,
    "handle_total_only_results": true,
    "error_handling": {
      "continue_on_error": true,
      "log_errors": true,
      "save_error_details": true
    }
  },
  "comparison_settings": {
    "tolerance": 0.001,
    "ignore_timestamps": true,
    "ignore_execution_times": true,
    "normalize_file_paths": true
  }
}
```

## 使用方法

### 1. 依存関係のインストール

新しい自動インストール機能を使用する前に、必要な依存関係をインストールしてください：

```bash
# 必要な依存関係をインストール
pip install questionary rich PyYAML packaging

# または requirements.txtから一括インストール
pip install -r tests/compatibility_test/requirements.txt

# uvを使用する場合
uv pip install questionary rich PyYAML packaging
uv pip install -r tests/compatibility_test/requirements.txt
```

### 2. 🚀 高度な自動インストール機能

#### インタラクティブモード（推奨）

```bash
# インタラクティブセットアップを開始
cd tests/compatibility_test
uv run python setup_versions.py --interactive
```

このモードでは以下の機能が利用できます：
- PyPIから最新のバージョンリストを自動取得
- 複数バージョンの選択（チェックボックス形式）
- 同時インストール数の設定（1-4）
- 既存バージョンの上書き確認
- リアルタイム進捗表示

#### コマンドライン引数

```bash
# 基本的な使用方法
uv run python setup_versions.py 1.6.1 1.9.2

# 利用可能なバージョンを表示
uv run python setup_versions.py --list-available

# インストール済みバージョンを表示
uv run python setup_versions.py --list-installed

# 並列インストール数を指定（デフォルト: 3）
uv run python setup_versions.py 1.6.1 1.9.2 --max-concurrent 4

# 既存バージョンを強制上書き
uv run python setup_versions.py 1.6.1 --force

# 特定バージョンを削除
uv run python setup_versions.py --cleanup 1.6.1
```

#### 並列インストールの例

```bash
# 複数バージョンを高速で並列インストール
uv run python setup_versions.py 1.6.1 1.6.0 1.5.0 --max-concurrent 3

# 最高速設定（4並列）
uv run python setup_versions.py 1.6.1 1.6.0 1.5.0 1.4.0 --max-concurrent 4
```

### 3. 従来の手動インストール方法

自動インストール機能を使用しない場合の手動セットアップ：

```bash
# 1. バージョンディレクトリを作成
mkdir -p tests/compatibility_test/versions/v1.7.0

# 2. 仮想環境を作成
cd tests/compatibility_test/versions/v1.7.0
python -m venv venv

# 3. 仮想環境をアクティベート
# Windows:
venv\Scripts\activate
# Unix/Linux/macOS:
source venv/bin/activate

# 4. MCPサポートを含む完全インストール（推奨）
pip install "tree-sitter-analyzer[mcp]==1.7.0"
```

### 4. テストの実行

```bash
# 利用可能なバージョンを確認
cd tests/compatibility_test
uv run python test_simplified_version_manager.py

# MCPテスト（現在のバージョン、特定バージョン）
uv run python mcp_test_direct.py --version current
uv run python mcp_test_direct.py --version 1.6.1

# CLIテスト（現在のバージョン、特定バージョン）
uv run python cli_test.py --version current
uv run python cli_test.py --version 1.6.1
```

### 5. バージョン管理の確認

```python
from version_manager import VersionManager

vm = VersionManager()
print("利用可能なバージョン:", vm.list_available_versions())

# バージョン情報の取得
version_info = vm.get_version_info("1.6.1")
print("Python実行可能ファイル:", version_info["python_executable"])
```

## 📦 新しい依存関係

### 必須依存関係

新しい自動インストール機能では以下の依存関係が必要です：

#### questionary (>=1.10.0)
- **用途**: インタラクティブなTUI（Terminal User Interface）
- **機能**: バージョン選択、設定確認、チェックボックス形式の選択
- **使用箇所**: [`interactive_setup()`](tests/compatibility_test/setup_versions.py:283)メソッド

#### rich (>=13.0.0)
- **用途**: リッチなテキスト表示と進捗バー
- **機能**:
  - カラフルなコンソール出力
  - リアルタイム進捗バー表示
  - テーブル形式の結果表示
  - パネル表示によるハイライト
- **使用箇所**: [`setup_multiple_versions_async()`](tests/compatibility_test/setup_versions.py:151)メソッド

#### PyYAML (>=6.0)
- **用途**: 設定ファイルの読み書き（将来の拡張用）
- **機能**: YAML形式の設定ファイルサポート
- **使用箇所**: 現在は将来の拡張のために準備

#### packaging (>=21.0)
- **用途**: バージョン文字列の解析とソート
- **機能**:
  - セマンティックバージョニングのサポート
  - バージョンの比較と並び替え
- **使用箇所**: [`get_available_versions_from_pypi()`](tests/compatibility_test/setup_versions.py:235)メソッド

### requirements.txtの使用方法

```bash
# 依存関係を一括インストール
pip install -r tests/compatibility_test/requirements.txt

# 特定の依存関係のみインストール
pip install questionary rich PyYAML packaging

# 開発環境での依存関係確認
pip list | grep -E "(questionary|rich|PyYAML|packaging)"
```

## 自動検出の仕組み

### 従来の検出機能
1. **ディレクトリスキャン**: `versions/`ディレクトリ内の`v{version}`パターンを検索
2. **仮想環境検証**: `venv/Scripts/python.exe`（Windows）または`venv/bin/python`（Unix系）の存在確認
3. **バージョン確認**: Python実行可能ファイルでtree-sitter-analyzerのバージョンを確認
4. **MCPサポート確認**: MCPサーバーの起動可能性を検証
5. **情報キャッシュ**: 検出されたバージョン情報をメモリにキャッシュ

### 🆕 新しい自動機能
6. **PyPI連携**: [`pip index versions`](tests/compatibility_test/setup_versions.py:242)による最新バージョン情報の自動取得
7. **非同期処理**: [`asyncio`](tests/compatibility_test/setup_versions.py:57)による並列インストール
8. **進捗監視**: リアルタイムでのインストール状況表示
9. **エラーハンドリング**: 各バージョンの個別エラー処理と継続実行
10. **バージョン検証**: インストール後の自動バージョン確認

## 利点

### 従来の利点
- **シンプル**: 複雑な設定ファイルが不要
- **予測可能**: 決まった規約に従うため、動作が理解しやすい
- **保守性**: 設定の複雑さがないため、メンテナンスが容易
- **拡張性**: 新しいバージョンの追加が簡単
- **互換性**: MCPとCLI両方のテストに対応
- **自動化**: バージョン検出とテスト実行の自動化

### 🆕 新機能の利点
- **高速化**: 並列インストールにより大幅な時間短縮（最大4倍高速）
- **ユーザビリティ**: インタラクティブモードによる直感的な操作
- **可視性**: リッチなUI表示による進捗の明確化
- **信頼性**: 各ステップでの検証とエラーハンドリング
- **最新性**: PyPIからの自動バージョン取得により常に最新情報を利用
- **柔軟性**: 同時実行数の調整による環境に応じた最適化

## トラブルシューティング

### 🆕 新機能関連の問題

#### 依存関係のインストールエラー

```bash
# エラー: 必要な依存関係がインストールされていません
# 解決方法: 依存関係を個別にインストール
pip install questionary rich PyYAML packaging

# または、requirements.txtを使用
pip install -r tests/compatibility_test/requirements.txt

# uvを使用する場合
uv pip install questionary rich PyYAML packaging
uv pip install -r tests/compatibility_test/requirements.txt
```

#### インタラクティブモードが起動しない

```bash
# エラー: questionary関連のエラー
# 解決方法: questionary のバージョンを確認
pip show questionary

# questionary を再インストール
pip uninstall questionary
pip install questionary>=1.10.0
```

#### 並列インストールでエラーが発生

```bash
# 同時実行数を減らして再試行
uv run python setup_versions.py 1.6.1 1.6.0 --max-concurrent 1

# 強制上書きオプションを使用
uv run python setup_versions.py 1.6.1 --force
```

#### PyPIからのバージョン取得に失敗

```bash
# ネットワーク接続を確認
ping pypi.org

# pip のアップデート
pip install --upgrade pip

# 手動でバージョンを指定
uv run python setup_versions.py 1.6.1 1.6.0 1.5.0
```

### 従来の問題

#### バージョンが検出されない場合

1. ディレクトリ構造を確認:
   ```bash
   ls -la tests/compatibility_test/versions/v1.6.1/venv/
   ```

2. Python実行可能ファイルの存在確認:
   ```bash
   # Windows
   tests/compatibility_test/versions/v1.6.1/venv/Scripts/python.exe --version
   
   # Unix/Linux/macOS
   tests/compatibility_test/versions/v1.6.1/venv/bin/python --version
   ```

3. tree-sitter-analyzerのインストール確認:
   ```bash
   tests/compatibility_test/versions/v1.6.1/venv/Scripts/python.exe -c "import tree_sitter_analyzer; print(tree_sitter_analyzer.__version__)"
   ```

4. MCPサーバーの動作確認:
   ```bash
   tests/compatibility_test/versions/v1.6.1/venv/Scripts/python.exe -m tree_sitter_analyzer.mcp.server --help
   ```

### よくある問題

#### 従来の問題
- **権限エラー**: 仮想環境のPython実行可能ファイルに実行権限があることを確認
- **パスの問題**: 絶対パスが正しく解決されていることを確認
- **バージョン不一致**: インストールされたtree-sitter-analyzerのバージョンがディレクトリ名と一致することを確認
- **MCPサポートなし**: 古いバージョンではMCPサポートがない場合があります
- **依存関係エラー**: 必要なtree-sitterパッケージがインストールされていることを確認

#### 🆕 新機能関連の問題
- **rich表示エラー**: ターミナルがカラー表示に対応していない場合、`--no-color`オプションを検討
- **questionary入力エラー**: キーボード入力が正しく認識されない場合、ターミナルの設定を確認
- **非同期エラー**: Python 3.7未満では非同期機能が制限される場合があります
- **メモリ不足**: 大量の並列インストール時はメモリ使用量を監視
- **ネットワークタイムアウト**: PyPI接続時のタイムアウトエラーは再試行で解決することが多い

## 移行ガイド

従来の複雑な設定ファイルベースのシステムから、この簡素化されたシステムへの移行は以下の手順で行います：

1. 既存のバージョンディレクトリを`versions/v{version}/venv/`構造に再編成
2. 新しい`config.json`（簡素化版）を使用
3. 新しい`version_manager.py`（規約ベース）を使用
4. テストスクリプトで動作確認

これにより、設定の複雑さを大幅に削減し、より理解しやすく保守しやすいシステムになります。

## 実装状況

### 従来機能
- ✅ 自動バージョン検出（`version_manager.py`）
- ✅ 簡素化された設定ファイル（`config.json`）
- ✅ MCPテスト実行（`mcp_test_direct.py`）
- ✅ CLIテスト実行（`cli_test.py`）
- ✅ 比較レポート生成（`compare_mcp.py`, `compare_cli.py`）
- ✅ 統合レポート（`unified_report.py`）

### 🆕 新機能
- ✅ 高度な自動インストール機能（[`setup_versions.py`](tests/compatibility_test/setup_versions.py)）
- ✅ インタラクティブセットアップモード（`--interactive`）
- ✅ 並列インストール機能（`--max-concurrent`）
- ✅ PyPIからの自動バージョン取得（[`get_available_versions_from_pypi()`](tests/compatibility_test/setup_versions.py:235)）
- ✅ リッチなUI表示（進捗バー、テーブル、パネル）
- ✅ 非同期処理による高速化（[`AsyncVersionSetup`](tests/compatibility_test/setup_versions.py:48)クラス）
- ✅ エラーハンドリングと継続実行
- ✅ バージョン管理とクリーンアップ機能

### 次のステップ
- 🔄 設定ファイル（YAML）サポートの完全実装
- 🔄 より詳細なログ出力機能
- 🔄 バッチ処理モードの追加
- 🔄 CI/CD統合のためのスクリプト最適化