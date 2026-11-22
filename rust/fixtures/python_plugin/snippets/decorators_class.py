"""类上的装饰器形态。"""

from dataclasses import dataclass


def audit(action: str):
    """自定义装饰器工厂:记录审计动作。"""

    def wrap(func):
        def inner(*args, **kwargs):
            return func(*args, **kwargs)

        return inner

    return wrap


class Registry:
    """演示内建与自定义装饰器的类。"""

    _created = 0

    def __init__(self, name: str) -> None:
        self.name = name
        Registry._created += 1

    @property
    def display_name(self) -> str:
        """展示用的大写名称。"""
        return self.name.upper()

    @display_name.setter
    def display_name(self, value: str) -> None:
        self.name = value.lower()

    @staticmethod
    def created_count() -> int:
        """已创建的实例数。"""
        return Registry._created

    @classmethod
    def reset(cls) -> None:
        """重置实例计数。"""
        cls._created = 0


@dataclass
class Point:
    """数据类:坐标点。"""

    x: float
    y: float
    label: str = "origin"


@audit("compute")
def distance(point: Point) -> float:
    """被自定义装饰器修饰的函数。"""
    return (point.x ** 2 + point.y ** 2) ** 0.5
