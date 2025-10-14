# 実装ガイドライン

## 1. 概要

本ガイドラインは、tree-sitter-analyzer v1.8.0における非同期処理不整合の緊急修正から品質保証プロセスまでの具体的な実装手順を定義します。

## 2. 緊急修正の具体的手順

### 2.1 事前準備

#### 環境確認
```bash
# 現在のブランチ確認
git branch

# developブランチに切り替え（既に完了済み）
git checkout develop
git pull origin develop

# 作業ブランチの作成
git checkout -b hotfix/async-query-service-fix

# 依存関係の確認
python -m pip list | grep tree-sitter
```

#### バックアップの作成
```bash
# 修正前のコミットハッシュを記録
git log --oneline -5 > backup_commit_hashes.txt

# 重要ファイルのバックアップ
cp tree_sitter_analyzer/core/query_service.py tree_sitter_analyzer/core/query_service.py.backup
```

### 2.2 Step 1: QueryService.execute_query()の非同期化

#### ファイル: `tree_sitter_analyzer/core/query_service.py`

**修正箇所1: メソッドシグネチャの変更**
```python
# 修正前（行33-40）
def execute_query(
    self,
    file_path: str,
    language: str,
    query_key: str | None = None,
    query_string: str | None = None,
    filter_expression: str | None = None,
) -> list[dict[str, Any]] | None:

# 修正後
async def execute_query(
    self,
    file_path: str,
    language: str,
    query_key: str | None = None,
    query_string: str | None = None,
    filter_expression: str | None = None,
) -> list[dict[str, Any]] | None:
```

**修正箇所2: ファイル読み込みの非同期化**
```python
# 修正前（行67）
content, encoding = read_file_safe(file_path)

# 修正後
content, encoding = await self._read_file_async(file_path)
```

**修正箇所3: 非同期ファイル読み込みメソッドの追加**
```python
# 新規追加メソッド（行290以降に追加）
async def _read_file_async(self, file_path: str) -> tuple[str, str]:
    """
    非同期ファイル読み込み
    
    Args:
        file_path: ファイルパス
        
    Returns:
        tuple[str, str]: (content, encoding)
    """
    import asyncio
    from ..encoding_utils import read_file_safe
    
    # CPU集約的でない単純なファイル読み込みなので、
    # run_in_executorを使用して非同期化
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, read_file_safe, file_path)
```

### 2.3 Step 2: 依存関係の確認と修正

#### インポート文の確認
```python
# ファイル先頭に追加が必要な場合
import asyncio
from typing import Any, Tuple
```

#### エラーハンドリングの改善
```python
# 修正前（行124-126）
except Exception as e:
    logger.error(f"Query execution failed: {e}")
    raise

# 修正後
except Exception as e:
    logger.error(f"Query execution failed: {e}")
    # 非同期処理でのエラー情報を追加
    if asyncio.current_task():
        logger.debug(f"Current async task: {asyncio.current_task()}")
    raise
```

### 2.4 Step 3: 基本動作確認テスト

#### テストスクリプトの作成
```python
# test_async_fix.py
import asyncio
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from tree_sitter_analyzer.core.query_service import QueryService

async def test_basic_query():
    """基本的なクエリ実行テスト"""
    service = QueryService()
    
    # テスト用のPythonファイルを作成
    test_file = "test_sample.py"
    with open(test_file, "w") as f:
        f.write("""
def hello_world():
    print("Hello, World!")

class TestClass:
    def test_method(self):
        pass
""")
    
    try:
        # 非同期クエリ実行テスト
        results = await service.execute_query(
            file_path=test_file,
            language="python",
            query_key="function"
        )
        
        print(f"✅ Query executed successfully. Results: {len(results) if results else 0}")
        return True
        
    except Exception as e:
        print(f"❌ Query execution failed: {e}")
        return False
    finally:
        # テストファイルのクリーンアップ
        Path(test_file).unlink(missing_ok=True)

async def test_custom_query():
    """カスタムクエリテスト"""
    service = QueryService()
    
    test_file = "test_custom.py"
    with open(test_file, "w") as f:
        f.write("x = 42\ny = 'hello'")
    
    try:
        results = await service.execute_query(
            file_path=test_file,
            language="python",
            query_string="(assignment) @assignment"
        )
        
        print(f"✅ Custom query executed successfully. Results: {len(results) if results else 0}")
        return True
        
    except Exception as e:
        print(f"❌ Custom query execution failed: {e}")
        return False
    finally:
        Path(test_file).unlink(missing_ok=True)

async def main():
    print("🔧 Testing async QueryService fix...")
    
    test1 = await test_basic_query()
    test2 = await test_custom_query()
    
    if test1 and test2:
        print("✅ All tests passed!")
        return 0
    else:
        print("❌ Some tests failed!")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
```

#### テスト実行
```bash
# 基本動作確認
python test_async_fix.py

# CLIコマンドテスト
python -m tree_sitter_analyzer query --file-path test_sample.py --query-key function
```

## 3. テストケースの追加要件

### 3.1 単体テスト

#### ファイル: `tests/test_async_query_service.py`
```python
import pytest
import asyncio
import tempfile
from pathlib import Path

from tree_sitter_analyzer.core.query_service import QueryService

class TestAsyncQueryService:
    """非同期QueryServiceのテスト"""
    
    @pytest.fixture
    def sample_python_file(self):
        """テスト用Pythonファイル"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("""
def test_function():
    return 42

class TestClass:
    def method(self):
        pass
""")
            yield f.name
        Path(f.name).unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_execute_query_is_async(self):
        """execute_queryが非同期メソッドであることを確認"""
        service = QueryService()
        
        # メソッドが非同期であることを確認
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def test(): pass")
            f.flush()
            
            result_coro = service.execute_query(
                file_path=f.name,
                language="python",
                query_key="function"
            )
            
            # コルーチンオブジェクトが返されることを確認
            assert asyncio.iscoroutine(result_coro)
            
            # 実際に実行
            result = await result_coro
            assert isinstance(result, list)
    
    @pytest.mark.asyncio
    async def test_query_key_execution(self, sample_python_file):
        """クエリキーによる実行テスト"""
        service = QueryService()
        
        results = await service.execute_query(
            file_path=sample_python_file,
            language="python",
            query_key="function"
        )
        
        assert results is not None
        assert len(results) >= 1
        assert results[0]["capture_name"] == "function"
    
    @pytest.mark.asyncio
    async def test_custom_query_execution(self, sample_python_file):
        """カスタムクエリによる実行テスト"""
        service = QueryService()
        
        results = await service.execute_query(
            file_path=sample_python_file,
            language="python",
            query_string="(function_definition) @func"
        )
        
        assert results is not None
        assert len(results) >= 1
    
    @pytest.mark.asyncio
    async def test_error_handling(self):
        """エラーハンドリングテスト"""
        service = QueryService()
        
        # 存在しないファイル
        with pytest.raises(Exception):
            await service.execute_query(
                file_path="nonexistent.py",
                language="python",
                query_key="function"
            )
        
        # 無効なクエリキー
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def test(): pass")
            f.flush()
            
            with pytest.raises(ValueError):
                await service.execute_query(
                    file_path=f.name,
                    language="python",
                    query_key="invalid_query"
                )
    
    @pytest.mark.asyncio
    async def test_concurrent_execution(self, sample_python_file):
        """並行実行テスト"""
        service = QueryService()
        
        # 複数のクエリを並行実行
        tasks = [
            service.execute_query(
                file_path=sample_python_file,
                language="python",
                query_key="function"
            )
            for _ in range(3)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # 全ての結果が正常に取得できることを確認
        for result in results:
            assert result is not None
            assert len(result) >= 1
```

### 3.2 統合テスト

#### ファイル: `tests/test_cli_async_integration.py`
```python
import pytest
import asyncio
import tempfile
from unittest.mock import Mock
from argparse import Namespace

from tree_sitter_analyzer.cli.commands.query_command import QueryCommand

class TestCLIAsyncIntegration:
    """CLI非同期統合テスト"""
    
    @pytest.fixture
    def mock_args(self):
        """モックの引数"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def test_function(): pass")
            f.flush()
            
            args = Namespace()
            args.file_path = f.name
            args.query_key = "function"
            args.filter = None
            args.output_format = "text"
            
            yield args
    
    @pytest.mark.asyncio
    async def test_query_command_execution(self, mock_args):
        """QueryCommandの非同期実行テスト"""
        command = QueryCommand(mock_args)
        
        # 非同期実行
        exit_code = await command.execute_async("python")
        
        # 正常終了を確認
        assert exit_code == 0
    
    @pytest.mark.asyncio
    async def test_query_command_error_handling(self):
        """QueryCommandのエラーハンドリングテスト"""
        args = Namespace()
        args.file_path = "nonexistent.py"
        args.query_key = "function"
        args.filter = None
        args.output_format = "text"
        
        command = QueryCommand(args)
        
        # エラー時の終了コードを確認
        exit_code = await command.execute_async("python")
        assert exit_code == 1
```

### 3.3 パフォーマンステスト

#### ファイル: `tests/test_async_performance.py`
```python
import pytest
import asyncio
import time
import tempfile
from pathlib import Path

from tree_sitter_analyzer.core.query_service import QueryService

class TestAsyncPerformance:
    """非同期処理のパフォーマンステスト"""
    
    @pytest.fixture
    def large_python_file(self):
        """大きなPythonファイル"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            # 100個の関数を持つファイルを生成
            for i in range(100):
                f.write(f"""
def function_{i}():
    '''Function {i}'''
    x = {i}
    return x * 2

class Class_{i}:
    def method_{i}(self):
        return {i}
""")
            yield f.name
        Path(f.name).unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_performance_baseline(self, large_python_file):
        """パフォーマンスベースラインテスト"""
        service = QueryService()
        
        start_time = time.time()
        
        results = await service.execute_query(
            file_path=large_python_file,
            language="python",
            query_key="function"
        )
        
        end_time = time.time()
        duration = end_time - start_time
        
        # 結果の確認
        assert results is not None
        assert len(results) >= 100  # 100個の関数が見つかることを確認
        
        # パフォーマンス要件: 5秒以内
        assert duration < 5.0, f"Query took too long: {duration:.2f}s"
        
        print(f"Performance: {duration:.2f}s for {len(results)} results")
    
    @pytest.mark.asyncio
    async def test_concurrent_performance(self, large_python_file):
        """並行処理のパフォーマンステスト"""
        service = QueryService()
        
        start_time = time.time()
        
        # 5つの並行クエリ
        tasks = [
            service.execute_query(
                file_path=large_python_file,
                language="python",
                query_key="function"
            )
            for _ in range(5)
        ]
        
        results = await asyncio.gather(*tasks)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # 全ての結果が正常
        for result in results:
            assert result is not None
            assert len(result) >= 100
        
        # 並行処理により、単一実行の5倍より速いことを確認
        # （理想的には2-3倍程度の時間で完了）
        assert duration < 15.0, f"Concurrent queries took too long: {duration:.2f}s"
        
        print(f"Concurrent performance: {duration:.2f}s for 5 parallel queries")
```

## 4. 品質保証プロセス

### 4.1 コードレビューチェックリスト

#### 非同期処理の確認
- [ ] `async def`キーワードが正しく使用されている
- [ ] `await`キーワードが適切に使用されている
- [ ] 非同期メソッドの戻り値の型注釈が正しい
- [ ] エラーハンドリングが非同期処理に対応している

#### 型安全性の確認
- [ ] 型注釈が完全に記述されている
- [ ] `mypy`による型チェックがパスする
- [ ] 戻り値の型が一貫している

#### テストカバレッジの確認
- [ ] 新しいコードのテストカバレッジが90%以上
- [ ] 非同期処理のテストが含まれている
- [ ] エラーケースのテストが含まれている

### 4.2 自動化テストの実行

#### テスト実行スクリプト
```bash
#!/bin/bash
# run_quality_tests.sh

echo "🔧 Running quality assurance tests..."

# 1. 型チェック
echo "📝 Running type checks..."
python -m mypy tree_sitter_analyzer/core/query_service.py
if [ $? -ne 0 ]; then
    echo "❌ Type check failed"
    exit 1
fi

# 2. 単体テスト
echo "🧪 Running unit tests..."
python -m pytest tests/test_async_query_service.py -v
if [ $? -ne 0 ]; then
    echo "❌ Unit tests failed"
    exit 1
fi

# 3. 統合テスト
echo "🔗 Running integration tests..."
python -m pytest tests/test_cli_async_integration.py -v
if [ $? -ne 0 ]; then
    echo "❌ Integration tests failed"
    exit 1
fi

# 4. パフォーマンステスト
echo "⚡ Running performance tests..."
python -m pytest tests/test_async_performance.py -v
if [ $? -ne 0 ]; then
    echo "❌ Performance tests failed"
    exit 1
fi

# 5. 回帰テスト
echo "🔄 Running regression tests..."
python -m pytest tests/ -k "not test_async" --tb=short
if [ $? -ne 0 ]; then
    echo "❌ Regression tests failed"
    exit 1
fi

# 6. カバレッジレポート
echo "📊 Generating coverage report..."
python -m pytest --cov=tree_sitter_analyzer.core.query_service --cov-report=html
if [ $? -ne 0 ]; then
    echo "❌ Coverage report generation failed"
    exit 1
fi

echo "✅ All quality assurance tests passed!"
```

### 4.3 継続的インテグレーション

#### GitHub Actions設定例
```yaml
# .github/workflows/async-fix-ci.yml
name: Async Fix CI

on:
  push:
    branches: [ hotfix/async-query-service-fix ]
  pull_request:
    branches: [ develop ]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.10, 3.11, 3.12]

    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v3
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -e .[dev]
    
    - name: Run type checks
      run: |
        python -m mypy tree_sitter_analyzer/core/query_service.py
    
    - name: Run async tests
      run: |
        python -m pytest tests/test_async_query_service.py -v
    
    - name: Run integration tests
      run: |
        python -m pytest tests/test_cli_async_integration.py -v
    
    - name: Run performance tests
      run: |
        python -m pytest tests/test_async_performance.py -v
    
    - name: Run regression tests
      run: |
        python -m pytest tests/ -k "not test_async" --tb=short
    
    - name: Generate coverage report
      run: |
        python -m pytest --cov=tree_sitter_analyzer.core.query_service --cov-report=xml
    
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
```

## 5. デプロイメント手順

### 5.1 プレリリース準備

#### バージョン更新
```bash
# pyproject.tomlのバージョン更新
sed -i 's/version = "1.8.0"/version = "1.8.1"/' pyproject.toml

# CHANGELOGの更新
echo "## [1.8.1] - $(date +%Y-%m-%d)
### Fixed
- Fixed async/await inconsistency in QueryService.execute_query()
- Improved error handling for async operations
" >> CHANGELOG.md
```

#### 最終テスト
```bash
# 全テストの実行
./run_quality_tests.sh

# パッケージビルドテスト
python -m build
python -m twine check dist/*
```

### 5.2 リリース手順

#### Git操作
```bash
# 変更のコミット
git add .
git commit -m "hotfix: Fix async/await inconsistency in QueryService

- Add async keyword to QueryService.execute_query()
- Implement async file reading with run_in_executor
- Add comprehensive async tests
- Update error handling for async operations

Fixes: Critical TypeError when using QueryCommand
Closes: #XXX"

# developブランチにマージ
git checkout develop
git merge hotfix/async-query-service-fix

# タグの作成
git tag -a v1.8.1 -m "Version 1.8.1: Async QueryService fix"

# リモートにプッシュ
git push origin develop
git push origin v1.8.1
```

#### パッケージリリース
```bash
# PyPIへのアップロード
python -m twine upload dist/*
```

## 6. 監視とフォローアップ

### 6.1 リリース後の監視

#### ログ監視
```python
# monitoring_script.py
import logging
import asyncio
from datetime import datetime

async def monitor_async_operations():
    """非同期処理の監視"""
    logger = logging.getLogger("tree_sitter_analyzer.core.query_service")
    
    # 非同期処理のメトリクス収集
    start_time = datetime.now()
    
    try:
        # サンプルクエリの実行
        from tree_sitter_analyzer.core.query_service import QueryService
        service = QueryService()
        
        result = await service.execute_query(
            "sample.py", 
            "python", 
            query_key="function"
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info(f"Monitoring: Async query completed in {duration:.2f}s")
        return True
        
    except Exception as e:
        logger.error(f"Monitoring: Async query failed: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(monitor_async_operations())
    print(f"Monitoring result: {'✅ Success' if success else '❌ Failed'}")
```

### 6.2 フィードバック収集

#### ユーザーフィードバックの収集
- GitHub Issuesでの報告監視
- パフォーマンス指標の追跡
- エラーレポートの分析

#### 改善計画
- 非同期処理の最適化
- 並行処理の導入検討
- リソース管理の改善

## 7. 緊急時対応

### 7.1 ロールバック手順

#### 即座のロールバック
```bash
# 前のバージョンに戻す
git checkout v1.8.0
git checkout -b emergency-rollback

# 緊急リリース
git tag -a v1.8.2 -m "Emergency rollback to v1.8.0"
git push origin emergency-rollback
git push origin v1.8.2
```

#### 部分的ロールバック
```bash
# 特定のファイルのみロールバック
git checkout v1.8.0 -- tree_sitter_analyzer/core/query_service.py
git commit -m "Partial rollback: QueryService to v1.8.0"
```

### 7.2 緊急時連絡体制

#### 対応チーム
- **技術リード**: 即座の技術判断
- **QAエンジニア**: 影響範囲の評価
- **DevOpsエンジニア**: デプロイメント対応

#### エスカレーション手順
1. **Level 1**: 自動監視による検出
2. **Level 2**: 開発チームによる初期対応
3. **Level 3**: 技術リードによる判断
4. **Level 4**: 緊急ロールバックの実行

---

**作成日**: 2025-10-14  
**対象バージョン**: v1.8.0 → v1.8.1  
**実装優先度**: Critical  
**推定作業時間**: 4-8時間