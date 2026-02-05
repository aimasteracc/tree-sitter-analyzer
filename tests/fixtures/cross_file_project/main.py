"""Main module that imports and calls functions from utils and config."""

from config import get_config
from utils import helper, validate


def main():
    """Main function that calls helper, validate, and get_config."""
    cfg = get_config()
    result = helper(cfg.get("input", "test"))
    is_valid = validate(result)
    return is_valid


def local_func():
    """Local function for testing same-file calls."""
    return main()
