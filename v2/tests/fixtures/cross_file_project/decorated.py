"""Module with decorated functions to test framework entry recognition.

Functions decorated with framework/builtin decorators should NOT be
flagged as dead code, even if they have no explicit callers within the project.
"""

from utils import helper


# Simulated framework decorators
def route(path):
    """Simulate Flask/FastAPI route decorator."""
    def route_wrapper(fn):
        return fn
    return route_wrapper


def command(name=None):
    """Simulate Click command decorator."""
    def command_wrapper(fn):
        return fn
    return command_wrapper


def fixture(fn):
    """Simulate pytest fixture decorator."""
    return fn


# --- These should NOT be dead code (they are framework-registered) ---

@route("/api/users")
def get_users():
    """API endpoint — called by web framework, not by project code."""
    return helper("users")


@command(name="deploy")
def deploy_command():
    """CLI command — called by Click framework, not by project code."""
    return "deployed"


@fixture
def db_session():
    """Test fixture — called by pytest framework, not by project code."""
    return "session"


class MyService:
    @property
    def name(self):
        """Property — accessed via attribute, not a direct call."""
        return "service"

    @staticmethod
    def create():
        """Static method — may be called via class, detected as method call."""
        return MyService()


# --- This IS dead code (no decorator, no caller, no import) ---

def orphan_function():
    """Truly dead — no decorator, no caller, no import."""
    return "orphan"
