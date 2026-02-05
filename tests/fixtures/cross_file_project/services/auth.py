"""Authentication service module."""

from utils import validate

from .data import fetch_user_data


def authenticate(username, password):
    """Authenticate a user.

    Cross-file calls:
    - validate() from utils.py (absolute import)
    - fetch_user_data() from services/data.py (relative import)

    Args:
        username: Username to authenticate
        password: Password to verify

    Returns:
        bool: True if authenticated, False otherwise
    """
    # Validate username
    if not validate(username):
        return False

    # Fetch user data
    user_data = fetch_user_data(username)

    if user_data and user_data.get("password") == password:
        return True

    return False


def logout(user_id):
    """Logout a user.

    Args:
        user_id: User ID to logout

    Returns:
        bool: True if logged out successfully
    """
    return True
