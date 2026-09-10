#!/usr/bin/env python3
"""同步发布必需的版本元数据。

以 pyproject.toml 的项目版本为准，更新 MCP 元数据、包 __init__.py，
以及 server.json 的服务器版本和本项目 PyPI 包版本。
--check 只检查；发现漂移时返回非零状态。
"""

import argparse
import json
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
    """列出必须存在的包版本文件；缺失由读取步骤报告。"""
    essential_files = [
        Path("tree_sitter_analyzer/__init__.py"),  # Main package version
    ]

    return essential_files


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
            except OSError as e:
                raise OSError(f"Failed to write {file_path}: {e}") from e
        else:
            return False, f"ℹ️  No changes needed in {file_path.relative_to(Path('.'))}"
    else:
        raise ValueError(f"No __version__ found in {file_path}")


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
        raise ValueError("No [tool.mcp].server_version found in pyproject.toml")

    new_content = re.sub(
        server_version_pattern, f'server_version = "{new_version}"', content
    )
    if new_content == content:
        return False, "ℹ️  No changes needed in pyproject.toml [tool.mcp].server_version"
    if check_only:
        return True, "⚠️  Would update pyproject.toml [tool.mcp].server_version"

    pyproject_path.write_text(new_content, encoding="utf-8")
    return True, "✅ Updated pyproject.toml [tool.mcp].server_version"


def update_registry_version(
    new_version: str, *, check_only: bool = False, project_root: Path = Path(".")
) -> tuple[bool, str]:
    """同步注册表中服务器和本项目的 PyPI 包版本，保留其他字段。"""
    path = project_root / "server.json"
    metadata = json.loads(path.read_text(encoding="utf-8"))
    packages = [
        package
        for package in metadata["packages"]
        if package.get("registryType") == "pypi"
        and package.get("identifier") == "tree-sitter-analyzer"
    ]
    if not packages:
        raise ValueError("server.json is missing the tree-sitter-analyzer PyPI package")
    changed = metadata["version"] != new_version or any(
        package["version"] != new_version for package in packages
    )
    if not changed:
        return False, "No changes needed in server.json"
    if check_only:
        return True, "Would update server.json"
    metadata["version"] = new_version
    for package in packages:
        package["version"] = new_version
    path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return True, "Updated server.json"


def check_versions(check_only: bool = False) -> bool:
    """检查或同步必需版本，返回是否无需更改。"""
    current_version = get_version_from_pyproject()
    print(f"📦 Current version in pyproject.toml: {current_version}")

    essential_files = get_essential_version_files()
    print(f"🔍 Found {len(essential_files)} essential version files")

    updated_files = []
    registry_changed, registry_message = update_registry_version(
        current_version, check_only=check_only
    )
    if registry_changed:
        updated_files.append(Path("server.json"))
    print(registry_message)

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
    return not updated_files


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
        consistent = check_versions(check_only=args.check)
        if args.check and not consistent:
            sys.exit(1)
    except Exception as e:
        print(f"❌ Minimal version synchronization failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
