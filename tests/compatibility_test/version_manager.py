#!/usr/bin/env python3
"""
バージョン管理ユーティリティ（簡素化版）

規約ベースのバージョン管理：
- versions/v{version}/venv/ 構造を前提
- 設定ファイルに依存しない
- シンプルで理解しやすい
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class VersionManager:
    """tree-sitter-analyzerのバージョン管理クラス（簡素化版）"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        規約ベースの初期化
        
        規約：
        - versions/v{version}/venv/ ディレクトリ構造
        - Windows: venv/Scripts/python.exe
        - Unix/Linux/macOS: venv/bin/python
        """
        self.compatibility_test_dir = Path(__file__).parent
        self.versions_dir = self.compatibility_test_dir / "versions"
        
        # 検出されたバージョン情報をキャッシュ
        self._detected_versions = {}
        
        # バージョンを自動検出
        self._detect_all_versions()
    
    def _detect_all_versions(self):
        """versions/ディレクトリからすべてのバージョンを検出"""
        if not self.versions_dir.exists():
            logger.debug(f"バージョンディレクトリが存在しません: {self.versions_dir}")
            return
        
        logger.info(f"バージョンを検出中: {self.versions_dir}")
        
        for item in self.versions_dir.iterdir():
            if item.is_dir() and item.name.startswith("v"):
                version = item.name[1:]  # "v"プレフィックスを除去
                version_info = self._detect_version_info(item, version)
                if version_info:
                    self._detected_versions[version] = version_info
                    logger.info(f"バージョン {version} を検出: {item}")
    
    def _detect_version_info(self, version_dir: Path, version: str) -> Optional[Dict[str, Any]]:
        """バージョンディレクトリからバージョン情報を検出"""
        venv_dir = version_dir / "venv"
        if not venv_dir.exists():
            logger.debug(f"venvディレクトリが存在しません: {venv_dir}")
            return None
        
        # Python実行可能ファイルを検索
        python_exe = self._find_python_executable(venv_dir)
        if not python_exe:
            logger.debug(f"Python実行可能ファイルが見つかりません: {venv_dir}")
            return None
        
        # バージョンを確認
        if not self._verify_version(python_exe, version):
            logger.warning(f"バージョンが一致しません: {python_exe} (期待: {version})")
            return None
        
        return {
            "python_executable": str(python_exe),
            "virtual_env": str(venv_dir),
            "module_path": "tree_sitter_analyzer",
            "description": f"Convention-based version {version}",
            "source_directory": str(version_dir)
        }
    
    def _find_python_executable(self, venv_dir: Path) -> Optional[Path]:
        """仮想環境のPython実行可能ファイルを検索"""
        # Windows
        python_exe = venv_dir / "Scripts" / "python.exe"
        if python_exe.exists():
            return python_exe
        
        # Unix/Linux/macOS
        python_exe = venv_dir / "bin" / "python"
        if python_exe.exists():
            return python_exe
        
        return None
    
    def _verify_version(self, python_exe: Path, expected_version: str) -> bool:
        """指定されたPython実行可能ファイルでバージョンを確認"""
        try:
            result = subprocess.run(
                [str(python_exe), "-c", 
                 "import tree_sitter_analyzer; print(tree_sitter_analyzer.__version__)"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                actual_version = result.stdout.strip()
                return actual_version == expected_version or expected_version in actual_version
            
        except Exception as e:
            logger.debug(f"バージョン確認エラー: {e}")
        
        return False
    
    def get_version_info(self, version: str) -> Dict[str, Any]:
        """指定されたバージョンの情報を取得"""
        if version == "current":
            return {
                "python_executable": sys.executable,
                "virtual_env": None,
                "module_path": "tree_sitter_analyzer",
                "description": "Current development version"
            }
        
        if version in self._detected_versions:
            return self._detected_versions[version].copy()
        
        raise ValueError(f"バージョン {version} が見つかりません。利用可能: {self.list_available_versions()}")
    
    def get_python_executable(self, version: str) -> str:
        """指定されたバージョンのPython実行可能ファイルを取得"""
        version_info = self.get_version_info(version)
        python_exe = version_info.get("python_executable")
        
        if python_exe and Path(python_exe).exists():
            return python_exe
        
        logger.warning(f"Python実行可能ファイルが見つかりません。デフォルトを使用: {sys.executable}")
        return sys.executable
    
    def get_module_path(self, version: str) -> str:
        """指定されたバージョンのモジュールパスを取得"""
        version_info = self.get_version_info(version)
        return version_info.get("module_path", "tree_sitter_analyzer")
    
    def get_environment_variables(self, version: str) -> Dict[str, str]:
        """指定されたバージョンの環境変数を取得"""
        version_info = self.get_version_info(version)
        env = os.environ.copy()
        
        # 仮想環境のパスを設定
        if version_info.get("virtual_env"):
            venv_path = Path(version_info["virtual_env"])
            if venv_path.exists():
                # PATHに仮想環境のbinディレクトリを追加
                if sys.platform == "win32":
                    scripts_dir = venv_path / "Scripts"
                else:
                    scripts_dir = venv_path / "bin"
                
                if scripts_dir.exists():
                    env["PATH"] = str(scripts_dir) + os.pathsep + env.get("PATH", "")
                
                # VIRTUAL_ENVを設定
                env["VIRTUAL_ENV"] = str(venv_path)
        
        return env
    
    def list_available_versions(self) -> List[str]:
        """利用可能なバージョンのリストを取得"""
        versions = ["current"]
        versions.extend(sorted(self._detected_versions.keys()))
        return versions
    
    def validate_version(self, version: str) -> bool:
        """指定されたバージョンが利用可能かチェック"""
        try:
            self.get_version_info(version)
            return True
        except ValueError:
            return False
    
    def get_version_directory(self, version: str) -> Optional[Path]:
        """指定されたバージョンのディレクトリを取得"""
        if version == "current":
            return None
        
        if version in self._detected_versions:
            source_dir = self._detected_versions[version].get("source_directory")
            return Path(source_dir) if source_dir else None
        
        return None


def create_version_manager(config_path: Optional[Path] = None) -> VersionManager:
    """VersionManagerのファクトリ関数（簡素化版）"""
    # 設定ファイルは使用せず、規約ベースで動作
    return VersionManager()