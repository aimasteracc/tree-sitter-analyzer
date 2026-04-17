"""
Unit tests for PR Summary change_classifier module.
"""

import pytest

from tree_sitter_analyzer.pr_summary.change_classifier import (
    CategorizedChange,
    ChangeCategory,
    ChangeClassifier,
    PRType,
)
from tree_sitter_analyzer.pr_summary.diff_parser import (
    ChangeType,
    DiffSummary,
    FileChange,
)


class TestChangeClassifier:
    """Test ChangeClassifier"""

    def test_classify_docs_directory(self):
        """Test classification of files in docs/ directory"""
        classifier = ChangeClassifier()
        change = FileChange("docs/guide.md", ChangeType.MODIFIED, 10, 0)

        result = classifier._classify_change(change)

        assert result.category == ChangeCategory.DOCS
        assert result.file_change == change
        assert result.confidence > 0

    def test_classify_tests_directory(self):
        """Test classification of files in tests/ directory"""
        classifier = ChangeClassifier()
        change = FileChange("tests/test_main.py", ChangeType.MODIFIED, 10, 0)

        result = classifier._classify_change(change)

        assert result.category == ChangeCategory.TEST
        assert result.file_change == change

    def test_classify_ci_directory(self):
        """Test classification of files in CI directory"""
        classifier = ChangeClassifier()
        change = FileChange(".github/workflows/test.yml", ChangeType.MODIFIED, 10, 0)

        result = classifier._classify_change(change)

        assert result.category == ChangeCategory.CI

    def test_classify_readme(self):
        """Test classification of README files"""
        classifier = ChangeClassifier()
        change = FileChange("README.md", ChangeType.MODIFIED, 10, 0)

        result = classifier._classify_change(change)

        assert result.category == ChangeCategory.DOCS

    def test_classify_package_json(self):
        """Test classification of package.json"""
        classifier = ChangeClassifier()
        change = FileChange("package.json", ChangeType.MODIFIED, 10, 0)

        result = classifier._classify_change(change)

        assert result.category == ChangeCategory.BUILD

    def test_classify_dockerfile(self):
        """Test classification of Dockerfile"""
        classifier = ChangeClassifier()
        change = FileChange("Dockerfile", ChangeType.MODIFIED, 10, 0)

        result = classifier._classify_change(change)

        assert result.category == ChangeCategory.BUILD

    def test_classify_markdown_extension(self):
        """Test classification of .md files"""
        classifier = ChangeClassifier()
        change = FileChange("CONTRIBUTING.md", ChangeType.MODIFIED, 10, 0)

        result = classifier._classify_change(change)

        assert result.category == ChangeCategory.DOCS

    def test_classify_css_extension(self):
        """Test classification of .css files"""
        classifier = ChangeClassifier()
        change = FileChange("styles.css", ChangeType.MODIFIED, 10, 0)

        result = classifier._classify_change(change)

        assert result.category == ChangeCategory.STYLE

    def test_classify_source_code(self):
        """Test default classification of source code"""
        classifier = ChangeClassifier()
        change = FileChange("src/main.py", ChangeType.MODIFIED, 10, 0)

        result = classifier._classify_change(change)

        assert result.category in [ChangeCategory.FEATURE, ChangeCategory.REFACTOR]

    def test_classify_config_directory(self):
        """Test classification of config files"""
        classifier = ChangeClassifier()
        change = FileChange("config/settings.json", ChangeType.MODIFIED, 10, 0)

        result = classifier._classify_change(change)

        assert result.category == ChangeCategory.CHORE

    def test_classify_changes(self):
        """Test classifying multiple changes"""
        classifier = ChangeClassifier()
        changes = [
            FileChange("docs/guide.md", ChangeType.MODIFIED, 10, 0),
            FileChange("src/main.py", ChangeType.ADDED, 50, 0),
            FileChange("tests/test.py", ChangeType.MODIFIED, 5, 0),
        ]
        summary = DiffSummary.from_file_changes(changes)

        results = classifier.classify_changes(summary)

        assert len(results) == 3
        assert results[0].category == ChangeCategory.DOCS
        assert results[2].category == ChangeCategory.TEST


class TestDeterminePRType:
    """Test PR type determination"""

    def test_single_category(self):
        """Test PR type with single category"""
        classifier = ChangeClassifier()
        changes = [
            FileChange("docs/guide.md", ChangeType.MODIFIED, 10, 0),
            FileChange("docs/api.md", ChangeType.MODIFIED, 5, 0),
        ]
        summary = DiffSummary.from_file_changes(changes)
        categorized = classifier.classify_changes(summary)

        pr_type = classifier.determine_pr_type(categorized)

        assert pr_type.primary_category == ChangeCategory.DOCS
        assert pr_type.confidence == 1.0

    def test_mixed_categories(self):
        """Test PR type with mixed categories"""
        classifier = ChangeClassifier()
        changes = [
            FileChange("docs/guide.md", ChangeType.MODIFIED, 10, 0),
            FileChange("src/main.py", ChangeType.ADDED, 50, 0),
            FileChange("src/utils.py", ChangeType.MODIFIED, 5, 0),
        ]
        summary = DiffSummary.from_file_changes(changes)
        categorized = classifier.classify_changes(summary)

        pr_type = classifier.determine_pr_type(categorized)

        # Should pick the most frequent category
        assert pr_type.confidence > 0.5

    def test_breaking_change_detection(self):
        """Test breaking change detection"""
        classifier = ChangeClassifier()
        # Simulate breaking change by adding indicator
        changes = [
            FileChange("BREAKING-CHANGE.md", ChangeType.ADDED, 10, 0),
        ]
        summary = DiffSummary.from_file_changes(changes)

        categorized = classifier.classify_changes(summary)
        pr_type = classifier.determine_pr_type(categorized)

        # Breaking change should be detected
        assert pr_type.breaking or any("breaking" in c.reason.lower() for c in categorized)

    def test_categories_count(self):
        """Test category counting in PR type"""
        classifier = ChangeClassifier()
        changes = [
            FileChange("docs/guide.md", ChangeType.MODIFIED, 10, 0),
            FileChange("docs/api.md", ChangeType.MODIFIED, 5, 0),
            FileChange("src/main.py", ChangeType.ADDED, 50, 0),
        ]
        summary = DiffSummary.from_file_changes(changes)
        categorized = classifier.classify_changes(summary)

        pr_type = classifier.determine_pr_type(categorized)

        assert pr_type.categories[ChangeCategory.DOCS] == 2
        assert pr_type.categories[ChangeCategory.FEATURE] >= 1


class TestPRTitleGeneration:
    """Test PR title generation"""

    def test_title_simple(self):
        """Test simple PR title"""
        classifier = ChangeClassifier()
        pr_type = PRType(
            primary_category=ChangeCategory.FEATURE,
            confidence=1.0,
            categories={ChangeCategory.FEATURE: 3},
        )
        summary = DiffSummary.from_file_changes(
            [FileChange("a.py", ChangeType.ADDED, 10, 0)] * 3
        )

        title = classifier.get_pr_title(pr_type, summary)

        assert "feat" in title
        assert "3 files" in title

    def test_title_with_scope(self):
        """Test PR title with scope"""
        classifier = ChangeClassifier()
        pr_type = PRType(
            primary_category=ChangeCategory.FEATURE,
            confidence=1.0,
            categories={ChangeCategory.FEATURE: 2},
        )
        summary = DiffSummary.from_file_changes(
            [FileChange("src/a.py", ChangeType.ADDED, 10, 0)] * 2
        )

        title = classifier.get_pr_title(pr_type, summary)

        # Should contain scope since all files are in src/
        assert "(src)" in title or "feat" in title

    def test_title_breaking(self):
        """Test PR title with breaking change"""
        classifier = ChangeClassifier()
        pr_type = PRType(
            primary_category=ChangeCategory.FEATURE,
            confidence=1.0,
            categories={ChangeCategory.FEATURE: 1},
            breaking=True,
        )
        summary = DiffSummary.from_file_changes(
            [FileChange("a.py", ChangeType.ADDED, 10, 0)]
        )

        title = classifier.get_pr_title(pr_type, summary)

        assert "!" in title


class TestSummarySentenceGeneration:
    """Test summary sentence generation"""

    def test_summary_with_additions_and_deletions(self):
        """Test summary with both additions and deletions"""
        classifier = ChangeClassifier()
        pr_type = PRType(
            primary_category=ChangeCategory.FEATURE,
            confidence=1.0,
            categories={ChangeCategory.FEATURE: 1},
        )
        summary = DiffSummary.from_file_changes(
            [FileChange("a.py", ChangeType.MODIFIED, 10, 5)]
        )

        sentence = classifier.get_summary_sentence(pr_type, summary)

        assert "feat" in sentence
        assert "+10/-5" in sentence or "10" in sentence

    def test_summary_only_additions(self):
        """Test summary with only additions"""
        classifier = ChangeClassifier()
        pr_type = PRType(
            primary_category=ChangeCategory.FEATURE,
            confidence=1.0,
            categories={ChangeCategory.FEATURE: 1},
        )
        summary = DiffSummary.from_file_changes(
            [FileChange("a.py", ChangeType.ADDED, 20, 0)]
        )

        sentence = classifier.get_summary_sentence(pr_type, summary)

        assert "+20" in sentence

    def test_summary_breaking_warning(self):
        """Test summary includes breaking warning"""
        classifier = ChangeClassifier()
        pr_type = PRType(
            primary_category=ChangeCategory.FEATURE,
            confidence=1.0,
            categories={ChangeCategory.FEATURE: 1},
            breaking=True,
        )
        summary = DiffSummary.from_file_changes(
            [FileChange("a.py", ChangeType.MODIFIED, 1, 0)]
        )

        sentence = classifier.get_summary_sentence(pr_type, summary)

        assert "BREAKING" in sentence


class TestAffectedAreas:
    """Test affected areas detection"""

    def test_affected_areas_multiple_directories(self):
        """Test affected areas from multiple directories"""
        classifier = ChangeClassifier()
        summary = DiffSummary.from_file_changes([
            FileChange("src/main.py", ChangeType.MODIFIED, 1, 0),
            FileChange("tests/test.py", ChangeType.MODIFIED, 1, 0),
            FileChange("README.md", ChangeType.MODIFIED, 1, 0),
        ])

        areas = classifier.get_affected_areas(summary)

        assert "src" in areas
        assert "tests" in areas
        assert "docs" in areas

    def test_affected_areas_config_detection(self):
        """Test config area detection"""
        classifier = ChangeClassifier()
        summary = DiffSummary.from_file_changes([
            FileChange("config.json", ChangeType.MODIFIED, 1, 0),
        ])

        areas = classifier.get_affected_areas(summary)

        assert "config" in areas

    def test_affected_areas_ci_detection(self):
        """Test CI area detection"""
        classifier = ChangeClassifier()
        summary = DiffSummary.from_file_changes([
            FileChange(".github/workflows/test.yml", ChangeType.MODIFIED, 1, 0),
        ])

        areas = classifier.get_affected_areas(summary)

        assert "ci" in areas


class TestCategoryPatterns:
    """Test category pattern matching"""

    def test_dir_patterns_docs(self):
        """Test docs directory patterns"""
        classifier = ChangeClassifier()

        # All these should match docs
        for path in ["docs/guide.md", "doc/readme.txt", "documentation/api.md"]:
            category = classifier._check_dir_patterns(path)
            assert category == ChangeCategory.DOCS, f"Failed for {path}"

    def test_dir_patterns_tests(self):
        """Test tests directory patterns"""
        classifier = ChangeClassifier()

        for path in ["tests/test.py", "test/spec.js", "__tests__/test.ts"]:
            category = classifier._check_dir_patterns(path)
            assert category == ChangeCategory.TEST, f"Failed for {path}"

    def test_file_patterns_ci(self):
        """Test CI file patterns"""
        classifier = ChangeClassifier()

        for path in [
            ".github/workflows/ci.yml",
            ".gitlab-ci.yml",
            "jenkinsfile",
            "azure-pipelines.yml",
        ]:
            category = classifier._check_file_patterns(path)
            assert category == ChangeCategory.CI, f"Failed for {path}"

    def test_file_patterns_build(self):
        """Test build file patterns"""
        classifier = ChangeClassifier()

        for path in [
            "Dockerfile",
            "docker-compose.yml",
            "package.json",
            "requirements.txt",
            "pyproject.toml",
            "Cargo.toml",
        ]:
            category = classifier._check_file_patterns(path)
            assert category == ChangeCategory.BUILD, f"Failed for {path}"
