"""
PR Summary - Git Diff Parser

解析 git diff 输出，提取文件变更信息。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ChangeType(Enum):
    """文件变更类型"""
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


@dataclass
class FileChange:
    """单个文件的变更信息"""
    path: str
    change_type: ChangeType
    additions: int
    deletions: int
    is_binary: bool = False

    @property
    def net_lines(self) -> int:
        """净增行数"""
        return self.additions - self.deletions


@dataclass
class DiffSummary:
    """Diff 摘要统计"""
    files: list[FileChange]
    total_additions: int
    total_deletions: int
    total_files_changed: int

    @property
    def net_lines(self) -> int:
        """净增行数"""
        return self.total_additions - self.total_deletions

    @classmethod
    def from_file_changes(cls, changes: list[FileChange]) -> DiffSummary:
        """从 FileChange 列表创建摘要"""
        return cls(
            files=changes,
            total_additions=sum(c.additions for c in changes),
            total_deletions=sum(c.deletions for c in changes),
            total_files_changed=len(changes),
        )


class DiffParser:
    """
    Git diff 输出解析器

    解析 git diff 或 git diff --stat 的输出。
    """

    # Regex patterns for diff parsing
    _DIFF_HEADER_RE = re.compile(r"^diff --git a/(.+) b/(.+)$")
    _NEW_FILE_RE = re.compile(r"^new file mode \d+$")
    _DELETED_FILE_RE = re.compile(r"^deleted file mode \d+$")
    _RENAME_RE = re.compile(r"^rename (from|to) (.+)$")
    _BINARY_FILE_RE = re.compile(r"^Binary file a/.+ b/.+ differs$")
    _HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
    _ADDITION_LINE_RE = re.compile(r"^\+")
    _DELETION_LINE_RE = re.compile(r"^-")

    # Regex for --stat output
    _STAT_LINE_RE = re.compile(r"^(.+) \| (\d+) ([\+\-]+)$")

    def parse_diff(self, diff_output: str) -> DiffSummary:
        """
        解析完整的 git diff 输出

        Args:
            diff_output: git diff 命令的输出

        Returns:
            DiffSummary 包含所有文件变更
        """
        changes: list[FileChange] = []
        lines = diff_output.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i]

            # Check for diff header
            header_match = self._DIFF_HEADER_RE.match(line)
            if header_match:
                change = self._parse_file_diff(lines, i)
                if change:
                    changes.append(change)
                    # Skip to next file
                    while i < len(lines) and not self._DIFF_HEADER_RE.match(lines[i]):
                        i += 1
                    continue

            i += 1

        return DiffSummary.from_file_changes(changes)

    def _parse_file_diff(self, lines: list[str], start_idx: int) -> FileChange | None:
        """解析单个文件的 diff"""
        path: str | None = None
        change_type = ChangeType.MODIFIED
        additions = 0
        deletions = 0
        is_binary = False

        i = start_idx
        while i < len(lines):
            line = lines[i]

            # Check for next file
            if self._DIFF_HEADER_RE.match(line) and i > start_idx:
                break

            # Extract path from diff header
            header_match = self._DIFF_HEADER_RE.match(line)
            if header_match:
                path = header_match.group(2)  # b/ path

            # Check for new file
            if self._NEW_FILE_RE.match(line):
                change_type = ChangeType.ADDED

            # Check for deleted file
            if self._DELETED_FILE_RE.match(line):
                change_type = ChangeType.DELETED

            # Check for binary file
            if self._BINARY_FILE_RE.match(line) or "Binary file" in line:
                is_binary = True
                break

            # Check for rename
            rename_match = self._RENAME_RE.match(line)
            if rename_match and rename_match.group(1) == "to":
                change_type = ChangeType.RENAMED

            # Count additions/deletions in hunk
            if self._HUNK_HEADER_RE.match(line):
                while i + 1 < len(lines) and not lines[i + 1].startswith("@@"):
                    i += 1
                    if i >= len(lines):
                        break
                    next_line = lines[i]
                    if next_line.startswith("+") and not next_line.startswith("++"):
                        additions += 1
                    elif next_line.startswith("-") and not next_line.startswith("--"):
                        deletions += 1

            i += 1

        if path:
            return FileChange(
                path=path,
                change_type=change_type,
                additions=additions,
                deletions=deletions,
                is_binary=is_binary,
            )
        return None

    def parse_stat(self, stat_output: str) -> DiffSummary:
        """
        解析 git diff --stat 输出

        Args:
            stat_output: git diff --stat 命令的输出

        Returns:
            DiffSummary 包含所有文件变更
        """
        changes: list[FileChange] = []
        lines = stat_output.split("\n")

        for line in lines:
            match = self._STAT_LINE_RE.match(line.strip())
            if match:
                path = match.group(1).strip()
                _total_changes = int(match.group(2))
                symbols = match.group(3)

                additions = symbols.count("+")
                deletions = symbols.count("-")

                # Determine change type from path or context
                # Default to MODIFIED, caller can adjust
                changes.append(
                    FileChange(
                        path=path,
                        change_type=ChangeType.MODIFIED,
                        additions=additions,
                        deletions=deletions,
                    )
                )

        return DiffSummary.from_file_changes(changes)

    def parse_repository(
        self,
        repo_path: Path | str,
        base: str = "main",
        head: str = "HEAD",
    ) -> DiffSummary:
        """
        解析仓库的 git diff

        Args:
            repo_path: 仓库路径
            base: 基础分支/commit
            head: 当前分支/commit

        Returns:
            DiffSummary 包含所有文件变更
        """
        import subprocess

        repo = Path(repo_path)

        # Try git diff first
        try:
            result = subprocess.run(
                ["git", "diff", f"{base}...{head}", "--stat"],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0 and result.stdout.strip():
                return self.parse_stat(result.stdout)
        except (FileNotFoundError, subprocess.SubprocessError):
            pass

        # Fallback to empty summary
        return DiffSummary.from_file_changes([])

    def get_file_extensions(self, summary: DiffSummary) -> dict[str, int]:
        """
        统计变更文件的扩展名

        Args:
            summary: DiffSummary

        Returns:
            扩展名到文件数量的映射
        """
        extensions: dict[str, int] = {}

        for change in summary.files:
            ext = Path(change.path).suffix or "(no extension)"
            extensions[ext] = extensions.get(ext, 0) + 1

        return extensions

    def get_changed_directories(self, summary: DiffSummary) -> dict[str, int]:
        """
        统计变更的目录

        Args:
            summary: DiffSummary

        Returns:
            目录到文件数量的映射
        """
        directories: dict[str, int] = {}

        for change in summary.files:
            parts = Path(change.path).parts
            if len(parts) > 1:
                # Use top-level directory
                directory = parts[0]
            else:
                directory = "(root)"
            directories[directory] = directories.get(directory, 0) + 1

        return directories
