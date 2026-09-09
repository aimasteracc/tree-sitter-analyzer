"""活动索引版本选择器的格式和项目隔离契约。"""

import json
from dataclasses import replace

import pytest

from tree_sitter_analyzer.cache.generation_selector import (
    SELECTOR_BYTE_LIMIT,
    GenerationSelector,
    InvalidGenerationSelector,
    decode_generation_selector,
)


@pytest.fixture
def selector(tmp_path):
    return GenerationSelector(
        str(tmp_path), str(tmp_path / ".ast-cache" / "index.db"), "a" * 32, "b" * 32
    )


def decode(data, selector):
    return decode_generation_selector(
        data,
        canonical_root=selector.canonical_root,
        logical_path=selector.logical_path,
    )


def test_selector_round_trip_preserves_every_identity(selector):
    assert decode(selector.encode(), selector) == selector
    assert json.loads(selector.encode()) == {
        "version": 1,
        "canonical_root": selector.canonical_root,
        "logical_path": selector.logical_path,
        "storage_epoch": "a" * 32,
        "generation_id": "b" * 32,
    }


def test_duplicate_generation_is_rejected(selector):
    # 2026-09-09：不能让不同 JSON 解析器对同一选择器认定不同活动版本。
    data = selector.encode()[:-1] + b',"generation_id":"' + b"c" * 32 + b'"}'
    with pytest.raises(
        InvalidGenerationSelector, match="INDEX_GENERATION_SELECTOR_INVALID"
    ):
        decode(data, selector)


@pytest.mark.parametrize("field", ["canonical_root", "logical_path"])
def test_other_locator_is_rejected(selector, field):
    other = replace(selector, **{field: getattr(selector, field) + "-other"})
    with pytest.raises(InvalidGenerationSelector):
        decode(other.encode(), selector)


@pytest.mark.parametrize("version", [True, 1.0, "1", 0, 2, None])
def test_noncanonical_protocol_version_is_rejected(selector, version):
    payload = json.loads(selector.encode())
    payload["version"] = version
    with pytest.raises(InvalidGenerationSelector):
        decode(json.dumps(payload).encode("utf-8"), selector)


@pytest.mark.parametrize(
    "identifier", ["../index", "a" * 31, "A" * 32, "g" * 32, 1, None]
)
@pytest.mark.parametrize("field", ["storage_epoch", "generation_id"])
def test_invalid_identifier_is_rejected(selector, field, identifier):
    payload = json.loads(selector.encode())
    payload[field] = identifier
    with pytest.raises(InvalidGenerationSelector):
        decode(json.dumps(payload).encode("utf-8"), selector)


@pytest.mark.parametrize("mutation", ["extra", "missing"])
def test_exact_field_set_is_required(selector, mutation):
    payload = json.loads(selector.encode())
    if mutation == "extra":
        payload["physical_path"] = selector.logical_path
    else:
        del payload["storage_epoch"]
    with pytest.raises(InvalidGenerationSelector):
        decode(json.dumps(payload).encode("utf-8"), selector)


@pytest.mark.parametrize("data", [b"[]", b"null", b"{", b"\xff", b"[" * 1500])
def test_malformed_selector_is_rejected(selector, data):
    with pytest.raises(InvalidGenerationSelector):
        decode(data, selector)


def test_decode_enforces_exact_byte_boundary(selector):
    data = selector.encode()
    boundary = data + b" " * (SELECTOR_BYTE_LIMIT - len(data))
    assert decode(boundary, selector) == selector
    with pytest.raises(InvalidGenerationSelector):
        decode(boundary + b" ", selector)


def test_encode_rejects_oversized_locator(selector):
    large = replace(
        selector, logical_path=selector.logical_path + "x" * SELECTOR_BYTE_LIMIT
    )
    with pytest.raises(InvalidGenerationSelector):
        large.encode()


@pytest.mark.parametrize("path", ["relative/index.db", "", "\x00"])
@pytest.mark.parametrize("field", ["canonical_root", "logical_path"])
def test_noncanonical_locator_is_rejected(selector, field, path):
    with pytest.raises(InvalidGenerationSelector):
        replace(selector, **{field: path})
