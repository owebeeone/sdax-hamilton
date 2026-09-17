"""Portable module fixtures; no campaign or workspace imports."""

import sys
import types
import uuid

import pytest


@pytest.fixture
def module_factory():
    modules = []

    def make_module(source_text, **bindings):
        module = types.ModuleType("sdax_hamilton_test_" + uuid.uuid4().hex)
        module.__dict__.update(bindings)
        sys.modules[module.__name__] = module
        modules.append(module)
        exec(source_text, module.__dict__)
        return module

    yield make_module
    for module in modules:
        sys.modules.pop(module.__name__, None)
