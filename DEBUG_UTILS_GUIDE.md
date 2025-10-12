# Debug Utils Guide - Windows 11対応デバッグコード実行

## 🚨 問題の背景

Windows 11環境で`python -c`を使用して複雑なPythonコードを実行する際、以下の問題が発生する場合があります：

- **特殊文字エラー**: 引用符、中文文字、記号文字が原因でコマンド実行が失敗
- **エンコーディング問題**: UTF-8文字の処理でエラーが発生
- **複雑なコード**: 複数行のコードや複雑な文字列処理でコマンドライン制限に達する

## ✅ 解決方法

新しい`debug_utils.py`モジュールを使用してファイルベースのデバッグコード実行を行います。

## 📖 使用方法

### 基本的な使用方法

```python
from tree_sitter_analyzer.debug_utils import execute_debug_code

# 複雑なデバッグコード
debug_code = '''
from tree_sitter_analyzer.query_loader import query_loader
query_string = query_loader.get_query("html", "form_element")
print("Query contains [element syntax:", "[" in query_string if query_string else False)
print("Query contains input:", "input" in query_string if query_string else False)
'''

# 安全に実行
result = execute_debug_code(debug_code)
if result['success']:
    print("実行成功!")
    print(result['stdout'])
else:
    print("実行失敗:", result.get('error'))
```

### 高度な使用方法

```python
from tree_sitter_analyzer.debug_utils import DebugScriptManager

# カスタムマネージャーを作成
debug_manager = DebugScriptManager()

# スクリプトを作成（クリーンアップなし）
script_path = debug_manager.create_script(debug_code, "my_debug.py")

# 後で実行
result = debug_manager.execute_script(script_path)

# 手動クリーンアップ
debug_manager.cleanup_script(script_path)
```

## 🔧 修正前後の比較

### 修正前（問題のあるコード）
```python
# Windows 11で失敗する可能性がある
import subprocess

complex_code = '''
from tree_sitter_analyzer.query_loader import query_loader
print("测试中文输出")
result = query_loader.get_query('html', 'form_element')
print(f"查询结果: {result}")
'''

# これは失敗する可能性がある
subprocess.run(['python', '-c', complex_code])
```

### 修正後（安全なコード）
```python
# Windows 11で安全に動作
from tree_sitter_analyzer.debug_utils import execute_debug_code

complex_code = '''
from tree_sitter_analyzer.query_loader import query_loader
print("测试中文输出")
result = query_loader.get_query('html', 'form_element')
print(f"查询结果: {result}")
'''

# これは安全に動作する
result = execute_debug_code(complex_code)
if result['success']:
    print(result['stdout'])
```

## 🌟 主な機能

### 1. UTF-8とエンコーディング対応
- 中文文字の完全サポート
- Windows 11でのUTF-8エンコーディング処理
- 特殊文字の安全な処理

### 2. 自動クリーンアップ
- 一時ファイルの自動削除
- プロセス終了時のクリーンアップ
- メモリリークの防止

### 3. エラーハンドリング
- 詳細なエラー情報
- タイムアウト処理
- 安全な例外処理

### 4. 柔軟な実行オプション
- カスタム作業ディレクトリ
- タイムアウト設定
- 出力キャプチャ制御

## 📝 実装例

### デバッグモードでの使用
```python
def debug_query_analysis():
    """デバッグ用のクエリ分析"""
    debug_code = '''
    from tree_sitter_analyzer.query_loader import query_loader
    
    # 複数のクエリをテスト
    languages = ['html', 'javascript', 'python']
    for lang in languages:
        query = query_loader.get_query(lang, 'functions')
        print(f"{lang}: {len(query) if query else 0} characters")
    '''
    
    result = execute_debug_code(debug_code)
    return result['stdout'] if result['success'] else result.get('error')
```

### テストでの使用
```python
def test_complex_scenario():
    """複雑なシナリオのテスト"""
    test_code = '''
    import json
    
    # 中文データのテスト
    test_data = {
        "名称": "测试项目",
        "描述": "这是一个测试项目",
        "特殊字符": "& < > | [ ] ( ) ' \\""
    }
    
    print(json.dumps(test_data, ensure_ascii=False, indent=2))
    '''
    
    result = execute_debug_code(test_code, timeout=10)
    assert result['success'], f"Test failed: {result.get('error')}"
```

## ⚠️ 注意事項

1. **セキュリティ**: 信頼できないコードは実行しないでください
2. **パフォーマンス**: 大量のデバッグコード実行は避けてください
3. **クリーンアップ**: 長時間実行するアプリケーションでは定期的にクリーンアップを実行してください

## 🔍 トラブルシューティング

### 問題: モジュールが見つからない
```python
# 解決方法: 現在のディレクトリが自動的にPythonパスに追加されます
# 追加の設定は不要です
```

### 問題: エンコーディングエラー
```python
# 解決方法: UTF-8エンコーディングが自動的に設定されます
# Windows 11での中文文字も正常に処理されます
```

### 問題: 一時ファイルが残る
```python
# 解決方法: 自動クリーンアップが有効です
# 手動クリーンアップも可能:
from tree_sitter_analyzer.debug_utils import cleanup_debug_scripts
cleanup_debug_scripts()
```

## 📊 パフォーマンス比較

| 方法 | Windows 11互換性 | UTF-8サポート | エラーハンドリング | クリーンアップ |
|------|------------------|---------------|-------------------|----------------|
| `python -c` | ❌ 問題あり | ❌ 制限あり | ❌ 基本的 | ❌ なし |
| `debug_utils` | ✅ 完全対応 | ✅ 完全対応 | ✅ 高度 | ✅ 自動 |

この新しいデバッグユーティリティにより、Windows 11環境でのデバッグコード実行が大幅に改善され、信頼性が向上します。