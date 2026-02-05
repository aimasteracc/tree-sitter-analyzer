"""Data processing service module."""

from processors.text_processor import clean_text
from utils import helper


def process(raw_data):
    """Process raw data.

    Cross-file calls:
    - helper() from utils.py (absolute import)
    - clean_text() from processors/text_processor.py (absolute import)

    Args:
        raw_data: Raw data to process

    Returns:
        str: Processed data
    """
    # Clean the text first
    cleaned = clean_text(raw_data)

    # Apply helper transformation
    result = helper(cleaned)

    return result


def fetch_user_data(username):
    """Fetch user data from database (mock).

    Args:
        username: Username to fetch

    Returns:
        dict: User data dictionary
    """
    # Mock user data
    return {"username": username, "password": "hashed_password", "role": "user"}


def save_data(data):
    """Save data to storage (mock).

    Args:
        data: Data to save

    Returns:
        bool: True if saved successfully
    """
    return True
