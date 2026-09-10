"""默认索引定位与操作内私有数据库绑定；读取不能隐式创建存储。"""

from __future__ import annotations

import os
import stat
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from .generation_selector import (
    SELECTOR_BYTE_LIMIT,
    GenerationSelector,
    InvalidGenerationSelector,
    decode_generation_selector,
)

_NativePath = type(Path.cwd())


def _require_plain_path(path: Path, *, directory: bool) -> None:
    info = os.lstat(path)
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if (
        not expected_type(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & 0x400
    ):
        raise InvalidGenerationSelector("INDEX_GENERATION_PATH_UNSAFE")


def logical_index_path(project_root: str) -> Path:
    return (
        _NativePath(os.path.realpath(os.path.abspath(project_root)))
        / ".ast-cache"
        / "index.db"
    )


def generation_storage_path(project_root: str) -> Path:
    return logical_index_path(project_root).parent / "index-generations"


def read_selector(root: str, storage: Path, logical: str) -> GenerationSelector | None:
    """拒绝损坏或已激活后丢失的选择器，不能因此退回旧库。"""
    path = storage / "active.json"
    if os.path.lexists(storage):
        _require_plain_path(storage.parent, directory=True)
        _require_plain_path(storage, directory=True)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        if os.path.lexists(storage / "activated") or os.path.lexists(
            _NativePath(logical).with_suffix(".generation")
        ):
            raise InvalidGenerationSelector(
                "INDEX_GENERATION_SELECTOR_MISSING"
            ) from None
        return None
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise InvalidGenerationSelector("INDEX_GENERATION_SELECTOR_INVALID")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            data = handle.read(SELECTOR_BYTE_LIMIT + 1)
    finally:
        os.close(descriptor)
    return decode_generation_selector(data, canonical_root=root, logical_path=logical)


@dataclass(frozen=True)
class IndexLocation:
    """一次读取或构建所绑定的数据库；发布版本只能只读打开。"""

    path: Path
    published: bool
    selector: GenerationSelector | None = None
    verify: Callable[[], None] | None = None


_WRITERS: ContextVar[dict[str, IndexLocation] | None] = ContextVar(
    "tsa_generation_writers", default=None
)


def resolve_index_location(project_root: str) -> IndexLocation:
    logical = logical_index_path(project_root)
    root = str(logical.parent.parent)
    private = (_WRITERS.get() or {}).get(str(logical))
    if private is not None:
        return private
    storage = generation_storage_path(root)
    selector = read_selector(root, storage, str(logical))
    if selector is None:
        return IndexLocation(logical, False)
    database = storage / "generations" / selector.generation_id / "index.db"
    _require_plain_path(database.parent.parent, directory=True)
    _require_plain_path(database.parent, directory=True)
    _require_plain_path(database, directory=False)
    return IndexLocation(database, True, selector)


def resolve_index_path(project_root: str) -> Path:
    return resolve_index_location(project_root).path


@contextmanager
def private_index(
    project_root: str, database: Path, *, verify: Callable[[], None] | None = None
) -> Iterator[None]:
    """同一索引操作内创建的默认 ASTCache 必须共享专属构建库。"""
    values = dict(_WRITERS.get() or {})
    values[str(logical_index_path(project_root))] = IndexLocation(
        database, False, verify=verify
    )
    token = _WRITERS.set(values)
    try:
        yield
    finally:
        _WRITERS.reset(token)
