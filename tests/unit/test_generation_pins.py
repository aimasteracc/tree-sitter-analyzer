"""跨进程版本钉：活钉阻止回收，墓碑使新钉退避（RFC-0032 slice 6）。

被杀持有者的钉过期由 test_generation_retirement 的被杀构建者用例端到端覆盖。
"""

from pathlib import Path

import pytest

_ID = "0123456789abcdef0123456789abcdef"


def test_live_pin_is_detected_until_released(tmp_path):
    from tree_sitter_analyzer.cache import generation_pins as pins

    directory = pins.pin_directory(tmp_path, _ID)
    pin = pins.pin_generation(tmp_path, _ID)
    # PR #1567 CI：持有中的钉文件须可被他人读取（Windows 字节锁曾阻断遍历读取）。
    live, content = pins.has_live_pin(directory), pin.path.read_bytes()
    pin.release()
    assert (live, content, pins.has_live_pin(directory)) == (True, b"", False)


def test_tombstone_makes_new_pin_back_off(tmp_path):
    from tree_sitter_analyzer.cache import generation_pins as pins

    directory = pins.pin_directory(tmp_path, _ID)
    directory.mkdir(parents=True)
    (directory / pins.TOMBSTONE).touch()
    assert pins.pin_generation(tmp_path, _ID) is None
    assert pins.has_live_pin(directory) is False


def test_only_managed_generation_paths_are_pinned(tmp_path):
    from tree_sitter_analyzer.cache.generation_pins import pin_database, pin_directory

    pin = pin_database(tmp_path / "generations" / _ID / "index.db")
    try:
        assert (
            pin_database(tmp_path / ".ast-cache" / "index.db"),
            pin.path.parent == tmp_path / "pins" / _ID,
            pin_directory(Path("s"), _ID),
        ) == (None, True, Path("s") / "pins" / _ID)
    finally:
        pin.release()
    with pytest.raises(ValueError, match="INDEX_GENERATION_ID_INVALID"):
        pin_directory(tmp_path, "../" + _ID[:29])
