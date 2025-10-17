# 🔧 トラブルシューティングガイド

## 概要

互換性テストシステムで発生する可能性のある問題と解決方法を詳しく説明します。問題の種類別に整理されており、迅速な問題解決をサポートします。

---

## 🚀 インストール・環境問題

### 1. uvコマンドが見つからない

**症状:**
```
'uv' は、内部コマンドまたは外部コマンド、
操作可能なプログラムまたはバッチ ファイルとして認識されていません。
```

**解決方法:**

#### Windows
```bash
# 方法1: pipでインストール
pip install uv

# 方法2: 公式インストーラー（PowerShell）
irm https://astral.sh/uv/install.ps1 | iex

# 方法3: Chocolatey
choco install uv

# 方法4: Scoop
scoop install uv
```

#### Linux/macOS
```bash
# 方法1: pipでインストール
pip install uv

# 方法2: 公式インストーラー
curl -LsSf https://astral.sh/uv/install.sh | sh

# 方法3: Homebrew (macOS)
brew install uv
```

### 2. coloramaライブラリが見つからない

**症状:**
```
ModuleNotFoundError: No module named 'colorama'
```

**解決方法:**
```bash
# 個別インストール
uv add colorama

# または pip で
pip install colorama>=0.4.6

# requirements.txt から一括インストール
uv pip install -r requirements.txt
```

### 3. 依存関係の競合

**症状:**
```
ERROR: pip's dependency resolver does not currently consider all the ways that
```

**解決方法:**
```bash
# 仮想環境を作成して隔離
python -m venv test_env
source test_env/bin/activate  # Linux/macOS
test_env\Scripts\activate     # Windows

# 依存関係を再インストール
uv sync --reinstall

# または強制的に再インストール
pip install --force-reinstall -r requirements.txt
```

---

## 🎨 色付きログ問題

### 1. 色が表示されない（Windows）

**症状:**
- ログに色が付かない
- エスケープシーケンスが文字として表示される

**解決方法:**

#### Windows 10/11の場合
```bash
# Windows 10 1511以降では自動的に有効化されます
# 手動で有効化する場合（レジストリ編集）
reg add HKCU\Console /v VirtualTerminalLevel /t REG_DWORD /d 1

# または環境変数で強制有効化
set FORCE_COLOR=1
```

#### 古いWindowsの場合
```bash
# coloramaの初期化を確認
python -c "from colorama import init; init(); print('colorama initialized')"

# ANSIエスケープシーケンスのテスト
python -c "from colorama import Fore; print(Fore.RED + 'Red text' + Fore.RESET)"
```

### 2. coloramaが正しく動作しない

**症状:**
```
AttributeError: module 'colorama' has no attribute 'Fore'
```

**解決方法:**
```bash
# coloramaのバージョン確認
python -c "import colorama; print(colorama.__version__)"

# 最新版に更新
pip install --upgrade colorama

# 完全に再インストール
pip uninstall colorama
pip install colorama>=0.4.6
```

---

## 📋 設定ファイル問題

### 1. JSON構文エラー

**症状:**
```
json.decoder.JSONDecodeError: Expecting ',' delimiter: line 10 column 5
```

**解決方法:**
```bash
# JSON構文チェック
python -m json.tool cli_test_cases.json

# 一般的なJSONエラー:
# - 末尾のカンマ
# - シングルクォート使用
# - コメント記述
# - 改行文字の問題
```

**正しいJSON例:**
```json
{
  "test_id": "CLI-001",
  "description": "テスト"  // ← コメント不可、末尾カンマ不可
}
```

### 2. テストケース設定エラー

**症状:**
```
KeyError: 'file_path'
テンプレート CLI-001-summary でパラメータが不足: 'file_path'
```

**解決方法:**
```bash
# テストケースローダーで検証
uv run python test_case_loader.py

# 設定ファイルの妥当性確認
uv run python cli_test.py --list-tests
```

**修正例:**
```json
{
  "template": "{file_path} --summary",
  "parameters": {
    "file_path": "examples/BigService.java"  // ← 必須パラメータを追加
  }
}
```

---

## 🔄 MCPテスト関連問題 ✨**新機能**

### 1. MCPツールインポートエラー

**症状:**
```
ImportError: cannot import name 'AnalyzeScaleTool' from 'tree_sitter_analyzer.mcp.tools.analyze_scale_tool'
```

**解決方法:**
```bash
# MCPパッケージの確認
python -c "import tree_sitter_analyzer.mcp; print('MCP module OK')"

# 必要なツールの確認
python -c "from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool; print('AnalyzeScaleTool OK')"

# tree-sitter-analyzer[mcp]の再インストール
uv add tree-sitter-analyzer[mcp]>=1.6.1
```

### 2. MCPテストケース設定エラー

**症状:**
```
KeyError: 'mcp_test_cases'
json.decoder.JSONDecodeError: Expecting property name enclosed in double quotes
```

**解決方法:**
```bash
# MCPテストケースファイルの構文チェック
python -m json.tool mcp_test_cases.json

# テストケースローダーでの検証
uv run python test_case_loader.py mcp_test_cases.json

# 設定ファイルの妥当性確認
uv run python mcp_test_direct.py --test-ids MCP-001 --verbose
```

**正しいMCPテストケース例:**
```json
{
  "mcp_test_cases": [
    {
      "id": "MCP-001",
      "tool": "check_code_scale",
      "category": "analysis",
      "description": "コードスケール分析テスト",
      "parameters": {
        "file_path": "examples/BigService.java",
        "include_complexity": true
      }
    }
  ]
}
```

### 3. MCPツール実行エラー

**症状:**
```
Exception: Tool execution failed
AttributeError: 'AnalyzeScaleTool' object has no attribute 'execute'
```

**解決方法:**
```bash
# ツールの初期化確認
python -c "
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
tool = AnalyzeScaleTool('.')
print('Tool initialized:', tool)
"

# プロジェクトルートの設定確認
uv run python mcp_test_direct.py --verbose
```

### 4. カテゴリ・ツールフィルタリング問題

**症状:**
```
実行するテストケースがありません
No test cases to run
```

**解決方法:**
```bash
# 利用可能なカテゴリ確認
uv run python mcp_test_direct.py --categories analysis --verbose

# 利用可能なツール確認
uv run python mcp_test_direct.py --tools check_code_scale --verbose

# 全テストケース実行（フィルタなし）
uv run python mcp_test_direct.py --verbose

# テストケースファイルの内容確認
python -c "
import json
with open('mcp_test_cases.json') as f:
    data = json.load(f)
    print('Available categories:', set(tc.get('category') for tc in data['mcp_test_cases']))
    print('Available tools:', set(tc.get('tool') for tc in data['mcp_test_cases']))
"
```

### 5. 色付きログが表示されない（MCP）

**症状:**
- MCPテストで色付きログが表示されない
- `--no-color`オプションが効かない

**解決方法:**
```bash
# 色付きログの動作確認
python -c "
from colored_logger import ColoredLogger
logger = ColoredLogger('test', use_color=True)
logger.info('Info message')
logger.success('Success message')
logger.error('Error message')
"

# MCPテストで色付きログ有効化
uv run python mcp_test_direct.py --verbose

# 色付きログ無効化
uv run python mcp_test_direct.py --no-color
```

### 6. 進捗表示の問題

**症状:**
- 進捗バーが正しく表示されない
- カテゴリ別サマリーが表示されない

**解決方法:**
```bash
# 進捗表示の確認
uv run python mcp_test_direct.py --test-ids MCP-001 MCP-002 --verbose

# カテゴリ別実行でサマリー確認
uv run python mcp_test_direct.py --categories analysis structure
```

---

## 🔄 テスト実行問題

### 1. ファイルが見つからない

**症状:**
```
FileNotFoundError: [Errno 2] No such file or directory: 'examples/BigService.java'
```

**解決方法:**
```bash
# 現在のディレクトリ確認
pwd
ls examples/  # ファイルの存在確認

# 正しいディレクトリから実行
cd tests/compatibility_test
uv run python cli_test.py

# プロジェクトルートからの相対パス確認
ls ../../examples/BigService.java
```

### 2. タイムアウトエラー

**症状:**
```
subprocess.TimeoutExpired: Command '...' timed out after 30 seconds
```

**解決方法:**

#### 個別テストのタイムアウト調整
```json
{
  "test_id": "CLI-001-summary",
  "timeout": 60  // ← 30秒から60秒に延長
}
```

#### グローバル設定の調整
```json
{
  "global_settings": {
    "default_timeout": 60
  }
}
```

### 3. 権限エラー

**症状:**
```
PermissionError: [Errno 13] Permission denied
```

**解決方法:**

#### Windows
```bash
# 管理者権限でコマンドプロンプト実行
# または仮想環境使用
python -m venv venv
venv\Scripts\activate
```

#### Linux/macOS
```bash
# ファイル権限確認
ls -la cli_test.py

# 実行権限付与
chmod +x cli_test.py

# または仮想環境使用
python -m venv venv
source venv/bin/activate
```

---

## 🔍 デバッグ方法

### 1. 詳細ログ出力

#### CLIテスト
```bash
# 詳細ログでデバッグ
uv run python cli_test.py --verbose

# 特定テストのみでデバッグ
uv run python cli_test.py --test-ids CLI-001-summary --verbose

# ログファイル確認
cat compatibility_test.log
```

#### MCPテスト ✨**新機能**
```bash
# MCPテストの詳細ログ
uv run python mcp_test_direct.py --verbose

# 特定MCPテストのデバッグ
uv run python mcp_test_direct.py --test-ids MCP-001 --verbose

# カテゴリ別デバッグ
uv run python mcp_test_direct.py --categories analysis --verbose

# ツール別デバッグ
uv run python mcp_test_direct.py --tools check_code_scale --verbose
```

### 2. 段階的デバッグ

#### 共通デバッグ手順
```bash
# 1. 色付きログシステムの動作確認
uv run python colored_logger.py

# 2. テストケースローダーの動作確認
uv run python test_case_loader.py

# 3. 設定管理の動作確認
uv run python config_manager.py
```

#### CLIテスト段階的デバッグ
```bash
# 3. 基本カテゴリのみ実行
uv run python cli_test.py --categories basic

# 4. エラーテストを除外
uv run python cli_test.py --no-errors
```

#### MCPテスト段階的デバッグ ✨**新機能**
```bash
# 3. 分析カテゴリのみ実行
uv run python mcp_test_direct.py --categories analysis

# 4. 単一ツールのみ実行
uv run python mcp_test_direct.py --tools check_code_scale

# 5. 単一テストケース実行
uv run python mcp_test_direct.py --test-ids MCP-001
```

### 3. 設定ファイル検証

#### CLIテスト設定
```bash
# JSON構文チェック
python -m json.tool cli_test_cases.json
python -m json.tool config.json

# テストケース一覧表示
uv run python cli_test.py --list-tests

# カテゴリ一覧表示
uv run python cli_test.py --list-categories
```

#### MCPテスト設定 ✨**新機能**
```bash
# MCPテストケース構文チェック
python -m json.tool mcp_test_cases.json

# MCPテストケースの妥当性確認
python -c "
import json
with open('mcp_test_cases.json') as f:
    data = json.load(f)
    print('Test cases:', len(data['mcp_test_cases']))
    print('Error cases:', len(data.get('error_test_cases', [])))
    print('Categories:', list(data.get('categories', {}).keys()))
"

# MCPツールの動作確認
python -c "
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
tool = AnalyzeScaleTool('.')
print('Tool initialized successfully')
"
```

---

## 🚨 よくあるエラーと解決法

### 1. UnicodeDecodeError

**症状:**
```
UnicodeDecodeError: 'cp932' codec can't encode character '\u2591'
```

**解決方法:**
```bash
# 環境変数設定
set PYTHONIOENCODING=utf-8

# または設定ファイルで指定
{
  "cli_settings": {
    "encoding": "utf-8"
  }
}
```

### 2. ImportError

**症状:**
```
ImportError: cannot import name 'get_logger' from 'colored_logger'
```

**解決方法:**
```bash
# モジュールパス確認
python -c "import sys; print(sys.path)"

# 現在のディレクトリから実行
cd tests/compatibility_test
python cli_test.py
```

### 3. JSONDecodeError

**症状:**
```
json.decoder.JSONDecodeError: Extra data
```

**解決方法:**
```bash
# 出力の確認（CLIが複数行JSON出力する場合）
uv run python -m tree_sitter_analyzer examples/BigService.java --summary

# 出力パース設定の調整
{
  "cli_settings": {
    "parse_json_output": true
  }
}
```

---

## 📊 パフォーマンス問題

### 1. テスト実行が遅い

**解決方法:**
```bash
# エラーテストを除外
uv run python cli_test.py --no-errors

# 基本カテゴリのみ実行
uv run python cli_test.py --categories basic

# 特定テストのみ実行
uv run python cli_test.py --test-ids CLI-001-summary
```

### 2. メモリ使用量が多い

**解決方法:**
```bash
# 大きなファイルのテストを除外
# または小さなファイルでテスト
{
  "parameters": {
    "file_path": "examples/small_sample.py"  // ← より小さなファイル
  }
}
```

---

## 🔧 環境別対応

### Windows固有の問題

1. **パス区切り文字**
   ```json
   // 良い例（両OS対応）
   "file_path": "examples/BigService.java"
   
   // 悪い例（Windows専用）
   "file_path": "examples\\BigService.java"
   ```

2. **文字エンコーディング**
   ```bash
   # コマンドプロンプトの文字コード設定
   chcp 65001  # UTF-8に設定
   ```

### Linux/macOS固有の問題

1. **実行権限**
   ```bash
   chmod +x *.py
   ```

2. **Python実行環境**
   ```bash
   # Python3を明示的に使用
   python3 cli_test.py
   ```

---

## 📞 サポート情報

### ログファイル

問題報告時に以下のファイルを確認します：

#### CLIテスト関連
- `compatibility_test.log`: メインログファイル
- `result/cli/v-current/cli_test_summary.json`: CLIテスト結果サマリー
- `result/cli/v-current/*.json`: 個別CLIテスト結果

#### MCPテスト関連 ✨**新機能**
- `result/mcp/v-current/mcp_test_summary.json`: MCPテスト結果サマリー
- `result/mcp/v-current/*.json`: 個別MCPテスト結果
- `mcp_test_cases.json`: MCPテストケース設定ファイル

### 環境情報収集

```bash
# Python環境情報
python --version
pip list | grep -E "(tree-sitter|colorama|uv)"

# MCPパッケージ確認
python -c "import tree_sitter_analyzer.mcp; print('MCP module version:', tree_sitter_analyzer.__version__)"

# システム情報
uname -a  # Linux/macOS
systeminfo | findstr /B /C:"OS Name" /C:"OS Version"  # Windows

# プロジェクト情報
ls -la
pwd

# MCPテスト固有情報
ls -la mcp_test_cases.json
python -c "
import json
try:
    with open('mcp_test_cases.json') as f:
        data = json.load(f)
        print('MCP test cases loaded successfully')
        print('Number of test cases:', len(data.get('mcp_test_cases', [])))
except Exception as e:
    print('MCP test cases error:', e)
"
```

### 問題報告テンプレート

#### CLIテスト問題報告
```
## 環境情報
- OS:
- Python:
- uv:
- colorama:
- tree-sitter-analyzer:

## 実行コマンド
```
uv run python cli_test.py --verbose
```

## エラーメッセージ
```
[エラーメッセージをここに貼り付け]
```

## 期待される動作
[期待される動作を記述]

## 実際の動作
[実際の動作を記述]
```

#### MCPテスト問題報告 ✨**新機能**
```
## 環境情報
- OS:
- Python:
- uv:
- colorama:
- tree-sitter-analyzer[mcp]:

## 実行コマンド
```
uv run python mcp_test_direct.py --verbose
```

## MCPテストケース設定
```
[mcp_test_cases.jsonの関連部分を貼り付け]
```

## エラーメッセージ
```
[エラーメッセージをここに貼り付け]
```

## 期待される動作
[期待される動作を記述]

## 実際の動作
[実際の動作を記述]

## 追加情報
- 使用したカテゴリ:
- 使用したツール:
- 使用したテストID:
```

---

## 🔄 更新・メンテナンス

### 定期的なメンテナンス

```bash
# 依存関係の更新
uv sync --upgrade

# 設定ファイルの検証
uv run python test_case_loader.py

# テストケースの動作確認
uv run python cli_test.py --categories basic
```

### 新機能追加時の確認事項

#### CLIテスト
1. 新しいテストケースを追加
2. 設定ファイルの妥当性を確認
3. 既存テストケースへの影響を確認
4. ドキュメントを更新

#### MCPテスト ✨**新機能**
1. 新しいMCPテストケースを追加
2. MCPテストケース設定ファイルの妥当性を確認
3. カテゴリ・ツールフィルタリングの動作を確認
4. 色付きログ・進捗表示の動作を確認
5. 既存MCPテストケースへの影響を確認
6. MCPドキュメントを更新

---

このトラブルシューティングガイドで解決しない問題がある場合は、詳細なログファイルと環境情報を添えて問題を報告します。