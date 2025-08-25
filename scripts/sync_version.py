#!/usr/bin/env python3
"""
Version Synchronization Script

This script ensures all version numbers across the project are consistent.
It reads the version from pyproject.toml and updates all other locations.
"""

import re
import sys
from pathlib import Path


class VersionSynchronizer:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.version_patterns = {
            "pyproject.toml": [
                (r'version = "(\d+\.\d+\.\d+)"', 'version = "{version}"'),
            ],
            "README.md": [
                (r"version-(\d+\.\d+\.\d+)-blue\.svg", "version-{version}-blue.svg"),
                (
                    r"Latest Quality Achievements \(v(\d+\.\d+\.\d+)\)",
                    "Latest Quality Achievements (v{version})",
                ),
            ],
            "README_zh.md": [
                (r"version-(\d+\.\d+\.\d+)-blue\.svg", "version-{version}-blue.svg"),
                (r"最新质量成就（v(\d+\.\d+\.\d+)）", "最新质量成就（v{version}）"),
            ],
            "README_ja.md": [
                (r"version-(\d+\.\d+\.\d+)-blue\.svg", "version-{version}-blue.svg"),
                (r"最新の品質成果（v(\d+\.\d+\.\d+)）", "最新の品質成果（v{version}）"),
            ],
        }

    def get_current_version(self) -> str:
        """Get the current version from pyproject.toml"""
        pyproject_path = self.project_root / "pyproject.toml"

        if not pyproject_path.exists():
            raise FileNotFoundError("pyproject.toml not found")

        content = pyproject_path.read_text(encoding="utf-8")
        match = re.search(r'version = "(\d+\.\d+\.\d+)"', content)

        if not match:
            raise ValueError("Version not found in pyproject.toml")

        return match.group(1)

    def update_file_versions(
        self, file_path: Path, patterns: list[tuple[str, str]], target_version: str
    ) -> bool:
        """Update version numbers in a specific file"""
        if not file_path.exists():
            print(f"Warning: {file_path} not found, skipping...")
            return False

        content = file_path.read_text(encoding="utf-8")
        updated = False

        for pattern, replacement in patterns:
            # Find all matches first to report what we're updating
            matches = re.findall(pattern, content)
            if matches:
                for match in matches:
                    current_version = (
                        match
                        if isinstance(match, str)
                        else match[0]
                        if isinstance(match, tuple)
                        else str(match)
                    )
                    if current_version != target_version:
                        print(
                            f"  Updating {file_path.name}: {current_version} -> {target_version}"
                        )
                        updated = True

                # Perform the replacement
                content = re.sub(
                    pattern, replacement.format(version=target_version), content
                )

        if updated:
            file_path.write_text(content, encoding="utf-8")
            return True

        return False

    def sync_all_versions(self, target_version: str = None) -> bool:
        """Synchronize all version numbers across the project"""
        if target_version is None:
            target_version = self.get_current_version()

        print(f"Synchronizing all versions to: {target_version}")

        updated_files = []

        for file_name, patterns in self.version_patterns.items():
            file_path = self.project_root / file_name
            if self.update_file_versions(file_path, patterns, target_version):
                updated_files.append(file_name)

        if updated_files:
            print(f"\nUpdated files: {', '.join(updated_files)}")
            return True
        else:
            print("\nAll versions are already synchronized!")
            return False

    def check_version_consistency(self) -> bool:
        """Check if all versions are consistent"""
        current_version = self.get_current_version()
        print(f"Checking version consistency (reference: {current_version})")

        inconsistent_files = []

        for file_name, patterns in self.version_patterns.items():
            if file_name == "pyproject.toml":  # Skip the reference file
                continue

            file_path = self.project_root / file_name
            if not file_path.exists():
                continue

            content = file_path.read_text(encoding="utf-8")

            for pattern, _ in patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    found_version = (
                        match
                        if isinstance(match, str)
                        else match[0]
                        if isinstance(match, tuple)
                        else str(match)
                    )
                    if found_version != current_version:
                        print(
                            f"  ❌ {file_name}: found {found_version}, expected {current_version}"
                        )
                        inconsistent_files.append(file_name)
                        break

        if inconsistent_files:
            print(
                f"\n❌ Version inconsistency found in: {', '.join(set(inconsistent_files))}"
            )
            return False
        else:
            print("\n✅ All versions are consistent!")
            return True


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Synchronize version numbers across the project"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check version consistency without updating",
    )
    parser.add_argument(
        "--version",
        help="Target version to sync to (default: read from pyproject.toml)",
    )

    args = parser.parse_args()

    synchronizer = VersionSynchronizer()

    try:
        if args.check:
            consistent = synchronizer.check_version_consistency()
            sys.exit(0 if consistent else 1)
        else:
            updated = synchronizer.sync_all_versions(args.version)
            if updated:
                print("\n✅ Version synchronization completed!")
            sys.exit(0)

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
