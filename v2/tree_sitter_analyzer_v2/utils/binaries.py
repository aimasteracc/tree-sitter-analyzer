"""
Binary detection and validation for fd and ripgrep.

This module detects and validates external binaries (fd and ripgrep)
that provide fast file/content search capabilities.
"""

import logging
import platform
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class BinaryNotFoundError(Exception):
    """Raised when a required binary is not found."""

    pass


def get_fd_path() -> Path | None:
    """
    Get path to fd binary.

    Returns:
        Path to fd binary, or None if not found
    """
    fd_path = shutil.which("fd")
    return Path(fd_path) if fd_path else None


def get_ripgrep_path() -> Path | None:
    """
    Get path to ripgrep binary.

    Returns:
        Path to ripgrep binary (rg), or None if not found
    """
    rg_path = shutil.which("rg")
    return Path(rg_path) if rg_path else None


def check_fd_available() -> bool:
    """
    Check if fd binary is available.

    Returns:
        True if fd is installed and available
    """
    return get_fd_path() is not None


def check_ripgrep_available() -> bool:
    """
    Check if ripgrep binary is available.

    Returns:
        True if ripgrep is installed and available
    """
    return get_ripgrep_path() is not None


def get_fd_version() -> str | None:
    """
    Get fd version string.

    Returns:
        Version string (e.g., "8.7.0"), or None if fd not found
    """
    fd_path = get_fd_path()
    if not fd_path:
        return None

    try:
        result = subprocess.run(
            [str(fd_path), "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        # Output is like "fd 8.7.0"
        version_line = result.stdout.strip()
        if version_line:
            parts = version_line.split()
            if len(parts) >= 2:
                return parts[1]
        return version_line
    except Exception as e:
        logger.debug("Failed to get fd version: %s", e)
        return None


def get_ripgrep_version() -> str | None:
    """
    Get ripgrep version string.

    Returns:
        Version string (e.g., "13.0.0"), or None if ripgrep not found
    """
    rg_path = get_ripgrep_path()
    if not rg_path:
        return None

    try:
        result = subprocess.run(
            [str(rg_path), "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        # Output is like "ripgrep 13.0.0"
        version_line = result.stdout.strip().split("\n")[0]
        if version_line:
            parts = version_line.split()
            if len(parts) >= 2:
                return parts[1]
        return version_line
    except Exception as e:
        logger.debug("Failed to get ripgrep version: %s", e)
        return None


def get_fd_installation_instructions() -> str:
    """
    Get platform-specific installation instructions for fd.

    Returns:
        Installation instructions as string
    """
    system = platform.system().lower()

    instructions = {
        "darwin": "Install fd:\n  brew install fd",
        "linux": "Install fd:\n  apt install fd-find  # Debian/Ubuntu\n  "
        "dnf install fd-find  # Fedora\n  "
        "pacman -S fd  # Arch\n  "
        "cargo install fd-find  # Via Rust",
        "windows": "Install fd:\n  scoop install fd  # Scoop\n  "
        "choco install fd  # Chocolatey\n  "
        "cargo install fd-find  # Via Rust",
    }

    return instructions.get(
        system,
        "Install fd:\n  Visit https://github.com/sharkdp/fd for installation instructions",
    )


def get_ripgrep_installation_instructions() -> str:
    """
    Get platform-specific installation instructions for ripgrep.

    Returns:
        Installation instructions as string
    """
    system = platform.system().lower()

    instructions = {
        "darwin": "Install ripgrep:\n  brew install ripgrep",
        "linux": "Install ripgrep:\n  apt install ripgrep  # Debian/Ubuntu\n  "
        "dnf install ripgrep  # Fedora\n  "
        "pacman -S ripgrep  # Arch\n  "
        "cargo install ripgrep  # Via Rust",
        "windows": "Install ripgrep:\n  scoop install ripgrep  # Scoop\n  "
        "choco install ripgrep  # Chocolatey\n  "
        "cargo install ripgrep  # Via Rust",
    }

    return instructions.get(
        system,
        "Install ripgrep:\n  Visit https://github.com/BurntSushi/ripgrep for installation instructions",
    )


def require_fd() -> Path:
    """
    Require fd binary to be available.

    Returns:
        Path to fd binary

    Raises:
        BinaryNotFoundError: If fd is not found
    """
    fd_path = get_fd_path()
    if not fd_path:
        instructions = get_fd_installation_instructions()
        raise BinaryNotFoundError(
            f"fd binary not found.\n\n{instructions}\n\n"
            "fd is required for fast file search (10-20x faster than Python glob)."
        )
    return fd_path


def require_ripgrep() -> Path:
    """
    Require ripgrep binary to be available.

    Returns:
        Path to ripgrep binary

    Raises:
        BinaryNotFoundError: If ripgrep is not found
    """
    rg_path = get_ripgrep_path()
    if not rg_path:
        instructions = get_ripgrep_installation_instructions()
        raise BinaryNotFoundError(
            f"ripgrep (rg) binary not found.\n\n{instructions}\n\n"
            "ripgrep is required for fast content search (5-10x faster than Python regex)."
        )
    return rg_path


def get_binaries_status() -> dict[str, dict[str, bool | str]]:
    """
    Get status of all required binaries.

    Returns:
        Dictionary with status of each binary:
        {
            "fd": {"available": bool, "path": str, "version": str},
            "ripgrep": {"available": bool, "path": str, "version": str}
        }
    """
    status: dict[str, dict[str, bool | str]] = {}

    # Check fd
    fd_path = get_fd_path()
    fd_info: dict[str, bool | str] = {"available": fd_path is not None}
    if fd_path:
        fd_info["path"] = str(fd_path)
        fd_version = get_fd_version()
        if fd_version:
            fd_info["version"] = fd_version
    status["fd"] = fd_info

    # Check ripgrep
    rg_path = get_ripgrep_path()
    rg_info: dict[str, bool | str] = {"available": rg_path is not None}
    if rg_path:
        rg_info["path"] = str(rg_path)
        rg_version = get_ripgrep_version()
        if rg_version:
            rg_info["version"] = rg_version
    status["ripgrep"] = rg_info

    return status


def require_all_binaries() -> dict[str, dict]:
    """
    Require all binaries to be available.

    Returns:
        Status dictionary if all binaries are available

    Raises:
        BinaryNotFoundError: If any binary is not found
    """
    status = get_binaries_status()

    missing = []
    if not status["fd"]["available"]:
        missing.append("fd")
    if not status["ripgrep"]["available"]:
        missing.append("ripgrep")

    if missing:
        instructions = []
        if "fd" in missing:
            instructions.append(get_fd_installation_instructions())
        if "ripgrep" in missing:
            instructions.append(get_ripgrep_installation_instructions())

        raise BinaryNotFoundError(
            f"Missing required binaries: {', '.join(missing)}\n\n" + "\n\n".join(instructions)
        )

    return status


def can_use_fast_search() -> bool:
    """
    Check if fast search (fd + ripgrep) is available.

    This is a convenience function for graceful fallback scenarios.

    Returns:
        True if both fd and ripgrep are available
    """
    return check_fd_available() and check_ripgrep_available()
