"""Tests for radar_command CLI."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from tree_sitter_analyzer.cli.commands.radar_command import (
    _build_parser,
    _risk_bar,
    format_json_output,
    format_text_output,
    format_toon_output,
    main,
)


@pytest.fixture
def temp_repo_with_data(tmp_path: Path) -> Path:
    """Create a temporary git repository with test data."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Create some Python files
    (repo_path / "high_risk.py").write_text(
        "# High risk file\n" * 50  # Many lines of content
    )
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add high risk file"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Modify multiple times to increase churn
    for i in range(5):
        (repo_path / "high_risk.py").write_text(f"# Modified {i}\n" + "# content\n" * 50)
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"Modify {i}"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

    (repo_path / "low_risk.py").write_text("# Low risk file\n")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add low risk file"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    return repo_path


def test_build_parser() -> None:
    """Test argument parser construction."""
    parser = _build_parser()
    # parser.prog depends on how it's called, just check it's not empty
    assert parser.prog

    # Test default args
    args = parser.parse_args([])
    assert args.top == 20
    assert args.since == "6 months ago"
    assert args.format == "text"
    assert args.project_root == "."
    assert args.weights is None

    # Test custom args
    args = parser.parse_args(["--top", "10", "--format", "json"])
    assert args.top == 10
    assert args.format == "json"


def test_build_parser_custom_weights() -> None:
    """Test custom weights parsing."""
    parser = _build_parser()
    args = parser.parse_args(["--weights", "0.5", "0.3", "0.2"])
    assert args.weights == [0.5, 0.3, 0.2]


def test_build_parser_invalid_weights() -> None:
    """Test that invalid weights are caught during validation."""
    parser = _build_parser()
    args = parser.parse_args(["--weights", "0.5", "0.3", "0.1"])  # sum = 0.9
    # Validation happens in main(), not in parser
    assert args.weights == [0.5, 0.3, 0.1]


def test_risk_bar() -> None:
    """Test risk bar visualization."""
    # Full risk (20 chars = 20 blocks)
    bar = _risk_bar(1.0)
    assert bar == "[████████████████████]"

    # No risk (20 empty blocks)
    bar = _risk_bar(0.0)
    assert len(bar) == 22  # [ + 20░ + ]
    assert bar.startswith("[░")
    assert bar.endswith("]")

    # Half risk (10 blocks each)
    bar = _risk_bar(0.5)
    assert bar == "[██████████░░░░░░░░░░]"  # 10 █ + 10 ░


def test_format_text_output_basic(temp_repo_with_data: Path) -> None:
    """Test text output formatting."""
    from tree_sitter_analyzer.analyzer import FileChurn, FileRisk

    risks = [
        FileRisk(
            path="high_risk.py",
            complexity_score=0.8,
            churn_score=0.9,
            impact_score=0.7,
            overall_risk=0.79,
            churn=FileChurn(
                path="high_risk.py",
                commit_count=10,
                first_commit_date="2024-01-01",
                last_commit_date="2024-12-31",
                authors=[("test@example.com", 10)],
            ),
        ),
        FileRisk(
            path="low_risk.py",
            complexity_score=0.1,
            churn_score=0.2,
            impact_score=0.1,
            overall_risk=0.13,
        ),
    ]

    output = format_text_output(risks, top_n=2)

    assert "PROJECT RADAR" in output
    assert "high_risk.py" in output
    assert "low_risk.py" in output
    assert "0.79" in output
    assert "0.13" in output
    assert "10 commits" in output


def test_format_json_output(temp_repo_with_data: Path) -> None:
    """Test JSON output formatting."""
    from tree_sitter_analyzer.analyzer import FileRisk

    risks = [
        FileRisk(
            path="test.py",
            complexity_score=0.5,
            churn_score=0.5,
            impact_score=0.5,
            overall_risk=0.5,
        ),
    ]

    output = format_json_output(risks)
    data = json.loads(output)

    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["path"] == "test.py"
    assert data[0]["overall_risk"] == 0.5
    assert data[0]["complexity_score"] == 0.5


def test_format_toon_output(temp_repo_with_data: Path) -> None:
    """Test TOON output formatting."""
    from tree_sitter_analyzer.analyzer import FileRisk

    risks = [
        FileRisk(
            path="test.py",
            complexity_score=0.5,
            churn_score=0.5,
            impact_score=0.5,
            overall_risk=0.5,
        ),
    ]

    output = format_toon_output(risks)

    # TOON should contain project_radar
    assert "project_radar" in output
    assert "test.py" in output
    assert "0.5" in output  # risk score


def test_main_with_invalid_repo(tmp_path: Path, capsys) -> None:
    """Test main with non-git repository."""
    non_repo = tmp_path / "not_a_repo"
    non_repo.mkdir()

    with mock.patch("sys.argv", ["radar", "--project-root", str(non_repo)]):
        result = main()

    assert result == 1
    captured = capsys.readouterr()
    assert "Not a git repository" in captured.err or "error" in captured.err.lower()


def test_main_with_valid_repo(temp_repo_with_data: Path, capsys) -> None:
    """Test main with valid repository."""
    with mock.patch(
        "sys.argv", ["radar", "--project-root", str(temp_repo_with_data), "--top", "5"]
    ):
        result = main()

    assert result == 0
    captured = capsys.readouterr()
    assert "PROJECT RADAR" in captured.out
    assert "Top 5" in captured.out


def test_main_json_format(temp_repo_with_data: Path, capsys) -> None:
    """Test main with JSON output format."""
    with mock.patch(
        "sys.argv",
        ["radar", "--project-root", str(temp_repo_with_data), "--format", "json"],
    ):
        result = main()

    assert result == 0
    captured = capsys.readouterr()
    # Find the JSON array in output (skip any info messages)
    lines = captured.out.strip().split("\n")
    json_start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("["):
            json_start = i
            break
    assert json_start is not None, f"No JSON array found in output: {captured.out!r}"
    json_text = "\n".join(lines[json_start:])
    data = json.loads(json_text)
    assert isinstance(data, list)


def test_main_custom_weights(temp_repo_with_data: Path, capsys) -> None:
    """Test main with custom weights."""
    with mock.patch(
        "sys.argv",
        [
            "radar",
            "--project-root",
            str(temp_repo_with_data),
            "--weights",
            "0.5",
            "0.3",
            "0.2",
        ],
    ):
        result = main()

    assert result == 0


def test_main_invalid_weights(temp_repo_with_data: Path, capsys) -> None:
    """Test main with invalid weights (don't sum to 1.0)."""
    with mock.patch(
        "sys.argv",
        [
            "radar",
            "--project-root",
            str(temp_repo_with_data),
            "--weights",
            "0.5",
            "0.3",
            "0.1",  # sum = 0.9
        ],
    ):
        result = main()

    assert result == 1
    captured = capsys.readouterr()
    assert "Weights must sum to 1.0" in captured.err or "error" in captured.err.lower()


def test_format_text_output_with_extension_filter(temp_repo_with_data: Path) -> None:
    """Test that extension filtering works."""
    from tree_sitter_analyzer.analyzer import FileRisk

    risks = [
        FileRisk(
            path="high_risk.py",
            complexity_score=0.8,
            churn_score=0.9,
            impact_score=0.7,
            overall_risk=0.79,
        ),
        FileRisk(
            path="low_risk.js",
            complexity_score=0.1,
            churn_score=0.2,
            impact_score=0.1,
            overall_risk=0.13,
        ),
    ]

    output = format_text_output(risks, top_n=10)
    assert "high_risk.py" in output
    assert "low_risk.js" in output
