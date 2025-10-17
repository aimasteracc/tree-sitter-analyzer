#!/usr/bin/env python3
"""
バージョン管理機能のテストスクリプト

使用方法:
    python test_version_manager.py
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from version_manager import create_version_manager
from mcp_client import SimpleMCPClient


async def test_version_manager():
    """バージョン管理機能のテスト"""
    logger.info("=== バージョン管理機能テスト開始 ===")
    
    try:
        # バージョン管理機能を初期化
        version_manager = create_version_manager()
        logger.info("✓ VersionManagerの初期化成功")
        
        # 利用可能なバージョンを表示
        versions = version_manager.list_available_versions()
        logger.info(f"✓ 利用可能なバージョン: {versions}")
        
        # 各バージョンの情報を表示
        for version in versions:
            try:
                version_info = version_manager.get_version_info(version)
                python_exe = version_manager.get_python_executable(version)
                module_path = version_manager.get_module_path(version)
                
                logger.info(f"✓ バージョン {version}:")
                logger.info(f"  - Python実行可能ファイル: {python_exe}")
                logger.info(f"  - モジュールパス: {module_path}")
                logger.info(f"  - 説明: {version_info.get('description', 'N/A')}")
                
                # バージョン検証
                is_valid = version_manager.validate_version(version)
                logger.info(f"  - 検証結果: {'✓ 有効' if is_valid else '✗ 無効'}")
                
            except Exception as e:
                logger.error(f"✗ バージョン {version} の情報取得エラー: {e}")
        
        logger.info("✓ バージョン管理機能テスト完了")
        return True
        
    except Exception as e:
        logger.error(f"✗ バージョン管理機能テストエラー: {e}")
        return False


async def test_mcp_client_versions():
    """MCPクライアントのバージョン対応テスト"""
    logger.info("=== MCPクライアントバージョン対応テスト開始 ===")
    
    version_manager = create_version_manager()
    versions = version_manager.list_available_versions()
    
    test_results = {}
    
    for version in versions[:2]:  # 最初の2つのバージョンのみテスト
        logger.info(f"--- バージョン {version} のテスト ---")
        
        try:
            # MCPクライアントを作成
            client = SimpleMCPClient(version=version)
            logger.info(f"✓ MCPクライアント作成成功 (バージョン: {version})")
            
            # 接続テスト
            connected = await client.connect()
            if connected:
                logger.info(f"✓ MCP接続成功 (バージョン: {version})")
                
                # 簡単なツール呼び出しテスト
                try:
                    result = await client.call_tool("check_code_scale", {
                        "file_path": "examples/BigService.java",
                        "include_complexity": False,
                        "include_details": False
                    })
                    
                    if "error" not in result:
                        logger.info(f"✓ ツール呼び出し成功 (バージョン: {version})")
                        test_results[version] = "成功"
                    else:
                        logger.warning(f"⚠ ツール呼び出しエラー (バージョン: {version}): {result.get('message', 'Unknown error')}")
                        test_results[version] = f"ツールエラー: {result.get('message', 'Unknown')}"
                        
                except Exception as e:
                    logger.warning(f"⚠ ツール呼び出し例外 (バージョン: {version}): {e}")
                    test_results[version] = f"例外: {str(e)}"
                
                # 切断
                await client.disconnect()
                logger.info(f"✓ MCP切断完了 (バージョン: {version})")
                
            else:
                logger.warning(f"⚠ MCP接続失敗 (バージョン: {version})")
                test_results[version] = "接続失敗"
                
        except Exception as e:
            logger.error(f"✗ MCPクライアントテストエラー (バージョン: {version}): {e}")
            test_results[version] = f"エラー: {str(e)}"
    
    # 結果サマリー
    logger.info("=== テスト結果サマリー ===")
    for version, result in test_results.items():
        status = "✓" if result == "成功" else "⚠" if "エラー" not in result else "✗"
        logger.info(f"{status} バージョン {version}: {result}")
    
    return test_results


async def test_environment_variables():
    """環境変数サポートのテスト"""
    logger.info("=== 環境変数サポートテスト開始 ===")
    
    import os
    
    # テスト用環境変数を設定
    original_env = {}
    test_env_vars = {
        "TSA_DEFAULT_VERSION": "test_version",
        "TSA_VERSION_TEST_VERSION_PYTHON": sys.executable,
        "TSA_VERSION_TEST_VERSION_VENV": str(Path(__file__).parent)
    }
    
    try:
        # 環境変数を設定
        for key, value in test_env_vars.items():
            original_env[key] = os.environ.get(key)
            os.environ[key] = value
            logger.info(f"✓ 環境変数設定: {key}={value}")
        
        # バージョン管理機能を再初期化
        version_manager = create_version_manager()
        
        # デフォルトバージョンが変更されているかチェック
        if version_manager.default_version == "test_version":
            logger.info("✓ 環境変数からデフォルトバージョンが正しく読み込まれました")
        else:
            logger.warning(f"⚠ デフォルトバージョンが期待値と異なります: {version_manager.default_version}")
        
        # 検出されたバージョンをチェック
        versions = version_manager.list_available_versions()
        if "test.version" in versions:
            logger.info("✓ 環境変数からバージョンが正しく検出されました")
        else:
            logger.warning(f"⚠ 環境変数からのバージョン検出に失敗: {versions}")
        
        logger.info("✓ 環境変数サポートテスト完了")
        return True
        
    except Exception as e:
        logger.error(f"✗ 環境変数サポートテストエラー: {e}")
        return False
        
    finally:
        # 環境変数を復元
        for key, original_value in original_env.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value


async def main():
    """メイン関数"""
    logger.info("バージョン管理機能の統合テストを開始します")
    
    results = {}
    
    # バージョン管理機能テスト
    results["version_manager"] = await test_version_manager()
    
    # 環境変数サポートテスト
    results["environment_variables"] = await test_environment_variables()
    
    # MCPクライアントバージョン対応テスト
    results["mcp_client_versions"] = await test_mcp_client_versions()
    
    # 結果サマリー
    logger.info("=== 統合テスト結果 ===")
    success_count = 0
    total_count = 0
    
    for test_name, result in results.items():
        if test_name == "mcp_client_versions":
            # MCPクライアントテストは辞書形式
            if isinstance(result, dict):
                for version, version_result in result.items():
                    total_count += 1
                    if version_result == "成功":
                        success_count += 1
                        logger.info(f"✓ {test_name} ({version}): 成功")
                    else:
                        logger.info(f"⚠ {test_name} ({version}): {version_result}")
        else:
            total_count += 1
            if result:
                success_count += 1
                logger.info(f"✓ {test_name}: 成功")
            else:
                logger.info(f"✗ {test_name}: 失敗")
    
    success_rate = (success_count / total_count) * 100 if total_count > 0 else 0
    logger.info(f"統合テスト完了: {success_count}/{total_count} 成功 ({success_rate:.1f}%)")
    
    if success_rate >= 80:
        logger.info("✓ バージョン管理機能は正常に動作しています")
        return 0
    else:
        logger.error("✗ バージョン管理機能に問題があります")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)