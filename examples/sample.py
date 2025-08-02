#!/usr/bin/env python3
"""
Sample Python file for testing the Python plugin.

This file contains various Python constructs to test the comprehensive
analysis capabilities of the Python plugin.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Person:
    """A simple person data class."""

    name: str
    age: int
    email: str | None = None

    def __post_init__(self):
        """Validate the person data after initialization."""
        if self.age < 0:
            raise ValueError("Age cannot be negative")

    def greet(self) -> str:
        """Return a greeting message."""
        return f"Hello, my name is {self.name} and I am {self.age} years old."


class Animal(ABC):
    """Abstract base class for animals."""

    def __init__(self, name: str, species: str):
        self.name = name
        self.species = species

    @abstractmethod
    def make_sound(self) -> str:
        """Make the sound characteristic of this animal."""
        pass

    def describe(self) -> str:
        """Describe the animal."""
        return f"This is {self.name}, a {self.species}."


class Dog(Animal):
    """A dog implementation of Animal."""

    def __init__(self, name: str, breed: str = "Mixed"):
        super().__init__(name, "Dog")
        self.breed = breed

    def make_sound(self) -> str:
        """Dogs bark."""
        return "Woof!"

    def fetch(self, item: str) -> str:
        """Dogs can fetch items."""
        return f"{self.name} fetched the {item}!"


class Cat(Animal):
    """A cat implementation of Animal."""

    def __init__(self, name: str, indoor: bool = True):
        super().__init__(name, "Cat")
        self.indoor = indoor

    def make_sound(self) -> str:
        """Cats meow."""
        return "Meow!"

    @staticmethod
    def purr() -> str:
        """Cats can purr."""
        return "Purrrr..."


async def fetch_data(url: str) -> dict[str, any]:
    """Asynchronously fetch data from a URL."""
    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()


def process_animals(animals: list[Animal]) -> dict[str, list[str]]:
    """Process a list of animals and categorize their sounds."""
    sounds_by_species = {}

    for animal in animals:
        species = animal.species
        sound = animal.make_sound()

        if species not in sounds_by_species:
            sounds_by_species[species] = []

        sounds_by_species[species].append(sound)

    return sounds_by_species


def calculate_statistics(numbers: list[int | float]) -> dict[str, float]:
    """Calculate basic statistics for a list of numbers."""
    if not numbers:
        return {"count": 0, "sum": 0, "mean": 0, "min": 0, "max": 0}

    count = len(numbers)
    total = sum(numbers)
    mean = total / count
    minimum = min(numbers)
    maximum = max(numbers)

    return {"count": count, "sum": total, "mean": mean, "min": minimum, "max": maximum}


def fibonacci_generator(n: int):
    """Generate Fibonacci numbers up to n."""
    a, b = 0, 1
    for _ in range(n):
        yield a
        a, b = b, a + b


def list_comprehension_examples():
    """Demonstrate various list comprehensions."""
    # Simple list comprehension
    squares = [x**2 for x in range(10)]

    # List comprehension with condition
    even_squares = [x**2 for x in range(10) if x % 2 == 0]

    # Dictionary comprehension
    square_dict = {x: x**2 for x in range(5)}

    # Set comprehension
    unique_remainders = {x % 3 for x in range(20)}

    return squares, even_squares, square_dict, unique_remainders


def exception_handling_example():
    """Demonstrate exception handling."""
    try:
        result = 10 / 0
    except ZeroDivisionError as e:
        print(f"Cannot divide by zero: {e}")
        result = None
    except Exception as e:
        print(f"Unexpected error: {e}")
        result = None
    else:
        print("Division successful")
    finally:
        print("Cleanup completed")

    return result


def context_manager_example():
    """Demonstrate context managers."""
    with open(__file__) as file:
        first_line = file.readline()

    return first_line.strip()


def lambda_and_higher_order_functions():
    """Demonstrate lambda functions and higher-order functions."""
    numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

    # Lambda with map (using list comprehension instead)
    squared = [x**2 for x in numbers]

    # Lambda with filter
    evens = list(filter(lambda x: x % 2 == 0, numbers))

    # Lambda with reduce
    from functools import reduce

    product = reduce(lambda x, y: x * y, numbers)

    return squared, evens, product


def decorator_example(func):
    """A simple decorator example."""

    def wrapper(*args, **kwargs):
        print(f"Calling function: {func.__name__}")
        result = func(*args, **kwargs)
        print(f"Function {func.__name__} completed")
        return result

    return wrapper


@decorator_example
def decorated_function(message: str) -> str:
    """A function that uses the decorator."""
    return f"Message: {message}"


def main():
    """Main function to demonstrate all features."""
    # Create some animals
    dog = Dog("Buddy", "Golden Retriever")
    cat = Cat("Whiskers", indoor=True)
    animals = [dog, cat]

    # Process animals
    sounds = process_animals(animals)
    print("Animal sounds:", sounds)

    # Calculate statistics
    numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    stats = calculate_statistics(numbers)
    print("Statistics:", stats)

    # Generate Fibonacci numbers
    fib_numbers = list(fibonacci_generator(10))
    print("Fibonacci:", fib_numbers)

    # List comprehensions
    squares, even_squares, square_dict, unique_remainders = (
        list_comprehension_examples()
    )
    print("Squares:", squares[:5])
    print("Even squares:", even_squares)

    # Exception handling
    exception_handling_example()

    # Context manager
    first_line = context_manager_example()
    print("First line of file:", first_line)

    # Lambda functions
    squared, evens, product = lambda_and_higher_order_functions()
    print("Squared (first 5):", squared[:5])
    print("Evens:", evens)

    # Decorator
    message = decorated_function("Hello, World!")
    print(message)

    # Create a person
    person = Person("Alice", 30, "alice@example.com")
    print(person.greet())


if __name__ == "__main__":
    main()
