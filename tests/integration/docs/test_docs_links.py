"""Tests for documentation links validity.

This module validates that all links to docs/ directory in README.md
reference files that actually exist.
"""

import re
from pathlib import Path

# Constants
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
README_PATH = PROJECT_ROOT / "README.md"
DOCS_DIR = PROJECT_ROOT / "docs"


def get_readme_content() -> str:
    """Read README content."""
    return README_PATH.read_text(encoding="utf-8")


def extract_docs_links(content: str) -> list[tuple[str, int]]:
    """Extract all links to docs/ directory with line numbers."""
    links = []
    # Match markdown links to docs/ directory
    # Pattern: [text](docs/...) or (docs/...)
    pattern = re.compile(r"\(docs/([^)]+)\)")

    for i, line in enumerate(content.splitlines(), 1):
        for match in pattern.finditer(line):
            relative_path = f"docs/{match.group(1)}"
            links.append((relative_path, i))

    return links


class TestDocumentationLinksValidity:
    """Tests for documentation links validity."""

    # **Feature: readme-restructure, Property 5: Documentation Links Validity**
    # **Validates: Requirements 5.3**

    def test_all_docs_links_are_valid(self) -> None:
        """All links to docs/ directory should reference existing files."""
        content = get_readme_content()
        links = extract_docs_links(content)

        invalid_links = []
        for relative_path, line_num in links:
            # Remove any anchor (#...) from the path
            clean_path = relative_path.split("#")[0]
            full_path = PROJECT_ROOT / clean_path

            if not full_path.exists():
                invalid_links.append(
                    f"Line {line_num}: {relative_path} -> {full_path} does not exist"
                )

        assert not invalid_links, "Invalid documentation links found:\n" + "\n".join(
            invalid_links
        )

    def test_docs_directory_exists(self) -> None:
        """docs/ directory should exist."""
        assert DOCS_DIR.exists(), "docs/ directory does not exist"
        assert DOCS_DIR.is_dir(), "docs/ should be a directory"


class TestRequiredDocsFiles:
    """Tests for required documentation files existence."""

    REQUIRED_DOCS = [
        "docs/installation.md",
        "docs/cli-reference.md",
        "docs/smart-workflow.md",
        "docs/features.md",
        "docs/architecture.md",
        "docs/CONTRIBUTING.md",
        "docs/api/mcp_tools_specification.md",
    ]

    def test_required_docs_exist(self) -> None:
        """All required documentation files should exist."""
        missing_files = []
        for doc_path in self.REQUIRED_DOCS:
            full_path = PROJECT_ROOT / doc_path
            if not full_path.exists():
                missing_files.append(doc_path)

        assert not missing_files, "Missing required documentation files:\n" + "\n".join(
            missing_files
        )

    def test_docs_assets_directory_exists(self) -> None:
        """docs/assets/ directory should exist for GIF and images."""
        assets_dir = DOCS_DIR / "assets"
        assert assets_dir.exists(), "docs/assets/ directory does not exist"


class TestChangelogLink:
    """Tests for CHANGELOG.md link."""

    def test_changelog_exists(self) -> None:
        """CHANGELOG.md should exist in project root."""
        changelog_path = PROJECT_ROOT / "CHANGELOG.md"
        assert changelog_path.exists(), "CHANGELOG.md does not exist"

    def test_readme_links_to_changelog(self) -> None:
        """README should link to CHANGELOG.md."""
        content = get_readme_content()
        assert "CHANGELOG.md" in content, "README should contain link to CHANGELOG.md"
