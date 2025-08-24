#!/usr/bin/env python3
"""
Version 1.1.2 Release Preparation Script

This script handles the transition from v1.1.1 to v1.1.2:
1. Updates README statistics for v1.1.1
2. Prepares v1.1.2 release
3. Updates version numbers and documentation
"""

import argparse
import logging
import subprocess  # nosec B404
import sys
from pathlib import Path

import toml


class Version112ReleasePrep:
    def __init__(self, dry_run: bool = False, verbose: bool = False):
        self.project_root = Path(__file__).parent.parent
        self.dry_run = dry_run
        self.verbose = verbose

        # Setup logging
        level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(level=level, format="%(levelname)s: %(message)s")
        self.logger = logging.getLogger(__name__)

    def get_current_version(self) -> str:
        """Get current version from pyproject.toml"""
        pyproject_path = self.project_root / "pyproject.toml"
        with open(pyproject_path, encoding="utf-8") as f:
            data = toml.load(f)
        return data["project"]["version"]

    def update_version(self, new_version: str) -> bool:
        """Update version in pyproject.toml"""
        pyproject_path = self.project_root / "pyproject.toml"

        try:
            with open(pyproject_path, encoding="utf-8") as f:
                content = f.read()

            # Update version
            import re

            old_pattern = r'version = "([^"]+)"'
            new_content = re.sub(old_pattern, f'version = "{new_version}"', content)

            if self.dry_run:
                self.logger.info(
                    f"Would update version from {self.get_current_version()} to {new_version}"
                )
                return True

            with open(pyproject_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            self.logger.info(f"Updated version to {new_version}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to update version: {e}")
            return False

    def update_changelog(self, new_version: str) -> bool:
        """Update CHANGELOG.md with new version entry"""
        changelog_path = self.project_root / "CHANGELOG.md"

        try:
            with open(changelog_path, encoding="utf-8") as f:
                content = f.read()

            # Add new version entry at the top
            new_entry = f"""# Changelog

## [{new_version}] - 2025-08-24

### Release: v{new_version}

- Updated README quality metrics to reflect current test coverage (1,504 tests, 74.44% coverage)
- Enhanced GitFlow automation and branch management
- Improved cross-platform compatibility and path handling
- Fixed version synchronization across all documentation files

---

"""

            # Remove existing header and add new entry
            content = content.replace("# Changelog\n", "")
            new_content = new_entry + content

            if self.dry_run:
                self.logger.info(f"Would add new changelog entry for {new_version}")
                return True

            with open(changelog_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            self.logger.info(f"Updated CHANGELOG.md with {new_version}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to update CHANGELOG.md: {e}")
            return False

    def sync_readme_statistics(self) -> bool:
        """Sync README statistics using the improved updater"""
        try:
            self.logger.info("Syncing README statistics...")

            result = subprocess.run(  # nosec B603
                ["python", "scripts/improved_readme_updater.py"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                self.logger.info("README statistics synced successfully")
                return True
            else:
                self.logger.error(f"README sync failed: {result.stderr}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to sync README statistics: {e}")
            return False

    def run_tests(self) -> bool:
        """Run tests to ensure quality"""
        try:
            self.logger.info("Running tests to ensure quality...")

            result = subprocess.run(  # nosec B603
                ["uv", "run", "pytest", "tests/", "--tb=no", "-q"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=300,  # 5 minutes timeout
            )

            if result.returncode == 0:
                self.logger.info("All tests passed!")
                return True
            else:
                self.logger.error(f"Tests failed: {result.stderr}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to run tests: {e}")
            return False

    def create_release_branch(self, version: str) -> bool:
        """Create release branch for the new version"""
        try:
            release_branch = f"release/{version}"

            if self.dry_run:
                self.logger.info(f"Would create release branch: {release_branch}")
                return True

            # Create release branch
            result = subprocess.run(  # nosec B603
                ["git", "checkout", "-b", release_branch],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                self.logger.info(f"Created release branch: {release_branch}")
                return True
            else:
                self.logger.error(f"Failed to create release branch: {result.stderr}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to create release branch: {e}")
            return False

    def commit_changes(self, version: str) -> bool:
        """Commit all changes for the release"""
        try:
            if self.dry_run:
                self.logger.info("Would commit changes for release")
                return True

            # Add all changes
            result = subprocess.run(  # nosec B603
                ["git", "add", "."],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                self.logger.error(f"Failed to add changes: {result.stderr}")
                return False

            # Commit changes
            result = subprocess.run(  # nosec B603
                ["git", "commit", "-m", f"chore: Prepare release {version}"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                self.logger.info(f"Committed changes for release {version}")
                return True
            else:
                self.logger.error(f"Failed to commit changes: {result.stderr}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to commit changes: {e}")
            return False

    def push_release_branch(self, version: str) -> bool:
        """Push release branch to remote"""
        try:
            release_branch = f"release/{version}"

            if self.dry_run:
                self.logger.info(f"Would push release branch: {release_branch}")
                return True

            result = subprocess.run(  # nosec B603
                ["git", "push", "origin", release_branch],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                self.logger.info(f"Pushed release branch: {release_branch}")
                return True
            else:
                self.logger.error(f"Failed to push release branch: {result.stderr}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to push release branch: {e}")
            return False

    def execute_release_prep(self, new_version: str) -> bool:
        """Execute the complete release preparation process"""
        self.logger.info(f"Starting release preparation for {new_version}")

        # 1. Sync README statistics
        if not self.sync_readme_statistics():
            self.logger.error("Failed to sync README statistics")
            return False

        # 2. Run tests
        if not self.run_tests():
            self.logger.error("Tests failed, cannot proceed with release")
            return False

        # 3. Update version
        if not self.update_version(new_version):
            self.logger.error("Failed to update version")
            return False

        # 4. Update changelog
        if not self.update_changelog(new_version):
            self.logger.error("Failed to update changelog")
            return False

        # 5. Create release branch
        if not self.create_release_branch(new_version):
            self.logger.error("Failed to create release branch")
            return False

        # 6. Commit changes
        if not self.commit_changes(new_version):
            self.logger.error("Failed to commit changes")
            return False

        # 7. Push release branch
        if not self.push_release_branch(new_version):
            self.logger.error("Failed to push release branch")
            return False

        self.logger.info(
            f"Release preparation for {new_version} completed successfully!"
        )
        return True


def main():
    parser = argparse.ArgumentParser(description="Version 1.1.2 Release Preparation")
    parser.add_argument(
        "--version", default="1.1.2", help="New version to release (default: 1.1.2)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )

    args = parser.parse_args()

    prep = Version112ReleasePrep(dry_run=args.dry_run, verbose=args.verbose)
    success = prep.execute_release_prep(args.version)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
