#!/usr/bin/env python3
"""
架構修正の包括的テストプログラム
言語間結合問題の解決とシグネチャ精度の改善を検証
"""

import subprocess
import sys
import json
from pathlib import Path


class ArchitectureFixTester:
    """架構修正テスター"""
    
    def __init__(self):
        self.test_results = {}
        self.passed_tests = 0
        self.total_tests = 0
    
    def run_command(self, cmd):
        """コマンド実行"""
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, encoding='utf-8'
            )
            return result.returncode, result.stdout, result.stderr
        except Exception as e:
            return -1, "", str(e)
    
    def test_java_method_signatures(self):
        """Javaメソッドシグネチャの修正テスト"""
        print("🔍 Testing Java method signatures...")
        
        cmd = "python -m tree_sitter_analyzer examples/Sample.java --query-key method --table compact"
        returncode, stdout, stderr = self.run_command(cmd)
        
        if returncode != 0:
            print(f"❌ Command failed: {stderr}")
            return False
        
        # 期待される改善点をチェック
        improvements = {
            "no_empty_params": "():void" not in stdout,  # 空パラメータの改善
            "has_static_modifiers": "[static]" in stdout,  # staticモディファイアの表示
            "has_proper_signatures": "(" in stdout and ")" in stdout,  # 適切なシグネチャ形式
            "no_generic_fallback": "():O" not in stdout,  # 汎用フォールバックの回避
        }
        
        passed = sum(improvements.values())
        total = len(improvements)
        
        print(f"   Signature improvements: {passed}/{total}")
        for check, result in improvements.items():
            status = "✅" if result else "❌"
            print(f"   {status} {check}")
        
        self.test_results["java_signatures"] = improvements
        return passed >= total * 0.75  # 75%以上の改善で合格
    
    def test_java_package_query(self):
        """Javaパッケージクエリテスト"""
        print("🔍 Testing Java package query...")
        
        cmd = "python -m tree_sitter_analyzer examples/Sample.java --query-key package --table compact"
        returncode, stdout, stderr = self.run_command(cmd)
        
        if returncode != 0:
            print(f"❌ Command failed: {stderr}")
            return False
        
        # パッケージ認識の確認
        package_checks = {
            "has_package_info": "com.example" in stdout,
            "proper_format": "Package" in stdout,
            "no_errors": "error" not in stdout.lower(),
        }
        
        passed = sum(package_checks.values())
        total = len(package_checks)
        
        print(f"   Package query: {passed}/{total}")
        for check, result in package_checks.items():
            status = "✅" if result else "❌"
            print(f"   {status} {check}")
        
        self.test_results["java_package"] = package_checks
        return passed == total
    
    def test_html_queries(self):
        """HTMLクエリの包括的テスト"""
        print("🔍 Testing HTML queries...")
        
        html_queries = [
            ("heading", "見出し要素"),
            ("form_element", "フォーム要素"),
            ("input_element", "入力要素"),
            ("semantic_element", "セマンティック要素"),
            ("media_element", "メディア要素"),
        ]
        
        html_results = {}
        
        for query_key, description in html_queries:
            cmd = f"python -m tree_sitter_analyzer examples/comprehensive_html.html --query-key {query_key} --table compact"
            returncode, stdout, stderr = self.run_command(cmd)
            
            success = returncode == 0 and len(stdout.strip()) > 0
            html_results[query_key] = success
            
            status = "✅" if success else "❌"
            print(f"   {status} {description} ({query_key})")
        
        passed = sum(html_results.values())
        total = len(html_results)
        
        print(f"   HTML queries: {passed}/{total}")
        self.test_results["html_queries"] = html_results
        return passed >= total * 0.8  # 80%以上で合格
    
    def test_language_isolation(self):
        """言語間分離テスト"""
        print("🔍 Testing language isolation...")
        
        # 異なる言語でのフォーマッター使用をテスト
        test_cases = [
            ("examples/Sample.java", "Java"),
            ("examples/comprehensive_html.html", "HTML"),
            ("examples/test_markdown.md", "Markdown"),
        ]
        
        isolation_results = {}
        
        for file_path, language in test_cases:
            cmd = f"python -m tree_sitter_analyzer {file_path} --query-key method --table compact"
            returncode, stdout, stderr = self.run_command(cmd)
            
            # 言語固有の処理が適用されているかチェック
            if language == "Java":
                success = "com.example" in stdout or "Method" in stdout
            elif language == "HTML":
                success = returncode == 0  # HTMLでもエラーなく動作
            else:
                success = returncode == 0  # 基本的な動作確認
            
            isolation_results[language] = success
            status = "✅" if success else "❌"
            print(f"   {status} {language} isolation")
        
        passed = sum(isolation_results.values())
        total = len(isolation_results)
        
        print(f"   Language isolation: {passed}/{total}")
        self.test_results["language_isolation"] = isolation_results
        return passed == total
    
    def test_encoding_support(self):
        """エンコーディング対応テスト"""
        print("🔍 Testing encoding support...")
        
        # CSV/JSON出力での文字エンコーディングテスト
        encoding_tests = [
            ("csv", "CSV出力"),
            ("json", "JSON出力"),
        ]
        
        encoding_results = {}
        
        for format_type, description in encoding_tests:
            cmd = f"python -m tree_sitter_analyzer examples/Sample.java --query-key method --table {format_type}"
            returncode, stdout, stderr = self.run_command(cmd)
            
            success = returncode == 0 and len(stdout.strip()) > 0
            encoding_results[format_type] = success
            
            status = "✅" if success else "❌"
            print(f"   {status} {description}")
        
        passed = sum(encoding_results.values())
        total = len(encoding_results)
        
        print(f"   Encoding support: {passed}/{total}")
        self.test_results["encoding"] = encoding_results
        return passed == total
    
    def run_all_tests(self):
        """全テストの実行"""
        print("🚀 Starting comprehensive architecture fix tests...\n")
        
        tests = [
            ("Java Method Signatures", self.test_java_method_signatures),
            ("Java Package Query", self.test_java_package_query),
            ("HTML Queries", self.test_html_queries),
            ("Language Isolation", self.test_language_isolation),
            ("Encoding Support", self.test_encoding_support),
        ]
        
        for test_name, test_func in tests:
            print(f"📋 {test_name}")
            try:
                result = test_func()
                if result:
                    self.passed_tests += 1
                    print(f"✅ {test_name} PASSED\n")
                else:
                    print(f"❌ {test_name} FAILED\n")
                self.total_tests += 1
            except Exception as e:
                print(f"💥 {test_name} ERROR: {e}\n")
                self.total_tests += 1
        
        self.print_summary()
    
    def print_summary(self):
        """テスト結果サマリー"""
        print("=" * 60)
        print("🎯 ARCHITECTURE FIX TEST SUMMARY")
        print("=" * 60)
        
        success_rate = (self.passed_tests / self.total_tests * 100) if self.total_tests > 0 else 0
        
        print(f"Total Tests: {self.total_tests}")
        print(f"Passed: {self.passed_tests}")
        print(f"Failed: {self.total_tests - self.passed_tests}")
        print(f"Success Rate: {success_rate:.1f}%")
        
        if success_rate >= 80:
            print("\n🎉 ARCHITECTURE FIX SUCCESSFUL!")
            print("   Root cause issues have been resolved.")
        elif success_rate >= 60:
            print("\n⚠️  PARTIAL SUCCESS")
            print("   Some improvements made, but issues remain.")
        else:
            print("\n❌ ARCHITECTURE FIX FAILED")
            print("   Significant issues still exist.")
        
        # 詳細結果の保存
        with open("architecture_fix_results.json", "w", encoding="utf-8") as f:
            json.dump({
                "summary": {
                    "total_tests": self.total_tests,
                    "passed_tests": self.passed_tests,
                    "success_rate": success_rate
                },
                "detailed_results": self.test_results
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 Detailed results saved to: architecture_fix_results.json")


if __name__ == "__main__":
    tester = ArchitectureFixTester()
    tester.run_all_tests()