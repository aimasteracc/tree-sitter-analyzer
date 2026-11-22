"""抽象基类与异常层级。"""

from abc import ABC, abstractmethod


class Storage(ABC):
    """抽象存储后端。"""

    @abstractmethod
    def load(self, key: str):
        """按键读取值。"""

    @abstractmethod
    def save(self, key: str, value) -> None:
        """按键持久化值。"""


class ReadOnlyStorage(Storage):
    """只实现 load 的具体存储。"""

    def load(self, key: str):
        return {"status": "read-only"}


class AnalyzerError(Exception):
    """分析器失败的基础错误。"""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


class ParseError(AnalyzerError):
    """源码无法解析时抛出。"""


class ValidationError(AnalyzerError):
    """输入校验失败时抛出。"""


def validate(data: dict) -> None:
    """缺失键时抛出 ValidationError。"""
    if "name" not in data:
        raise ValidationError("missing name", code=2)
