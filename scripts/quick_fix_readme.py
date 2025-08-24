#!/usr/bin/env python3
"""
Quick Fix Script for README Statistics Issues

This script quickly fixes common README statistics problems:
1. Version number mismatches
2. Statistics inconsistencies
3. CI validation failures

Usage:
    python scripts/quick_fix_readme.py
"""

import re
import subprocess
import sys
from pathlib import Path


def run_command(command: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result"""
    try:
        print(f"🔄 Running: {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True, check=check)
        return result
    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed: {' '.join(command)}")
        if check:
            sys.exit(1)
        return e


def get_current_version() -> str:
    """Get current version from pyproject.toml"""
    pyproject_path = Path("pyproject.toml")
    if not pyproject_path.exists():
        print("❌ pyproject.toml not found")
        sys.exit(1)

    try:
        content = pyproject_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Try different encodings
        try:
            content = pyproject_path.read_text(encoding="cp1252")
        except UnicodeDecodeError:
            content = pyproject_path.read_text(encoding="latin-1")

    version_match = re.search(r'version = "([^"]+)"', content)
    if not version_match:
        print("❌ Could not find version in pyproject.toml")
        sys.exit(1)

    return version_match.group(1)


def fix_version_in_readme(file_path: Path, current_version: str) -> bool:
    """Fix version number in README file"""
    if not file_path.exists():
        print(f"⚠️  File not found: {file_path}")
        return False

    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = file_path.read_text(encoding="cp1252")
        except UnicodeDecodeError:
            content = file_path.read_text(encoding="latin-1")

    # Find and replace version patterns
    patterns = [
        (r"version-(\d+\.\d+\.\d+)", f"version-{current_version}"),
        (r'version = "(\d+\.\d+\.\d+)"', f'version = "{current_version}"'),
    ]

    original_content = content
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)

    if content != original_content:
        try:
            file_path.write_text(content, encoding="utf-8")
            print(f"✅ Fixed version in {file_path.name}")
            return True
        except Exception as e:
            print(f"⚠️  Could not write to {file_path.name}: {e}")
            return False
    else:
        print(f"ℹ️  No version changes needed in {file_path.name}")
        return False


def sync_readme_statistics() -> bool:
    """Sync README statistics using the existing script"""
    print("📊 Syncing README statistics...")

    try:
        subprocess.run(
            ["uv", "run", "python", "scripts/improved_readme_updater.py"],
            capture_output=True,
            text=True,
            check=True,
        )
        print("✅ README statistics updated successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to update README statistics: {e}")
        return False


def check_git_status() -> bool:
    """Check git status and show changes"""
    print("🔍 Checking git status...")

    result = run_command(["git", "status", "--porcelain"], check=False)
    if result.stdout.strip():
        print("📝 Changes detected:")
        print(result.stdout)
        return True
    else:
        print("ℹ️  No changes detected")
        return False


def commit_and_push_changes() -> bool:
    """Commit and push README changes"""
    print("📤 Committing and pushing changes...")

    try:
        # Add README files
        run_command(["git", "add", "README.md", "README_zh.md", "README_ja.md"])

        # Commit
        run_command(
            ["git", "commit", "-m", "fix: Sync README statistics and version numbers"]
        )

        # Push
        run_command(["git", "push", "origin", "develop"])

        print("✅ Changes committed and pushed successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to commit and push: {e}")
        return False


def main():
    """Main function"""
    print("🚀 Quick Fix Script for README Issues")
    print("=" * 50)

    try:
        # Step 1: Get current version
        current_version = get_current_version()
        print(f"📦 Current version: {current_version}")

        # Step 2: Fix version numbers in README files
        readme_files = [Path("README.md"), Path("README_zh.md"), Path("README_ja.md")]

        version_fixed = False
        for readme_file in readme_files:
            if fix_version_in_readme(readme_file, current_version):
                version_fixed = True

        # Step 3: Sync README statistics
        stats_updated = sync_readme_statistics()

        # Step 4: Check git status
        has_changes = check_git_status()

        # Step 5: Commit and push if there are changes
        if has_changes:
            print("\n📋 Summary of fixes:")
            if version_fixed:
                print("   ✅ Version numbers fixed")
            if stats_updated:
                print("   ✅ Statistics synchronized")

            print("\n🚀 Ready to commit and push changes!")

            response = input("Do you want to commit and push these changes? (y/N): ")
            if response.lower() in ["y", "yes"]:
                commit_and_push_changes()
            else:
                print("ℹ️  Changes are staged but not committed")
                print("You can manually commit them later with:")
                print(
                    "   git commit -m 'fix: Sync README statistics and version numbers'"
                )
                print("   git push origin develop")
        else:
            print("🎉 No changes needed! README files are already up to date.")

        print("\n✅ Quick fix completed successfully!")

    except Exception as e:
        print(f"❌ Quick fix failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
