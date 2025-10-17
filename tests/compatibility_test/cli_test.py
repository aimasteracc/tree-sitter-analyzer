#!/usr/bin/env python3
"""
CLI互換性テストスクリプト

このスクリプトは、tree-sitter-analyzerのCLIコマンドの互換性をテストします。
README.mdに記載された全CLIコマンドを実行してテストを行います。

対象コマンド:
- 基本コマンド（--summary, --structure, --advanced）
- テーブル出力（--table=full, --table=compact）
- 部分読み取り（--partial-read）
- クエリ実行（--query-key）
- 情報表示（--help, --list-queries, --show-supported-languages）
"""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from colored_logger import get_logger
from test_case_loader import TestCaseLoader

logger = get_logger(__name__)

class CLITestRunner:
    """CLIテスト実行クラス"""
    
    def __init__(self, version: str = "current", test_cases_file: Optional[str] = None):
        self.version = version
        self.project_root = Path(__file__).parent.parent.parent
        self.test_dir = Path(__file__).parent
        self.result_dir = self.test_dir / "result" / "cli" / f"v-{version}"
        
        # 結果ディレクトリを作成
        self.result_dir.mkdir(parents=True, exist_ok=True)
        
        # テストケースローダーを初期化
        if test_cases_file is None:
            test_cases_file = self.test_dir / "cli_test_cases.json"
        
        try:
            self.test_loader = TestCaseLoader(test_cases_file)
            logger.success(f"テストケース設定を読み込みました: {test_cases_file}")
        except Exception as e:
            logger.error(f"テストケース設定の読み込みに失敗: {e}")
            raise
        
    def resolve_file_paths_in_args(self, args: List[str]) -> List[str]:
        """引数内のファイルパスを絶対パスに解決"""
        resolved_args = []
        
        for arg in args:
            # ファイルパスらしき引数を検出（拡張子がある、またはexamplesで始まる）
            if ('.' in arg and not arg.startswith('-')) or arg.startswith('examples/'):
                path = Path(arg)
                if not path.is_absolute():
                    # プロジェクトルートからの相対パスとして解決
                    absolute_path = self.project_root / arg
                    if absolute_path.exists():
                        resolved_args.append(str(absolute_path))
                    else:
                        # ファイルが存在しない場合は元の引数を使用（エラーテスト用）
                        resolved_args.append(arg)
                else:
                    resolved_args.append(arg)
            else:
                resolved_args.append(arg)
        
        return resolved_args

    def run_cli_command(self, args: List[str], timeout: int = 30) -> Tuple[int, str, str]:
        """CLIコマンドを実行"""
        try:
            # ファイルパスを解決
            resolved_args = self.resolve_file_paths_in_args(args)
            
            # uvを使用してコマンドを実行
            cmd = ["uv", "run", "python", "-m", "tree_sitter_analyzer"] + resolved_args
            
            logger.debug(f"実行コマンド: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding='utf-8',
                errors='replace'
            )
            
            return result.returncode, result.stdout, result.stderr
            
        except subprocess.TimeoutExpired:
            return -1, "", "タイムアウトエラー"
        except UnicodeDecodeError as e:
            logger.error(f"文字エンコーディングエラー: {e}")
            return -1, "", f"文字エンコーディングエラー: {e}"
        except Exception as e:
            return -1, "", str(e)
    
    def normalize_cli_output(self, output: str) -> str:
        """CLI出力を正規化"""
        lines = output.split('\n')
        normalized_lines = []
        
        for line in lines:
            # タイムスタンプや実行時間を正規化
            if 'elapsed' in line.lower() or 'time' in line.lower():
                continue
            if 'timestamp' in line.lower():
                continue
            
            # 絶対パスを相対パスに変換
            if self.project_root.as_posix() in line:
                line = line.replace(str(self.project_root), "PROJECT_ROOT")
            
            normalized_lines.append(line)
        
        return '\n'.join(normalized_lines)
    
    def parse_json_output(self, output: str) -> Optional[Dict[str, Any]]:
        """JSON出力をパース"""
        if not output or not output.strip():
            return None
        try:
            # 複数行のJSONを処理
            lines = output.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('{') and line.endswith('}'):
                    return json.loads(line)
            
            # 全体がJSONの場合
            if output.strip().startswith('{') and output.strip().endswith('}'):
                return json.loads(output.strip())
            return None
        except json.JSONDecodeError as e:
            logger.debug(f"JSON解析エラー: {e}")
            return None
        except Exception as e:
            logger.debug(f"JSON解析で予期しないエラー: {e}")
            return None
    
    def get_test_cases(self,
                      categories: Optional[List[str]] = None,
                      test_ids: Optional[List[str]] = None,
                      include_errors: bool = True) -> List[Dict[str, Any]]:
        """外部設定からテストケースを取得"""
        return self.test_loader.filter_test_cases(categories, test_ids, include_errors)
    
    def run_test_case(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """単一のテストケースを実行"""
        test_id = test_case["test_id"]
        args = test_case["args"]
        expected_success = test_case["expected_success"]
        timeout = test_case.get("timeout", 30)
        
        logger.debug(f"CLIテスト実行中: {test_id} - {test_case['description']}")
        
        start_time = time.time()
        returncode, stdout, stderr = self.run_cli_command(args, timeout)
        end_time = time.time()
        
        # 成功判定
        success = (returncode == 0) == expected_success
        
        # 出力を正規化
        normalized_stdout = self.normalize_cli_output(stdout)
        normalized_stderr = self.normalize_cli_output(stderr)
        
        # JSON出力をパース（可能な場合）
        parsed_json = self.parse_json_output(stdout)
        
        # テスト結果を構築
        test_result = {
            "test_id": test_id,
            "description": test_case["description"],
            "args": args,
            "returncode": returncode,
            "stdout": normalized_stdout,
            "stderr": normalized_stderr,
            "parsed_json": parsed_json,
            "execution_time": end_time - start_time,
            "success": success,
            "expected_success": expected_success,
            "category": test_case.get("category", "unknown"),
            "timestamp": datetime.now().isoformat()
        }
        
        # 結果をログ出力
        logger.test_result(test_id, success, test_case["description"])
        
        if not success:
            if returncode != 0 and expected_success:
                logger.warning(f"  予期しないエラー: 終了コード {returncode}")
                if stderr:
                    logger.warning(f"  エラー出力: {stderr[:200]}...")
            elif returncode == 0 and not expected_success:
                logger.warning(f"  期待されたエラーが発生しませんでした")
        
        # 個別結果ファイルを保存
        result_file = self.result_dir / f"{test_id}.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(test_result, f, indent=2, ensure_ascii=False)
        
        return test_result
    
    def run_all_tests(self,
                     categories: Optional[List[str]] = None,
                     test_ids: Optional[List[str]] = None,
                     include_errors: bool = True) -> Dict[str, Any]:
        """全CLIテストケースを実行"""
        
        logger.section_header(f"CLI互換性テスト (バージョン: {self.version})")
        
        # テストケースを取得
        test_cases = self.get_test_cases(categories, test_ids, include_errors)
        
        if not test_cases:
            logger.warning("実行するテストケースがありません")
            return {
                "version": self.version,
                "timestamp": datetime.now().isoformat(),
                "total_tests": 0,
                "successful_tests": 0,
                "failed_tests": 0,
                "success_rate": 0,
                "results": []
            }
        
        logger.info(f"実行予定テストケース: {len(test_cases)}個")
        
        # カテゴリ別集計
        category_counts = {}
        for case in test_cases:
            category = case.get("category", "unknown")
            category_counts[category] = category_counts.get(category, 0) + 1
        
        logger.info("カテゴリ別テストケース:")
        for category, count in category_counts.items():
            logger.info(f"  {category}: {count}個")
        
        results = []
        
        # 各テストケースを実行
        for i, test_case in enumerate(test_cases, 1):
            try:
                # 進捗表示
                logger.progress(f"実行中: {test_case['test_id']}", i, len(test_cases))
                
                result = self.run_test_case(test_case)
                results.append(result)
                
            except Exception as e:
                logger.error(f"テストケース {test_case['test_id']} でエラー: {e}")
                results.append({
                    "test_id": test_case["test_id"],
                    "description": test_case["description"],
                    "error": str(e),
                    "success": False,
                    "category": test_case.get("category", "unknown")
                })
        
        logger.progress_complete("全テストケース実行完了")
        
        # サマリーを作成
        total_tests = len(results)
        successful_tests = sum(1 for r in results if r.get("success", False))
        failed_tests = total_tests - successful_tests
        
        # カテゴリ別結果集計
        category_results = {}
        for result in results:
            category = result.get("category", "unknown")
            if category not in category_results:
                category_results[category] = {"total": 0, "success": 0, "failed": 0}
            
            category_results[category]["total"] += 1
            if result.get("success", False):
                category_results[category]["success"] += 1
            else:
                category_results[category]["failed"] += 1
        
        summary = {
            "version": self.version,
            "timestamp": datetime.now().isoformat(),
            "total_tests": total_tests,
            "successful_tests": successful_tests,
            "failed_tests": failed_tests,
            "success_rate": successful_tests / total_tests if total_tests > 0 else 0,
            "category_results": category_results,
            "test_loader_summary": self.test_loader.get_test_summary(),
            "results": results
        }
        
        # サマリーファイルを保存
        summary_file = self.result_dir / "cli_test_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        # 結果サマリーを表示
        logger.summary(total_tests, successful_tests, failed_tests)
        
        # カテゴリ別結果を表示
        logger.info("\nカテゴリ別結果:")
        for category, stats in category_results.items():
            success_rate = (stats["success"] / stats["total"]) * 100 if stats["total"] > 0 else 0
            logger.info(f"  {category}: {stats['success']}/{stats['total']} ({success_rate:.1f}%)")
        
        logger.success(f"結果ファイル保存: {summary_file}")
        
        return summary

def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="CLI互換性テスト - 色付きログと外部設定対応版",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 基本実行
  python cli_test.py
  
  # 特定カテゴリのみ実行
  python cli_test.py --categories basic table
  
  # 特定テストIDのみ実行
  python cli_test.py --test-ids CLI-001-summary CLI-002-structure
  
  # エラーテストを除外
  python cli_test.py --no-errors
  
  # カスタム設定ファイル使用
  python cli_test.py --test-cases custom_test_cases.json
        """
    )
    
    parser.add_argument("--version", default="current", help="テスト対象バージョン")
    parser.add_argument("--verbose", action="store_true", help="詳細ログ出力")
    parser.add_argument("--test-cases", help="テストケース設定ファイル")
    parser.add_argument("--categories", nargs="+", help="実行するカテゴリ")
    parser.add_argument("--test-ids", nargs="+", help="実行するテストID")
    parser.add_argument("--no-errors", action="store_true", help="エラーテストを除外")
    parser.add_argument("--list-categories", action="store_true", help="利用可能なカテゴリを表示")
    parser.add_argument("--list-tests", action="store_true", help="利用可能なテストケースを表示")
    
    args = parser.parse_args()
    
    # ログレベル設定
    if args.verbose:
        import logging
        logger.logger.setLevel(logging.DEBUG)
    
    try:
        runner = CLITestRunner(args.version, args.test_cases)
        
        # カテゴリ一覧表示
        if args.list_categories:
            categories = runner.test_loader.get_categories()
            logger.section_header("利用可能なカテゴリ")
            for category, info in categories.items():
                logger.info(f"{category}: {info.get('description', 'No description')}")
            return
        
        # テスト一覧表示
        if args.list_tests:
            test_cases = runner.get_test_cases()
            logger.section_header("利用可能なテストケース")
            for case in test_cases:
                logger.info(f"{case['test_id']}: {case['description']} (カテゴリ: {case.get('category', 'unknown')})")
            return
        
        # テスト実行
        result = runner.run_all_tests(
            categories=args.categories,
            test_ids=args.test_ids,
            include_errors=not args.no_errors
        )
        
        # 終了判定
        success_rate = result['success_rate']
        if success_rate >= 0.9:
            logger.success(f"テスト完了: 成功率 {success_rate:.1%} - 優秀")
            sys.exit(0)
        elif success_rate >= 0.8:
            logger.warning(f"テスト完了: 成功率 {success_rate:.1%} - 良好")
            sys.exit(0)
        elif success_rate >= 0.7:
            logger.warning(f"テスト完了: 成功率 {success_rate:.1%} - 許容範囲")
            sys.exit(0)
        else:
            logger.error(f"テスト完了: 成功率 {success_rate:.1%} - 改善が必要")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.warning("テストが中断されました")
        sys.exit(130)
    except Exception as e:
        logger.error(f"テスト実行エラー: {e}")
        if args.verbose:
            import traceback
            logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()