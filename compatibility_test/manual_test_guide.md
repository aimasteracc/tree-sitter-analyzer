# tree-sitter-analyzer MCP互換性テスト手動実行ガイド

## 概要
このガイドでは、tree-sitter-analyzerの2つのバージョン（1.6.1.2と1.9.2）における8つのMCPツールの互換性を手動でテストする方法を説明します。

## 前提条件
- mcp_settings.jsonが正しく設定されていること
- 両バージョンで8つのツール全てがalwaysAllowに設定されていること
- .analysis-1.6.1.2と.analysis-1.9.2ディレクトリが存在すること

## テスト対象ツール
1. `analyze_code_structure` - コード構造分析
2. `query_code` - tree-sitterクエリ実行
3. `check_code_scale` - コードスケール分析
4. `extract_code_section` - コードセクション抽出
5. `set_project_path` - プロジェクトパス設定
6. `list_files` - ファイル一覧取得
7. `find_and_grep` - ファイル検索とコンテンツ検索
8. `search_content` - コンテンツ検索

## テスト手順

### ステップ0: キャッシュのクリア（重要）

手動テストを開始する前に、必ずキャッシュをクリアしてください。これにより、異なるバージョンのテスト結果が互いに影響し合うのを防ぎ、クリーンな状態でテストを実行できます。

以下のコマンドを実行して、すべてのキャッシュをクリアします。

```bash
python compatibility_test/utils/cache_manager.py clear
```

`cache_manager.py` は、`UnifiedAnalysisEngine`と`SearchContentTool`の両方のキャッシュをクリアします。

### 1. バージョン1.6.1.2のテスト

#### 1.1 サーバー有効化
```python
# 自動テストスクリプトを実行
python compatibility_test/mcp_compatibility_test.py
```

または手動でmcp_settings.jsonを編集：
- `tree-sitter-analyzer-1.6.1.2`の`disabled`を`false`に設定
- `tree-sitter-analyzer-1.9.2`の`disabled`を`true`に設定

#### 1.2 各ツールのテスト

##### set_project_path
```json
{
  "server_name": "tree-sitter-analyzer-1.6.1.2",
  "tool_name": "set_project_path",
  "arguments": {
    "project_path": "C:/git-private/tree-sitter-analyzer"
  }
}
```

##### list_files
```json
{
  "server_name": "tree-sitter-analyzer-1.6.1.2",
  "tool_name": "list_files",
  "arguments": {
    "roots": ["."],
    "extensions": ["py"],
    "limit": 10
  }
}
```

##### check_code_scale
```json
{
  "server_name": "tree-sitter-analyzer-1.6.1.2",
  "tool_name": "check_code_scale",
  "arguments": {
    "file_path": "tree_sitter_analyzer/core/engine.py",
    "include_complexity": true,
    "include_guidance": true
  }
}
```

```json
{
  "server_name": "tree-sitter-analyzer-1.6.1.2",
  "tool_name": "check_code_scale",
  "arguments": {
    "file_path": "examples/Sample.java",
    "include_complexity": true,
    "include_guidance": true
  }
}
```

##### analyze_code_structure
```json
{
  "server_name": "tree-sitter-analyzer-1.6.1.2",
  "tool_name": "analyze_code_structure",
  "arguments": {
    "file_path": "tree_sitter_analyzer/core/engine.py",
    "format_type": "full"
  }
}
```

```json
{
  "server_name": "tree-sitter-analyzer-1.6.1.2",
  "tool_name": "analyze_code_structure",
  "arguments": {
    "file_path": "examples/Sample.java",
    "format_type": "full"
  }
}
```

##### query_code
```json
{
  "server_name": "tree-sitter-analyzer-1.6.1.2",
  "tool_name": "query_code",
  "arguments": {
    "file_path": "tree_sitter_analyzer/core/engine.py",
    "query_key": "methods",
    "output_format": "json"
  }
}
```

```json
{
  "server_name": "tree-sitter-analyzer-1.6.1.2",
  "tool_name": "query_code",
  "arguments": {
    "file_path": "examples/Sample.java",
    "query_key": "methods",
    "output_format": "json"
  }
}
```

##### extract_code_section
```json
{
  "server_name": "tree-sitter-analyzer-1.6.1.2",
  "tool_name": "extract_code_section",
  "arguments": {
    "file_path": "tree_sitter_analyzer/core/engine.py",
    "start_line": 1,
    "end_line": 50,
    "format": "text"
  }
}
```

```json
{
  "server_name": "tree-sitter-analyzer-1.6.1.2",
  "tool_name": "extract_code_section",
  "arguments": {
    "file_path": "examples/Sample.java",
    "start_line": 1,
    "end_line": 30,
    "format": "text"
  }
}
```

##### find_and_grep
```json
{
  "server_name": "tree-sitter-analyzer-1.6.1.2",
  "tool_name": "find_and_grep",
  "arguments": {
    "roots": ["."],
    "pattern": "*.py",
    "glob": true,
    "query": "class",
    "summary_only": true
  }
}
```

```json
{
  "server_name": "tree-sitter-analyzer-1.6.1.2",
  "tool_name": "find_and_grep",
  "arguments": {
    "roots": ["."],
    "pattern": "*.java",
    "glob": true,
    "query": "public class",
    "summary_only": true
  }
}
```

##### search_content
```json
{
  "server_name": "tree-sitter-analyzer-1.6.1.2",
  "tool_name": "search_content",
  "arguments": {
    "roots": ["."],
    "query": "def __init__",
    "include_globs": ["*.py"],
    "summary_only": true
  }
}
```

```json
{
  "server_name": "tree-sitter-analyzer-1.6.1.2",
  "tool_name": "search_content",
  "arguments": {
    "roots": ["."],
    "query": "public class",
    "include_globs": ["*.java"],
    "summary_only": true
  }
}
```

### 2. バージョン1.9.2のテスト

#### 2.1 サーバー切り替え
- `tree-sitter-analyzer-1.6.1.2`の`disabled`を`true`に設定
- `tree-sitter-analyzer-1.9.2`の`disabled`を`false`に設定

#### 2.2 各ツールのテスト
上記と同じテストケースを`server_name`を`tree-sitter-analyzer-1.9.2`に変更して実行

## 期待される結果

### 共通の期待結果
- 全てのツールが正常に実行される
- エラーが発生しない
- 適切な出力が返される

### バージョン固有の違い
- 出力フォーマットの微細な違いがある可能性
- パフォーマンスの違いがある可能性
- 新機能や改善された機能がある可能性

## 結果の記録

### 成功ケース
- ✅ ツール名: 正常に実行され、期待される出力が得られた
- 実行時間: X秒
- 出力サイズ: Xバイト

### 失敗ケース
- ❌ ツール名: エラーが発生
- エラーメッセージ: [具体的なエラー内容]
- 原因: [推定される原因]

## トラブルシューティング

### よくある問題

#### 1. サーバーが起動しない
- mcp_settings.jsonの設定を確認
- 環境変数の設定を確認
- ログファイルを確認

#### 2. ツールが見つからない
- alwaysAllowの設定を確認
- サーバーの再起動を試行

#### 3. パフォーマンスの問題
- ファイルサイズを確認
- メモリ使用量を監視
- タイムアウト設定を調整

## レポート作成

テスト完了後、以下の情報を含むレポートを作成：

1. **テスト環境**
   - OS情報
   - Python バージョン
   - tree-sitter-analyzer バージョン

2. **テスト結果サマリー**
   - 成功したツール数
   - 失敗したツール数
   - 全体的な互換性評価

3. **詳細結果**
   - 各ツールの個別結果
   - パフォーマンス比較
   - 発見された問題

4. **推奨事項**
   - 使用すべきバージョン
   - 注意すべき点
   - 今後の改善提案

## 自動化スクリプトの使用

手動テストの代わりに、提供された自動化スクリプトを使用することも可能：

```bash
cd compatibility_test
python mcp_compatibility_test.py
```

このスクリプトは：
- 自動的にバージョンを切り替え
- 基本的なテストケースを実行
- 結果をJSONとMarkdown形式で保存
- 詳細なレポートを生成

## 関連技術文書

- **[MCP直接実行の技術的背景](MCP_DIRECT_EXECUTION_TECHNICAL_BACKGROUND.md)**: なぜ自動化スクリプトがMCPサーバーを経由せずに直接ツールクラスを実行できるのか、その技術的根拠を詳しく説明。
- **[キャッシュシステム設計分析](../docs/CACHE_SYSTEM_ANALYSIS.md)**: テスト実行前のキャッシュクリアが重要な理由と、2つのキャッシュシステムの設計妥当性について。

## スマート比較の手動実行

1.  **テストの実行**:
    `run_compatibility_test.py` を実行して、比較対象のJSONファイルを生成します。

    ```bash
    python compatibility_test/scripts/run_compatibility_test.py --version-a 1.9.2 --version-b 1.6.1.2
    ```

2.  **差分分析の実行**:
    `analyze_differences.py` を `--smart-compare` オプション付きで実行します。

    ```bash
    python compatibility_test/scripts/analyze_differences.py --version-a 1.9.2 --version-b 1.6.1.2 --smart-compare
    ```
    
3.  **正規化ファイルの生成（オプション）**:
    `--generate-normalized` を追加すると、比較に使用された正規化済みJSONファイルが `.analysis-*-normalized/` ディレクトリに保存されます。これはデバッグに役立ちます。

    ```bash
    python compatibility_test/scripts/analyze_differences.py --version-a 1.9.2 --version-b 1.6.1.2 --smart-compare --generate-normalized
    ```
    
4.  **結果の確認**:
    生成されたレポート (`compatibility_test/reports/smart_comparison_report_*.md`) を確認し、差分内容を分析します。
