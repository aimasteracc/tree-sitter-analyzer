"""
Main entry point for tree-sitter-analyzer v2.

Allows running as: python -m tree_sitter_analyzer_v2
"""

import sys

from tree_sitter_analyzer_v2.cli import main

if __name__ == "__main__":
    sys.exit(main())
