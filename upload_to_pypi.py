#!/usr/bin/env python3
"""
Smart PyPI Upload Script for tree-sitter-analyzer
Automatically detects version and handles all edge cases
"""

import getpass
import os
import subprocess  # nosec B404
import sys
from pathlib import Path


def get_version_from_pyproject() -> str | None:
    """Get version from pyproject.toml"""
    try:
        # Try to use built-in tomllib (Python 3.11+)
        import tomllib

        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        return data["project"]["version"]
    except ImportError:
        # Fallback for older Python versions - use regex parsing
        try:
            with open("pyproject.toml", encoding="utf-8") as f:
                content = f.read()

            import re

            match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1)
            else:
                print("❌ Could not find version in pyproject.toml")
                return None
        except Exception as e:
            print(f"❌ Failed to read version from pyproject.toml: {e}")
            return None
    except Exception as e:
        print(f"❌ Failed to read version from pyproject.toml: {e}")
        return None


def get_version_from_package() -> str | None:
    """Get version from package __init__.py"""
    try:
        import tree_sitter_analyzer

        return tree_sitter_analyzer.__version__
    except Exception as e:
        print(f"❌ Failed to read version from package: {e}")
        return None


def get_version() -> str | None:
    """Get version using multiple methods"""
    # Try pyproject.toml first
    version = get_version_from_pyproject()
    if version:
        return version

    # Fallback to package
    version = get_version_from_package()
    if version:
        return version

    print("❌ Could not determine version")
    return None


def check_git_status() -> bool:
    """Check if git repo is clean"""
    try:
        result = subprocess.run(  # nosec B607, B603
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
        )
        if result.stdout.strip():
            print("⚠️  Warning: Git working directory is not clean")
            print("Uncommitted changes:")
            print(result.stdout)
            return False
        return True
    except subprocess.CalledProcessError:
        print("⚠️  Warning: Not in a git repository or git not available")
        return False


def check_git_tag(version: str) -> bool:
    """Check if git tag exists for version"""
    try:
        result = subprocess.run(  # nosec B607, B603
            ["git", "tag", "-l", f"v{version}"],
            capture_output=True,
            text=True,
            check=True,
        )
        if result.stdout.strip():
            print(f"✅ Git tag v{version} exists")
            return True
        else:
            print(f"⚠️  Warning: Git tag v{version} does not exist")
            return False
    except subprocess.CalledProcessError:
        return False


def check_packages(version: str) -> bool:
    """Check if packages are built"""
    dist_path = Path("dist")
    if not dist_path.exists():
        print("❌ dist/ directory not found. Please run 'uv build' first.")
        return False

    wheel_file = dist_path / f"tree_sitter_analyzer-{version}-py3-none-any.whl"
    tar_file = dist_path / f"tree_sitter_analyzer-{version}.tar.gz"

    missing_files = []
    if not wheel_file.exists():
        missing_files.append(str(wheel_file))
    if not tar_file.exists():
        missing_files.append(str(tar_file))

    if missing_files:
        print(f"❌ Package files not found for version {version}:")
        for file in missing_files:
            print(f"  - {file}")
        print("Please run 'uv build' first.")
        return False

    print("✅ Package files found:")
    print(f"  - {wheel_file}")
    print(f"  - {tar_file}")
    return True


def check_pypi_version(version: str) -> bool:
    """Check if version already exists on PyPI"""
    print(f"🔍 Checking if version {version} already exists on PyPI...")

    # Method 1: Direct PyPI API check (most reliable)
    try:
        import json
        import urllib.request

        url = "https://pypi.org/pypi/tree-sitter-analyzer/json"
        with urllib.request.urlopen(url, timeout=10) as response:  # nosec B310
            data = json.loads(response.read().decode())
            existing_versions = list(data.get("releases", {}).keys())

        if version in existing_versions:
            print(f"❌ Version {version} already exists on PyPI")
            print(
                f"📋 Existing versions: {', '.join(sorted(existing_versions, reverse=True)[:5])}..."
            )
            return False
        else:
            print(f"✅ Version {version} is new")
            return True

    except Exception as e:
        print(f"⚠️  PyPI API check failed ({e}), trying alternative method...")

    # Method 2: Try using requests as fallback
    try:
        import requests

        url = f"https://pypi.org/pypi/tree-sitter-analyzer/{version}/json"
        response = requests.head(url, timeout=10)
        if response.status_code == 200:
            print(f"❌ Version {version} already exists on PyPI")
            return False
        else:
            print(f"✅ Version {version} is new")
            return True
    except Exception as e:
        print(f"⚠️  Requests check failed ({e}), trying pip method...")

    # Method 3: Try pip index (may not work in all environments)
    try:
        result = subprocess.run(  # nosec B607, B603
            ["uv", "run", "pip", "index", "versions", "tree-sitter-analyzer"],
            capture_output=True,
            text=True,
            check=True,
        )
        if version in result.stdout:
            print(f"❌ Version {version} already exists on PyPI")
            return False
        else:
            print(f"✅ Version {version} is new")
            return True
    except Exception:
        print("⚠️  Could not reliably check PyPI versions")
        print("⚠️  Proceeding anyway - upload will fail if version exists")
        return True


def run_tests() -> bool:
    """Run tests before upload"""
    print("🧪 Running tests...")
    try:
        result = subprocess.run(  # nosec B607, B603
            ["uv", "run", "pytest", "--tb=short"], capture_output=True, text=True
        )
        if result.returncode == 0:
            print("✅ All tests passed")
            return True
        else:
            print("❌ Tests failed:")
            print(result.stdout)
            print(result.stderr)
            return False
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to run tests: {e}")
        return False


def upload_with_uv() -> bool:
    """Upload using uv"""
    print("\n🚀 Uploading to PyPI using uv...")

    # Check for .pypirc file first
    pypirc_path = Path.home() / ".pypirc"
    has_pypirc = pypirc_path.exists()

    if has_pypirc:
        print("📁 Found .pypirc configuration file")
        try:
            # Try upload without token (using .pypirc)
            cmd = ["uv", "publish"]
            print("Running: uv publish (using .pypirc)")

            result = subprocess.run(cmd, capture_output=True, text=True)  # nosec B607, B603

            if result.returncode == 0:
                print("✅ Successfully uploaded to PyPI using .pypirc!")
                if result.stdout:
                    print(result.stdout)
                return True
            else:
                # Check if it's a version conflict error
                error_output = (result.stderr or "") + (result.stdout or "")
                if any(
                    keyword in error_output.lower()
                    for keyword in [
                        "already exists",
                        "file already exists",
                        "conflict",
                        "version already exists",
                        "403",
                        "forbidden",
                    ]
                ):
                    print("❌ Upload failed: Version already exists on PyPI")
                    print("💡 Please increment the version number and try again")
                    if result.stderr:
                        print(f"Error details: {result.stderr}")
                    return False
                else:
                    print("⚠️  .pypirc upload failed, trying token method...")
                    print(f"Error: {result.stderr}")
                    # Fall through to token method
        except Exception as e:
            print(f"⚠️  .pypirc upload error: {e}, trying token method...")
            # Fall through to token method

    # Token method (fallback or when no .pypirc)
    if not has_pypirc:
        print("📁 No .pypirc found, using token authentication")

    # Check for environment variable first
    token = os.getenv("PYPI_API_TOKEN") or os.getenv("UV_PUBLISH_TOKEN")

    if not token:
        token = getpass.getpass("Enter your PyPI API token (starts with 'pypi-'): ")
        if not token.startswith("pypi-"):
            print("❌ Invalid token format. Token should start with 'pypi-'")
            return False

    try:
        # Upload using uv with token
        env = os.environ.copy()
        env["UV_PUBLISH_TOKEN"] = token

        cmd = ["uv", "publish"]
        print("Running: uv publish (using token)")

        result = subprocess.run(cmd, env=env, capture_output=True, text=True)  # nosec B607, B603

        if result.returncode == 0:
            print("✅ Successfully uploaded to PyPI!")
            if result.stdout:
                print(result.stdout)
            return True
        else:
            # Check if it's a version conflict error
            error_output = (result.stderr or "") + (result.stdout or "")
            if any(
                keyword in error_output.lower()
                for keyword in [
                    "already exists",
                    "file already exists",
                    "conflict",
                    "version already exists",
                    "403",
                    "forbidden",
                ]
            ):
                print("❌ Upload failed: Version already exists on PyPI")
                print("💡 Please increment the version number and try again")
                if result.stderr:
                    print(f"Error details: {result.stderr}")
            else:
                print("❌ Upload failed:")
                if result.stderr:
                    print(result.stderr)
                if result.stdout:
                    print(result.stdout)

                # Provide helpful tip about .pypirc
                if not has_pypirc:
                    print("\n💡 Tip: Consider setting up .pypirc for easier uploads:")
                    print("   Create ~/.pypirc with:")
                    print("   [distutils]")
                    print("   index-servers = pypi")
                    print("   ")
                    print("   [pypi]")
                    print("   username = __token__")
                    print("   password = pypi-your-token-here")
            return False

    except Exception as e:
        print(f"❌ Error during upload: {e}")
        return False


def main():
    """Main function"""
    print("🚀 Smart PyPI Upload for tree-sitter-analyzer")
    print("=" * 50)

    # Get version
    version = get_version()
    if not version:
        sys.exit(1)

    print(f"📦 Detected version: {version}")
    print()

    # Pre-upload checks
    print("🔍 Running pre-upload checks...")

    checks_passed = True

    # Check git status
    if not check_git_status():
        checks_passed = False

    # Check git tag
    if not check_git_tag(version):
        checks_passed = False

    # Check packages
    if not check_packages(version):
        checks_passed = False
        sys.exit(1)

    # Check PyPI version
    if not check_pypi_version(version):
        checks_passed = False
        sys.exit(1)

    if not checks_passed:
        response = input("\n⚠️  Some checks failed. Continue anyway? (y/N): ")
        if response.lower() != "y":
            print("Aborting upload.")
            sys.exit(1)

    # Optional: Run tests
    run_tests_choice = input("\n🧪 Run tests before upload? (Y/n): ")
    if run_tests_choice.lower() != "n":
        if not run_tests():
            response = input("\n❌ Tests failed. Continue anyway? (y/N): ")
            if response.lower() != "y":
                sys.exit(1)

    print(f"\n📋 Ready to upload tree-sitter-analyzer v{version}")
    print("✅ All checks passed (or skipped)")

    # Upload
    response = input("\n🚀 Proceed with upload? (Y/n): ")
    if response.lower() != "n":
        if upload_with_uv():
            print(f"\n🎉 Successfully uploaded tree-sitter-analyzer v{version}!")
            print("\n🧪 Test the installation:")
            print(f"  pip install tree-sitter-analyzer=={version}")
            print(
                '  python -c "import tree_sitter_analyzer; print(tree_sitter_analyzer.__version__)"'
            )
        else:
            print("\n❌ Upload failed. Please check the error messages above.")
            sys.exit(1)
    else:
        print("Upload cancelled.")


if __name__ == "__main__":
    main()
