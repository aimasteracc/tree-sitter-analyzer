"""不可变索引版本的选择器契约；文件句柄固定由存储层负责。"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

SELECTOR_BYTE_LIMIT = 4096
_IDENTIFIER = re.compile(r"[0-9a-f]{32}\Z")
_FIELDS = frozenset(
    {"version", "canonical_root", "logical_path", "storage_epoch", "generation_id"}
)


class InvalidGenerationSelector(ValueError):
    """选择器不能证明活动版本身份；调用者不得回退到旧数据库。"""


def _invalid() -> InvalidGenerationSelector:
    return InvalidGenerationSelector("INDEX_GENERATION_SELECTOR_INVALID")


def _canonical_locator(value: str) -> bool:
    return (
        isinstance(value, str)
        and "\x00" not in value
        and os.path.isabs(value)
        and os.path.normpath(value) == value
    )


@dataclass(frozen=True)
class GenerationSelector:
    """只保存已校验身份，不接受选择器指定任意物理数据库路径。"""

    canonical_root: str
    logical_path: str
    storage_epoch: str
    generation_id: str

    def __post_init__(self) -> None:
        if not all(
            _canonical_locator(value)
            for value in (self.canonical_root, self.logical_path)
        ):
            raise _invalid()
        for identifier in (self.storage_epoch, self.generation_id):
            if not isinstance(identifier, str) or not _IDENTIFIER.fullmatch(identifier):
                raise _invalid()

    def encode(self) -> bytes:
        """生成稳定、有界的 UTF-8 选择器；不进行文件写入。"""
        payload = {
            "version": 1,
            "canonical_root": self.canonical_root,
            "logical_path": self.logical_path,
            "storage_epoch": self.storage_epoch,
            "generation_id": self.generation_id,
        }
        data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        if len(data) > SELECTOR_BYTE_LIMIT:
            raise _invalid()
        return data


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _invalid()
        result[key] = value
    return result


def decode_generation_selector(
    data: bytes, *, canonical_root: str, logical_path: str
) -> GenerationSelector:
    """验证格式和调用方绑定；传入字节须由存储层在读取时限制大小。"""
    if len(data) > SELECTOR_BYTE_LIMIT:
        raise _invalid()
    try:
        payload = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise _invalid() from None
    if (
        not isinstance(payload, dict)
        or set(payload) != _FIELDS
        or type(payload["version"]) is not int
        or payload["version"] != 1
    ):
        raise _invalid()
    selector = GenerationSelector(
        payload["canonical_root"],
        payload["logical_path"],
        payload["storage_epoch"],
        payload["generation_id"],
    )
    if (
        selector.canonical_root != canonical_root
        or selector.logical_path != logical_path
    ):
        raise _invalid()
    return selector
