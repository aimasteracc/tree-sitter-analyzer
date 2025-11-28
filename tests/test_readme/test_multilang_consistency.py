"""Tests for multi-language README structure consistency.

This module validates that all localized README files maintain
consistent structure across languages.
"""

import re
from pathlib import Path

# Constants
PROJECT_ROOT = Path(__file__).parent.parent.parent
README_PATH = PROJECT_ROOT / "README.md"
README_JA_PATH = PROJECT_ROOT / "README_ja.md"
README_ZH_PATH = PROJECT_ROOT / "README_zh.md"


def get_section_headers(readme_path: Path) -> list[str]:
    """Extract section headers from README."""
    if not readme_path.exists():
        return []

    content = readme_path.read_text(encoding="utf-8")
    headers = []

    for line in content.splitlines():
        if line.startswith("## "):
            # Extract emoji from header for comparison
            # Headers may have different translations but same emoji
            emoji_match = re.search(
                r"[\U0001F300-\U0001F9FF"
                r"\U0001F600-\U0001F64F"
                r"\U0001F680-\U0001F6FF"
                r"\U0001F1E0-\U0001F1FF"
                r"\U00002600-\U000027BF"
                r"\U0001F900-\U0001F9FF]",
                line,
            )
            if emoji_match:
                headers.append(emoji_match.group())

    return headers


class TestMultiLanguageConsistency:
    """Tests for multi-language README structure consistency."""

    # **Feature: readme-restructure, Property 4: Multi-language README Structure Consistency**
    # **Validates: Requirements 5.2**

    def test_japanese_readme_exists(self) -> None:
        """README_ja.md should exist."""
        assert README_JA_PATH.exists(), "README_ja.md does not exist"

    def test_chinese_readme_exists(self) -> None:
        """README_zh.md should exist."""
        assert README_ZH_PATH.exists(), "README_zh.md does not exist"

    def test_japanese_readme_section_count(self) -> None:
        """README_ja.md should have same number of sections as README.md."""
        en_headers = get_section_headers(README_PATH)
        ja_headers = get_section_headers(README_JA_PATH)

        assert len(ja_headers) == len(en_headers), (
            f"README_ja.md has {len(ja_headers)} sections, "
            f"README.md has {len(en_headers)} sections"
        )

    def test_chinese_readme_section_count(self) -> None:
        """README_zh.md should have same number of sections as README.md."""
        en_headers = get_section_headers(README_PATH)
        zh_headers = get_section_headers(README_ZH_PATH)

        assert len(zh_headers) == len(en_headers), (
            f"README_zh.md has {len(zh_headers)} sections, "
            f"README.md has {len(en_headers)} sections"
        )

    def test_section_emojis_match(self) -> None:
        """Section emojis should match across all README versions."""
        en_headers = get_section_headers(README_PATH)
        ja_headers = get_section_headers(README_JA_PATH)
        zh_headers = get_section_headers(README_ZH_PATH)

        # Compare emoji sequences
        assert en_headers == ja_headers, (
            f"Section emojis mismatch between README.md and README_ja.md:\n"
            f"EN: {en_headers}\n"
            f"JA: {ja_headers}"
        )

        assert en_headers == zh_headers, (
            f"Section emojis mismatch between README.md and README_zh.md:\n"
            f"EN: {en_headers}\n"
            f"ZH: {zh_headers}"
        )

    def test_language_switcher_present(self) -> None:
        """All READMEs should have language switcher links."""
        for readme_path, lang_name in [
            (README_PATH, "English"),
            (README_JA_PATH, "Japanese"),
            (README_ZH_PATH, "Chinese"),
        ]:
            content = readme_path.read_text(encoding="utf-8")

            # Check for links to other language versions
            assert (
                "README.md" in content or "English" in content
            ), f"{lang_name} README should link to English version"
            assert (
                "README_ja.md" in content or "日本語" in content
            ), f"{lang_name} README should link to Japanese version"
            assert (
                "README_zh.md" in content or "中文" in content or "简体中文" in content
            ), f"{lang_name} README should link to Chinese version"

    def test_all_readmes_under_500_lines(self) -> None:
        """All README versions should be under 500 lines."""
        max_lines = 500

        for readme_path, lang_name in [
            (README_PATH, "English"),
            (README_JA_PATH, "Japanese"),
            (README_ZH_PATH, "Chinese"),
        ]:
            lines = readme_path.read_text(encoding="utf-8").splitlines()
            assert len(lines) < max_lines, (
                f"{lang_name} README has {len(lines)} lines, "
                f"should be under {max_lines}"
            )
