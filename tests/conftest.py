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


@pytest.fixture
def hamilton_oracle(module_factory):
    """Construct a fresh stock graph with the same portable module fixture."""
    from hamilton import driver

    def build(source_text, *, config=None, **bindings):
        module = module_factory(source_text, **bindings)
        return driver.Builder().with_modules(module).with_config(dict(config or {})).build()

    return build


@pytest.fixture
def graph_signature():
    """Compare consumed graph facts without retaining a second executable graph."""
    from hamilton.node import DependencyType, Node

    from sdax_hamilton._model import MISSING, NodeSpec

    def signature(nodes, *, tag_keys=()):
        result = {}
        for name, entry in nodes.items():
            if isinstance(entry, Node):
                if entry.user_defined:
                    continue
                output_type = entry.type
                inputs = {key: typ for key, (typ, _) in entry.input_types.items()}
                optional = frozenset(
                    key
                    for key, (_, kind) in entry.input_types.items()
                    if kind is DependencyType.OPTIONAL
                )
                tags = entry.tags
            elif isinstance(entry, NodeSpec):
                output_type = entry.output_type
                inputs = {key: spec.typ for key, spec in entry.inputs.items()}
                optional = frozenset(
                    key for key, spec in entry.inputs.items() if spec.default is not MISSING
                )
                tags = getattr(entry, "tags", {})
            else:
                raise TypeError("Unsupported conformance node")
            result[name] = (
                output_type,
                inputs,
                optional,
                {key: tags[key] for key in tag_keys if key in tags},
            )
        return result

    return signature
