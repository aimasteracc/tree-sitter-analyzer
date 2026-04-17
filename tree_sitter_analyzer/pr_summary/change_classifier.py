"""
PR Summary - Change Type Classifier

基于文件路径和内容分类代码变更类型。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from tree_sitter_analyzer.pr_summary.diff_parser import DiffSummary, FileChange


class ChangeCategory(Enum):
    """变更类别（用于 PR type）"""

    FEATURE = "feat"
    BUGFIX = "fix"
    REFACTOR = "refactor"
    DOCS = "docs"
    TEST = "test"
    CHORE = "chore"
    PERF = "perf"
    STYLE = "style"
    CI = "ci"
    BUILD = "build"


@dataclass
class CategorizedChange:
    """分类后的变更信息"""

    file_change: FileChange
    category: ChangeCategory
    confidence: float  # 0.0 to 1.0
    reason: str  # 分类理由
    is_breaking: bool = False  # 是否是破坏性变更


@dataclass
class PRType:
    """PR 类型判定"""

    primary_category: ChangeCategory
    confidence: float
    categories: dict[ChangeCategory, int]  # 各类别的文件数
    breaking: bool = False


class ChangeClassifier:
    """
    变更类型分类器

    基于以下规则分类：
    1. 文件路径模式（docs/, tests/, src/ 等）
    2. 文件扩展名（.md, .py, .js 等）
    3. 文件名模式（Dockerfile, package.json 等）
    """

    # Directory patterns for categories
    _DIR_PATTERNS: dict[ChangeCategory, list[str]] = {
        ChangeCategory.DOCS: ["docs/", "doc/", "documentation/", "guides/"],
        ChangeCategory.TEST: ["tests/", "test/", "__tests__/", "spec/"],
        ChangeCategory.CI: [".github/", ".gitlab-ci/", "ci/", "workflow/"],
        ChangeCategory.BUILD: ["build/", "tools/build/", "gradle/", "maven/"],
    }

    # File extension patterns for categories
    _EXT_PATTERNS: dict[ChangeCategory, list[str]] = {
        ChangeCategory.DOCS: [".md", ".rst", ".txt", ".adoc"],
        ChangeCategory.STYLE: [".css", ".scss", ".less", ".sass"],
        ChangeCategory.CI: [".yml", ".yaml"],  # Workflow files (json is too generic)
        ChangeCategory.BUILD: [
            ".gradle",
            ".maven",
            "pom.xml",
            "build.gradle",
            "Makefile",
            "CMakeLists.txt",
        ],
    }

    # File name patterns for special categories
    _FILE_PATTERNS: dict[ChangeCategory, list[re.Pattern[str]]] = {
        ChangeCategory.CI: [
            re.compile(r"\.github/workflows/.*\.ya?ml"),
            re.compile(r"\.gitlab-ci\.ya?ml"),
            re.compile(r"jenkins.*"),
            re.compile(r"azure-pipelines.*"),
        ],
        ChangeCategory.BUILD: [
            re.compile(r"Dockerfile"),
            re.compile(r"docker-compose.*"),
            re.compile(r"package\.json"),
            re.compile(r"requirements.*\.txt"),
            re.compile(r"pyproject\.toml"),
            re.compile(r"setup\.py"),
            re.compile(r"Cargo\.toml"),
            re.compile(r"go\.mod"),
        ],
        ChangeCategory.DOCS: [
            re.compile(r"README.*"),
            re.compile(r"CHANGELOG.*"),
            re.compile(r"CONTRIBUTING.*"),
            re.compile(r"LICENSE.*"),
        ],
    }

    # Breaking change indicators
    _BREAKING_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"BREAKING[- ]CHANGE", re.IGNORECASE),  # Conventional commits: space or dash
        re.compile(r"!:.*"),  # Conventional commits
        re.compile(r"\(.+\)!:"),  # Conventional commits with scope
    ]

    def classify_changes(self, summary: DiffSummary) -> list[CategorizedChange]:
        """
        分类所有变更

        Args:
            summary: DiffSummary

        Returns:
            CategorizedChange 列表
        """
        return [self._classify_change(change) for change in summary.files]

    def _classify_change(self, change: FileChange) -> CategorizedChange:
        """
        分类单个文件变更

        Args:
            change: FileChange

        Returns:
            CategorizedChange
        """
        path = change.path
        is_breaking = self._is_breaking_change(path)

        # Check breaking change patterns first
        if is_breaking:
            # Breaking changes are usually features/refactors
            category = ChangeCategory.FEATURE
            confidence = 0.9
            reason = "Breaking change detected in path"

        # Check directory patterns
        elif (dir_category := self._check_dir_patterns(path)) is not None:
            category = dir_category
            confidence = 0.8
            reason = f"File in {category.value}/ directory"

        # Check file name patterns
        elif (file_category := self._check_file_patterns(path)) is not None:
            category = file_category
            confidence = 0.85
            reason = f"File matches {category.value} pattern"

        # Check extension patterns
        elif (ext_category := self._check_ext_patterns(path)) is not None:
            category = ext_category
            confidence = 0.7
            reason = f"File has {category.value} extension"

        # Default classification based on source file location
        else:
            category = self._default_classification(path)
            confidence = 0.6
            reason = "Default classification for source file"

        return CategorizedChange(
            file_change=change,
            category=category,
            confidence=confidence,
            reason=reason,
            is_breaking=is_breaking,
        )

    def _is_breaking_change(self, path: str) -> bool:
        """检查是否是破坏性变更"""
        return any(p.search(path) for p in self._BREAKING_PATTERNS)

    def _check_dir_patterns(self, path: str) -> ChangeCategory | None:
        """检查目录模式"""
        path_lower = path.lower()

        for category, patterns in self._DIR_PATTERNS.items():
            if any(p in path_lower for p in patterns):
                return category

        return None

    def _check_file_patterns(self, path: str) -> ChangeCategory | None:
        """检查文件名模式"""
        filename = Path(path).name

        for category, patterns in self._FILE_PATTERNS.items():
            if any(p.search(filename) or p.search(path) for p in patterns):
                return category

        return None

    def _check_ext_patterns(self, path: str) -> ChangeCategory | None:
        """检查扩展名模式"""
        ext = Path(path).suffix.lower()

        for category, extensions in self._EXT_PATTERNS.items():
            if ext in extensions:
                return category

        return None

    def _default_classification(self, path: str) -> ChangeCategory:
        """
        默认分类规则

        源代码文件通常根据删除/新增比例判断：
        - 新增多 → feature
        - 删除多 → refactor/cleanup
        - 修改 → 根据路径判断
        """
        path_lower = path.lower()

        # Source directories
        if any(d in path_lower for d in ["src/", "lib/", "app/", "server/"]):
            return ChangeCategory.FEATURE

        # Config files
        if any(d in path_lower for d in ["config/", "configs/"]):
            return ChangeCategory.CHORE

        # Default to refactor for modifications
        return ChangeCategory.REFACTOR

    def determine_pr_type(self, changes: list[CategorizedChange]) -> PRType:
        """
        确定 PR 的主要类型

        Args:
            changes: CategorizedChange 列表

        Returns:
            PRType
        """
        # Count categories
        category_counts: dict[ChangeCategory, int] = dict.fromkeys(ChangeCategory, 0)
        breaking = False

        for change in changes:
            category_counts[change.category] += 1
            if change.is_breaking:
                breaking = True

        # Find primary category (most frequent)
        primary = max(category_counts, key=category_counts.get)  # type: ignore
        count = category_counts[primary]
        total = len(changes)

        confidence = count / total if total > 0 else 0.0

        return PRType(
            primary_category=primary,
            confidence=confidence,
            categories=category_counts,
            breaking=breaking,
        )

    def get_pr_title(self, pr_type: PRType, summary: DiffSummary) -> str:
        """
        生成 PR 标题

        Args:
            pr_type: PRType
            summary: DiffSummary

        Returns:
            PR 标题字符串
        """
        category = pr_type.primary_category.value
        breaking = "!" if pr_type.breaking else ""

        # Get most affected directory for context
        dirs: dict[str, int] = {}
        for change in summary.files:
            parts = Path(change.path).parts
            if parts:
                dirs[parts[0]] = dirs.get(parts[0], 0) + 1

        scope = ""
        if dirs:
            top_dir = max(dirs.keys(), key=lambda k: dirs[k])
            if len(dirs) == 1:
                scope = f"({top_dir})"

        file_count = summary.total_files_changed
        return f"{category}{scope}{breaking}: Update {file_count} file{'s' if file_count != 1 else ''}"

    def get_summary_sentence(self, pr_type: PRType, summary: DiffSummary) -> str:
        """
        生成摘要句子

        Args:
            pr_type: PRType
            summary: DiffSummary

        Returns:
            摘要句子
        """
        category = pr_type.primary_category.value
        file_count = summary.total_files_changed
        additions = summary.total_additions
        deletions = summary.total_deletions

        if pr_type.breaking:
            breaking = " ⚠️ **BREAKING CHANGE**"
        else:
            breaking = ""

        if additions > 0 and deletions > 0:
            changes = f"+{additions}/-{deletions} lines"
        elif additions > 0:
            changes = f"+{additions} lines"
        elif deletions > 0:
            changes = f"-{deletions} lines"
        else:
            changes = "0 lines"

        return f"This PR {category} changes to {file_count} file(s) ({changes}){breaking}."

    def get_affected_areas(self, summary: DiffSummary) -> list[str]:
        """
        获取受影响的代码区域

        Args:
            summary: DiffSummary

        Returns:
            受影响区域列表
        """
        areas: set[str] = set()

        for change in summary.files:
            path = change.path

            # Top-level directory
            parts = Path(path).parts
            if parts:
                areas.add(parts[0])

            # Language-specific detection
            if any(
                p in path.lower()
                for p in ["test", "spec", "__tests__", "tests", "testing"]
            ):
                areas.add("tests")
            if any(p in path.lower() for p in ["doc", "readme", "changelog"]):
                areas.add("docs")
            if any(
                p in path.lower()
                for p in ["config", "setting", "env", ".env", "dockerfile"]
            ):
                areas.add("config")
            if any(p in path.lower() for p in ["workflow", "ci", "build", "gradle"]):
                areas.add("ci")

        return sorted(areas)
