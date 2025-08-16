#!/usr/bin/env python3
"""
README Configuration Management

Centralized configuration for README statistics and content management.
This separates configuration from logic for better maintainability.
"""

from dataclasses import dataclass


@dataclass
class StatisticPattern:
    """Configuration for a statistic pattern to update"""

    name: str
    patterns: list[str]  # List of regex patterns to match
    format_template: str  # How to format the replacement
    description: str


@dataclass
class ReadmeConfig:
    """Configuration for README management"""

    # File paths
    readme_files = {"zh": "README_zh.md", "en": "README.md", "ja": "README_ja.md"}

    # Statistics patterns to update
    statistics = [
        StatisticPattern(
            name="test_count",
            patterns=[r"tests-\d+%20passed"],  # Only match badge URLs, not text content
            format_template="tests-{value}%20passed",
            description="Number of tests in the project",
        ),
        StatisticPattern(
            name="coverage",
            patterns=[
                r"coverage-\d+\.?\d*%25",
                r"覆盖率[：:]\s*(\d+\.?\d*)%",
                r"coverage[：:]\s*(\d+\.?\d*)%",
                r"カバレッジ[：:]\s*(\d+\.?\d*)%",
            ],
            format_template="coverage-{value:.2f}%25",
            description="Code coverage percentage",
        ),
        StatisticPattern(
            name="bigservice_lines",
            patterns=[r"(\d+) 行", r"(\d+)-line", r"Lines: (\d+)", r"(\d+)行"],
            format_template="{value}",
            description="Lines in BigService.java example",
        ),
        StatisticPattern(
            name="bigservice_methods",
            patterns=[
                r"(\d+) 个方法",
                r"(\d+) methods",
                r"Methods: (\d+)",
                r"(\d+)メソッド",
            ],
            format_template="{value}",
            description="Methods in BigService.java example",
        ),
        StatisticPattern(
            name="bigservice_fields",
            patterns=[
                r"Fields: (\d+)",
                r"(\d+) 个字段",
                r"(\d+) fields",
                r"(\d+)フィールド",
            ],
            format_template="{value}",
            description="Fields in BigService.java example",
        ),
    ]

    # Validation patterns - what must be present in README files
    validation_patterns = {
        "test_badge": r"tests-[0-9]+%20passed",
        "coverage_badge": r"coverage-[0-9]+\.[0-9]+%25",
        "bigservice_stats": r"Lines: [0-9]+",
        "version_info": r"v\d+\.\d+\.\d+",
    }

    # Commands to get statistics
    stat_commands = {
        "test_count": ["uv", "run", "pytest", "tests/", "--collect-only", "-q"],
        "coverage": [
            "uv",
            "run",
            "pytest",
            "tests/",
            "--cov=tree_sitter_analyzer",
            "--cov-report=term-missing",
        ],
        "bigservice_analysis": [
            "uv",
            "run",
            "python",
            "-m",
            "tree_sitter_analyzer",
            "examples/BigService.java",
            "--advanced",
            "--output-format=text",
        ],
    }


# Language-specific formatting rules
LANGUAGE_FORMATS = {
    "zh": {
        "test_count": "{value} 个测试",
        "coverage": "覆盖率 {value:.2f}%",
        "lines": "{value} 行",
        "methods": "{value} 个方法",
        "fields": "{value} 个字段",
    },
    "en": {
        "test_count": "{value} tests",
        "coverage": "coverage {value:.2f}%",
        "lines": "{value} lines",
        "methods": "{value} methods",
        "fields": "{value} fields",
    },
    "ja": {
        "test_count": "{value} テスト",
        "coverage": "カバレッジ {value:.2f}%",
        "lines": "{value}行",
        "methods": "{value}メソッド",
        "fields": "{value}フィールド",
    },
}
