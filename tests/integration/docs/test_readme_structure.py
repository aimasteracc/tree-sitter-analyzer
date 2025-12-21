"""Tests for README structure validation.

This module validates that README files follow the restructured format
with proper sections, line counts, and content organization.
"""

import re
from pathlib import Path

import pytest

# Constants
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
README_PATH = PROJECT_ROOT / "README.md"
README_JA_PATH = PROJECT_ROOT / "README_ja.md"
README_ZH_PATH = PROJECT_ROOT / "README_zh.md"

MAX_README_LINES = 500
MAX_WHATS_NEW_LINES = 15
HERO_SECTION_MAX_LINE = 20


def get_readme_content(readme_path: Path) -> str:
    """Read README content."""
    return readme_path.read_text(encoding="utf-8")


def get_readme_lines(readme_path: Path) -> list[str]:
    """Get README lines as list."""
    return get_readme_content(readme_path).splitlines()


def get_section_headers(content: str) -> list[tuple[int, str]]:
    """Extract section headers with their line numbers."""
    headers = []
    for i, line in enumerate(content.splitlines(), 1):
        if line.startswith("## "):
            headers.append((i, line))
    return headers


class TestReadmeLineCount:
    """Tests for README line count constraints."""

    # **Feature: readme-restructure, Property 1: README Line Count Constraint**
    # **Validates: Requirements 6.3**

    def test_readme_under_500_lines(self) -> None:
        """README.md should be under 500 lines."""
        lines = get_readme_lines(README_PATH)
        assert (
            len(lines) < MAX_README_LINES
        ), f"README.md has {len(lines)} lines, should be under {MAX_README_LINES}"


class TestHeroSection:
    """Tests for Hero section position and content."""

    # **Feature: readme-restructure, Property 2: Hero Section Position**
    # **Validates: Requirements 1.1**

    def test_hero_section_within_first_20_lines(self) -> None:
        """Hero section (project name, badges, value proposition) should be within first 20 lines."""
        lines = get_readme_lines(README_PATH)
        first_20_lines = "\n".join(lines[:HERO_SECTION_MAX_LINE])

        # Check for project name
        assert (
            "Tree-sitter Analyzer" in first_20_lines
        ), "Project name should appear in first 20 lines"

        # Check for badges (at least one badge)
        assert (
            "[![" in first_20_lines
        ), "At least one badge should appear in first 20 lines"

        # Check for value proposition (emoji + description)
        assert (
            ">" in first_20_lines or "Enterprise" in first_20_lines
        ), "Value proposition should appear in first 20 lines"


class TestSectionHeaders:
    """Tests for section header formatting."""

    # **Feature: readme-restructure, Property 3: Section Header Emoji Consistency**
    # **Validates: Requirements 6.1**

    def test_section_headers_have_emoji(self) -> None:
        """All major section headers should contain emoji for visual navigation."""
        content = get_readme_content(README_PATH)
        headers = get_section_headers(content)

        # Emoji pattern - matches common emoji ranges
        emoji_pattern = re.compile(
            r"[\U0001F300-\U0001F9FF"  # Miscellaneous Symbols and Pictographs
            r"\U0001F600-\U0001F64F"  # Emoticons
            r"\U0001F680-\U0001F6FF"  # Transport and Map Symbols
            r"\U0001F1E0-\U0001F1FF"  # Flags
            r"\U00002600-\U000027BF"  # Misc symbols
            r"\U0001F900-\U0001F9FF"  # Supplemental Symbols
            r"]"
        )

        headers_without_emoji = []
        for line_num, header in headers:
            if not emoji_pattern.search(header):
                headers_without_emoji.append(f"Line {line_num}: {header}")

        assert not headers_without_emoji, (
            "Section headers without emoji:\n" + "\n".join(headers_without_emoji)
        )


class TestWhatsNewSection:
    """Tests for What's New section brevity."""

    # **Feature: readme-restructure, Property 6: What's New Section Brevity**
    # **Validates: Requirements 7.3**

    def test_whats_new_section_brevity(self) -> None:
        """What's New section should be limited to 15 lines or fewer."""
        content = get_readme_content(README_PATH)
        lines = content.splitlines()

        whats_new_start = None
        whats_new_end = None

        for i, line in enumerate(lines):
            if "## ✨ What's New" in line:
                whats_new_start = i
            elif whats_new_start is not None and line.startswith("## "):
                whats_new_end = i
                break

        if whats_new_start is None:
            pytest.skip("What's New section not found")

        if whats_new_end is None:
            whats_new_end = len(lines)

        section_lines = whats_new_end - whats_new_start
        assert section_lines <= MAX_WHATS_NEW_LINES, (
            f"What's New section has {section_lines} lines, "
            f"should be {MAX_WHATS_NEW_LINES} or fewer"
        )


class TestAIIntegrationPosition:
    """Tests for AI Integration section position."""

    # **Feature: readme-restructure, Property 8: AI Integration Section Position**
    # **Validates: Requirements 2.1**

    def test_ai_integration_in_first_half(self) -> None:
        """AI Integration section should appear within first 50% of the document."""
        content = get_readme_content(README_PATH)
        lines = content.splitlines()
        total_lines = len(lines)
        half_point = total_lines // 2

        ai_section_line = None
        for i, line in enumerate(lines):
            if "## 🤖 AI Integration" in line:
                ai_section_line = i
                break

        assert ai_section_line is not None, "AI Integration section not found"

        assert ai_section_line < half_point, (
            f"AI Integration section at line {ai_section_line}, "
            f"should be before line {half_point} (first 50%)"
        )


class TestCLICommandsSection:
    """Tests for CLI Commands section completeness."""

    # **Feature: readme-restructure, Property 7: CLI Commands Section Completeness**
    # **Validates: Requirements 3.1**

    def test_cli_commands_has_five_examples(self) -> None:
        """Common CLI Commands section should contain at least 5 distinct command examples."""
        content = get_readme_content(README_PATH)
        lines = content.splitlines()

        cli_start = None
        cli_end = None

        for i, line in enumerate(lines):
            if "## 💻 Common CLI Commands" in line:
                cli_start = i
            elif cli_start is not None and line.startswith("## "):
                cli_end = i
                break

        if cli_start is None:
            pytest.skip("Common CLI Commands section not found")

        if cli_end is None:
            cli_end = len(lines)

        cli_section = "\n".join(lines[cli_start:cli_end])

        # Count command examples (lines starting with uv run)
        command_pattern = re.compile(r"uv run\s+")
        commands = command_pattern.findall(cli_section)

        assert len(commands) >= 5, (
            f"CLI Commands section has {len(commands)} command examples, "
            f"should have at least 5"
        )


class TestRequiredSections:
    """Tests for required sections existence."""

    REQUIRED_SECTIONS = [
        "What's New",
        "Quick Start",
        "AI Integration",
        "CLI Commands",
        "Supported Languages",
        "Features",
        "Quality",
        "Development",
        "Contributing",
        "Documentation",
    ]

    def test_required_sections_exist(self) -> None:
        """All required sections should exist in README."""
        content = get_readme_content(README_PATH)

        missing_sections = []
        for section in self.REQUIRED_SECTIONS:
            if section not in content:
                missing_sections.append(section)

        assert not missing_sections, f"Missing required sections: {missing_sections}"
