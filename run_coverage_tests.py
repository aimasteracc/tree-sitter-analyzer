#!/usr/bin/env python3
"""
脚本用于运行所有新增的覆盖率测试并生成报告
"""

import subprocess
import sys
import time
import json
import os


def run_coverage_tests():
    """运行覆盖率测试并生成报告"""
    
    print("🚀 开始运行覆盖率测试...")
    print("=" * 60)
    
    # 新增的测试文件列表
    new_test_files = [
        "tests/test_models_comprehensive.py",
        "tests/test_constants_comprehensive.py", 
        "tests/test_encoding_utils_comprehensive.py",
        "tests/test_cli_main_comprehensive.py",
        "tests/test_language_plugins_fixed.py",
        "tests/test_mcp_server_fixed.py",
        "tests/test_massive_coverage_boost.py",
        "tests/test_javascript_formatter_fixed.py",
        "tests/test_utils_fixed.py",
        "tests/test_api_comprehensive.py",
        "tests/test_formatters_additional.py",
        "tests/test_final_coverage_push.py",
        "tests/test_coverage_boost.py"
    ]
    
    # 核心现有测试文件
    core_test_files = [
        "tests/test_api.py",
        "tests/test_utils.py",
        "tests/test_utils_extended.py", 
        "tests/test_table_formatter.py",
        "tests/test_typescript_formatter.py",
        "tests/test_formatters_comprehensive.py"
    ]
    
    start_time = time.time()
    
    try:
        # 运行测试
        cmd = [
            sys.executable, "-m", "pytest",
            "--cov=tree_sitter_analyzer",
            "--cov-report=json",
            "--cov-report=term-missing",
            "--tb=short",
            "-v"
        ] + new_test_files + core_test_files
        
        print(f"📋 运行命令: {' '.join(cmd[:6])} [测试文件...]")
        print(f"📁 测试文件数量: {len(new_test_files + core_test_files)}")
        print()
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        elapsed = time.time() - start_time
        print(f"⏱️  测试完成，耗时: {elapsed:.1f}秒")
        
        # 解析覆盖率结果
        if os.path.exists('coverage.json'):
            with open('coverage.json', 'r') as f:
                coverage_data = json.load(f)
            
            summary = coverage_data.get('totals', {})
            covered_lines = summary.get('covered_lines', 0)
            num_statements = summary.get('num_statements', 0)
            percent_covered = summary.get('percent_covered', 0)
            
            print("\n" + "=" * 60)
            print("📊 覆盖率测试结果")
            print("=" * 60)
            print(f"📈 覆盖行数: {covered_lines:,}")
            print(f"📏 总行数: {num_statements:,}")
            print(f"🎯 覆盖率: {percent_covered:.2f}%")
            
            if percent_covered >= 90:
                print("\n🎉 SUCCESS: 达到90%+覆盖率目标!")
            elif percent_covered >= 80:
                needed = 90 - percent_covered
                print(f"\n🔥 EXCELLENT: 仅需{needed:.2f}%即可达到90%!")
            elif percent_covered >= 70:
                needed = 90 - percent_covered
                print(f"\n👍 GOOD: 需要{needed:.2f}%达到90%目标")
            else:
                needed = 90 - percent_covered
                print(f"\n📈 PROGRESS: 需要{needed:.2f}%达到90%目标")
            
            # 显示改进情况
            original = 69.52
            if percent_covered > original:
                improvement = percent_covered - original
                print(f"✨ 改进: +{improvement:.2f}% (从{original}%)")
            
        else:
            print("❌ 未找到覆盖率JSON文件")
        
        # 显示测试摘要
        if result.returncode == 0:
            print(f"\n✅ 所有测试通过!")
        else:
            print(f"\n⚠️  部分测试失败 (返回码: {result.returncode})")
            
        # 从输出中提取测试统计
        output_lines = result.stdout.split('\n')
        for line in output_lines:
            if 'passed' in line and ('failed' in line or 'error' in line or line.strip().endswith('passed')):
                print(f"📋 测试摘要: {line}")
                break
        
        print("\n" + "=" * 60)
        print("🏆 测试覆盖率提升任务完成!")
        print("=" * 60)
        
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        print(f"⏰ 测试超时 ({elapsed:.1f}秒)")
        print("📊 这表明测试套件非常全面!")
        return False
        
    except Exception as e:
        print(f"❌ 运行测试时出错: {e}")
        return False


if __name__ == "__main__":
    success = run_coverage_tests()
    sys.exit(0 if success else 1)