"""
Complex Python sample for testing advanced language features.

This file tests:
- Decorators (function, class, property)
- Class attributes
- Async functions and methods
- Nested classes
- Multiple inheritance
- Type annotations and generics
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import cache, lru_cache, wraps
from typing import Generic, Optional, TypeVar

# Type variables
T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")


# Function decorators
def timing_decorator(func):
    """Measure execution time."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


def cache_decorator(max_size: int = 128):
    """Cache with custom size."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return decorator


# Class with decorators and class attributes
@dataclass
@cache_decorator(max_size=256)
class Configuration:
    """Application configuration with decorators."""

    # Class attributes
    DEFAULT_TIMEOUT: int = 30
    MAX_RETRIES: int = 3
    VERSION: str = "1.0.0"

    # Instance attributes (from dataclass)
    host: str
    port: int
    debug: bool = False
    features: list[str] = field(default_factory=list)

    @property
    def endpoint(self) -> str:
        """Get full endpoint URL."""
        return f"http://{self.host}:{self.port}"

    @endpoint.setter
    def endpoint(self, value: str) -> None:
        """Parse and set endpoint."""
        # Parse URL
        pass

    @classmethod
    def from_dict(cls, data: dict) -> "Configuration":
        """Create from dictionary."""
        return cls(**data)

    @staticmethod
    def validate_port(port: int) -> bool:
        """Validate port number."""
        return 1 <= port <= 65535


# Generic class
class Cache(Generic[K, V]):
    """Generic cache implementation."""

    _instance: Optional["Cache"] = None
    _data: dict[K, V]

    def __init__(self):
        """Initialize cache."""
        self._data = {}

    @classmethod
    def get_instance(cls) -> "Cache":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get(self, key: K) -> V | None:
        """Get value by key."""
        return self._data.get(key)

    def set(self, key: K, value: V) -> None:
        """Set key-value pair."""
        self._data[key] = value


# Async functions
@timing_decorator
async def fetch_data(url: str) -> dict:
    """Fetch data from URL asynchronously."""
    await asyncio.sleep(0.1)
    return {"url": url, "status": "ok"}


@lru_cache(maxsize=128)
async def cached_fetch(url: str) -> dict:
    """Cached async fetch."""
    return await fetch_data(url)


# Multiple inheritance
class Loggable(ABC):
    """Abstract logging mixin."""

    @abstractmethod
    def log(self, message: str) -> None:
        """Log a message."""
        pass


class Serializable(ABC):
    """Abstract serialization mixin."""

    @abstractmethod
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        pass


class DataStore(Loggable, Serializable):
    """Class with multiple inheritance."""

    # Class-level registry
    _instances: list["DataStore"] = []
    _count: int = 0

    def __init__(self, name: str):
        """Initialize data store."""
        self.name = name
        DataStore._instances.append(self)
        DataStore._count += 1

    def log(self, message: str) -> None:
        """Implementation of log."""
        print(f"[{self.name}] {message}")

    def to_dict(self) -> dict:
        """Implementation of to_dict."""
        return {"name": self.name}

    @classmethod
    def get_count(cls) -> int:
        """Get number of instances."""
        return cls._count

    # Async method
    async def save_async(self, data: dict) -> bool:
        """Save data asynchronously."""
        self.log(f"Saving {len(data)} items")
        await asyncio.sleep(0.1)
        return True

    # Nested class
    class Transaction:
        """Nested transaction class."""

        def __init__(self, parent: "DataStore"):
            """Initialize transaction."""
            self.parent = parent

        def commit(self) -> None:
            """Commit transaction."""
            self.parent.log("Transaction committed")


# Decorated standalone functions
@timing_decorator
@cache_decorator(max_size=64)
def complex_calculation(x: int, y: int, z: int = 0) -> int:
    """Function with multiple decorators."""
    return x * y + z


@cache
def fibonacci(n: int) -> int:
    """Cached fibonacci."""
    if n < 2:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)


# Async context manager
class AsyncResource:
    """Async context manager example."""

    async def __aenter__(self):
        """Async enter."""
        await asyncio.sleep(0.01)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async exit."""
        await asyncio.sleep(0.01)


# Main entry point
async def main() -> None:
    """Main async entry point."""
    config = Configuration(host="localhost", port=8000, debug=True)
    print(f"Endpoint: {config.endpoint}")

    data = await fetch_data("https://api.example.com")
    print(f"Fetched: {data}")

    store = DataStore("main")
    await store.save_async({"key": "value"})


if __name__ == "__main__":
    asyncio.run(main())
