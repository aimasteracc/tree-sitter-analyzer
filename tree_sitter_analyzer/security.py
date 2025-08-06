#!/usr/bin/env python3
"""
Security Module - セキュリティファースト設計

革命的システムのセキュリティを保証するモジュール。
すべての入力を検証し、安全な実行環境を提供します。

Security Principles:
- Zero Trust Architecture
- Principle of Least Privilege  
- Defense in Depth
- Secure by Default
"""

import os
import re
import hashlib
from pathlib import Path
from typing import Any, List, Optional, Union
from urllib.parse import urlparse

from .utils import setup_logger


class SecurityValidator:
    """
    セキュリティバリデーター
    
    すべての入力を検証し、セキュリティ脅威を防止します。
    """
    
    def __init__(self):
        self.logger = setup_logger("security")
        self.max_path_length = 4096
        self.allowed_extensions = {
            '.py', '.java', '.js', '.ts', '.cpp', '.c', '.h', '.hpp',
            '.cs', '.go', '.rs', '.rb', '.php', '.swift', '.kt',
            '.scala', '.clj', '.hs', '.ml', '.fs', '.vb', '.pl',
            '.sh', '.bat', '.ps1', '.yaml', '.yml', '.json', '.xml',
            '.toml', '.ini', '.cfg', '.conf', '.properties', '.env'
        }
        self.dangerous_patterns = [
            r'\.\./.*',  # Path traversal
            r'[<>:"|?*]',  # Invalid filename characters (Windows)
            r'^\s*$',  # Empty or whitespace only
            r'.*\x00.*',  # Null bytes
            r'.*[\x01-\x1f\x7f-\x9f].*',  # Control characters
        ]
    
    def validate_path(self, path: Union[str, Path]) -> bool:
        """
        パスの安全性を検証
        
        Args:
            path: 検証するパス
            
        Returns:
            bool: パスが安全な場合True
        """
        try:
            path_str = str(path)
            
            # 基本的な検証
            if not self._validate_path_basic(path_str):
                return False
            
            # パストラバーサル攻撃の検証
            if not self._validate_path_traversal(path_str):
                return False
            
            # ファイルシステムアクセスの検証
            if not self._validate_filesystem_access(path_str):
                return False
            
            # プロジェクトルートの検証
            if not self._validate_project_root(path_str):
                return False
            
            self.logger.debug(f"✅ パス検証成功: {path_str}")
            return True
            
        except Exception as e:
            self.logger.warning(f"⚠️ パス検証エラー: {e}")
            return False
    
    def _validate_path_basic(self, path: str) -> bool:
        """基本的なパス検証"""
        # 長さチェック
        if len(path) > self.max_path_length:
            self.logger.warning(f"⚠️ パスが長すぎます: {len(path)} > {self.max_path_length}")
            return False
        
        # 危険なパターンチェック
        for pattern in self.dangerous_patterns:
            if re.search(pattern, path):
                self.logger.warning(f"⚠️ 危険なパターン検出: {pattern}")
                return False
        
        return True
    
    def _validate_path_traversal(self, path: str) -> bool:
        """パストラバーサル攻撃の検証"""
        try:
            # パスを正規化
            normalized = Path(path).resolve()
            
            # 相対パス要素のチェック
            path_parts = Path(path).parts
            if '..' in path_parts or '.' in path_parts:
                self.logger.warning("⚠️ 相対パス要素検出")
                return False
            
            return True
            
        except (OSError, ValueError) as e:
            self.logger.warning(f"⚠️ パス正規化エラー: {e}")
            return False
    
    def _validate_filesystem_access(self, path: str) -> bool:
        """ファイルシステムアクセスの検証"""
        try:
            path_obj = Path(path)
            
            # 存在チェック
            if not path_obj.exists():
                self.logger.warning(f"⚠️ パスが存在しません: {path}")
                return False
            
            # 読み取り権限チェック
            if not os.access(path, os.R_OK):
                self.logger.warning(f"⚠️ 読み取り権限がありません: {path}")
                return False
            
            # ディレクトリの場合の追加チェック
            if path_obj.is_dir():
                # 実行権限チェック（ディレクトリ内容の読み取りに必要）
                if not os.access(path, os.X_OK):
                    self.logger.warning(f"⚠️ ディレクトリアクセス権限がありません: {path}")
                    return False
            
            return True
            
        except (OSError, PermissionError) as e:
            self.logger.warning(f"⚠️ ファイルシステムアクセスエラー: {e}")
            return False
    
    def _validate_project_root(self, path: str) -> bool:
        """プロジェクトルートの妥当性検証"""
        try:
            path_obj = Path(path)
            
            # プロジェクトの特徴的なファイル・ディレクトリの存在チェック
            project_indicators = [
                # Python プロジェクト
                'setup.py', 'pyproject.toml', 'requirements.txt', 'Pipfile',
                # Java プロジェクト
                'pom.xml', 'build.gradle', 'build.xml',
                # JavaScript/Node.js プロジェクト
                'package.json', 'yarn.lock', 'package-lock.json',
                # C/C++ プロジェクト
                'Makefile', 'CMakeLists.txt', 'configure.ac',
                # 一般的なプロジェクト
                '.git', '.gitignore', 'README.md', 'README.txt',
                # ディレクトリ構造
                'src', 'lib', 'app', 'source', 'code'
            ]
            
            # いずれかの指標が存在すればプロジェクトと判定
            for indicator in project_indicators:
                if (path_obj / indicator).exists():
                    return True
            
            # ソースファイルが存在すればプロジェクトと判定
            source_files = list(path_obj.rglob("*"))
            for file_path in source_files[:100]:  # 最初の100ファイルをチェック
                if file_path.suffix.lower() in self.allowed_extensions:
                    return True
            
            self.logger.warning(f"⚠️ プロジェクトの特徴が見つかりません: {path}")
            return False
            
        except Exception as e:
            self.logger.warning(f"⚠️ プロジェクトルート検証エラー: {e}")
            return False
    
    def sanitize_input(self, input_value: str, max_length: int = 1000) -> str:
        """
        入力値のサニタイゼーション
        
        Args:
            input_value: サニタイズする入力値
            max_length: 最大長
            
        Returns:
            str: サニタイズされた値
        """
        if not isinstance(input_value, str):
            return str(input_value)[:max_length]
        
        # 長さ制限
        sanitized = input_value[:max_length]
        
        # 制御文字の除去
        sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', sanitized)
        
        # 危険な文字列の除去
        dangerous_strings = [
            '<script', '</script>', 'javascript:', 'vbscript:',
            'onload=', 'onerror=', 'onclick=', 'onmouseover=',
            'eval(', 'exec(', 'system(', 'shell_exec(',
            'DROP TABLE', 'DELETE FROM', 'INSERT INTO', 'UPDATE SET'
        ]
        
        for dangerous in dangerous_strings:
            sanitized = sanitized.replace(dangerous, '')
        
        return sanitized.strip()
    
    def validate_file_extension(self, file_path: Union[str, Path]) -> bool:
        """
        ファイル拡張子の検証
        
        Args:
            file_path: 検証するファイルパス
            
        Returns:
            bool: 許可された拡張子の場合True
        """
        try:
            path_obj = Path(file_path)
            extension = path_obj.suffix.lower()
            
            if extension in self.allowed_extensions:
                return True
            
            self.logger.warning(f"⚠️ 許可されていない拡張子: {extension}")
            return False
            
        except Exception as e:
            self.logger.warning(f"⚠️ 拡張子検証エラー: {e}")
            return False
    
    def generate_secure_cache_path(self, project_path: str) -> Path:
        """
        セキュアなキャッシュパスの生成
        
        Args:
            project_path: プロジェクトパス
            
        Returns:
            Path: セキュアなキャッシュパス
        """
        # プロジェクトパスのハッシュ化
        path_hash = hashlib.sha256(str(Path(project_path).resolve()).encode()).hexdigest()[:16]
        
        # OS標準のキャッシュディレクトリを使用
        try:
            import platformdirs
            cache_root = Path(platformdirs.user_cache_dir("TreeSitterAnalyzer", "AugmentCode"))
        except ImportError:
            # platformdirs が利用できない場合のフォールバック
            if os.name == 'nt':  # Windows
                cache_root = Path(os.environ.get('LOCALAPPDATA', '~'), 'TreeSitterAnalyzer')
            else:  # Unix-like
                cache_root = Path.home() / '.cache' / 'tree-sitter-analyzer'
        
        # キャッシュディレクトリの作成
        cache_path = cache_root / "projects" / path_hash
        cache_path.mkdir(parents=True, exist_ok=True)
        
        return cache_path
    
    def is_safe_for_analysis(self, file_path: Union[str, Path]) -> bool:
        """
        ファイルが分析に安全かどうかを判定
        
        Args:
            file_path: 判定するファイルパス
            
        Returns:
            bool: 分析に安全な場合True
        """
        try:
            path_obj = Path(file_path)
            
            # 基本的な安全性チェック
            if not self.validate_file_extension(file_path):
                return False
            
            # ファイルサイズチェック（100MB制限）
            if path_obj.exists() and path_obj.stat().st_size > 100 * 1024 * 1024:
                self.logger.warning(f"⚠️ ファイルサイズが大きすぎます: {file_path}")
                return False
            
            # バイナリファイルの除外
            if path_obj.exists() and self._is_binary_file(path_obj):
                return False
            
            return True
            
        except Exception as e:
            self.logger.warning(f"⚠️ 安全性判定エラー: {e}")
            return False
    
    def _is_binary_file(self, file_path: Path) -> bool:
        """バイナリファイルかどうかを判定"""
        try:
            with open(file_path, 'rb') as f:
                chunk = f.read(1024)
                return b'\x00' in chunk
        except:
            return True  # 読み取りエラーの場合は安全側に倒す


class SecurityError(Exception):
    """セキュリティ関連のエラー"""
    pass


class InputValidationError(SecurityError):
    """入力検証エラー"""
    pass


class PathTraversalError(SecurityError):
    """パストラバーサル攻撃エラー"""
    pass


class FileAccessError(SecurityError):
    """ファイルアクセスエラー"""
    pass
