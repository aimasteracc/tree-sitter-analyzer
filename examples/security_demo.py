#!/usr/bin/env python3
"""
Security Module Demonstration

This script demonstrates the enhanced security features implemented in Phase 1
of the tree-sitter-analyzer security improvements.
"""

import tempfile
from pathlib import Path

from tree_sitter_analyzer.exceptions import SecurityError
from tree_sitter_analyzer.security import (
    ProjectBoundaryManager,
    RegexSafetyChecker,
    SecurityValidator,
)


def demo_file_path_validation():
    """Demonstrate file path validation capabilities."""
    print("🔒 File Path Validation Demo")
    print("=" * 50)

    # Create temporary project directory
    with tempfile.TemporaryDirectory() as temp_dir:
        validator = SecurityValidator(temp_dir)

        test_cases = [
            ("src/main.py", "✅ Valid relative path"),
            ("", "❌ Empty path"),
            ("src/test\x00.py", "❌ Null byte injection"),
            ("/etc/passwd", "❌ Absolute path"),
            ("C:\\Windows\\System32", "❌ Windows drive letter"),
            ("../../../etc/passwd", "❌ Path traversal attack"),
            ("src/../../../etc/passwd", "❌ Nested path traversal"),
        ]

        for path, description in test_cases:
            is_valid, error = validator.validate_file_path(path, temp_dir)
            status = "PASS" if is_valid else "BLOCK"
            print(f"  {description}")
            print(f"    Path: {path}")
            print(f"    Result: {status}")
            if error:
                print(f"    Error: {error}")
            print()


def demo_project_boundary_control():
    """Demonstrate project boundary control."""
    print("🏗️ Project Boundary Control Demo")
    print("=" * 50)

    with tempfile.TemporaryDirectory() as temp_dir:
        # Create project structure
        temp_path = Path(temp_dir)
        project_root = temp_path / "project"
        project_root.mkdir(exist_ok=True)

        src_dir = project_root / "src"
        src_dir.mkdir(exist_ok=True)

        # Create test files
        project_file = src_dir / "main.py"
        with open(project_file, "w") as f:
            f.write("print('Hello from project')")

        outside_file = temp_path / "outside.py"
        with open(outside_file, "w") as f:
            f.write("print('Hello from outside')")

        # Initialize boundary manager
        boundary_manager = ProjectBoundaryManager(str(project_root))

        test_files = [
            (str(project_file), "File inside project"),
            (str(outside_file), "File outside project"),
            ("/etc/passwd", "System file"),
        ]

        for file_path, description in test_files:
            is_within = boundary_manager.is_within_project(file_path)
            status = "ALLOWED" if is_within else "BLOCKED"
            print(f"  {description}")
            print(f"    Path: {file_path}")
            print(f"    Access: {status}")

            if is_within:
                rel_path = boundary_manager.get_relative_path(file_path)
                print(f"    Relative: {rel_path}")

            # Audit the access
            boundary_manager.audit_access(file_path, "read")
            print()


def demo_regex_safety_checker():
    """Demonstrate regex safety checking."""
    print("🔍 Regex Safety Checker Demo")
    print("=" * 50)

    checker = RegexSafetyChecker()

    test_patterns = [
        (r"hello.*world", "Safe pattern"),
        (r"[a-zA-Z0-9]+", "Safe character class"),
        (r"(.+)+", "Dangerous nested quantifiers"),
        (r"(.*)*", "Dangerous nested quantifiers"),
        (r"(.{0,})+", "Potential ReDoS pattern"),
        (r"(a|a)*", "Alternation with overlap"),
        (r"[", "Invalid syntax"),
        ("a" * 2000, "Pattern too long"),
    ]

    for pattern, description in test_patterns:
        print(f"  {description}")
        print(f"    Pattern: {pattern[:50]}{'...' if len(pattern) > 50 else ''}")

        is_safe, error = checker.validate_pattern(pattern)
        status = "SAFE" if is_safe else "DANGEROUS"
        print(f"    Result: {status}")

        if error:
            print(f"    Error: {error}")

        if is_safe:
            # Try to compile the pattern
            compiled = checker.create_safe_pattern(pattern)
            if compiled:
                print("    Compiled: Successfully")
            else:
                print("    Compiled: Failed")
        else:
            # Try to suggest a safer alternative
            suggestion = checker.suggest_safer_pattern(pattern)
            if suggestion:
                print(f"    Suggestion: {suggestion}")

        # Show complexity analysis for valid patterns
        if is_safe and len(pattern) <= 100:
            metrics = checker.analyze_complexity(pattern)
            if "error" not in metrics:
                print(f"    Complexity Score: {metrics.get('complexity_score', 0):.1f}")

        print()


def demo_input_sanitization():
    """Demonstrate input sanitization."""
    print("🧹 Input Sanitization Demo")
    print("=" * 50)

    validator = SecurityValidator()

    test_inputs = [
        ("Hello, World!", "Clean input"),
        ("Hello\x00World", "Null byte injection"),
        ("Hello\x01\x02World\x7f", "Control characters"),
        ("Normal text", "Normal text"),
        ("a" * 50, "Long but acceptable"),
        ("a" * 2000, "Too long input"),
    ]

    for input_text, description in test_inputs:
        print(f"  {description}")
        print(
            f"    Input: {repr(input_text[:50])}{'...' if len(input_text) > 50 else ''}"
        )

        try:
            sanitized = validator.sanitize_input(input_text, max_length=1000)
            print(
                f"    Sanitized: {repr(sanitized[:50])}{'...' if len(sanitized) > 50 else ''}"
            )
            print("    Status: CLEANED")
        except SecurityError as e:
            print(f"    Error: {e}")
            print("    Status: REJECTED")

        print()


def demo_comprehensive_security():
    """Demonstrate comprehensive security workflow."""
    print("🛡️ Comprehensive Security Workflow Demo")
    print("=" * 50)

    with tempfile.TemporaryDirectory() as temp_dir:
        # Setup
        temp_path = Path(temp_dir)
        project_root = temp_path / "secure_project"
        project_root.mkdir(exist_ok=True)

        validator = SecurityValidator(str(project_root))

        # Simulate a real-world scenario
        scenarios = [
            {
                "name": "Legitimate file access",
                "file_path": "src/utils.py",
                "regex_pattern": r"def\s+\w+\s*\(",
                "user_input": "search_term",
            },
            {
                "name": "Path traversal attack",
                "file_path": "../../../etc/passwd",
                "regex_pattern": r"root:.*",
                "user_input": "malicious_input",
            },
            {
                "name": "ReDoS attack attempt",
                "file_path": "src/main.py",
                "regex_pattern": r"(.+)+",
                "user_input": "normal_input",
            },
            {
                "name": "Input injection attempt",
                "file_path": "src/data.py",
                "regex_pattern": r"data\s*=\s*.*",
                "user_input": "malicious\x00\x01input",
            },
        ]

        for scenario in scenarios:
            print(f"  Scenario: {scenario['name']}")

            # Validate file path
            file_valid, file_error = validator.validate_file_path(
                scenario["file_path"], str(project_root)
            )
            print(f"    File Path: {'✅ SAFE' if file_valid else '❌ BLOCKED'}")
            if file_error:
                print(f"      Error: {file_error}")

            # Validate regex pattern
            regex_valid, regex_error = validator.validate_regex_pattern(
                scenario["regex_pattern"]
            )
            print(f"    Regex Pattern: {'✅ SAFE' if regex_valid else '❌ BLOCKED'}")
            if regex_error:
                print(f"      Error: {regex_error}")

            # Sanitize user input
            try:
                sanitized_input = validator.sanitize_input(scenario["user_input"])
                print("    User Input: ✅ SANITIZED")
                if sanitized_input != scenario["user_input"]:
                    print(f"      Original: {repr(scenario['user_input'])}")
                    print(f"      Sanitized: {repr(sanitized_input)}")
            except SecurityError as e:
                print("    User Input: ❌ REJECTED")
                print(f"      Error: {e}")

            # Overall security assessment
            overall_safe = file_valid and regex_valid
            print(
                f"    Overall: {'🟢 SAFE TO PROCEED' if overall_safe else '🔴 SECURITY RISK'}"
            )
            print()


def main():
    """Run all security demonstrations."""
    print("🔐 Tree-sitter Analyzer Security Module Demo")
    print("=" * 60)
    print("This demo showcases the enhanced security features implemented")
    print("in Phase 1 of the security improvements.")
    print("=" * 60)
    print()

    try:
        demo_file_path_validation()
        demo_project_boundary_control()
        demo_regex_safety_checker()
        demo_input_sanitization()
        demo_comprehensive_security()

        print("✅ Security Demo Completed Successfully!")
        print("\nKey Security Features Demonstrated:")
        print("  • Multi-layer file path validation")
        print("  • Project boundary enforcement")
        print("  • ReDoS attack prevention")
        print("  • Input sanitization")
        print("  • Comprehensive security workflow")

    except Exception as e:
        print(f"❌ Demo failed with error: {e}")
        raise


if __name__ == "__main__":
    main()
