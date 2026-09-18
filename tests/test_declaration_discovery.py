"""Recursive declaration discovery stays finite, explicit, and identity based."""

import types

import pytest

from sdax_hamilton._discovery import discover_declarations, discover_shutdowns_for


def test_subdag_module_discovers_nested_functions_and_owned_shutdowns(module_factory):
    nested = module_factory(
        """
from sdax_hamilton import Acquisition, shutdown

def alpha() -> int:
    return 1

def beta(alpha: int) -> int:
    return alpha + 1

@shutdown(of=alpha)
def close(state: Acquisition[int]) -> None:
    pass
"""
    )
    root = module_factory(
        """
from hamilton.function_modifiers import subdag

@subdag(nested)
def result(beta: int) -> int:
    return beta
""",
        nested=nested,
    )

    snapshot = discover_declarations([root])

    assert snapshot.roots == (root.result,)
    assert snapshot.nested == (nested.alpha, nested.beta)
    assert snapshot.shutdowns == (nested.close,)


def test_parameterized_subdag_accepts_module_and_function_sources(module_factory):
    nested = module_factory(
        """
def value() -> int:
    return 3
"""
    )
    root = module_factory(
        """
from hamilton.function_modifiers import parameterized_subdag

@parameterized_subdag(nested, first={})
def from_module(value: int) -> int:
    return value

@parameterized_subdag(value, second={})
def from_function(value: int) -> int:
    return value
""",
        nested=nested,
        value=nested.value,
    )

    snapshot = discover_declarations([root])

    assert snapshot.roots == (root.from_function, root.from_module)
    assert snapshot.nested == (nested.value,)
    assert snapshot.shutdowns == ()


def test_direct_subdag_ignores_unrelated_declarations_and_shutdowns(module_factory):
    nested = module_factory(
        """
from sdax_hamilton import Acquisition, shutdown

def selected() -> int:
    return 1

def unrelated() -> int:
    return 2

@shutdown(of=unrelated)
def close_unrelated(state: Acquisition[int]) -> None:
    pass
"""
    )
    root = module_factory(
        """
from hamilton.function_modifiers import subdag

@subdag(selected)
def result(selected: int) -> int:
    return selected
""",
        selected=nested.selected,
    )

    snapshot = discover_declarations([root])

    assert snapshot.nested == (nested.selected,)
    assert snapshot.shutdowns == ()


def test_root_orphan_shutdown_fails_while_nested_unrelated_shutdown_is_ignored(module_factory):
    external = module_factory("def owner() -> int:\n    return 1")
    root = module_factory(
        """
from sdax_hamilton import Acquisition, shutdown

@shutdown(of=external_owner)
def close(state: Acquisition[int]) -> None:
    pass
""",
        external_owner=external.owner,
    )

    with pytest.raises(ValueError, match="close: owner not discovered in supplied modules"):
        discover_declarations([root])


def test_discovery_rejects_a_missing_or_rebound_defining_module(module_factory):
    missing = types.ModuleType("sdax_hamilton_missing_declaration")
    exec("def selected() -> int:\n    return 1", missing.__dict__)
    root = module_factory(
        """
from hamilton.function_modifiers import subdag

@subdag(selected)
def result(selected: int) -> int:
    return selected
""",
        selected=missing.selected,
    )

    with pytest.raises(ValueError, match="defining module"):
        discover_declarations([root])

    nested = module_factory("def selected() -> int:\n    return 1")
    original = nested.selected
    exec("def selected() -> int:\n    return 2", nested.__dict__)
    rebound_root = module_factory(
        """
from hamilton.function_modifiers import subdag

@subdag(selected)
def result(selected: int) -> int:
    return selected
""",
        selected=original,
    )

    with pytest.raises(ValueError, match="ambiguous defining module"):
        discover_declarations([rebound_root])


def test_discovery_rejects_recursive_subdag_declarations(module_factory):
    first = module_factory("def first() -> int:\n    return 1")
    second = module_factory("def second() -> int:\n    return 2")
    from hamilton.function_modifiers import subdag

    first.first = subdag(second.second)(first.first)
    second.second = subdag(first.first)(second.second)

    with pytest.raises(ValueError, match="Recursive subdag declaration cycle"):
        discover_declarations([first])


def test_discovery_rejects_a_shutdown_owner_with_an_ambiguous_identity(module_factory):
    nested = module_factory(
        """
from sdax_hamilton import Acquisition, shutdown

def selected() -> int:
    return 1

@shutdown(of=selected)
def close(state: Acquisition[int]) -> None:
    pass
"""
    )
    exec("def selected() -> int:\n    return 2", nested.__dict__)
    root = module_factory(
        """
from hamilton.function_modifiers import subdag

@subdag(nested)
def result(selected: int) -> int:
    return selected
""",
        nested=nested,
    )

    with pytest.raises(ValueError, match="Ambiguous shutdown owner"):
        discover_declarations([root])


def test_helper_shutdown_discovery_reads_only_explicit_helper_scopes(module_factory):
    helpers = module_factory(
        """
from sdax_hamilton import Acquisition, shutdown

def captured() -> int:
    return 1

def unrelated() -> int:
    return 2

@shutdown(of=captured)
def close_captured(state: Acquisition[int]) -> None:
    pass

@shutdown(of=unrelated)
def close_unrelated(state: Acquisition[int]) -> None:
    pass
"""
    )

    assert discover_shutdowns_for([helpers.captured]) == (helpers.close_captured,)


def test_helper_shutdown_discovery_ignores_an_unrelated_rebound_function(module_factory):
    helpers = module_factory(
        """
from sdax_hamilton import Acquisition, shutdown

def captured() -> int:
    return 1

def unrelated() -> int:
    return 2

@shutdown(of=captured)
def close_captured(state: Acquisition[int]) -> None:
    pass
"""
    )
    helpers.rebound = helpers.unrelated
    del helpers.unrelated

    assert discover_shutdowns_for([helpers.captured]) == (helpers.close_captured,)
