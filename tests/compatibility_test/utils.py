"""
Tree-sitter Analyzer 互換性テスト用ユーティリティ関数

このモジュールは、互換性テストで使用される共通機能を提供します。
"""

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import venv
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
import copy

logger = logging.getLogger(__name__)

def get_project_root() -> Path:
    """プロジェクトルートディレクトリを取得"""
    current = Path(__file__).resolve()
    
    # .gitディレクトリまたはpyproject.tomlを探す
    for parent in current.parents:
        if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
            return parent
    
    # 見つからない場合は現在のディレクトリから3つ上を返す
    return current.parent.parent.parent

async def setup_virtual_environments(venv_dir: Path) -> bool:
    """仮想環境をセットアップ"""
    try:
        logger.info("仮想環境をセットアップ中...")
        venv_dir.mkdir(parents=True, exist_ok=True)
        
        # v1.6.1用の仮想環境
        v161_venv = venv_dir / "v1.6.1"
        if not v161_venv.exists():
            logger.info("v1.6.1用仮想環境を作成中...")
            venv.create(v161_venv, with_pip=True)
            
            # tree-sitter-analyzer==1.6.1をインストール
            pip_path = v161_venv / "Scripts" / "pip.exe" if os.name == "nt" else v161_venv / "bin" / "pip"
            subprocess.run([
                str(pip_path), "install", "tree-sitter-analyzer==1.6.1"
            ], check=True)
        
        # PyPI最新版用の仮想環境
        pypi_venv = venv_dir / "pypi"
        if not pypi_venv.exists():
            logger.info("PyPI最新版用仮想環境を作成中...")
            venv.create(pypi_venv, with_pip=True)
            
            # tree-sitter-analyzer最新版をインストール
            pip_path = pypi_venv / "Scripts" / "pip.exe" if os.name == "nt" else pypi_venv / "bin" / "pip"
            subprocess.run([
                str(pip_path), "install", "tree-sitter-analyzer[mcp]"
            ], check=True)
        
        logger.info("仮想環境のセットアップが完了しました")
        return True
        
    except Exception as e:
        logger.error(f"仮想環境のセットアップに失敗: {e}")
        return False

async def start_mcp_server(version: str, venv_path: Path, port: int) -> Optional[subprocess.Popen]:
    """MCPサーバーを起動"""
    try:
        # Python実行ファイルのパス
        python_path = venv_path / "Scripts" / "python.exe" if os.name == "nt" else venv_path / "bin" / "python"
        
        # MCPサーバー起動コマンド
        cmd = [
            str(python_path),
            "-m", "tree_sitter_analyzer.mcp.server",
            "--port", str(port)
        ]
        
        # 環境変数の設定
        env = os.environ.copy()
        env["PYTHONPATH"] = str(venv_path / "lib" / "python3.10" / "site-packages")
        
        # プロセス起動
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=get_project_root()
        )
        
        # 起動確認のため少し待機
        await asyncio.sleep(2)
        
        # プロセスが正常に起動しているかチェック
        if process.poll() is None:
            return process
        else:
            stdout, stderr = process.communicate()
            logger.error(f"MCPサーバー起動失敗 ({version}): {stderr.decode()}")
            return None
            
    except Exception as e:
        logger.error(f"MCPサーバー起動エラー ({version}): {e}")
        return None

async def stop_mcp_server(process: subprocess.Popen):
    """MCPサーバーを停止"""
    try:
        if process and process.poll() is None:
            process.terminate()
            
            # 正常終了を待機
            try:
                await asyncio.wait_for(
                    asyncio.create_task(_wait_for_process(process)),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                # 強制終了
                process.kill()
                await asyncio.create_task(_wait_for_process(process))
                
    except Exception as e:
        logger.error(f"MCPサーバー停止エラー: {e}")

async def _wait_for_process(process: subprocess.Popen):
    """プロセスの終了を待機"""
    while process.poll() is None:
        await asyncio.sleep(0.1)

def normalize_result(result: Dict[str, Any], tool: str) -> Dict[str, Any]:
    """
    テスト結果を正規化
    
    Args:
        result: 生の結果
        tool: ツール名
        
    Returns:
        正規化された結果
    """
    normalized = copy.deepcopy(result)
    
    # 共通の正規化処理
    normalized = _remove_timestamps(normalized)
    normalized = _normalize_paths(normalized)
    normalized = _normalize_numbers(normalized)
    
    # ツール固有の正規化
    if tool == "check_code_scale":
        normalized = _normalize_code_scale(normalized)
    elif tool == "analyze_code_structure":
        normalized = _normalize_code_structure(normalized)
    elif tool == "extract_code_section":
        normalized = _normalize_code_section(normalized)
    elif tool == "query_code":
        normalized = _normalize_query_code(normalized)
    elif tool in ["list_files", "search_content", "find_and_grep"]:
        normalized = _normalize_file_operations(normalized)
    
    return normalized

def _remove_timestamps(data: Any) -> Any:
    """タイムスタンプを除去"""
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            # タイムスタンプ関連のキーを除外
            if key.lower() in ['timestamp', 'created_at', 'updated_at', 'execution_time']:
                continue
            result[key] = _remove_timestamps(value)
        return result
    elif isinstance(data, list):
        return [_remove_timestamps(item) for item in data]
    else:
        return data

def _normalize_paths(data: Any) -> Any:
    """パスを正規化"""
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            result[key] = _normalize_paths(value)
        return result
    elif isinstance(data, list):
        return [_normalize_paths(item) for item in data]
    elif isinstance(data, str):
        # 絶対パスを相対パスに変換
        if os.path.isabs(data):
            try:
                project_root = get_project_root()
                return os.path.relpath(data, project_root)
            except ValueError:
                return data
        return data
    else:
        return data

def _normalize_numbers(data: Any, precision: int = 6) -> Any:
    """数値を正規化（精度を統一）"""
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            result[key] = _normalize_numbers(value, precision)
        return result
    elif isinstance(data, list):
        return [_normalize_numbers(item, precision) for item in data]
    elif isinstance(data, float):
        return round(data, precision)
    else:
        return data

def _normalize_code_scale(data: Dict[str, Any]) -> Dict[str, Any]:
    """check_code_scale結果の正規化"""
    # ファイルサイズなどの環境依存値を除外
    if 'file_info' in data:
        file_info = data['file_info'].copy()
        # ファイルサイズは環境によって異なる可能性があるため除外
        file_info.pop('file_size', None)
        file_info.pop('last_modified', None)
        data['file_info'] = file_info
    
    return data

def _normalize_code_structure(data: Dict[str, Any]) -> Dict[str, Any]:
    """analyze_code_structure結果の正規化"""
    # テーブル出力の行番号などを正規化
    if 'table_output' in data and isinstance(data['table_output'], str):
        # 行番号の正規化（環境によって異なる可能性）
        table_output = re.sub(r'\|\s*\d+\s*\|', '| LINE |', data['table_output'])
        data['table_output'] = table_output
    
    return data

def _normalize_code_section(data: Dict[str, Any]) -> Dict[str, Any]:
    """extract_code_section結果の正規化"""
    # 特に正規化が必要な項目はないが、将来の拡張のため
    return data

def _normalize_query_code(data: Dict[str, Any]) -> Dict[str, Any]:
    """query_code結果の正規化"""
    # クエリ結果の位置情報を正規化
    if 'query_results' in data and isinstance(data['query_results'], list):
        for result in data['query_results']:
            if isinstance(result, dict):
                # 位置情報の正規化
                for key in ['start_line', 'end_line', 'start_column', 'end_column']:
                    if key in result:
                        result[key] = int(result[key])
    
    return data

def _normalize_file_operations(data: Dict[str, Any]) -> Dict[str, Any]:
    """ファイル操作結果の正規化"""
    # ファイルパスとタイムスタンプの正規化
    if 'files' in data and isinstance(data['files'], list):
        for file_info in data['files']:
            if isinstance(file_info, dict):
                # ファイルサイズやタイムスタンプを除外
                file_info.pop('size', None)
                file_info.pop('modified_time', None)
                file_info.pop('created_time', None)
    
    if 'matches' in data and isinstance(data['matches'], list):
        for match in data['matches']:
            if isinstance(match, dict):
                # マッチ結果のパス正規化
                if 'file' in match:
                    match['file'] = _normalize_paths(match['file'])
    
    return data

async def save_test_result(
    test_id: str,
    tool: str,
    results: Dict[str, Any],
    results_dir: Path
) -> bool:
    """テスト結果を保存"""
    try:
        # バージョン別に結果を保存
        for version, result in results.items():
            version_dir = results_dir / f"v-{version.replace('.', '-')}"
            version_dir.mkdir(parents=True, exist_ok=True)
            
            # ファイル名の生成
            filename = f"{test_id.zfill(3)}-{tool}-test.json"
            filepath = version_dir / filename
            
            # 結果の保存
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
        
        return True
        
    except Exception as e:
        logger.error(f"テスト結果の保存に失敗: {test_id} - {e}")
        return False

def create_directory_structure(base_dir: Path) -> bool:
    """ディレクトリ構造を作成"""
    try:
        directories = [
            base_dir / "tests" / "compatibility_test" / "result" / "v-1.6.1",
            base_dir / "tests" / "compatibility_test" / "result" / "v-1.9.2",
            base_dir / "tests" / "compatibility_test" / "venvs",
            base_dir / "tests" / "test_data"
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            logger.info(f"ディレクトリを作成: {directory}")
        
        return True
        
    except Exception as e:
        logger.error(f"ディレクトリ構造の作成に失敗: {e}")
        return False

def validate_test_environment() -> bool:
    """テスト環境の検証"""
    try:
        # 必要なコマンドの存在確認
        required_commands = ["python"]
        
        # uvまたはpipのいずれかが利用可能かチェック
        package_manager = None
        if shutil.which("uv") is not None:
            package_manager = "uv"
        elif shutil.which("pip") is not None:
            package_manager = "pip"
        else:
            logger.error("パッケージマネージャー（uvまたはpip）が見つかりません")
            return False
        
        logger.info(f"パッケージマネージャー: {package_manager}")
        
        for cmd in required_commands:
            if shutil.which(cmd) is None:
                logger.error(f"必要なコマンドが見つかりません: {cmd}")
                return False
        
        # プロジェクトルートの確認
        project_root = get_project_root()
        if not project_root.exists():
            logger.error("プロジェクトルートが見つかりません")
            return False
        
        # pyproject.tomlの確認
        if not (project_root / "pyproject.toml").exists():
            logger.error("pyproject.tomlが見つかりません")
            return False
        
        logger.info("テスト環境の検証が完了しました")
        return True
        
    except Exception as e:
        logger.error(f"テスト環境の検証に失敗: {e}")
        return False

def generate_test_report(summary: Dict[str, Any], output_path: Path) -> bool:
    """テストレポートを生成"""
    try:
        report_lines = [
            "# Tree-sitter Analyzer 互換性テストレポート",
            "",
            f"**実行日時**: {summary['timestamp']}",
            f"**実行時間**: {summary['execution_time']:.2f}秒",
            "",
            "## 結果サマリー",
            "",
            f"- 総テスト数: {summary['total_tests']}",
            f"- 互換テスト数: {summary['compatible_tests']}",
            f"- 非互換テスト数: {summary['incompatible_tests']}",
            f"- 互換性率: {summary['compatibility_rate']:.1%}",
            ""
        ]
        
        # 非互換テストの詳細
        if summary['incompatible_tests'] > 0:
            report_lines.extend([
                "## 非互換テスト詳細",
                ""
            ])
            
            for result in summary['test_results']:
                if not result['compatible']:
                    report_lines.extend([
                        f"### {result['test_id']} ({result['tool']})",
                        "",
                        "**結果**:",
                        "```json",
                        json.dumps(result['results'], indent=2, ensure_ascii=False),
                        "```",
                        ""
                    ])
        
        # レポートの保存
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report_lines))
        
        logger.info(f"テストレポートを生成しました: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"テストレポートの生成に失敗: {e}")
        return False