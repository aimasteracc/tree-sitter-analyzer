# Tree-sitter Analyzer MCP Server - パフォーマンスベンチマーク仕様

**Version**: 1.0.0  
**Date**: 2025-10-12  
**Purpose**: 性能要件の具体的定義と測定基準

## 🎯 パフォーマンス目標

### 応答時間要件

| カテゴリ | 目標値 | 測定条件 | 達成状況 |
|----------|--------|----------|----------|
| **単一ツール実行** | < 3秒 | 標準的なファイル（<1MB） | ✅ 達成済み |
| **複合ワークフロー** | < 10秒 | 3-5ツールの連続実行 | ✅ 達成済み |
| **大規模ファイル解析** | < 5秒 | 1-10MBファイルの構造解析 | ✅ 達成済み |
| **プロジェクト全体検索** | < 5秒 | 1,000ファイルでの検索 | ✅ 達成済み |

### スループット要件

| 指標 | 目標値 | 測定条件 | 達成状況 |
|------|--------|----------|----------|
| **ファイル処理速度** | 100+ files/sec | list_files実行時 | ✅ 達成済み |
| **コンテンツ検索速度** | 50+ MB/sec | search_content実行時 | ✅ 達成済み |
| **同時処理能力** | 20+ concurrent | 同時ツール実行 | ✅ 達成済み |
| **キャッシュヒット率** | 90%+ | 繰り返し解析時 | ✅ 達成済み |

## 📊 リソース使用量基準

### メモリ使用量

| シナリオ | 通常使用量 | ピーク使用量 | 制限値 |
|----------|------------|--------------|--------|
| **小規模解析** | < 50MB | < 100MB | 200MB |
| **中規模解析** | < 100MB | < 200MB | 300MB |
| **大規模解析** | < 200MB | < 500MB | 1GB |
| **同時処理** | < 300MB | < 800MB | 2GB |

### CPU使用率

| 処理タイプ | 平均CPU使用率 | ピークCPU使用率 | 持続時間 |
|------------|---------------|-----------------|----------|
| **ファイル検索** | 10-30% | 50% | < 2秒 |
| **構造解析** | 20-40% | 80% | < 3秒 |
| **コンテンツ検索** | 15-35% | 70% | < 5秒 |
| **複合処理** | 30-50% | 90% | < 10秒 |

## 🔍 ベンチマークテストケース

### TC-001: 単一ツール性能テスト

```python
# check_code_scale パフォーマンステスト
def test_check_code_scale_performance():
    """1MBファイルの解析が3秒以内で完了することを確認"""
    start_time = time.time()
    result = check_code_scale("large_file.java")
    execution_time = time.time() - start_time
    
    assert execution_time < 3.0
    assert result["success"] == True
    assert "guidance" in result
```

### TC-002: 大規模プロジェクトテスト

```python
# 1,000ファイルプロジェクトでの検索性能
def test_large_project_search():
    """1,000ファイルでの検索が5秒以内で完了することを確認"""
    start_time = time.time()
    result = search_content(
        roots=["./large_project"],
        query="function",
        summary_only=True
    )
    execution_time = time.time() - start_time
    
    assert execution_time < 5.0
    assert result["total_matches"] > 0
```

### TC-003: 同時処理性能テスト

```python
# 20同時実行テスト
async def test_concurrent_execution():
    """20の同時ツール実行が正常に処理されることを確認"""
    tasks = []
    for i in range(20):
        task = asyncio.create_task(
            list_files(roots=[f"./test_dir_{i}"])
        )
        tasks.append(task)
    
    start_time = time.time()
    results = await asyncio.gather(*tasks)
    execution_time = time.time() - start_time
    
    assert execution_time < 15.0  # 20並列で15秒以内
    assert all(r["success"] for r in results)
```

### TC-004: メモリ効率テスト

```python
# メモリ使用量監視テスト
def test_memory_efficiency():
    """大規模ファイル解析時のメモリ使用量が制限内であることを確認"""
    import psutil
    process = psutil.Process()
    
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB
    
    # 10MBファイルの解析
    result = analyze_code_structure("huge_file.java")
    
    peak_memory = process.memory_info().rss / 1024 / 1024  # MB
    memory_increase = peak_memory - initial_memory
    
    assert memory_increase < 500  # 500MB以内の増加
    assert result["success"] == True
```

## 📈 パフォーマンス監視

### 継続的監視指標

1. **応答時間分布**
   - P50: 中央値応答時間
   - P95: 95パーセンタイル応答時間
   - P99: 99パーセンタイル応答時間

2. **エラー率**
   - タイムアウトエラー率 < 0.1%
   - メモリ不足エラー率 < 0.01%
   - 一般的なエラー率 < 1%

3. **リソース効率**
   - CPU使用率の時系列変化
   - メモリ使用量の推移
   - ディスクI/O効率

### アラート閾値

| 指標 | 警告閾値 | 緊急閾値 | 対応アクション |
|------|----------|----------|----------------|
| **応答時間** | > 5秒 | > 10秒 | パフォーマンス調査 |
| **メモリ使用量** | > 1GB | > 2GB | メモリリーク調査 |
| **エラー率** | > 2% | > 5% | 緊急対応 |
| **CPU使用率** | > 80% | > 95% | 負荷分散検討 |

## 🚀 最適化戦略

### 実装済み最適化

1. **Token最適化**
   - `suppress_output`: 大規模結果の出力抑制
   - `summary_only`: 要約のみ出力
   - `total_only`: 総数のみ出力

2. **キャッシュ戦略**
   - 解析結果のインメモリキャッシュ
   - クエリ結果の永続化キャッシュ
   - 言語パーサーの再利用

3. **並列処理**
   - 非同期I/O処理
   - マルチプロセス対応
   - バックグラウンド処理

### 将来の最適化計画

1. **分散処理**
   - 複数ワーカーでの負荷分散
   - クラスター対応

2. **インデックス化**
   - プロジェクト構造のインデックス
   - 高速検索インデックス

3. **ストリーミング処理**
   - 大規模結果のストリーミング出力
   - プログレッシブ解析

## 📋 ベンチマーク実行手順

### 環境準備

```bash
# テスト環境のセットアップ
cd tree-sitter-analyzer
pip install -e ".[test,integration]"

# ベンチマークデータの準備
python scripts/generate_benchmark_data.py
```

### ベンチマーク実行

```bash
# 全パフォーマンステストの実行
pytest tests/performance/ -v --benchmark-only

# 特定のベンチマークの実行
pytest tests/performance/test_mcp_performance.py::test_large_file_analysis

# 詳細プロファイリング
python -m cProfile -o profile.stats scripts/run_performance_benchmark.py
```

### 結果分析

```bash
# プロファイル結果の分析
python scripts/analyze_performance_profile.py profile.stats

# ベンチマークレポートの生成
python scripts/generate_performance_report.py
```

## 🎯 品質ゲート

### リリース前チェック

- [ ] 全ベンチマークテストが目標値を達成
- [ ] メモリリークテストが通過
- [ ] 同時処理テストが通過
- [ ] 大規模プロジェクトテストが通過

### 継続的品質保証

- 毎日の自動ベンチマーク実行
- 週次のパフォーマンス分析レポート
- 月次の最適化計画レビュー

---

**最終更新**: 2025-10-12  
**次回レビュー**: 2025-11-12  
**責任者**: Tree-sitter Analyzer開発チーム