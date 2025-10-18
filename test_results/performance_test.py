#!/usr/bin/env python3
"""
INT-LOG-03: パフォーマンス影響テスト
ログ機能を有効にした場合と無効にした場合の実行時間を比較する
"""

import time
import os
import sys
from pathlib import Path
from tree_sitter_analyzer.api import analyze_file

def clear_environment():
    """環境変数をクリア"""
    env_vars = [
        'TREE_SITTER_ANALYZER_ENABLE_FILE_LOG',
        'TREE_SITTER_ANALYZER_LOG_DIR', 
        'TREE_SITTER_ANALYZER_FILE_LOG_LEVEL',
        'LOG_LEVEL'
    ]
    for var in env_vars:
        if var in os.environ:
            del os.environ[var]

def setup_logging_environment():
    """ログ機能を有効にする環境変数を設定"""
    os.environ['TREE_SITTER_ANALYZER_ENABLE_FILE_LOG'] = 'true'
    os.environ['TREE_SITTER_ANALYZER_LOG_DIR'] = './test_logs_performance'
    os.environ['TREE_SITTER_ANALYZER_FILE_LOG_LEVEL'] = 'INFO'

def run_performance_test(test_name, iterations=10):
    """パフォーマンステストを実行"""
    print(f"\n=== {test_name} ===")
    
    # テスト対象ファイル
    test_files = [
        "examples/BigService.java",
        "examples/Sample.java",
        "examples/MultiClass.java"
    ]
    
    # 存在するファイルのみを使用
    available_files = []
    for file_path in test_files:
        if Path(file_path).exists():
            available_files.append(file_path)
    
    if not available_files:
        print("テスト対象ファイルが見つかりません")
        return None
    
    print(f"テスト対象ファイル: {available_files}")
    print(f"反復回数: {iterations}")
    
    total_time = 0
    successful_runs = 0
    
    for i in range(iterations):
        iteration_start = time.time()
        
        try:
            for file_path in available_files:
                result = analyze_file(file_path)
                # 結果が正常に取得できたかを簡単にチェック
                if not result or 'metadata' not in result:
                    print(f"警告: {file_path} の解析結果が不完全です")
            
            iteration_end = time.time()
            iteration_time = iteration_end - iteration_start
            total_time += iteration_time
            successful_runs += 1
            
            print(f"反復 {i+1}/{iterations}: {iteration_time:.3f}秒")
            
        except Exception as e:
            print(f"エラー (反復 {i+1}): {e}")
    
    if successful_runs > 0:
        average_time = total_time / successful_runs
        print(f"成功した実行: {successful_runs}/{iterations}")
        print(f"総実行時間: {total_time:.3f}秒")
        print(f"平均実行時間: {average_time:.3f}秒")
        return {
            'total_time': total_time,
            'average_time': average_time,
            'successful_runs': successful_runs,
            'iterations': iterations,
            'files_processed': len(available_files)
        }
    else:
        print("すべての実行が失敗しました")
        return None

def main():
    print("INT-LOG-03: パフォーマンス影響テスト開始")
    
    # Case 1: ログ機能無効
    print("\n" + "="*50)
    print("Case 1: ログ機能無効")
    clear_environment()
    case1_result = run_performance_test("ログ機能無効", iterations=5)
    
    # Case 2: ログ機能有効
    print("\n" + "="*50)
    print("Case 2: ログ機能有効")
    setup_logging_environment()
    case2_result = run_performance_test("ログ機能有効", iterations=5)
    
    # 結果比較
    print("\n" + "="*50)
    print("結果比較")
    
    if case1_result and case2_result:
        case1_avg = case1_result['average_time']
        case2_avg = case2_result['average_time']
        
        if case1_avg > 0:
            overhead_ratio = (case2_avg - case1_avg) / case1_avg * 100
            performance_ratio = case2_avg / case1_avg
            
            print(f"ログ無効時平均: {case1_avg:.3f}秒")
            print(f"ログ有効時平均: {case2_avg:.3f}秒")
            print(f"オーバーヘッド: {overhead_ratio:+.1f}%")
            print(f"実行時間比: {performance_ratio:.2f}倍")
            
            # 判定基準
            if performance_ratio <= 2.0:  # 2倍以下なら許容範囲
                print("✅ 判定: パフォーマンス影響は許容範囲内")
                status = "PASS"
            else:
                print("❌ 判定: パフォーマンス影響が大きすぎます")
                status = "FAIL"
            
            return {
                'case1': case1_result,
                'case2': case2_result,
                'overhead_percentage': overhead_ratio,
                'performance_ratio': performance_ratio,
                'status': status
            }
        else:
            print("❌ Case 1の実行時間が0のため比較できません")
            return None
    else:
        print("❌ テストの実行に失敗しました")
        return None

if __name__ == "__main__":
    result = main()
    if result:
        print(f"\n最終判定: {result['status']}")
    else:
        print("\n最終判定: テスト失敗")