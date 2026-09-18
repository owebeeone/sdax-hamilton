"""Optional profile identity checks neither import nor activate a backend."""

import sys
from importlib import metadata
from types import ModuleType

import pytest

from sdax_hamilton import _optional_profiles as profiles


def test_exact_loaded_class_is_required_without_module_attribute_callbacks(monkeypatch):
    module_name = "hamilton.plugins.h_polars"
    module = ModuleType(module_name)
    calls = []
    module.__getattr__ = lambda name: calls.append(name)
    exact = type("with_columns", (), {"__module__": module_name})
    module.with_columns = exact
    monkeypatch.setitem(sys.modules, module_name, module)

    assert profiles.identify_optional_modifier(exact()) == "polars"
    derived = type("derived", (exact,), {"__module__": module_name})
    assert profiles.identify_optional_modifier(derived()) is None
    impostor = type("with_columns", (), {"__module__": module_name})
    assert profiles.identify_optional_modifier(impostor()) is None
    del module.with_columns
    assert profiles.identify_optional_modifier(exact()) is None
    assert calls == []


def test_absent_backend_is_not_imported(monkeypatch):
    module_name = "hamilton.plugins.h_polars"
    monkeypatch.delitem(sys.modules, module_name, raising=False)
    declaration = type("with_columns", (), {"__module__": module_name})()
    assert profiles.identify_optional_modifier(declaration) is None
    assert module_name not in sys.modules


def test_profile_version_mismatch_fails_without_backend_import(monkeypatch):
    before = set(sys.modules)
    monkeypatch.setattr(profiles.metadata, "version", lambda name: "0.0.0")
    with pytest.raises(RuntimeError, match=r"polars==1\.44\.2"):
        profiles.validate_optional_profile("polars")
    assert set(sys.modules) == before


def test_missing_distribution_and_unknown_profile_fail_closed(monkeypatch):
    def absent(name):
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(profiles.metadata, "version", absent)
    with pytest.raises(RuntimeError, match="requires pydantic"):
        profiles.validate_optional_profile("pydantic")
    with pytest.raises(ValueError, match="Unknown"):
        profiles.validate_optional_profile("unregistered")
