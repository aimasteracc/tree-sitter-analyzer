#!/usr/bin/env python3
"""
簡素化されたバージョン管理システムのテスト
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.compatibility_test.version_manager import VersionManager


def test_version_manager():
    """VersionManagerの基本機能をテスト"""
    print("=== 簡素化されたVersionManagerのテスト ===")
    
    # VersionManagerを作成
    vm = VersionManager()
    
    # 利用可能なバージョンを表示
    available_versions = vm.list_available_versions()
    print(f"利用可能なバージョン: {available_versions}")
    
    # 各バージョンの情報を表示
    for version in available_versions:
        try:
            print(f"\n--- バージョン {version} ---")
            version_info = vm.get_version_info(version)
            print(f"  説明: {version_info.get('description', 'N/A')}")
            print(f"  Python実行可能ファイル: {version_info.get('python_executable', 'N/A')}")
            print(f"  仮想環境: {version_info.get('virtual_env', 'N/A')}")
            print(f"  モジュールパス: {version_info.get('module_path', 'N/A')}")
            
            # バージョン検証
            is_valid = vm.validate_version(version)
            print(f"  バージョン検証: {'✓' if is_valid else '✗'}")
            
            # Python実行可能ファイルの取得
            python_exe = vm.get_python_executable(version)
            print(f"  実際のPython実行可能ファイル: {python_exe}")
            
        except Exception as e:
            print(f"  エラー: {e}")
    
    print("\n=== テスト完了 ===")


if __name__ == "__main__":
    test_version_manager()