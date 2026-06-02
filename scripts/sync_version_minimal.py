#!/usr/bin/env python3
"""
Minimal Version Synchronization Script

This script only synchronizes version numbers in essential files:
- pyproject.toml (source of truth)
- pyproject.toml [tool.mcp].server_version (MCP metadata)
- tree_sitter_analyzer/__init__.py (main package version)

Other __init__.py files are left unchanged to reduce complexity.

Usage:
    python scripts/sync_version_minimal.py
    python scripts/sync_version_minimal.py --check  # Only check, don't update
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


def get_essential_version_files() -> list[Path]:
    """Get only essential files that need version synchronization"""
    essential_files = [
        Path("tree_sitter_analyzer/__init__.py"),  # Main package version
    ]

    # Only include files that exist
    return [f for f in essential_files if f.exists()]


def update_version_in_file(
    file_path: Path, new_version: str, *, check_only: bool = False
) -> tuple[bool, str]:
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
            if check_only:
                return True, f"⚠️  Would update {file_path.relative_to(Path('.'))}"
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


def update_mcp_server_version(
    new_version: str, *, check_only: bool = False
) -> tuple[bool, str]:
    """Update [tool.mcp].server_version in pyproject.toml."""
    pyproject_path = Path("pyproject.toml")
    try:
        content = pyproject_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = pyproject_path.read_text(encoding="cp1252")
        except UnicodeDecodeError:
            content = pyproject_path.read_text(encoding="latin-1")

    server_version_pattern = r'server_version\s*=\s*"([^"]+)"'
    if not re.search(server_version_pattern, content):
        return False, "⚠️  No [tool.mcp].server_version found in pyproject.toml"

    new_content = re.sub(
        server_version_pattern, f'server_version = "{new_version}"', content
    )
    if new_content == content:
        return False, "ℹ️  No changes needed in pyproject.toml [tool.mcp].server_version"
    if check_only:
        return True, "⚠️  Would update pyproject.toml [tool.mcp].server_version"

    pyproject_path.write_text(new_content, encoding="utf-8")
    return True, "✅ Updated pyproject.toml [tool.mcp].server_version"


def check_versions(check_only: bool = False) -> None:
    """Check and optionally update essential version numbers only"""
    current_version = get_version_from_pyproject()
    print(f"📦 Current version in pyproject.toml: {current_version}")

    essential_files = get_essential_version_files()
    print(f"🔍 Found {len(essential_files)} essential version files")

    updated_files = []

    server_success, server_message = update_mcp_server_version(
        current_version, check_only=check_only
    )
    if server_success:
        updated_files.append(Path("pyproject.toml"))
    print(server_message)

    for file_path in essential_files:
        success, message = update_version_in_file(
            file_path, current_version, check_only=check_only
        )
        if success:
            updated_files.append(file_path)
        print(message)

    print("\n" + "=" * 60)

    if updated_files:
        print(f"✅ Successfully updated {len(updated_files)} essential files:")
        for file_path in updated_files:
            print(f"   - {file_path.relative_to(Path('.'))}")

    if not check_only and updated_files:
        print("\n🚀 Minimal version synchronization completed!")
        print(f"   Essential files now have version: {current_version}")
        print("   Note: Other __init__.py files were left unchanged")
    elif check_only:
        print("\n🔍 Minimal version check completed!")
        print(f"   Found {len(updated_files)} essential files that would be updated")

    print("\n💡 This script only updates essential version files.")
    print("   For full synchronization, use: python scripts/sync_version.py")


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Minimal version synchronization for essential files only"
    )
    parser.add_argument(
        "--check", action="store_true", help="Only check versions, don't update"
    )

    args = parser.parse_args()

    try:
        check_versions(check_only=args.check)
    except Exception as e:
        print(f"❌ Minimal version synchronization failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
