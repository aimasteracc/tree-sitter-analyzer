"""Shared fixtures for language plugin tests."""

import pytest


@pytest.fixture
def sample_python_source():
    """Sample Python source code for language plugin testing."""
    return '''
class MyClass:
    """A sample class."""

    def __init__(self, name: str):
        self.name = name

    def greet(self) -> str:
        return f"Hello, {self.name}"

def standalone_function(x: int, y: int) -> int:
    """A standalone function."""
    return x + y

async def async_function():
    """An async function."""
    pass
'''


@pytest.fixture
def sample_javascript_source():
    """Sample JavaScript source code for language plugin testing."""
    return '''
class MyClass {
    constructor(name) {
        this.name = name;
    }

    greet() {
        return `Hello, ${this.name}`;
    }
}

function standaloneFunction(x, y) {
    return x + y;
}

const arrowFunction = (x) => x * 2;

export default MyClass;
'''


@pytest.fixture
def sample_typescript_source():
    """Sample TypeScript source code for language plugin testing."""
    return '''
interface Greeter {
    greet(): string;
}

class MyClass implements Greeter {
    constructor(private name: string) {}

    greet(): string {
        return `Hello, ${this.name}`;
    }
}

function standaloneFunction(x: number, y: number): number {
    return x + y;
}

type Result = string | number;

export { MyClass, Result };
'''


@pytest.fixture
def sample_java_source():
    """Sample Java source code for language plugin testing."""
    return '''
public class MyClass {
    private String name;

    public MyClass(String name) {
        this.name = name;
    }

    public String greet() {
        return "Hello, " + name;
    }

    public static int add(int x, int y) {
        return x + y;
    }
}
'''


@pytest.fixture
def sample_sql_source():
    """Sample SQL source code for language plugin testing."""
    return '''
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE
);

SELECT u.name, u.email
FROM users u
WHERE u.id > 10
ORDER BY u.name;

INSERT INTO users (name, email)
VALUES ('John', 'john@example.com');
'''
