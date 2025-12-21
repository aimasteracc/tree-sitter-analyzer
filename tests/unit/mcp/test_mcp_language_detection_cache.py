import pytest

from tree_sitter_analyzer.language_detector import (
    LanguageDetector,
    detect_language_from_file,
)
from tree_sitter_analyzer.mcp.utils.shared_cache import get_shared_cache


@pytest.mark.unit
def test_language_detection_cache_hit(tmp_path, monkeypatch):
    get_shared_cache().clear()

    p = tmp_path / "a.py"
    p.write_text("print('x')\n", encoding="utf-8")

    calls = 0
    original = LanguageDetector.detect_from_extension

    def _spy(self, file_path):  # noqa: ANN001
        nonlocal calls
        calls += 1
        return original(self, file_path)

    monkeypatch.setattr(LanguageDetector, "detect_from_extension", _spy)

    lang1 = detect_language_from_file(str(p), project_root=str(tmp_path))
    lang2 = detect_language_from_file(str(p), project_root=str(tmp_path))

    assert lang1 == "python"
    assert lang2 == "python"
    assert calls == 1


@pytest.mark.unit
def test_language_detection_cache_invalidates_on_mtime_change(tmp_path, monkeypatch):
    get_shared_cache().clear()

    p = tmp_path / "a.py"
    p.write_text("print('x')\n", encoding="utf-8")

    calls = 0
    original = LanguageDetector.detect_from_extension

    def _spy(self, file_path):  # noqa: ANN001
        nonlocal calls
        calls += 1
        return original(self, file_path)

    monkeypatch.setattr(LanguageDetector, "detect_from_extension", _spy)

    import os

    detect_language_from_file(str(p), project_root=str(tmp_path))

    # Force mtime_ns change without relying on filesystem timestamp granularity
    st = os.stat(p)
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    detect_language_from_file(str(p), project_root=str(tmp_path))

    assert calls == 2


@pytest.mark.unit
def test_unknown_is_cached(tmp_path, monkeypatch):
    get_shared_cache().clear()

    p = tmp_path / "a.unknownext"
    p.write_text("some content\n", encoding="utf-8")

    calls = 0
    original = LanguageDetector.detect_from_extension

    def _spy(self, file_path):  # noqa: ANN001
        nonlocal calls
        calls += 1
        return original(self, file_path)

    monkeypatch.setattr(LanguageDetector, "detect_from_extension", _spy)

    lang1 = detect_language_from_file(str(p), project_root=str(tmp_path))
    lang2 = detect_language_from_file(str(p), project_root=str(tmp_path))

    assert lang1 == "unknown"
    assert lang2 == "unknown"
    assert calls == 1


@pytest.mark.unit
def test_missing_file_is_not_cached(tmp_path, monkeypatch):
    get_shared_cache().clear()

    missing = tmp_path / "does_not_exist.py"
    assert not missing.exists()

    calls = 0
    original = LanguageDetector.detect_from_extension

    def _spy(self, file_path):  # noqa: ANN001
        nonlocal calls
        calls += 1
        return original(self, file_path)

    monkeypatch.setattr(LanguageDetector, "detect_from_extension", _spy)

    lang = detect_language_from_file(str(missing), project_root=str(tmp_path))

    assert lang == "python"

    # Should not cache because stat() fails.
    meta = get_shared_cache().get_language_meta(
        str(missing), project_root=str(tmp_path)
    )
    assert meta is None

    # Without stat() we must not cache; repeated calls should still perform detection.
    assert (
        detect_language_from_file(str(missing), project_root=str(tmp_path)) == "python"
    )
    assert calls == 2
