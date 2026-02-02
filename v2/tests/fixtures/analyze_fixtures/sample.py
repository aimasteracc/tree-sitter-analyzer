"""
Sample Python file for testing check_code_scale tool.

This file contains various Python elements to test metrics and structure extraction.
"""


class Calculator:
    """A simple calculator class."""

    def __init__(self):
        """Initialize the calculator."""
        self.result = 0

    def add(self, a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    def subtract(self, a: int, b: int) -> int:
        """Subtract two numbers."""
        return a - b


class DataProcessor:
    """Process data from various sources."""

    def __init__(self):
        """Initialize the data processor."""
        self.data = []

    def process(self, data: list[str]) -> list[str]:
        """Process a list of data items."""
        return [item.upper() for item in data]

    def transform(self, data: dict) -> dict:
        """Transform a dictionary."""
        return {k.upper(): v for k, v in data.items()}


def greet(name: str, greeting: str = "Hello") -> str:
    """Greet someone with a custom message."""
    return f"{greeting}, {name}!"


def helper_function(x: int) -> int:
    """A standalone helper function."""
    return x * 2


def main():
    """Main entry point."""
    calc = Calculator()
    result = calc.add(5, 3)
    print(f"Result: {result}")


if __name__ == "__main__":
    main()
