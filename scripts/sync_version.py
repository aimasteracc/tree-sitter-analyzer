#!/usr/bin/env python3
"""
Version Synchronization Script

This script automatically synchronizes version numbers across all __init__.py files
by reading the version from pyproject.toml and updating all Python files.

Usage:
    python scripts/sync_version.py
    python scripts/sync_version.py --check  # Only check, don't update
"""

import argparse
import re
import sys
from pathlib import Path


def get_version_from_pyproject() -> str:
    """Get current version from pyproject.toml"""
    pyproject_path = Path("pyproject.toml")
    if not pyproject_path.exists():
        print("❌ pyproject.toml not found")
        sys.exit(1)

    try:
        content = pyproject_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = pyproject_path.read_text(encoding="cp1252")
        except UnicodeDecodeError:
            content = pyproject_path.read_text(encoding="latin-1")

    version_match = re.search(r'version = "([^"]+)"', content)
    if not version_match:
        print("❌ Could not find version in pyproject.toml")
        sys.exit(1)

    return version_match.group(1)


def find_init_files() -> list[Path]:
    """Find all __init__.py files in the project"""
    project_root = Path(".")
    init_files = []

    for init_file in project_root.rglob("__init__.py"):
        # Skip virtual environments and build directories
        if any(
            part in str(init_file)
            for part in [".venv", "venv", "env", "__pycache__", "build", "dist"]
        ):
            continue
        init_files.append(init_file)

    return sorted(init_files)


def update_version_in_file(file_path: Path, new_version: str) -> tuple[bool, str]:
    """Update version in a single file"""
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = file_path.read_text(encoding="cp1252")
        except UnicodeDecodeError:
            content = file_path.read_text(encoding="latin-1")

    # Pattern to match __version__ = "x.x.x"
    version_pattern = r'__version__\s*=\s*["\']([^"\']+)["\']'

    if re.search(version_pattern, content):
        # Update existing version
        new_content = re.sub(version_pattern, f'__version__ = "{new_version}"', content)
        if new_content != content:
            try:
                file_path.write_text(new_content, encoding="utf-8")
                return True, f"✅ Updated {file_path.relative_to(Path('.'))}"
            except Exception as e:
                return (
                    False,
                    f"❌ Failed to write {file_path.relative_to(Path('.'))}: {e}",
                )
        else:
            return False, f"ℹ️  No changes needed in {file_path.relative_to(Path('.'))}"
    else:
        return False, f"⚠️  No __version__ found in {file_path.relative_to(Path('.'))}"


def check_versions(check_only: bool = False) -> None:
    """Check and optionally update all version numbers"""
    current_version = get_version_from_pyproject()
    print(f"📦 Current version in pyproject.toml: {current_version}")

    init_files = find_init_files()
    print(f"🔍 Found {len(init_files)} __init__.py files")

    updated_files = []
    issues = []

    for init_file in init_files:
        success, message = update_version_in_file(init_file, current_version)
        if success:
            updated_files.append(init_file)
        elif "No __version__ found" in message:
            issues.append(message)
        print(message)

    print("\n" + "=" * 60)

    if updated_files:
        print(f"✅ Successfully updated {len(updated_files)} files:")
        for file_path in updated_files:
            print(f"   - {file_path.relative_to(Path('.'))}")

    if issues:
        print("\n⚠️  Files without __version__ (consider adding):")
        for issue in issues:
            print(f"   - {issue}")

    if not check_only and updated_files:
        print("\n🚀 Version synchronization completed!")
        print(f"   All __init__.py files now have version: {current_version}")
    elif check_only:
        print("\n🔍 Version check completed!")
        print(f"   Found {len(updated_files)} files that would be updated")


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Synchronize version numbers across all __init__.py files"
    )
    parser.add_argument(
        "--check", action="store_true", help="Only check versions, don't update"
    )

    args = parser.parse_args()

    try:
        check_versions(check_only=args.check)
    except Exception as e:
        print(f"❌ Version synchronization failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
