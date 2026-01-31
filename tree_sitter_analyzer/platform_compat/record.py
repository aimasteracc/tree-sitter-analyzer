#!/usr/bin/env python3
"""
Behavior Recording CLI.

CLI tool for recording SQL behavior profiles.

Key Features:
    - Profile recording
    - Output directory configuration
    - Platform detection
    - Profile persistence

Version: 1.10.5
Date: 2026-01-28
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter_analyzer.platform_compat.recorder import BehaviorRecorder
    from tree_sitter_analyzer.utils import setup_logger
else:
    try:
        from tree_sitter_analyzer.platform_compat.recorder import BehaviorRecorder
        from tree_sitter_analyzer.utils import setup_logger
    except ImportError as e:
        import logging

        logging.warning(f"Import fallback triggered in record: {e}")
        setup_logger = None  # type: ignore[assignment]

__all__ = ["main"]

logger = setup_logger(__name__)  # type: ignore


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record SQL behavior profile for current platform"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Directory to save the profile",
        default="tests/platform_profiles",
    )
    args = parser.parse_args()

    try:
        logger.info("Starting SQL behavior recording...")
        recorder = BehaviorRecorder()
        profile = recorder.record_all()

        logger.info(f"Recorded profile for {profile.platform_key}")
        logger.info(f"Captured {len(profile.behaviors)} behaviors")

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save profile
        # The save method expects a base path and constructs the structure {os}/{python}/profile.json
        # But if we want to save to a specific artifact directory in CI, we might want more control.
        # BehaviorProfile.save(base_path) does:
        # path = base_path / self.platform_key.replace("-", "/") / "profile.json"

        # Let's use the standard save mechanism
        profile.save(output_dir)
        logger.info(f"Profile saved to {output_dir}")

    except Exception as e:
        logger.error(f"Failed to record profile: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
