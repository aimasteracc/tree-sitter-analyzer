"""Tests for platform_compat.profiles validation fallbacks."""

import sys
from types import SimpleNamespace

import pytest

from tree_sitter_analyzer.platform_compat.profiles import validate_profile


def _valid_profile_data():
    return {
        "schema_version": "1.0.0",
        "platform_key": "linux-3.14",
        "behaviors": {
            "select_all": {
                "construct_id": "select_all",
                "node_type": "select_statement",
                "element_count": 1,
                "attributes": ["keyword:SELECT"],
                "has_error": False,
                "known_issues": [],
            }
        },
        "adaptation_rules": [],
    }


def test_validate_profile_falls_back_when_jsonschema_runtime_fails(monkeypatch):
    def fail_validation(*args, **kwargs):
        raise RuntimeError("validator resource unavailable")

    fake_jsonschema = SimpleNamespace(
        validate=fail_validation, exceptions=SimpleNamespace()
    )
    monkeypatch.setitem(sys.modules, "jsonschema", fake_jsonschema)

    validate_profile(_valid_profile_data())


def test_validate_profile_reraises_jsonschema_validation_errors(monkeypatch):
    class FakeValidationError(Exception):
        pass

    def fail_validation(*args, **kwargs):
        raise FakeValidationError("profile is invalid")

    fake_jsonschema = SimpleNamespace(
        validate=fail_validation,
        exceptions=SimpleNamespace(ValidationError=FakeValidationError),
    )
    monkeypatch.setitem(sys.modules, "jsonschema", fake_jsonschema)

    with pytest.raises(FakeValidationError):
        validate_profile(_valid_profile_data())


def test_validate_profile_fallback_rejects_invalid_nested_behavior(monkeypatch):
    def fail_validation(*args, **kwargs):
        raise RuntimeError("validator resource unavailable")

    fake_jsonschema = SimpleNamespace(
        validate=fail_validation, exceptions=SimpleNamespace()
    )
    monkeypatch.setitem(sys.modules, "jsonschema", fake_jsonschema)
    data = _valid_profile_data()
    data["behaviors"]["select_all"].pop("node_type")

    with pytest.raises(ValueError, match="missing required fields: node_type"):
        validate_profile(data)
