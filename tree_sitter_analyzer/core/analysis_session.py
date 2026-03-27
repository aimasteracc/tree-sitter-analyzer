#!/usr/bin/env python3
"""
Analysis Session Recording and Replay

Provides auditable session recording for all TSA analysis operations,
enabling reproducibility and debugging.

Features:
- Session metadata tracking (timestamp, git commit, tools used)
- File integrity verification via SHA256 hashing
- Token statistics recording (before/after comparison)
- Session persistence to ~/.tsa/sessions/
- Replay capability with integrity checks
"""

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


class AnalysisSession:
    """
    记录和管理 TSA 分析会话

    每个 session 包含：
    - 唯一 session ID (timestamp + uuid4)
    - 分析的文件列表及其 SHA256 hash
    - Git commit（可选）
    - 使用的工具列表
    - Token 统计信息
    """

    # Session 默认保留期（90天）
    DEFAULT_RETENTION_DAYS = 90

    def __init__(
        self,
        input_files: list[str],
        output_format: str,
        git_commit: str | None = None,
        tools_used: list[str] | None = None,
        token_count_before: int | None = None,
        token_count_after: int | None = None,
        auto_detect_git_commit: bool = False,
    ) -> None:
        """
        初始化 Analysis Session

        Args:
            input_files: 输入文件路径列表
            output_format: 输出格式 (toon/json/csv/compact/full)
            git_commit: Git commit hash（可选）
            tools_used: 使用的工具列表（可选）
            token_count_before: 分析前 token 数量（可选）
            token_count_after: 分析后 token 数量（可选）
            auto_detect_git_commit: 是否自动检测 git commit

        Raises:
            ValueError: 输入验证失败时抛出
        """
        # 输入验证
        if not input_files:
            raise ValueError("input_files cannot be empty")

        valid_formats = ["toon", "json", "csv", "compact", "full"]
        if output_format not in valid_formats:
            raise ValueError(
                f"Invalid output_format: {output_format}. "
                f"Must be one of {valid_formats}"
            )

        if token_count_before is not None and token_count_before < 0:
            raise ValueError("Token counts cannot be negative")

        if token_count_after is not None and token_count_after < 0:
            raise ValueError("Token counts cannot be negative")

        # 生成 session ID: YYYYMMDD-HHMMSS-uuid4
        now = datetime.utcnow()
        timestamp_part = now.strftime("%Y%m%d-%H%M%S")
        uuid_part = str(uuid4())
        self.session_id = f"{timestamp_part}-{uuid_part}"

        # ISO 8601 timestamp
        self.timestamp = now.isoformat() + "Z"

        # 基本信息
        self.input_files = input_files
        self.output_format = output_format
        self.tools_used = tools_used or []
        self.token_count_before = token_count_before
        self.token_count_after = token_count_after

        # 计算文件 hash
        self.file_hashes = self._calculate_file_hashes(input_files)

        # Git commit
        if git_commit:
            # 手动提供的 git_commit 优先
            self.git_commit = git_commit
        elif auto_detect_git_commit:
            # 自动检测 git commit
            self.git_commit = self._detect_git_commit()
        else:
            self.git_commit = None

    @property
    def token_savings_pct(self) -> float | None:
        """
        计算 token 节省百分比

        Returns:
            Token 节省百分比，如果数据不完整返回 None
        """
        if self.token_count_before is None or self.token_count_after is None:
            return None

        if self.token_count_before == 0:
            return 0.0

        savings = (
            (self.token_count_before - self.token_count_after)
            / self.token_count_before
            * 100
        )
        # 四舍五入到1位小数，避免浮点数精度问题
        return round(savings, 1)

    def _calculate_file_hashes(self, file_paths: list[str]) -> dict[str, str | None]:
        """
        计算文件的 SHA256 hash

        Args:
            file_paths: 文件路径列表

        Returns:
            {file_path: sha256_hash} 字典，文件不存在时 hash 为 None
        """
        hashes = {}
        for file_path in file_paths:
            path = Path(file_path)
            if not path.exists():
                hashes[file_path] = None
                continue

            try:
                sha256_hash = hashlib.sha256()
                with open(path, "rb") as f:
                    # 分块读取，避免大文件内存问题
                    for chunk in iter(lambda: f.read(8192), b""):
                        sha256_hash.update(chunk)
                hashes[file_path] = sha256_hash.hexdigest()
            except Exception:
                # 读取失败时设为 None
                hashes[file_path] = None

        return hashes

    def _detect_git_commit(self) -> str | None:
        """
        自动检测当前 git commit

        Returns:
            Git commit hash，如果不在 git repo 中返回 None
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=False,  # 不自动抛出异常，手动检查 returncode
            )
            # 检查命令是否成功
            if result.returncode != 0:
                return None
            # 去除换行符
            return result.stdout.strip()
        except FileNotFoundError:
            # git 命令不存在
            return None

    def to_dict(self) -> dict[str, Any]:
        """
        转换为字典格式（用于 JSON 序列化）

        Returns:
            包含所有 session 数据的字典
        """
        return {
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "input_files": self.input_files,
            "file_hashes": self.file_hashes,
            "output_format": self.output_format,
            "git_commit": self.git_commit,
            "tools_used": self.tools_used,
            "token_count_before": self.token_count_before,
            "token_count_after": self.token_count_after,
            "token_savings_pct": self.token_savings_pct,
        }

    def save_to_audit_log(self) -> Path:
        """
        保存 session 到审计日志

        Session 保存到 ~/.tsa/sessions/{session_id}.json
        如果目录不存在会自动创建

        Returns:
            保存的文件路径
        """
        # 确保 sessions 目录存在
        sessions_dir = Path.home() / ".tsa" / "sessions"
        if not sessions_dir.exists():
            sessions_dir.mkdir(parents=True, exist_ok=True)

        # 保存文件
        output_path = sessions_dir / f"{self.session_id}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

        return output_path
