# FileOutputManager モック設定修正レポート

**日付**: 2025-10-16  
**修正者**: speckit.implement準拠の実装プロセス  
**対象**: `tests/test_suppress_output_feature.py`

## 問題の概要

`FileOutputManager.get_managed_instance()`のモック設定が不適切で、以下のテストが失敗していました：

- `test_suppress_output_true_with_output_file_excludes_table_output`
- `test_suppress_output_false_with_output_file_includes_table_output`

## 根本原因

### 問題のあったモック設定
```python
@patch('tree_sitter_analyzer.mcp.tools.table_format_tool.FileOutputManager')
```

### 実際のコード実装
`TableFormatTool`では以下のようにクラスメソッドを直接呼び出していました：
```python
# line 45, 57 in table_format_tool.py
self.file_output_manager = FileOutputManager.get_managed_instance(project_root)
```

### 問題の詳細
- クラス全体をモックしても、クラスメソッド`get_managed_instance()`の呼び出しは正しくモックされない
- 実際のメソッド呼び出しをモックする必要があった

## 修正内容

### 修正前
```python
@patch('tree_sitter_analyzer.mcp.tools.table_format_tool.FileOutputManager')
async def test_suppress_output_true_with_output_file_excludes_table_output(
    self, mock_file_manager, mock_monitor, mock_detect_lang, mock_engine, temp_java_file
):
    # Mock file output manager
    mock_file_manager_instance = Mock()
    mock_file_manager_instance.save_to_file.return_value = "/path/to/output.md"
    mock_file_manager.return_value = mock_file_manager_instance
```

### 修正後
```python
@patch('tree_sitter_analyzer.mcp.tools.table_format_tool.FileOutputManager.get_managed_instance')
async def test_suppress_output_true_with_output_file_excludes_table_output(
    self, mock_get_managed_instance, mock_monitor, mock_detect_lang, mock_engine, temp_java_file
):
    # Mock file output manager
    mock_file_manager_instance = Mock()
    mock_file_manager_instance.save_to_file.return_value = "/path/to/output.md"
    mock_get_managed_instance.return_value = mock_file_manager_instance
```

## 修正対象ファイル

- **ファイル**: `tests/test_suppress_output_feature.py`
- **修正行**: 186行目、234行目のデコレータとパラメータ名

## テスト結果

### 修正前
- 2つのテストが失敗
- モック設定の不整合によるAttributeError

### 修正後
- 全9テストが成功 (9/9 PASSED)
- CI/CDパイプラインの正常化

## 学習ポイント

1. **クラスメソッドのモック**: クラス全体ではなく、実際に呼び出されるメソッドをモックする
2. **実装の詳細確認**: テスト対象コードの実装を正確に理解してからモック設定を行う
3. **speckit.implement準拠**: 体系的なテスト修正プロセスの重要性

## 品質指標の改善

- **テスト成功率**: 77.8% → 100% (2/9 → 9/9)
- **CI/CDパイプライン**: 正常化
- **コードカバレッジ**: 維持
- **技術的負債**: 削減

## 今後の予防策

1. モック設定時は実装の詳細を必ず確認する
2. クラスメソッド、インスタンスメソッドの違いを意識する
3. テスト失敗時は根本原因を特定してから修正する