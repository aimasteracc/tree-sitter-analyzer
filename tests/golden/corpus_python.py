"""
Python Golden Corpus - Grammar Coverage MECE 测试

此文件包含所有 Python 关键 node types，用于验证 tree-sitter-python 语法覆盖完整性。
特别关注 Issue #112 的回归测试：decorated_definition 必须被正确提取。
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

# ============================================================================
# DECORATED_DEFINITION - Issue #112 Regression Test (CRITICAL)
# ============================================================================

@dataclass
class Person:
    """使用 @dataclass 装饰器的类（decorated_definition）"""
    name: str
    age: int
    email: str | None = None

    def __post_init__(self):
        """数据类的初始化后处理"""
        if self.age < 0:
            raise ValueError("年龄不能为负")

    def greet(self) -> str:
        """问候方法"""
        return f"你好，我是 {self.name}"


class PropertyExample:
    """属性装饰器示例（decorated_definition）"""

    def __init__(self, value: int):
        self._value = value

    @property
    def value(self) -> int:
        """使用 @property 装饰器（decorated_definition）"""
        return self._value

    @value.setter
    def value(self, val: int) -> None:
        """属性 setter（decorated_definition）"""
        self._value = val

    @staticmethod
    def static_method() -> str:
        """静态方法（decorated_definition）"""
        return "静态方法"

    @classmethod
    def class_method(cls) -> str:
        """类方法（decorated_definition）"""
        return f"类方法：{cls.__name__}"


def timing_decorator(func):
    """自定义装饰器"""
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


@timing_decorator
def decorated_function(x: int) -> int:
    """使用自定义装饰器的函数（decorated_definition）"""
    return x * 2


# ============================================================================
# REGULAR FUNCTIONS
# ============================================================================

def regular_function(a: int, b: int) -> int:
    """常规函数定义"""
    return a + b


async def async_function(url: str) -> dict:
    """异步函数定义"""
    return {"url": url, "data": "fetched"}


def function_with_defaults(x: int, y: int = 10, z: str = "default") -> str:
    """带默认参数的函数"""
    return f"{x}, {y}, {z}"


def variadic_function(*args: int, **kwargs: str) -> tuple:
    """可变参数函数"""
    return args, kwargs


# ============================================================================
# LAMBDA EXPRESSIONS
# ============================================================================

# Lambda expressions (intentional E731 - testing lambda syntax)
square = lambda x: x ** 2  # noqa: E731
add = lambda a, b: a + b  # noqa: E731
complex_lambda = lambda x, y=5: x * y if x > 0 else 0  # noqa: E731
key_function = lambda item: item[1]  # noqa: E731
filter_function = lambda x: x % 2 == 0  # noqa: E731


# ============================================================================
# GENERATORS AND COMPREHENSIONS
# ============================================================================

def generator_function(n: int) -> Iterator[int]:
    """生成器函数（yield）"""
    # Intentional yield loop (UP028 - testing yield syntax, not yield from)
    for i in range(n):  # noqa: UP028
        yield i  # noqa: UP028


def fibonacci_generator(limit: int) -> Iterator[int]:
    """斐波那契生成器（yield）"""
    a, b = 0, 1
    while a < limit:
        yield a
        a, b = b, a + b


async def async_generator(n: int) -> Any:
    """异步生成器（yield）"""
    for i in range(n):
        yield i


# Comprehensions
numbers = [1, 2, 3, 4, 5]
list_comp = [x * 2 for x in numbers if x > 2]  # list_comprehension
dict_comp = {x: x**2 for x in numbers}  # dictionary_comprehension
set_comp = {x % 3 for x in numbers}  # set_comprehension

# Generator expressions
gen_expr = (x * 2 for x in numbers)  # generator_expression
filtered_gen = (x for x in numbers if x % 2 == 0)  # generator_expression


# ============================================================================
# CLASSES
# ============================================================================

class Animal(ABC):
    """抽象基类"""

    def __init__(self, name: str, species: str):
        self.name = name
        self.species = species

    @abstractmethod
    def make_sound(self) -> str:
        """抽象方法（必须被子类实现）"""
        pass

    def describe(self) -> str:
        """普通方法"""
        return f"{self.name} 是一只 {self.species}"


class Dog(Animal):
    """继承自 Animal 的子类"""

    def __init__(self, name: str, breed: str):
        super().__init__(name, "狗")
        self.breed = breed

    def make_sound(self) -> str:
        """实现抽象方法"""
        return "汪汪！"

    def fetch(self, item: str) -> str:
        """狗的特有方法"""
        return f"{self.name} 捡回了 {item}"


class NestedClassExample:
    """嵌套类示例"""

    class Inner:
        """内部类"""
        def inner_method(self) -> str:
            return "内部方法"

    def outer_method(self) -> str:
        """外部方法"""
        return "外部方法"


# ============================================================================
# COMPLEX NESTED STRUCTURES
# ============================================================================

class ComplexNesting:
    """复杂嵌套结构（测试深度遍历）"""

    def level1_method(self):
        """第一层方法"""

        def level2_nested():
            """嵌套函数（第二层）"""

            class Level3Class:
                """嵌套类（第三层）"""

                def level4_method(self):
                    """嵌套类的方法（第四层）"""
                    return "深度嵌套"

            return Level3Class()

        return level2_nested()


# ============================================================================
# MODULE-LEVEL STATEMENTS
# ============================================================================

if __name__ == "__main__":
    # 测试所有定义的函数和类
    person = Person("张三", 30)
    print(person.greet())

    prop_example = PropertyExample(42)
    print(f"属性值：{prop_example.value}")

    print(f"装饰函数：{decorated_function(21)}")

    dog = Dog("旺财", "金毛")
    print(dog.make_sound())
    print(dog.fetch("球"))

    # 测试生成器
    for num in generator_function(5):
        print(num)

    # 测试推导式
    print(f"列表推导式：{list_comp}")
    print(f"字典推导式：{dict_comp}")
    print(f"集合推导式：{set_comp}")

    # 测试 lambda
    print(f"Lambda 平方：{square(5)}")
