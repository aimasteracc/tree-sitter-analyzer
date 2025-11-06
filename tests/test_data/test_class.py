"""Python class test with different patterns"""

from dataclasses import dataclass


class Animal:
    """Base animal class"""

    def __init__(self, name: str):
        self.name = name
        self._age = 0  # Protected convention
        self.__secret = "hidden"  # Private convention

    def speak(self) -> str:
        return f"{self.name} makes a sound"

    def _protected_method(self) -> None:
        """Protected method (convention)"""
        pass

    def __private_method(self) -> None:
        """Private method (convention)"""
        pass


class Dog(Animal):
    """Dog class extending Animal"""

    def __init__(self, name: str, breed: str):
        super().__init__(name)
        self.breed = breed

    def speak(self) -> str:
        return f"{self.name} barks"

    def get_breed(self) -> str:
        return self.breed


@dataclass
class Point:
    x: float
    y: float

    def distance_from_origin(self) -> float:
        return (self.x**2 + self.y**2) ** 0.5
