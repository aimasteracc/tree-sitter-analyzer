"""导入形态与模块级常量(仅解析,不执行)。"""

import os
import sys as system
from collections import OrderedDict
from typing import Any, Dict, List as PyList
from os import path as ospath
from . import sibling
from .helpers import util
from math import *

MAX_RETRIES: int = 3
DEFAULT_TIMEOUT: float = 30.0
APP_NAME = "tsa-fixture"
_FLAGS = frozenset({"fast", "safe"})

__version__ = "1.2.3"
__all__ = ["APP_NAME", "MAX_RETRIES"]

cache: Dict[str, PyList[Any]] = {}
enabled: bool = True
