"""
Pytest configuration and shared fixtures for tree-sitter-analyzer v2.

This module provides test fixtures and configuration for the entire test suite.
"""

import sys
from collections.abc import Generator
from pathlib import Path

import pytest

# Add v2 source to path for imports
v2_root = Path(__file__).parent.parent
sys.path.insert(0, str(v2_root))


@pytest.fixture
def project_root() -> Path:
    """Return the v2 project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def fixtures_dir(project_root: Path) -> Path:
    """Return the test fixtures directory."""
    return project_root / "tests" / "fixtures"


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Generator[Path, None, None]:
    """Provide a temporary workspace for tests."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    yield workspace


@pytest.fixture
def sample_python_code() -> str:
    """Sample Python code for testing."""
    return '''
def hello_world(name: str) -> str:
    """Say hello to someone."""
    return f"Hello, {name}!"

class Calculator:
    """A simple calculator."""

    def add(self, a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    def subtract(self, a: int, b: int) -> int:
        """Subtract b from a."""
        return a - b
'''


@pytest.fixture
def sample_typescript_code() -> str:
    """Sample TypeScript code for testing."""
    return """
interface User {
    id: number;
    name: string;
    email: string;
}

class UserService {
    private users: User[] = [];

    addUser(user: User): void {
        this.users.push(user);
    }

    getUser(id: number): User | undefined {
        return this.users.find(u => u.id === id);
    }
}
"""


@pytest.fixture
def sample_java_code() -> str:
    """Sample Java code for testing."""
    return """
package com.example;

import java.util.List;

public class UserService {
    private List<User> users;

    public UserService() {
        this.users = new ArrayList<>();
    }

    public void addUser(User user) {
        users.add(user);
    }

    public User getUser(int id) {
        return users.stream()
            .filter(u -> u.getId() == id)
            .findFirst()
            .orElse(null);
    }
}
"""
