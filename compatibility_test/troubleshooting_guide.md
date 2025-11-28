# MCP互換性テスト トラブルシューティングガイド

このガイドでは、tree-sitter-analyzer MCP互換性テストの実行中に発生する可能性のある問題と、その解決方法について説明します。

## 目次

1. [MCPサーバー関連の問題](#mcpサーバー関連の問題)
2. [環境設定の問題](#環境設定の問題)
3. [テスト実行の問題](#テスト実行の問題)
4. [出力ファイルの問題](#出力ファイルの問題)
5. [パフォーマンスの問題](#パフォーマンスの問題)
6. [よくある質問](#よくある質問)

## MCPサーバー関連の問題

### 問題1: "No tools available" エラー

**症状**: MCPサーバーに接続できるが、利用可能なツールが表示されない

**原因**:
- MCPサーバーの起動に失敗している
- `mcp_settings.json` の設定に問題がある
- 依存関係が正しくインストールされていない

**解決方法**:

1. **手動でのサーバー起動テスト**:
   ```bash
   # バージョン1.9.2の場合
   uvx --from tree-sitter-analyzer[mcp]==1.9.2 tree-sitter-analyzer-mcp
   ```

2. **依存関係の再インストール**:
   ```bash
   uv cache clean
   uv pip install --upgrade tree-sitter-analyzer[mcp]==1.9.2
   ```

3. **設定ファイルの確認**:
   - `mcp_settings.json` の `alwaysAllow` リストに必要なツールが含まれているか確認
   - `disabled` フラグが `false` になっているか確認

4. **環境変数の確認**:
   ```json
   {
     "env": {
       "TREE_SITTER_PROJECT_ROOT": "C:/git-private/tree-sitter-analyzer",
       "TREE_SITTER_OUTPUT_PATH": "C:/git-private/tree-sitter-analyzer/.analysis-1.9.2"
     }
   }
   ```

### 問題2: MCPサーバーの起動が遅い

**症状**: サーバーの切り替え後、ツールが利用可能になるまで時間がかかる

**解決方法**:
- テストスクリプトの待機時間を延長する（デフォルト10秒→15秒）
- `timeout` 設定を増やす（デフォルト3600秒）

### 問題3: 複数バージョンの競合

**症状**: 異なるバージョンのサーバーが同時に動作してしまう

**解決方法**:
1. **全サーバーの無効化**:
   ```python
   # mcp_settings.jsonで全てのtree-sitter-analyzerサーバーを無効化
   for server_name in settings.get("mcpServers", {}):
       if "tree-sitter-analyzer" in server_name:
           settings["mcpServers"][server_name]["disabled"] = True
   ```

2. **プロセスの強制終了**:
   ```bash
   # Windowsの場合
   taskkill /f /im python.exe
   ```

## 環境設定の問題

### 問題4: パスの問題

**症状**: ファイルが見つからない、または出力ディレクトリにアクセスできない

**解決方法**:
1. **絶対パスの使用**:
   - 相対パスではなく絶対パスを使用する
   - `{PROJECT_ROOT}` プレースホルダーが正しく置換されているか確認

2. **ディレクトリの権限確認**:
   ```bash
   # 出力ディレクトリの作成権限を確認
   mkdir -p compatibility_test/results/v1.9.2
   ```

3. **パスの区切り文字**:
   - Windows環境では `\` または `/` を適切に使用
   - Pythonの `pathlib.Path` を使用することを推奨

### 問題5: Python環境の問題

**症状**: `uv` コマンドが見つからない、またはPythonバージョンの不整合

**解決方法**:
1. **uv のインストール確認**:
   ```bash
   uv --version
   ```

2. **Python バージョンの確認**:
   ```bash
   python --version
   # Python 3.10以上が必要
   ```

3. **仮想環境の確認**:
   ```bash
   uv venv --python 3.10
   uv pip install tree-sitter-analyzer[mcp]
   ```

## テスト実行の問題

### 問題6: テストケースの実行失敗

**症状**: 特定のテストケースが常に失敗する

**解決方法**:
1. **テストファイルの存在確認**:
   ```bash
   ls -la examples/Sample.java
   ls -la tree_sitter_analyzer/core/engine.py
   ```

2. **パラメータの検証**:
   - `test_cases.json` の構文が正しいか確認
   - 必須パラメータが不足していないか確認

3. **個別テストの実行**:
   ```python
   # 単一のテストケースを手動で実行してデバッグ
   python -c "
   import json
   with open('compatibility_test/test_cases.json') as f:
       cases = json.load(f)
   print(cases['analyze_code_structure'][0])
   "
   ```

### 問題7: タイムアウトエラー

**症状**: テストの実行中にタイムアウトが発生する

**解決方法**:
1. **タイムアウト値の調整**:
   ```json
   {
     "timeout": 7200  // 2時間に延長
   }
   ```

2. **大きなファイルの除外**:
   - テスト対象から非常に大きなファイルを除外
   - `test_cases.json` でファイルサイズを制限

## 出力ファイルの問題

### 問題8: 出力ファイルが生成されない

**症状**: テストは成功するが、期待される出力ファイルが作成されない

**解決方法**:
1. **出力ディレクトリの確認**:
   ```bash
   ls -la compatibility_test/results/v1.9.2/
   ```

2. **権限の確認**:
   ```bash
   # ディレクトリの書き込み権限を確認
   touch compatibility_test/results/v1.9.2/test_file.txt
   ```

3. **ディスク容量の確認**:
   ```bash
   df -h
   ```

### 問題9: JSONファイルの破損

**症状**: 生成されたJSONファイルが不正な形式になっている

**解決方法**:
1. **JSON構文の検証**:
   ```bash
   python -m json.tool compatibility_test/results/v1.9.2/output.json
   ```

2. **エンコーディングの確認**:
   - UTF-8エンコーディングで保存されているか確認
   - BOMが含まれていないか確認

## パフォーマンスの問題

### 問題10: テスト実行が非常に遅い

**症状**: 全テストの完了に数時間かかる

**解決方法**:
1. **並列実行の有効化**:
   ```python
   # test_cases.jsonで並列実行可能なケースを分離
   ```

2. **キャッシュの活用**:
   ```bash
   # tree-sitterのキャッシュを有効化
   export TREE_SITTER_CACHE_ENABLED=true
   ```

3. **テストケースの最適化**:
   - 重複するテストケースを削除
   - 小さなファイルでの基本テストを優先

## よくある質問

### Q1: 異なるOS間でテストを実行できますか？

**A**: はい、ただし以下の点に注意してください：
- パスの区切り文字の違い（Windows: `\`, Unix: `/`）
- 改行コードの違い（Windows: `\r\n`, Unix: `\n`）
- ファイル権限の違い

### Q2: 新しいバージョンのテストを追加するには？

**A**: 以下の手順で追加できます：
1. `mcp_settings.json` に新しいバージョンのサーバー設定を追加
2. `test_cases.json` で新しいバージョン固有のテストケースを追加（必要に応じて）
3. テストスクリプトを実行

### Q3: カスタムテストケースを追加するには？

**A**: `test_cases.json` を編集して新しいテストケースを追加してください：
```json
{
  "my_custom_tool": [
    {
      "id": "custom_test_1",
      "params": {
        "file_path": "path/to/test/file.py",
        "custom_param": "value"
      },
      "output_file": "custom_test_output.json"
    }
  ]
}
```

### Q4: テスト結果の差分が期待と異なる場合は？

**A**: 以下を確認してください：
1. 両バージョンが正しく動作しているか
2. テスト環境が一貫しているか
3. ファイルのタイムスタンプやパフォーマンスメトリクスの変動を除外しているか

### Q5: 大量のテストケースを効率的に管理するには？

**A**: 以下の方法を推奨します：
1. テストケースをカテゴリ別に分離
2. 重要度に基づいてテストの優先順位を設定
3. 継続的インテグレーション（CI）での自動実行を検討

## 緊急時の対応

### 完全なリセット手順

テスト環境に問題が発生した場合の完全リセット手順：

1. **MCPサーバーの停止**:
   ```bash
   # 全てのPythonプロセスを停止
   taskkill /f /im python.exe  # Windows
   pkill -f python             # Unix
   ```

2. **設定ファイルのバックアップと初期化**:
   ```bash
   cp mcp_settings.json mcp_settings.json.backup
   # テンプレートから再作成
   ```

3. **キャッシュのクリア**:
   ```bash
   uv cache clean
   rm -rf .analysis-*
   ```

4. **依存関係の再インストール**:
   ```bash
   uv pip install --force-reinstall tree-sitter-analyzer[mcp]
   ```

5. **テスト環境の再構築**:
   ```bash
   python compatibility_test/scripts/run_compatibility_test.py --version-a 1.9.2 --version-b 1.9.3
   ```

## サポートとフィードバック

問題が解決しない場合は、以下の情報を含めてサポートに連絡してください：

1. **環境情報**:
   - OS とバージョン
   - Python バージョン
   - uv バージョン
   - tree-sitter-analyzer バージョン

2. **エラーログ**:
   - 完全なエラーメッセージ
   - スタックトレース
   - 実行したコマンド

3. **設定ファイル**:
   - `mcp_settings.json` の内容（機密情報を除く）
   - `test_cases.json` の関連部分

4. **再現手順**:
    - 問題が発生するまでの具体的な手順
    - 期待される結果と実際の結果

## 関連技術文書

問題の根本的な理解のために、以下の技術文書も参照してください：

- **[MCP直接実行の技術的背景](MCP_DIRECT_EXECUTION_TECHNICAL_BACKGROUND.md)**: 互換性テストがなぜMCPサーバーを経由せずに動作するのか、その技術的根拠を詳しく説明。
- **[キャッシュシステム設計分析](../docs/CACHE_SYSTEM_ANALYSIS.md)**: キャッシュ関連の問題が発生した場合の理解に役立つ、2つのキャッシュシステムの設計分析。
