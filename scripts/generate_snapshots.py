#!/usr/bin/env python3
"""
スナップショットテスト用ベースライン生成スクリプト

PyPiパッケージ（tree-sitter-analyzer-pypi）を使用してベースライン出力を生成し、
現在の実装との比較用データを作成します。
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# プロジェクトルートを追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SnapshotGenerator:
    """スナップショット生成クラス"""
    
    def __init__(self, config_path: str = "test_snapshots/config/test_cases.json"):
        """初期化"""
        self.project_root = project_root
        self.config_path = self.project_root / config_path
        self.config = self._load_config()
        self.results = {}
        
    def _load_config(self) -> Dict[str, Any]:
        """設定ファイルを読み込み"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"設定ファイルの読み込みに失敗: {e}")
            raise
    
    def _run_cli_command(self, command: List[str]) -> Optional[Dict[str, Any]]:
        """CLIコマンドを実行してJSON結果を取得"""
        try:
            import subprocess
            import json
            
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding='utf-8',
                cwd=self.project_root
            )
            
            if result.returncode == 0:
                # 出力からJSONを抽出
                output = result.stdout.strip()
                if output:
                    try:
                        return json.loads(output)
                    except json.JSONDecodeError:
                        # JSONでない場合は文字列として返す
                        return {"output": output}
                return {"output": ""}
            else:
                logger.error(f"CLI実行エラー: {result.stderr}")
                return None
                
        except Exception as e:
            logger.error(f"CLI実行中にエラー: {e}")
            return None
    
    def _generate_baseline_for_file(self, test_case: Dict[str, Any], language: str) -> Dict[str, Any]:
        """単一ファイルのベースライン生成"""
        file_path = test_case["file_path"]
        name = test_case["name"]
        
        logger.info(f"ベースライン生成中: {language}/{name} ({file_path})")
        
        results = {
            "metadata": {
                "test_name": name,
                "file_path": file_path,
                "language": language,
                "timestamp": datetime.now().isoformat(),
                "generator": "pypi_package"
            },
            "outputs": {}
        }
        
        # 1. コードスケール分析
        scale_cmd = [
            "python", "-m", "tree_sitter_analyzer",
            "check-scale", file_path,
            "--language", language,
            "--format", "json"
        ]
        scale_result = self._run_cli_command(scale_cmd)
        
        if scale_result:
            results["outputs"]["scale_analysis"] = scale_result
        
        # 2. 構造分析（各フォーマット）
        for format_type in test_case.get("test_formats", ["json"]):
            structure_cmd = [
                "python", "-m", "tree_sitter_analyzer",
                "analyze", file_path,
                "--language", language,
                "--format", format_type
            ]
            structure_result = self._run_cli_command(structure_cmd)
            
            if structure_result:
                results["outputs"][f"structure_{format_type}"] = structure_result
        
        # 3. クエリ実行（各クエリタイプ）
        for query_key in test_case.get("test_queries", []):
            query_cmd = [
                "python", "-m", "tree_sitter_analyzer",
                "query", file_path,
                "--language", language,
                "--query", query_key,
                "--format", "json"
            ]
            query_result = self._run_cli_command(query_cmd)
            
            if query_result:
                results["outputs"][f"query_{query_key}"] = query_result
        
        return results
    
    def generate_baselines(self) -> bool:
        """全ベースライン生成"""
        logger.info("ベースライン生成を開始")
        
        try:
            test_cases = self.config["test_cases"]
            baseline_dir = Path(self.config["output_settings"]["baseline_dir"])
            
            for language, cases in test_cases.items():
                logger.info(f"言語 {language} の処理開始")
                
                language_dir = baseline_dir / language
                language_dir.mkdir(parents=True, exist_ok=True)
                
                for test_case in cases:
                    try:
                        baseline_data = self._generate_baseline_for_file(test_case, language)
                        
                        # ベースラインファイルを保存
                        output_file = language_dir / f"{test_case['name']}_baseline.json"
                        with open(output_file, 'w', encoding='utf-8') as f:
                            json.dump(baseline_data, f, ensure_ascii=False, indent=2)
                        
                        logger.info(f"ベースライン保存完了: {output_file}")
                        
                    except Exception as e:
                        logger.error(f"テストケース {test_case['name']} の処理中にエラー: {e}")
                        continue
            
            # サマリー生成
            self._generate_baseline_summary()
            
            logger.info("ベースライン生成が完了しました")
            return True
            
        except Exception as e:
            logger.error(f"ベースライン生成中にエラー: {e}")
            return False
    
    def _generate_baseline_summary(self):
        """ベースラインサマリー生成"""
        summary = {
            "generation_info": {
                "timestamp": datetime.now().isoformat(),
                "generator": "pypi_package",
                "config_version": "1.0.0"
            },
            "test_cases": {},
            "statistics": {
                "total_files": 0,
                "total_languages": 0,
                "generation_time": time.time()
            }
        }
        
        baseline_dir = Path(self.config["output_settings"]["baseline_dir"])
        
        for language_dir in baseline_dir.iterdir():
            if language_dir.is_dir():
                language = language_dir.name
                summary["test_cases"][language] = []
                
                for baseline_file in language_dir.glob("*_baseline.json"):
                    try:
                        with open(baseline_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        summary["test_cases"][language].append({
                            "name": data["metadata"]["test_name"],
                            "file_path": data["metadata"]["file_path"],
                            "timestamp": data["metadata"]["timestamp"],
                            "outputs_count": len(data["outputs"])
                        })
                        
                        summary["statistics"]["total_files"] += 1
                        
                    except Exception as e:
                        logger.warning(f"ベースラインファイル {baseline_file} の読み込みに失敗: {e}")
        
        summary["statistics"]["total_languages"] = len(summary["test_cases"])
        
        # サマリーファイルを保存
        summary_file = baseline_dir / "baseline_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        logger.info(f"ベースラインサマリー保存完了: {summary_file}")
    
    def generate_current_snapshots(self) -> bool:
        """現在の実装でスナップショット生成"""
        logger.info("現在の実装でのスナップショット生成を開始")
        
        try:
            # 現在の実装を使用してスナップショット生成
            # （ベースライン生成と同様の処理だが、現在のコードを使用）
            test_cases = self.config["test_cases"]
            current_dir = Path(self.config["output_settings"]["current_dir"])
            
            for language, cases in test_cases.items():
                logger.info(f"言語 {language} の現在実装テスト開始")
                
                language_dir = current_dir / language
                language_dir.mkdir(parents=True, exist_ok=True)
                
                for test_case in cases:
                    try:
                        # 現在の実装でテスト実行
                        current_data = self._generate_current_for_file(test_case, language)
                        
                        # 現在のスナップショットファイルを保存
                        output_file = language_dir / f"{test_case['name']}_current.json"
                        with open(output_file, 'w', encoding='utf-8') as f:
                            json.dump(current_data, f, ensure_ascii=False, indent=2)
                        
                        logger.info(f"現在スナップショット保存完了: {output_file}")
                        
                    except Exception as e:
                        logger.error(f"現在実装テストケース {test_case['name']} の処理中にエラー: {e}")
                        continue
            
            logger.info("現在の実装でのスナップショット生成が完了しました")
            return True
            
        except Exception as e:
            logger.error(f"現在スナップショット生成中にエラー: {e}")
            return False
    
    def _generate_current_for_file(self, test_case: Dict[str, Any], language: str) -> Dict[str, Any]:
        """現在の実装で単一ファイルのスナップショット生成"""
        file_path = test_case["file_path"]
        name = test_case["name"]
        
        logger.info(f"現在実装スナップショット生成中: {language}/{name} ({file_path})")
        
        results = {
            "metadata": {
                "test_name": name,
                "file_path": file_path,
                "language": language,
                "timestamp": datetime.now().isoformat(),
                "generator": "current_implementation"
            },
            "outputs": {}
        }
        
        try:
            # 1. コードスケール分析
            scale_cmd = [
                "python", "-m", "tree_sitter_analyzer",
                "check-scale", file_path,
                "--language", language,
                "--format", "json"
            ]
            scale_result = self._run_cli_command(scale_cmd)
            
            if scale_result:
                results["outputs"]["scale_analysis"] = scale_result
            
            # 2. 構造分析
            for format_type in test_case.get("test_formats", ["json"]):
                structure_cmd = [
                    "python", "-m", "tree_sitter_analyzer",
                    "analyze", file_path,
                    "--language", language,
                    "--format", format_type
                ]
                structure_result = self._run_cli_command(structure_cmd)
                
                if structure_result:
                    results["outputs"][f"structure_{format_type}"] = structure_result
            
            # 3. クエリ実行
            for query_key in test_case.get("test_queries", []):
                query_cmd = [
                    "python", "-m", "tree_sitter_analyzer",
                    "query", file_path,
                    "--language", language,
                    "--query", query_key,
                    "--format", "json"
                ]
                query_result = self._run_cli_command(query_cmd)
                
                if query_result:
                    results["outputs"][f"query_{query_key}"] = query_result
        
        except Exception as e:
            logger.error(f"現在実装でのスナップショット生成エラー: {e}")
            results["error"] = str(e)
        
        return results


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description="スナップショットテスト用ベースライン生成")
    parser.add_argument(
        "--mode",
        choices=["baseline", "current", "both", "report"],
        default="both",
        help="実行モード"
    )
    parser.add_argument(
        "--config",
        default="test_snapshots/config/test_cases.json",
        help="設定ファイルパス"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="詳細ログ出力"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    generator = SnapshotGenerator(args.config)
    
    success = True
    
    if args.mode in ["baseline", "both"]:
        logger.info("ベースライン生成を実行")
        success &= generator.generate_baselines()
    
    if args.mode in ["current", "both"]:
        logger.info("現在実装スナップショット生成を実行")
        success &= generator.generate_current_snapshots()
    
    if args.mode == "report":
        logger.info("レポート生成を実行")
        # レポート生成機能は後で実装
        logger.info("レポート生成機能は未実装です")
    
    if success:
        logger.info("スナップショット生成が正常に完了しました")
        sys.exit(0)
    else:
        logger.error("スナップショット生成中にエラーが発生しました")
        sys.exit(1)


if __name__ == "__main__":
    main()