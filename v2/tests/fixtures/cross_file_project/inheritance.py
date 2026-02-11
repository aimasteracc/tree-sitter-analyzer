"""Test fixture for class inheritance chain tracking."""

from abc import ABC, abstractmethod


class Animal(ABC):
    """Base class for all animals."""

    @abstractmethod
    def speak(self):
        pass

    def breathe(self):
        return "breathing"


class Mammal(Animal):
    """Intermediate class."""

    def feed_young(self):
        return "milk"


class Dog(Mammal):
    """Concrete class — deep inheritance chain."""

    def speak(self):
        return "woof"

    def fetch(self):
        return "fetching"


class Cat(Mammal):
    """Another concrete class."""

    def speak(self):
        return "meow"


class Serializable:
    """Mixin / interface-like class."""

    def to_dict(self):
        return {}


class Persistable:
    """Another mixin."""

    def save(self):
        pass


class PersistentDog(Dog, Serializable, Persistable):
    """Multiple inheritance — Diamond pattern."""

    def to_dict(self):
        return {"name": "buddy", "type": "dog"}


class StrayDog(Dog):
    """Further depth in chain."""
    pass
